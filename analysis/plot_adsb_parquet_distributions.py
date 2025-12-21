#!/usr/bin/env python3
"""
统计 OpenSky ADS-B Parquet 数据的分布并导出直方图计数。

特点：
- 兼容任意包含 *.parquet 的目录（重点：opensky_2024_PRC_dataset/rawtrajectories）。
- 只统计“源数据中已落盘”的列；不会为缺失列做额外派生计算。
- 多进程按文件分块并行，适合 365 天分片的大数据量场景。
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pyarrow.parquet as pq

DEFAULT_DATA_DIR = Path("opensky_2024_PRC_dataset/rawtrajectories")

# 默认仅关注“物理意义明确”的列；只要列在源数据中存在，就会被统计。
DEFAULT_BIN_WIDTHS: Dict[str, float] = {
    "latitude": 0.001,
    "longitude": 0.001,
    "altitude": 25.0,
    "groundspeed": 1.0,
    "track": 1.0,
    "vertical_rate": 32.0,
    "u_component_of_wind": 0.05,
    "v_component_of_wind": 0.05,
    "wind": 0.05,
    "temperature": 0.05,
    "specific_humidity": 1e-4,
    # 插值目录可能存在（若源数据没落盘，不会计算）
    "gsx": 1.0,
    "gsy": 1.0,
    "tasx": 1.0,
    "tasy": 1.0,
    "tas": 1.0,
    "daltitude": 32.0,
    # xue_processed_raw__v1
    "TAS": 1.0,
}

UNITS: Dict[str, str] = {
    "latitude": "deg",
    "longitude": "deg",
    "altitude": "ft",
    "groundspeed": "kt",
    "track": "deg",
    "vertical_rate": "ft/min",
    "u_component_of_wind": "m/s",
    "v_component_of_wind": "m/s",
    "wind": "m/s",
    "temperature": "K",
    "specific_humidity": "kg/kg",
    "gsx": "kt",
    "gsy": "kt",
    "tasx": "kt",
    "tasy": "kt",
    "tas": "kt",
    "daltitude": "ft/min",
    "TAS": "kt",
}

DEFAULT_HEATMAP_LON_RANGE = (70.0, 140.0)
DEFAULT_HEATMAP_LAT_RANGE = (0.0, 70.0)


@dataclass(frozen=True)
class ColumnMetaStats:
    min_value: float
    max_value: float


@dataclass(frozen=True)
class HistogramSpec:
    column: str
    start: float
    width: float
    bins: int


@dataclass
class ChunkResult:
    counts: List[np.ndarray]
    valid: np.ndarray
    missing: np.ndarray
    sums: np.ndarray
    sumsq: np.ndarray
    out_of_range: np.ndarray
    total_rows: int
    files: int


def _extract_date_yyyy_mm_dd(file_name: str) -> Optional[str]:
    # 兼容：2022-01-01.parquet / interpolated_2022-01-01.parquet / xue_2022-01-01.parquet
    for part in file_name.split("_"):
        if len(part) >= 10 and part[:10].count("-") == 2:
            date_str = part[:10]
            if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                return date_str
    stem = file_name.split(".")[0]
    if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
        return stem
    return None


def _iter_parquet_files(
    directory: Path, date_from: Optional[str], date_to: Optional[str]
) -> List[Path]:
    files = sorted(directory.glob("*.parquet"))
    if date_from is None and date_to is None:
        return files

    filtered: List[Path] = []
    for file_path in files:
        date_str = _extract_date_yyyy_mm_dd(file_path.name)
        if date_str is None:
            continue
        if date_from is not None and date_str < date_from:
            continue
        if date_to is not None and date_str > date_to:
            continue
        filtered.append(file_path)
    return filtered


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float, np.number)):
        value_f = float(value)
        if math.isnan(value_f):
            return None
        return value_f
    return None


def _scan_column_min_max(
    files: Sequence[Path], columns: Sequence[str]
) -> Tuple[int, int, Dict[str, ColumnMetaStats]]:
    total_rows = 0
    files_scanned = 0
    min_values: Dict[str, Optional[float]] = {c: None for c in columns}
    max_values: Dict[str, Optional[float]] = {c: None for c in columns}

    for file_path in files:
        parquet = pq.ParquetFile(str(file_path))
        total_rows += parquet.metadata.num_rows
        files_scanned += 1
        name_to_index = {name: idx for idx, name in enumerate(parquet.schema.names)}

        for col in columns:
            if col not in name_to_index:
                continue
            col_idx = name_to_index[col]
            for rg_idx in range(parquet.metadata.num_row_groups):
                stats = parquet.metadata.row_group(rg_idx).column(col_idx).statistics
                if stats is None:
                    continue
                lo = _safe_float(stats.min)
                hi = _safe_float(stats.max)
                if lo is not None:
                    cur = min_values[col]
                    min_values[col] = lo if cur is None else min(cur, lo)
                if hi is not None:
                    cur = max_values[col]
                    max_values[col] = hi if cur is None else max(cur, hi)

    out: Dict[str, ColumnMetaStats] = {}
    for col in columns:
        lo = min_values[col]
        hi = max_values[col]
        if lo is None or hi is None:
            raise RuntimeError(
                f"无法从 Parquet 元数据获取列 {col} 的 min/max（可能缺少统计信息）"
            )
        out[col] = ColumnMetaStats(min_value=lo, max_value=hi)

    return files_scanned, total_rows, out


def _floor_align(value: float, step: float) -> float:
    return math.floor(value / step) * step


def _build_hist_specs(
    columns: Sequence[str],
    widths: Dict[str, float],
    meta_stats: Dict[str, ColumnMetaStats],
) -> List[HistogramSpec]:
    specs: List[HistogramSpec] = []
    for col in columns:
        width = widths[col]
        if width <= 0:
            raise ValueError(f"bin 宽度必须为正数: {col}={width}")
        min_val = meta_stats[col].min_value
        max_val = meta_stats[col].max_value
        start = _floor_align(min_val, width)
        span = max_val - start
        bins = int(math.floor(span / width + 1e-12)) + 1
        bins = max(bins, 1)
        specs.append(HistogramSpec(column=col, start=start, width=width, bins=bins))
    return specs


def _process_file_chunk(
    args: Tuple[List[str], List[HistogramSpec], int]
) -> ChunkResult:
    file_paths, specs, batch_size = args
    columns = [spec.column for spec in specs]

    counts = [np.zeros(spec.bins, dtype=np.uint64) for spec in specs]
    valid = np.zeros(len(specs), dtype=np.int64)
    missing = np.zeros(len(specs), dtype=np.int64)
    sums = np.zeros(len(specs), dtype=np.float64)
    sumsq = np.zeros(len(specs), dtype=np.float64)
    out_of_range = np.zeros(len(specs), dtype=np.int64)
    total_rows = 0

    for file_path_str in file_paths:
        parquet = pq.ParquetFile(file_path_str)
        total_rows += parquet.metadata.num_rows

        for batch in parquet.iter_batches(columns=columns, batch_size=batch_size):
            for idx, spec in enumerate(specs):
                arr = batch.column(idx).to_numpy(zero_copy_only=False)
                if arr.size == 0:
                    continue
                finite_mask = np.isfinite(arr)
                if not finite_mask.all():
                    missing[idx] += int(arr.size - finite_mask.sum())
                    values = arr[finite_mask]
                else:
                    values = arr

                bin_idx = np.floor((values - spec.start) / spec.width).astype(np.int64)
                in_range = (bin_idx >= 0) & (bin_idx < spec.bins)
                if not in_range.all():
                    out_of_range[idx] += int(bin_idx.size - in_range.sum())
                    bin_idx = bin_idx[in_range]
                    values = values[in_range]

                if bin_idx.size == 0:
                    continue

                counts[idx] += np.bincount(bin_idx, minlength=spec.bins).astype(
                    np.uint64, copy=False
                )
                valid[idx] += int(values.size)
                sums[idx] += float(values.sum(dtype=np.float64))
                sumsq[idx] += float(np.square(values, dtype=np.float64).sum(dtype=np.float64))

    return ChunkResult(
        counts=counts,
        valid=valid,
        missing=missing,
        sums=sums,
        sumsq=sumsq,
        out_of_range=out_of_range,
        total_rows=total_rows,
        files=len(file_paths),
    )


def _write_summary_csv(
    out_path: Path,
    specs: Sequence[HistogramSpec],
    meta_stats: Dict[str, ColumnMetaStats],
    total_rows: int,
    counts: Sequence[np.ndarray],
    valid: np.ndarray,
    missing: np.ndarray,
    sums: np.ndarray,
    sumsq: np.ndarray,
    out_of_range: np.ndarray,
) -> None:
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "column",
                "unit",
                "bin_width",
                "start",
                "bins",
                "meta_min",
                "meta_max",
                "total_rows",
                "valid",
                "missing",
                "missing_ratio",
                "mean",
                "std",
                "out_of_range",
            ]
        )
        for idx, spec in enumerate(specs):
            v = int(valid[idx])
            m = int(missing[idx])
            oor = int(out_of_range[idx])
            mean = float(sums[idx] / v) if v else float("nan")
            var = float(sumsq[idx] / v - mean * mean) if v else float("nan")
            std = float(math.sqrt(var)) if v and var >= 0 else float("nan")
            writer.writerow(
                [
                    spec.column,
                    UNITS.get(spec.column, ""),
                    spec.width,
                    spec.start,
                    spec.bins,
                    meta_stats[spec.column].min_value,
                    meta_stats[spec.column].max_value,
                    total_rows,
                    v,
                    m,
                    (m / total_rows) if total_rows else float("nan"),
                    mean,
                    std,
                    oor,
                ]
            )


def _split_into_chunks(items: Sequence[Path], chunks: int) -> List[List[str]]:
    chunks = max(1, min(chunks, len(items)))
    result: List[List[str]] = [[] for _ in range(chunks)]
    for idx, path in enumerate(items):
        result[idx % chunks].append(str(path))
    return [c for c in result if c]


def _plot_histograms(
    out_dir: Path,
    specs: Sequence[HistogramSpec],
    counts: Sequence[np.ndarray],
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for idx, spec in enumerate(specs):
        y = counts[idx]
        x = spec.start + spec.width * (np.arange(spec.bins, dtype=np.float64) + 0.5)

        fig, ax = plt.subplots(figsize=(10, 4), dpi=150)
        ax.plot(x, y, linewidth=0.8)
        ax.set_title(f"{spec.column} histogram (bin={spec.width} {UNITS.get(spec.column, '')})")
        xlabel_unit = UNITS.get(spec.column, "")
        ax.set_xlabel(f"{spec.column} ({xlabel_unit})" if xlabel_unit else spec.column)
        ax.set_ylabel("count")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
        ax.set_xlim(spec.start, spec.start + spec.bins * spec.width)
        fig.tight_layout()
        fig.savefig(out_dir / f"hist_{spec.column}.png")
        plt.close(fig)


def _choose_heatmap_range(
    mode: str,
    *,
    lon_min_data: float,
    lon_max_data: float,
    lat_min_data: float,
    lat_max_data: float,
    lon_step: float,
    lat_step: float,
    max_cells: int,
    lon_min_arg: Optional[float],
    lon_max_arg: Optional[float],
    lat_min_arg: Optional[float],
    lat_max_arg: Optional[float],
) -> Tuple[float, float, float, float, str]:
    if (
        lon_min_arg is not None
        and lon_max_arg is not None
        and lat_min_arg is not None
        and lat_max_arg is not None
    ):
        return lon_min_arg, lon_max_arg, lat_min_arg, lat_max_arg, "custom"

    def cells(lon_min: float, lon_max: float, lat_min: float, lat_max: float) -> int:
        width = int(math.floor((lon_max - lon_min) / lon_step + 1e-12)) + 1
        height = int(math.floor((lat_max - lat_min) / lat_step + 1e-12)) + 1
        return width * height

    if mode not in {"auto", "full", "bbox"}:
        raise ValueError(f"heatmap range mode 不支持: {mode}")

    full = (lon_min_data, lon_max_data, lat_min_data, lat_max_data)
    bbox = (
        max(lon_min_data, DEFAULT_HEATMAP_LON_RANGE[0]),
        min(lon_max_data, DEFAULT_HEATMAP_LON_RANGE[1]),
        max(lat_min_data, DEFAULT_HEATMAP_LAT_RANGE[0]),
        min(lat_max_data, DEFAULT_HEATMAP_LAT_RANGE[1]),
    )

    if mode == "full":
        return *full, "full"
    if mode == "bbox":
        return *bbox, "bbox"

    if cells(*full) <= max_cells:
        return *full, "auto(full)"
    return *bbox, "auto(bbox)"


def _render_lat_lon_heatmap(
    out_dir: Path,
    files: Sequence[Path],
    lon_col: str,
    lat_col: str,
    lon_range: Tuple[float, float],
    lat_range: Tuple[float, float],
    lon_step: float,
    lat_step: float,
    color_scale: str,
) -> None:
    try:
        import dask.dataframe as dd
        import datashader as ds
        import datashader.transfer_functions as tf
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "缺少绘制 2D 热力图所需依赖（dask + datashader）。"
        ) from e

    lon_min, lon_max = lon_range
    lat_min, lat_max = lat_range
    plot_width = int(math.floor((lon_max - lon_min) / lon_step + 1e-12)) + 1
    plot_height = int(math.floor((lat_max - lat_min) / lat_step + 1e-12)) + 1
    if plot_width <= 0 or plot_height <= 0:
        raise ValueError(
            f"heatmap range 非法：lon_range={lon_range}, lat_range={lat_range}, step=({lon_step},{lat_step})"
        )

    ddf = dd.read_parquet(
        [str(p) for p in files],
        columns=[lon_col, lat_col],
        engine="pyarrow",
    ).dropna(subset=[lon_col, lat_col])
    ddf = ddf[
        (ddf[lon_col] >= lon_min)
        & (ddf[lon_col] <= lon_max)
        & (ddf[lat_col] >= lat_min)
        & (ddf[lat_col] <= lat_max)
    ]

    cvs = ds.Canvas(
        plot_width=plot_width,
        plot_height=plot_height,
        x_range=(lon_min, lon_max),
        y_range=(lat_min, lat_max),
    )
    agg = cvs.points(ddf, lon_col, lat_col, agg=ds.count())
    img = tf.shade(agg, how=color_scale)
    img = tf.set_background(img, "white")
    img.to_pil().save(out_dir / "heatmap_lat_lon.png")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="统计 ADS-B parquet 分布，导出直方图计数（不额外派生缺失列）。"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="包含 *.parquet 的目录（默认：opensky_2024_PRC_dataset/rawtrajectories）",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("reports/data_distributions"),
        help="输出根目录（默认：reports/data_distributions）",
    )
    parser.add_argument("--label", type=str, default=None, help="输出子目录名（默认：data-dir 名）")
    parser.add_argument("--date-from", type=str, default=None, help="起始日期 YYYY-MM-DD（含）")
    parser.add_argument("--date-to", type=str, default=None, help="结束日期 YYYY-MM-DD（含）")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(max(mp.cpu_count() - 2, 1), 8),
        help="并行进程数（默认：min(cpu-2, 8)）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000_000,
        help="pyarrow iter_batches 的 batch_size（默认：1,000,000）",
    )
    parser.add_argument(
        "--no-hist-plots",
        action="store_true",
        help="不输出 1D 直方图 PNG（仍会输出 hist_counts.npz）",
    )
    parser.add_argument(
        "--no-heatmap",
        action="store_true",
        help="不输出经纬 2D 热力图",
    )
    parser.add_argument(
        "--heatmap-lon-step",
        type=float,
        default=0.005,
        help="经度方向网格步长（度，默认：0.005）",
    )
    parser.add_argument(
        "--heatmap-lat-step",
        type=float,
        default=0.005,
        help="纬度方向网格步长（度，默认：0.005）",
    )
    parser.add_argument(
        "--heatmap-range-mode",
        type=str,
        default="auto",
        choices=["auto", "full", "bbox"],
        help="热力图范围选择：auto=超大时回退 bbox；full=全范围；bbox=固定中国附近范围（默认：auto）",
    )
    parser.add_argument(
        "--heatmap-max-cells",
        type=int,
        default=250_000_000,
        help="热力图最大像素数上限（用于 auto 决策，默认：250,000,000）",
    )
    parser.add_argument("--heatmap-lon-min", type=float, default=None)
    parser.add_argument("--heatmap-lon-max", type=float, default=None)
    parser.add_argument("--heatmap-lat-min", type=float, default=None)
    parser.add_argument("--heatmap-lat-max", type=float, default=None)
    parser.add_argument(
        "--heatmap-color-scale",
        type=str,
        default="linear",
        choices=["linear", "log", "eq_hist"],
        help="热力图颜色映射方式（默认：linear）",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    if not data_dir.exists():
        raise FileNotFoundError(f"目录不存在: {data_dir}")

    files = _iter_parquet_files(data_dir, args.date_from, args.date_to)
    if not files:
        raise FileNotFoundError(f"未找到 parquet 文件: {data_dir}")

    parquet0 = pq.ParquetFile(str(files[0]))
    available_cols = set(parquet0.schema.names)
    columns = [c for c in DEFAULT_BIN_WIDTHS.keys() if c in available_cols]
    if not columns:
        raise RuntimeError(f"在 {files[0].name} 中未找到任何目标列（可用列：{sorted(available_cols)}）")

    label = args.label or data_dir.name
    range_tag = f"{args.date_from or 'all'}__{args.date_to or 'all'}"
    out_dir = args.out_root / label / range_tag
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] data_dir={data_dir}")
    print(f"[INFO] files={len(files)} (date_from={args.date_from}, date_to={args.date_to})")
    print(f"[INFO] columns={columns}")
    print(f"[INFO] workers={args.workers}, batch_size={args.batch_size}")
    print(f"[INFO] out_dir={out_dir}")

    scanned_files, total_rows_meta, meta_stats = _scan_column_min_max(files, columns)
    specs = _build_hist_specs(columns, DEFAULT_BIN_WIDTHS, meta_stats)

    chunks = _split_into_chunks(files, args.workers)
    print(f"[INFO] chunk_count={len(chunks)}")

    total_counts = [np.zeros(spec.bins, dtype=np.uint64) for spec in specs]
    total_valid = np.zeros(len(specs), dtype=np.int64)
    total_missing = np.zeros(len(specs), dtype=np.int64)
    total_sums = np.zeros(len(specs), dtype=np.float64)
    total_sumsq = np.zeros(len(specs), dtype=np.float64)
    total_oor = np.zeros(len(specs), dtype=np.int64)
    total_rows = 0

    with ProcessPoolExecutor(max_workers=len(chunks)) as executor:
        futures = [
            executor.submit(_process_file_chunk, (chunk, specs, args.batch_size))
            for chunk in chunks
        ]
        for future in as_completed(futures):
            result = future.result()
            total_rows += result.total_rows
            total_valid += result.valid
            total_missing += result.missing
            total_sums += result.sums
            total_sumsq += result.sumsq
            total_oor += result.out_of_range
            for idx in range(len(specs)):
                total_counts[idx] += result.counts[idx]

    if total_rows != total_rows_meta:
        print(
            f"[WARN] total_rows(meta)={total_rows_meta}, total_rows(read)={total_rows}，两者不一致"
        )

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_dir": str(data_dir),
        "files": [p.name for p in files[:5]] + (["..."] if len(files) > 5 else []),
        "files_count": len(files),
        "files_scanned_for_meta": scanned_files,
        "total_rows": total_rows,
        "date_from": args.date_from,
        "date_to": args.date_to,
        "workers": args.workers,
        "batch_size": args.batch_size,
        "histograms": {
            spec.column: {
                "unit": UNITS.get(spec.column, ""),
                **asdict(spec),
                **asdict(meta_stats[spec.column]),
            }
            for spec in specs
        },
    }
    (out_dir / "hist_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    np.savez_compressed(
        out_dir / "hist_counts.npz",
        **{spec.column: total_counts[idx] for idx, spec in enumerate(specs)},
    )
    _write_summary_csv(
        out_dir / "summary.csv",
        specs,
        meta_stats,
        total_rows,
        total_counts,
        total_valid,
        total_missing,
        total_sums,
        total_sumsq,
        total_oor,
    )

    if not args.no_hist_plots:
        _plot_histograms(out_dir, specs, total_counts)
        print("[INFO] 已生成 1D 直方图 PNG：hist_<col>.png")

    if not args.no_heatmap and ("latitude" in available_cols and "longitude" in available_cols):
        lon_min, lon_max, lat_min, lat_max, range_mode_used = _choose_heatmap_range(
            args.heatmap_range_mode,
            lon_min_data=meta_stats["longitude"].min_value,
            lon_max_data=meta_stats["longitude"].max_value,
            lat_min_data=meta_stats["latitude"].min_value,
            lat_max_data=meta_stats["latitude"].max_value,
            lon_step=args.heatmap_lon_step,
            lat_step=args.heatmap_lat_step,
            max_cells=args.heatmap_max_cells,
            lon_min_arg=args.heatmap_lon_min,
            lon_max_arg=args.heatmap_lon_max,
            lat_min_arg=args.heatmap_lat_min,
            lat_max_arg=args.heatmap_lat_max,
        )
        cells = (
            int(math.floor((lon_max - lon_min) / args.heatmap_lon_step + 1e-12)) + 1
        ) * (int(math.floor((lat_max - lat_min) / args.heatmap_lat_step + 1e-12)) + 1)
        if cells > args.heatmap_max_cells and args.heatmap_range_mode == "auto":
            print(
                f"[WARN] heatmap 像素数过大（{cells}），已使用 bbox 回退（如需全范围请改用 --heatmap-range-mode full 或增大 --heatmap-max-cells）"
            )

        print(
            "[INFO] heatmap range "
            f"mode={range_mode_used}, lon=[{lon_min},{lon_max}], lat=[{lat_min},{lat_max}], step=({args.heatmap_lon_step},{args.heatmap_lat_step})"
        )
        _render_lat_lon_heatmap(
            out_dir,
            files,
            lon_col="longitude",
            lat_col="latitude",
            lon_range=(lon_min, lon_max),
            lat_range=(lat_min, lat_max),
            lon_step=args.heatmap_lon_step,
            lat_step=args.heatmap_lat_step,
            color_scale=args.heatmap_color_scale,
        )
        print("[INFO] 已生成 2D 热力图 PNG：heatmap_lat_lon.png")
    elif not args.no_heatmap:
        print("[INFO] 数据中不存在 latitude/longitude，跳过 2D 热力图")

    print("[INFO] done (已生成 hist_meta.json / hist_counts.npz / summary.csv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
