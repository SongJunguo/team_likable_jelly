#!/usr/bin/env python3
"""
Compare raw vs filtered trajectories on two aspects:
1. Total points / retention ratio
2. Latitude/longitude/altitude missing ratios (any NaN means the row is missing)
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

COLUMNS: Tuple[str, ...] = ("latitude", "longitude", "altitude")


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
    nan_counts: Dict[str, int] = field(default_factory=lambda: {col: 0 for col in COLUMNS})
    any_nan: int = 0


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
    table = parquet.read(columns=list(columns))

    nan_counts: Dict[str, int] = {}
    any_mask = None
    for column_name in columns:
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

    any_nan = int(pc.sum(pc.cast(any_mask, "int64")).as_py()) if any_mask is not None else 0

    return FileSummary(
        file_name=file_path.name,
        points=num_rows,
        file_size=size,
        nan_counts=nan_counts,
        any_nan=any_nan,
    )


def _collect_dataset_stats(directory: Path, max_workers: Optional[int]) -> Tuple[DatasetStats, List[FileSummary]]:
    files = _iter_parquet_files(directory)
    if not files:
        raise FileNotFoundError(f"No parquet files found in: {directory}")

    workers = (
        max_workers
        if max_workers
        else min(len(files), max(mp.cpu_count() - 2, 1), 64)
    )

    stats = DatasetStats(files=len(files))
    summaries: List[FileSummary] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_analyze_file, (path, COLUMNS)): path for path in files
        }
        for future in as_completed(futures):
            summary = future.result()
            summaries.append(summary)
            stats.total_points += summary.points
            stats.total_size += summary.file_size
            stats.any_nan += summary.any_nan
            for col in COLUMNS:
                stats.nan_counts[col] += summary.nan_counts[col]

    summaries.sort(key=lambda item: item.file_name)
    return stats, summaries


def _print_point_summary(raw_stats: DatasetStats, filtered_stats: DatasetStats) -> None:
    raw_points = raw_stats.total_points
    filtered_points = filtered_stats.total_points
    dropped = raw_points - filtered_points
    retention = filtered_points / raw_points * 100 if raw_points else 0.0
    drop_ratio = dropped / raw_points * 100 if raw_points else 0.0

    print("Point Summary")
    print("=" * 60)
    print(f"Raw files:       {raw_stats.files}")
    print(f"Raw points:      {_format_number(raw_points)}")
    print(f"Filtered files:  {filtered_stats.files}")
    print(f"Filtered points: {_format_number(filtered_points)}")
    print("-" * 60)
    print(f"Points removed:  {_format_number(dropped)}")
    print(f"Drop ratio:      {drop_ratio:.3f}%")
    print(f"Retention ratio: {retention:.3f}%")
    print("=" * 60)


def _print_nan_summary(label: str, stats: DatasetStats) -> None:
    print(f"\nNaN Summary - {label}")
    print("-" * 60)
    for col in COLUMNS:
        count = stats.nan_counts[col]
        ratio = _format_percent(count, stats.total_points)
        print(f"{col:<10}: {count:,} rows ({ratio})")
    ratio_any = _format_percent(stats.any_nan, stats.total_points)
    print(f"{'any_nan':<10}: {stats.any_nan:,} rows ({ratio_any})")


def _save_ratio_csv(
    raw_stats: DatasetStats,
    filtered_stats: DatasetStats,
    raw_files: List[FileSummary],
    filtered_files: List[FileSummary],
    output_path: Path,
) -> None:
    import csv

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "dataset",
        "file_name",
        "total_points",
        "latitude_nan_ratio",
        "longitude_nan_ratio",
        "altitude_nan_ratio",
        "any_nan_ratio",
    ]

    def ratio_row(
        dataset: str,
        file_name: str,
        points: int,
        nan_counts: Dict[str, int],
        any_nan: int,
    ) -> List[str]:
        total = points or 1
        ratios = [nan_counts[col] / total for col in COLUMNS]
        ratios.append(any_nan / total)
        ratio_values = [f"{value:.10f}" for value in ratios]
        return [dataset, file_name, str(points), *ratio_values]

    rows: List[List[str]] = [
        ratio_row("raw", "__TOTAL__", raw_stats.total_points, raw_stats.nan_counts, raw_stats.any_nan),
        ratio_row("filtered", "__TOTAL__", filtered_stats.total_points, filtered_stats.nan_counts, filtered_stats.any_nan),
    ]

    for summary in raw_files:
        rows.append(
            ratio_row("raw", summary.file_name, summary.points, summary.nan_counts, summary.any_nan)
        )
    for summary in filtered_files:
        rows.append(
            ratio_row("filtered", summary.file_name, summary.points, summary.nan_counts, summary.any_nan)
        )

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare raw vs filtered trajectory stats, including nan ratios."
    )
    parser.add_argument("--raw-dir", type=Path, default=RAW_DEFAULT, help="Raw trajectory directory")
    parser.add_argument(
        "--filtered-dir",
        type=Path,
        default=FILTERED_DEFAULT,
        help="Filtered trajectory directory",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Maximum worker processes (auto by default)",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="CSV output path包含汇总与逐文件缺失率（raw 行在前，filtered 行随后）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print(f"Raw directory:      {args.raw_dir}")
    print(f"Filtered directory: {args.filtered_dir}")
    if args.max_workers:
        print(f"Max workers:        {args.max_workers}")

    raw_stats, raw_files = _collect_dataset_stats(args.raw_dir, args.max_workers)
    filtered_stats, filtered_files = _collect_dataset_stats(args.filtered_dir, args.max_workers)

    _print_point_summary(raw_stats, filtered_stats)
    _print_nan_summary("Raw", raw_stats)
    _print_nan_summary("Filtered", filtered_stats)

    if args.output_csv:
        _save_ratio_csv(raw_stats, filtered_stats, raw_files, filtered_files, args.output_csv)
        print(f"\nNaN ratio CSV saved to: {args.output_csv}")


if __name__ == "__main__":
    main()
