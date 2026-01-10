#!/usr/bin/env python3
"""
多目录轨迹统计：
- raw / filtered / segmented / interpolated 的文件数、总点数、体积
- raw vs filtered 的点数保留率
- 指定列（默认 latitude/longitude/altitude）以及任一列缺失的数量与比例
- 同一个 CSV 输出汇总与逐文件缺失情况
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pyarrow.compute as pc
import pyarrow.parquet as pq
import pyarrow.types as patypes

RAW_DEFAULT = Path(
    "/workspace/aircraft_trajectory/team_likable_jelly"
    "/opensky_2024_PRC_dataset/rawtrajectories"
)
FILTERED_DEFAULT = Path(
    "/workspace/aircraft_trajectory/team_likable_jelly"
    "/opensky_2024_PRC_dataset/filtered_clean__PCA_v3"
)
SEGMENTED_DEFAULT = Path(
    "/workspace/aircraft_trajectory/team_likable_jelly"
    "/opensky_2024_PRC_dataset/segmented_clean__PCA_v3"
)
INTERPOLATED_DEFAULT = Path(
    "/workspace/aircraft_trajectory/team_likable_jelly"
    "/opensky_2024_PRC_dataset/interpolated_clean__PCA_v3"
)

DEFAULT_COLUMNS: Tuple[str, ...] = ("latitude", "longitude", "altitude")


@dataclass
class FileSummary:
    file_name: str
    points: int
    file_size: int
    nan_counts: Dict[str, int]
    any_nan: int


@dataclass
class DatasetStats:
    files: int = 0
    total_points: int = 0
    total_size: int = 0
    nan_counts: Dict[str, int] = field(default_factory=dict)
    any_nan: int = 0


@dataclass
class DatasetResult:
    label: str
    path: Path
    stats: DatasetStats
    files: List[FileSummary]
    columns: Tuple[str, ...]


def _iter_parquet_files(directory: Path) -> List[Path]:
    if not directory.exists():
        raise FileNotFoundError(f"Directory does not exist: {directory}")
    return sorted(directory.glob("*.parquet"))


def _format_number(value: float) -> str:
    return f"{value:,.0f}"


def _format_percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.000000%"
    return f"{numerator / denominator * 100:.6f}%"


def _analyze_file(args: Tuple[Path, Tuple[str, ...]]) -> FileSummary:
    file_path, columns = args
    parquet = pq.ParquetFile(str(file_path))
    num_rows = parquet.metadata.num_rows
    size = file_path.stat().st_size
    schema_cols = set(parquet.schema.names)
    present_cols = [col for col in columns if col in schema_cols]
    missing_cols = [col for col in columns if col not in schema_cols]
    table = parquet.read(columns=list(present_cols)) if present_cols else None

    nan_counts: Dict[str, int] = {col: 0 for col in columns}
    any_mask = None
    for column_name in present_cols:
        column = table[column_name].combine_chunks()
        null_mask = pc.is_null(column)
        nan_mask = pc.is_nan(column) if patypes.is_floating(column.type) else None
        if nan_mask is not None and nan_mask.null_count:
            nan_mask = pc.fill_null(nan_mask, False)
        combined_mask = null_mask if nan_mask is None else pc.or_(null_mask, nan_mask)
        if combined_mask.null_count:
            combined_mask = pc.fill_null(combined_mask, False)
        null_count = int(pc.sum(pc.cast(combined_mask, "int64")).as_py())
        nan_counts[column_name] = null_count
        if any_mask is None:
            any_mask = combined_mask
        else:
            temp = pc.or_(any_mask, combined_mask)
            if temp.null_count:
                temp = pc.fill_null(temp, False)
            any_mask = temp

    for column_name in missing_cols:
        nan_counts[column_name] = num_rows

    if missing_cols:
        any_nan = num_rows
    else:
        any_nan = int(pc.sum(pc.cast(any_mask, "int64")).as_py()) if any_mask is not None else 0

    return FileSummary(
        file_name=file_path.name,
        points=num_rows,
        file_size=size,
        nan_counts=nan_counts,
        any_nan=any_nan,
    )


def _within_range(file_name: str, date_from: Optional[str], date_to: Optional[str]) -> bool:
    if date_from is None and date_to is None:
        return True
    stem = file_name.split(".")[0]
    if date_from and stem < date_from:
        return False
    if date_to and stem > date_to:
        return False
    return True


def _collect_dataset_stats(
    directory: Path,
    max_workers: Optional[int],
    columns: Tuple[str, ...],
    allowed_files: Optional[Sequence[str]] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[DatasetStats, List[FileSummary]]:
    files = _iter_parquet_files(directory)
    if allowed_files is not None:
        allowed_set = set(allowed_files)
        files = [f for f in files if f.name in allowed_set]
    files = [f for f in files if _within_range(f.name, date_from, date_to)]
    if not files:
        raise FileNotFoundError(f"No parquet files found in: {directory}")

    workers = (
        max_workers
        if max_workers
        else min(len(files), max(mp.cpu_count() - 2, 1), 64)
    )

    stats = DatasetStats(
        files=len(files),
        nan_counts={col: 0 for col in columns},
    )
    summaries: List[FileSummary] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_analyze_file, (path, columns)): path for path in files
        }
        for future in as_completed(futures):
            summary = future.result()
            summaries.append(summary)
            stats.total_points += summary.points
            stats.total_size += summary.file_size
            stats.any_nan += summary.any_nan
            for col in columns:
                stats.nan_counts[col] += summary.nan_counts[col]

    summaries.sort(key=lambda item: item.file_name)
    return stats, summaries


def _format_gb(num_bytes: int) -> str:
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def _build_point_comparison_text(raw_stats: DatasetStats, filtered_stats: DatasetStats) -> str:
    raw_points = raw_stats.total_points
    filtered_points = filtered_stats.total_points
    dropped = raw_points - filtered_points
    retention = filtered_points / raw_points * 100 if raw_points else 0.0
    drop_ratio = dropped / raw_points * 100 if raw_points else 0.0

    lines = [
        "",
        "Point Comparison (raw -> filtered)",
        "=" * 60,
        f"Raw points:      {_format_number(raw_points)} in {raw_stats.files} files",
        f"Filtered points: {_format_number(filtered_points)} in {filtered_stats.files} files",
        "-" * 60,
        f"Points removed:  {_format_number(dropped)}",
        f"Drop ratio:      {drop_ratio:.3f}%",
        f"Retention ratio: {retention:.3f}%",
        "=" * 60,
    ]
    return "\n".join(lines)


def _build_dataset_report_text(result: DatasetResult) -> str:
    stats = result.stats
    lines = [
        "",
        f"Dataset Summary - {result.label}",
        "=" * 60,
        f"Path:          {result.path}",
        f"Files:         {stats.files}",
        f"Total points:  {_format_number(stats.total_points)}",
        f"Total size:    {_format_gb(stats.total_size)}",
        "-" * 60,
    ]
    for col in result.columns:
        count = stats.nan_counts.get(col, 0)
        lines.append(f"{col:<10}: {count:,} rows ({_format_percent(count, stats.total_points)})")
    lines.append(f"{'any_nan':<10}: {stats.any_nan:,} rows ({_format_percent(stats.any_nan, stats.total_points)})")
    return "\n".join(lines)


def _build_total_ratio_text(datasets: Sequence[DatasetResult]) -> Optional[str]:
    if not datasets:
        return None
    base_total = None
    for result in datasets:
        if result.label == "raw":
            base_total = result.stats.total_points
            break
    if base_total is None:
        base_total = sum(result.stats.total_points for result in datasets)
    if base_total == 0:
        return None

    lines = [
        "",
        "Total Points Ratio (normalized to raw dates)",
        "=" * 60,
    ]
    for result in datasets:
        ratio = result.stats.total_points / base_total * 100 if base_total else 0.0
        lines.append(
            f"{result.label:<12}: {result.stats.total_points:>15,} pts ({ratio:.3f}%)"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def _save_ratio_csv(results: Sequence[DatasetResult], output_path: Path, columns: Tuple[str, ...]) -> None:
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = ["dataset", "file_name", "total_points"]
    header.extend([f"{col}_nan_count" for col in columns])
    header.append("any_nan_count")
    header.extend([f"{col}_nan_ratio" for col in columns])
    header.append("any_nan_ratio")
    header.append("point_ratio")

    def ratio_row(
        label: str,
        file_name: str,
        points: int,
        counts: Dict[str, int],
        any_nan: int,
        dataset_total: int,
    ) -> List[str]:
        total = points or 1
        ratios = [counts.get(col, 0) / total for col in columns]
        ratios.append(any_nan / total)
        share = points / dataset_total if dataset_total else 0.0
        return [
            label,
            file_name,
            str(points),
            *[str(counts.get(col, 0)) for col in columns],
            str(any_nan),
            *[f"{value:.10f}" for value in ratios],
            f"{share:.10f}",
        ]

    rows: List[List[str]] = []
    for result in results:
        rows.append(
            ratio_row(
                result.label,
                "__TOTAL__",
                result.stats.total_points,
                result.stats.nan_counts,
                result.stats.any_nan,
                result.stats.total_points,
            )
        )
        for summary in result.files:
            rows.append(
                ratio_row(
                    result.label,
                    summary.file_name,
                    summary.points,
                    summary.nan_counts,
                    summary.any_nan,
                    result.stats.total_points,
                )
            )

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="统计 raw/filtered/segmented/interpolated 的点数与指定列缺失情况（多进程）"
    )
    parser.add_argument("--raw-dir", type=Path, default=RAW_DEFAULT, help="原始数据目录（可选）")
    parser.add_argument("--filtered-dir", type=Path, default=FILTERED_DEFAULT, help="过滤后目录（可选）")
    parser.add_argument("--segment-dir", type=Path, default=SEGMENTED_DEFAULT, help="切分后目录（可选）")
    parser.add_argument("--interpolated-dir", type=Path, default=INTERPOLATED_DEFAULT, help="插值后目录（可选）")
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="最大并行进程数（默认自动）",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="输出 CSV（含各目录汇总与逐文件缺失率）",
    )
    parser.add_argument("--summary-txt", type=Path, default=None, help="输出整体汇总的 txt")
    parser.add_argument("--from-date", type=str, default=None, help="限定统计起始日期（含）")
    parser.add_argument("--to-date", type=str, default=None, help="限定统计截止日期（含）")
    parser.add_argument("--skip-raw", action="store_true", help="跳过 raw 目录")
    parser.add_argument("--skip-filtered", action="store_true", help="跳过 filtered 目录")
    parser.add_argument("--skip-segmented", action="store_true", help="跳过 segmented 目录")
    parser.add_argument("--skip-interpolated", action="store_true", help="跳过 interpolated 目录")
    parser.add_argument("--req-cols", default=None, help="统计列（空格分隔，默认 latitude longitude altitude）")
    return parser.parse_args()


def _parse_columns(value: Optional[str]) -> Tuple[str, ...]:
    if value is None:
        return DEFAULT_COLUMNS
    cols = [c for c in value.split() if c]
    if not cols:
        raise ValueError("req-cols 不能为空")
    return tuple(cols)


def _gather_datasets(args: argparse.Namespace, columns: Tuple[str, ...]) -> List[DatasetResult]:
    dataset_info = {
        "raw": (args.raw_dir, args.skip_raw),
        "filtered": (args.filtered_dir, args.skip_filtered),
        "segmented": (args.segment_dir, args.skip_segmented),
        "interpolated": (args.interpolated_dir, args.skip_interpolated),
    }
    order = ["raw", "filtered", "segmented", "interpolated"]

    results: Dict[str, DatasetResult] = {}
    allowed_files: Optional[List[str]] = None

    # collect filtered first to determine date coverage
    filtered_path, filtered_skip = dataset_info["filtered"]
    if not filtered_skip and filtered_path is not None:
        path = Path(filtered_path)
        if path.exists():
            try:
                stats, files = _collect_dataset_stats(
                    path,
                    args.max_workers,
                    columns,
                    date_from=args.from_date,
                    date_to=args.to_date,
                )
                results["filtered"] = DatasetResult("filtered", path, stats, files, columns)
                allowed_files = [f.file_name for f in files]
            except FileNotFoundError as exc:
                print(f"[WARN] Skip filtered: {exc}")
        else:
            print(f"[WARN] Skip filtered: {path} 不存在")

    for label in order:
        if label == "filtered" and "filtered" in results:
            continue
        path, skip_flag = dataset_info[label]
        if skip_flag or path is None:
            continue
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"[WARN] Skip {label}: {path_obj} 不存在")
            continue
        file_filter = allowed_files if (allowed_files and label == "raw") else None
        try:
            stats, files = _collect_dataset_stats(
                path_obj,
                args.max_workers,
                columns,
                file_filter,
                args.from_date,
                args.to_date,
            )
        except FileNotFoundError as exc:
            print(f"[WARN] Skip {label}: {exc}")
            continue
        results[label] = DatasetResult(label=label, path=path_obj, stats=stats, files=files, columns=columns)

    return [results[label] for label in order if label in results]


def main() -> None:
    args = parse_args()
    columns = _parse_columns(args.req_cols)
    datasets = _gather_datasets(args, columns)
    if not datasets:
        raise SystemExit("未找到可用的数据目录")

    dataset_map = {result.label: result for result in datasets}
    summary_lines: List[str] = []
    if "raw" in dataset_map and "filtered" in dataset_map:
        comparison_text = _build_point_comparison_text(dataset_map["raw"].stats, dataset_map["filtered"].stats)
        print(comparison_text)
        summary_lines.append(comparison_text)

    ratio_text = _build_total_ratio_text(datasets)
    if ratio_text:
        print(ratio_text)
        summary_lines.append(ratio_text)

    for result in datasets:
        report_text = _build_dataset_report_text(result)
        print(report_text)
        summary_lines.append(report_text)

    if args.output_csv:
        _save_ratio_csv(datasets, args.output_csv, columns)
        print(f"\n统计结果已写入: {args.output_csv}")

    if args.summary_txt:
        args.summary_txt.parent.mkdir(parents=True, exist_ok=True)
        args.summary_txt.write_text("\n\n".join(summary_lines).strip() + "\n", encoding="utf-8")
        print(f"汇总摘要写入: {args.summary_txt}")


if __name__ == "__main__":
    main()
