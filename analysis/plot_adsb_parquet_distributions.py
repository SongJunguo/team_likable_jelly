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
# DEFAULT_DATA_DIR = Path("opensky_2024_PRC_dataset/xue_processed_raw__v1")
DEFAULT_FLIGHTS_META_PATH = Path(
    "opensky_2024_PRC_dataset/flights/challenge_set.parquet"
)
DEFAULT_AIRPORTS_META_PATH = Path("opensky_2024_PRC_dataset/airports_tz.parquet")
DEFAULT_EUROPE_CONTINENT = "EU"


# 默认仅关注“物理意义明确”的列；只要列在源数据中存在，就会被统计。
DEFAULT_BIN_WIDTHS: Dict[str, float] = {
    "latitude": 0.001,
    "longitude": 0.001,
    "altitude": 25.0,
    "groundspeed": 1.0,
    "track": 0.01,
    "vertical_rate": 1.0,
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

DEFAULT_PLOT_XLIMS: Dict[str, Tuple[float, float]] = {
    "altitude": (-1000.0, 45000.0),
    "vertical_rate": (-5000.0, 5000.0),
    "daltitude": (-5000.0, 5000.0),
    "groundspeed": (0.0, 700.0),
}

DELTA_DEFAULTS = {
    "latitude": {"bin_width": 1e-5, "max": 0.02, "circular": False},
    "longitude": {"bin_width": 1e-5, "max": 0.02, "circular": False},
    "track": {"bin_width": 0.01, "max": 10.0, "circular": True},
    "vertical_rate": {"bin_width": 1.0, "max": 2000.0, "circular": False},
    "u_component_of_wind": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "v_component_of_wind": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "temperature": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "specific_humidity": {"bin_width": 1e-4, "max": 0.01, "circular": False},
}


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


@dataclass(frozen=True)
class DeltaHistogramSpec:
    column: str
    source_column: str
    start: float
    width: float
    bins: int
    circular: bool
    max_value: float


@dataclass
class ChunkResult:
    counts: List[np.ndarray]
    valid: np.ndarray
    missing: np.ndarray
    sums: np.ndarray
    sumsq: np.ndarray
    out_of_range: np.ndarray
    delta_counts: List[np.ndarray]
    delta_valid: np.ndarray
    delta_missing: np.ndarray
    delta_sums: np.ndarray
    delta_sumsq: np.ndarray
    delta_out_of_range: np.ndarray
    delta_pairs_total: int
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


def _load_eu_flight_ids(
    flights_path: Path, airports_path: Path, europe_continent: str
) -> np.ndarray:
    airports = pq.read_table(airports_path, columns=["icao_code", "continent"])
    airports_dict = airports.to_pydict()
    eu_airports = {
        code
        for code, cont in zip(airports_dict["icao_code"], airports_dict["continent"])
        if code and cont == europe_continent
    }

    flights = pq.read_table(flights_path, columns=["flight_id", "adep", "ades"])
    flights_dict = flights.to_pydict()
    allowed: List[int] = []
    for fid, adep, ades in zip(
        flights_dict["flight_id"], flights_dict["adep"], flights_dict["ades"]
    ):
        if fid is None:
            continue
        if adep in eu_airports and ades in eu_airports:
            allowed.append(int(fid))
    return np.array(allowed, dtype=np.int64)


def _scan_column_min_max_filtered(
    files: Sequence[Path],
    columns: Sequence[str],
    flight_id_col: str,
    allowed_ids: np.ndarray,
    batch_size: int,
) -> Tuple[int, int, Dict[str, ColumnMetaStats]]:
    total_rows = 0
    files_scanned = 0
    min_values: Dict[str, Optional[float]] = {c: None for c in columns}
    max_values: Dict[str, Optional[float]] = {c: None for c in columns}

    for file_path in files:
        parquet = pq.ParquetFile(str(file_path))
        files_scanned += 1
        read_columns = [flight_id_col] + list(columns)
        for batch in parquet.iter_batches(columns=read_columns, batch_size=batch_size):
            fid = batch.column(0).to_numpy(zero_copy_only=False)
            if fid.size == 0:
                continue
            if fid.dtype.kind not in {"i", "u"}:
                fid = fid.astype(np.int64, copy=False)
            allowed_mask = np.isin(fid, allowed_ids)
            if not allowed_mask.any():
                continue
            total_rows += int(allowed_mask.sum())
            for idx, col in enumerate(columns, start=1):
                arr = batch.column(idx).to_numpy(zero_copy_only=False)
                arr = arr[allowed_mask]
                if arr.size == 0:
                    continue
                finite_mask = np.isfinite(arr)
                if not finite_mask.any():
                    continue
                values = arr[finite_mask].astype(np.float64, copy=False)
                lo = float(values.min())
                hi = float(values.max())
                cur_min = min_values[col]
                cur_max = max_values[col]
                min_values[col] = lo if cur_min is None else min(cur_min, lo)
                max_values[col] = hi if cur_max is None else max(cur_max, hi)

    if total_rows == 0:
        raise RuntimeError("过滤后无有效轨迹点，无法统计分布")

    out: Dict[str, ColumnMetaStats] = {}
    for col in columns:
        lo = min_values[col]
        hi = max_values[col]
        if lo is None or hi is None:
            raise RuntimeError(f"过滤后列 {col} 无有效数据，无法生成直方图")
        out[col] = ColumnMetaStats(min_value=lo, max_value=hi)

    return files_scanned, total_rows, out


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
    args: Tuple[
        List[str],
        List[HistogramSpec],
        List[DeltaHistogramSpec],
        int,
        int,
        Optional[np.ndarray],
        Optional[str],
        Optional[str],
    ]
) -> ChunkResult:
    (
        file_paths,
        specs,
        delta_specs,
        batch_size,
        required_dt_ns,
        allowed_ids,
        flight_id_col,
        delta_fid_col,
    ) = args
    columns_hist = [spec.column for spec in specs]
    delta_enabled = bool(delta_specs)
    filter_enabled = allowed_ids is not None
    if delta_enabled and not delta_fid_col:
        raise RuntimeError("delta_fid_col 为空，无法计算 delta-hist")

    counts = [np.zeros(spec.bins, dtype=np.uint64) for spec in specs]
    valid = np.zeros(len(specs), dtype=np.int64)
    missing = np.zeros(len(specs), dtype=np.int64)
    sums = np.zeros(len(specs), dtype=np.float64)
    sumsq = np.zeros(len(specs), dtype=np.float64)
    out_of_range = np.zeros(len(specs), dtype=np.int64)
    delta_counts = [np.zeros(spec.bins, dtype=np.uint64) for spec in delta_specs]
    delta_valid = np.zeros(len(delta_specs), dtype=np.int64)
    delta_missing = np.zeros(len(delta_specs), dtype=np.int64)
    delta_sums = np.zeros(len(delta_specs), dtype=np.float64)
    delta_sumsq = np.zeros(len(delta_specs), dtype=np.float64)
    delta_out_of_range = np.zeros(len(delta_specs), dtype=np.int64)
    delta_pairs_total = 0
    total_rows = 0

    for file_path_str in file_paths:
        parquet = pq.ParquetFile(file_path_str)

        read_columns = list(columns_hist)
        if filter_enabled:
            if flight_id_col is None:
                raise RuntimeError("flight_id_col 为空，无法做轨迹过滤")
            read_columns.append(flight_id_col)
        if delta_enabled:
            read_columns.extend([delta_fid_col, "timestamp"])
            read_columns.extend([spec.source_column for spec in delta_specs])
        read_columns = sorted(set(read_columns))
        col_to_idx = {col: idx for idx, col in enumerate(read_columns)}

        last_fid: Optional[np.int64] = None
        last_ts: Optional[np.datetime64] = None
        last_values: Dict[str, float] = {}

        for batch in parquet.iter_batches(columns=read_columns, batch_size=batch_size):
            arrays = {
                col: batch.column(col_to_idx[col]).to_numpy(zero_copy_only=False)
                for col in read_columns
            }

            allowed_mask = None
            if filter_enabled:
                fid_for_filter = arrays[flight_id_col]
                if fid_for_filter.dtype.kind not in {"i", "u"}:
                    fid_for_filter = fid_for_filter.astype(np.int64, copy=False)
                allowed_mask = np.isin(fid_for_filter, allowed_ids)
                if not allowed_mask.any():
                    continue
                total_rows += int(allowed_mask.sum())
            else:
                sample_arr = arrays[columns_hist[0]] if columns_hist else arrays[delta_fid_col]
                total_rows += int(sample_arr.size)

            for idx, spec in enumerate(specs):
                arr = arrays[spec.column]
                if allowed_mask is not None:
                    arr = arr[allowed_mask]
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

            if delta_enabled:
                fid = arrays[delta_fid_col]
                ts = arrays["timestamp"]
                if allowed_mask is not None:
                    fid = fid[allowed_mask]
                    ts = ts[allowed_mask]
                if fid.size == 0:
                    continue
                if fid.size != ts.size:
                    raise RuntimeError(
                        f"{delta_fid_col} 与 timestamp 行数不一致，无法计算 delta-hist"
                    )
                if fid.dtype.kind not in {"i", "u"}:
                    fid = fid.astype(np.int64, copy=False)

                fid_prev = fid[:-1]
                fid_curr = fid[1:]
                ts_prev = ts[:-1]
                ts_curr = ts[1:]
                dt_ns = (ts_curr - ts_prev).astype("timedelta64[ns]").astype(np.int64)
                base_mask = (fid_curr == fid_prev) & (dt_ns == required_dt_ns)
                delta_pairs_total += int(base_mask.sum())

                cross_mask = False
                cross_dt_ok = False
                if last_fid is not None and last_ts is not None:
                    dt0 = (ts[0] - last_ts).astype("timedelta64[ns]").astype(np.int64)
                    cross_dt_ok = bool(dt0 == required_dt_ns)
                    cross_mask = bool(fid[0] == last_fid and cross_dt_ok)
                    if cross_mask:
                        delta_pairs_total += 1

                for d_idx, dspec in enumerate(delta_specs):
                    arr = arrays[dspec.source_column].astype(np.float64, copy=False)
                    if allowed_mask is not None:
                        arr = arr[allowed_mask]

                    val_prev = arr[:-1]
                    val_curr = arr[1:]
                    finite_pair = np.isfinite(val_prev) & np.isfinite(val_curr)
                    mask = base_mask & finite_pair
                    if not finite_pair.all():
                        delta_missing[d_idx] += int((base_mask & ~finite_pair).sum())

                    if mask.any():
                        if dspec.circular:
                            diff = val_curr[mask] - val_prev[mask]
                            delta = np.abs(((diff + 180.0) % 360.0) - 180.0)
                        else:
                            delta = np.abs(val_curr[mask] - val_prev[mask])

                        bin_idx = np.floor((delta - dspec.start) / dspec.width).astype(
                            np.int64
                        )
                        in_range = (bin_idx >= 0) & (bin_idx < dspec.bins)
                        if not in_range.all():
                            delta_out_of_range[d_idx] += int(
                                bin_idx.size - in_range.sum()
                            )
                            bin_idx = bin_idx[in_range]
                            delta = delta[in_range]

                        if bin_idx.size:
                            delta_counts[d_idx] += np.bincount(
                                bin_idx, minlength=dspec.bins
                            ).astype(np.uint64, copy=False)
                            delta_valid[d_idx] += int(delta.size)
                            delta_sums[d_idx] += float(delta.sum(dtype=np.float64))
                            delta_sumsq[d_idx] += float(
                                np.square(delta, dtype=np.float64).sum(dtype=np.float64)
                            )

                    if cross_mask:
                        v_prev = float(last_values.get(dspec.source_column, float("nan")))
                        v_curr = float(arr[0])
                        if math.isfinite(v_prev) and math.isfinite(v_curr):
                            if dspec.circular:
                                diff = v_curr - v_prev
                                delta0 = abs(((diff + 180.0) % 360.0) - 180.0)
                            else:
                                delta0 = abs(v_curr - v_prev)
                            bin0 = int(math.floor((delta0 - dspec.start) / dspec.width))
                            if 0 <= bin0 < dspec.bins:
                                delta_counts[d_idx][bin0] += np.uint64(1)
                                delta_valid[d_idx] += 1
                                delta_sums[d_idx] += float(delta0)
                                delta_sumsq[d_idx] += float(delta0 * delta0)
                            else:
                                delta_out_of_range[d_idx] += 1
                        else:
                            delta_missing[d_idx] += 1

                    last_values[dspec.source_column] = float(arr[-1])

                last_fid = fid[-1]
                last_ts = ts[-1]

    return ChunkResult(
        counts=counts,
        valid=valid,
        missing=missing,
        sums=sums,
        sumsq=sumsq,
        out_of_range=out_of_range,
        delta_counts=delta_counts,
        delta_valid=delta_valid,
        delta_missing=delta_missing,
        delta_sums=delta_sums,
        delta_sumsq=delta_sumsq,
        delta_out_of_range=delta_out_of_range,
        delta_pairs_total=delta_pairs_total,
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


def _write_hist_counts_csv(
    out_path: Path,
    specs: Sequence[HistogramSpec],
    counts: Sequence[np.ndarray],
) -> None:
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "column",
                "unit",
                "bin_width",
                "start",
                "bin_index",
                "bin_left",
                "bin_right",
                "count",
            ]
        )
        for spec, y in zip(specs, counts):
            unit = UNITS.get(spec.column, "")
            start = float(spec.start)
            width = float(spec.width)
            for bin_index, c in enumerate(y):
                bin_left = start + width * bin_index
                writer.writerow(
                    [
                        spec.column,
                        unit,
                        width,
                        start,
                        bin_index,
                        bin_left,
                        bin_left + width,
                        int(c),
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
    *,
    yscale: str,
    xlims: Optional[Dict[str, Tuple[float, float]]] = None,
    dpi: int = 600,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    if yscale not in {"linear", "log"}:
        raise ValueError(f"不支持的 yscale: {yscale}")
    if dpi <= 0:
        raise ValueError(f"dpi 必须为正数: {dpi}")

    for idx, spec in enumerate(specs):
        y_full = counts[idx]

        xlim = None if not xlims else xlims.get(spec.column)
        if xlim is not None:
            lo, hi = float(xlim[0]), float(xlim[1])
            i0 = int(math.floor((lo - spec.start) / spec.width)) - 1
            i1 = int(math.ceil((hi - spec.start) / spec.width)) + 1
            i0 = max(i0, 0)
            i1 = min(i1, spec.bins)
            if i1 <= i0:
                i0 = max(min(i0, spec.bins - 1), 0)
                i1 = min(i0 + 1, spec.bins)
            y = y_full[i0:i1]
            x = spec.start + spec.width * (
                np.arange(i0, i1, dtype=np.float64) + 0.5
            )
        else:
            y = y_full
            x = spec.start + spec.width * (np.arange(spec.bins, dtype=np.float64) + 0.5)

        fig, ax = plt.subplots(figsize=(10, 4), dpi=dpi)
        if yscale == "log":
            y_plot = np.maximum(y.astype(np.float64, copy=False), 1.0)
            ax.step(x, y_plot, where="mid", linewidth=0.8)
            ax.set_yscale("log")
            ax.set_ylim(bottom=1)
        else:
            ax.step(x, y, where="mid", linewidth=0.8)

        ax.set_title(
            f"{spec.column} histogram (bin={spec.width} {UNITS.get(spec.column, '')}, y={yscale})"
        )
        xlabel_unit = UNITS.get(spec.column, "")
        ax.set_xlabel(f"{spec.column} ({xlabel_unit})" if xlabel_unit else spec.column)
        ax.set_ylabel("count")
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
        if xlim is not None:
            ax.set_xlim(xlim[0], xlim[1])
        else:
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


def _adjust_heatmap_steps_for_max_cells(
    lon_range: Tuple[float, float],
    lat_range: Tuple[float, float],
    lon_step: float,
    lat_step: float,
    max_cells: int,
) -> Tuple[float, float, int, int, int, float]:
    if lon_step <= 0 or lat_step <= 0:
        raise ValueError(f"heatmap step 必须为正数: lon_step={lon_step}, lat_step={lat_step}")
    if max_cells <= 0:
        raise ValueError(f"heatmap max_cells 必须为正数: {max_cells}")

    lon_min, lon_max = lon_range
    lat_min, lat_max = lat_range
    lon_span = float(lon_max - lon_min)
    lat_span = float(lat_max - lat_min)
    if lon_span <= 0 or lat_span <= 0:
        raise ValueError(f"heatmap range 非法：lon_range={lon_range}, lat_range={lat_range}")

    def compute(step_x: float, step_y: float) -> Tuple[int, int, int]:
        width = int(math.floor(lon_span / step_x + 1e-12)) + 1
        height = int(math.floor(lat_span / step_y + 1e-12)) + 1
        return width, height, width * height

    width0, height0, cells0 = compute(lon_step, lat_step)
    if cells0 <= max_cells:
        return lon_step, lat_step, width0, height0, cells0, 1.0

    scale = math.sqrt(cells0 / max_cells)
    scale = max(scale, 1.0)
    step_x = lon_step * scale
    step_y = lat_step * scale
    width, height, cells = compute(step_x, step_y)
    while cells > max_cells:
        step_x *= 1.01
        step_y *= 1.01
        width, height, cells = compute(step_x, step_y)

    return step_x, step_y, width, height, cells, scale


def _render_lat_lon_heatmap(
    out_dir: Path,
    files: Sequence[Path],
    lon_col: str,
    lat_col: str,
    alt_col: Optional[str],
    mean_altitude: bool,
    alt_min: float,
    alt_max: float,
    lon_range: Tuple[float, float],
    lat_range: Tuple[float, float],
    plot_width: int,
    plot_height: int,
    lon_step: float,
    lat_step: float,
    dpi: int,
    color_scale: str,
    mean_alt_color_scale: str,
    dynspread: bool,
    dynspread_threshold: float,
    dynspread_max_px: int,
    allowed_ids: Optional[np.ndarray],
    flight_id_col: Optional[str],
) -> None:
    try:
        import dask.dataframe as dd
        import datashader as ds
        import datashader.transfer_functions as tf
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "缺少绘制 2D 热力图所需依赖（dask + datashader）。"
        ) from e

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LogNorm, Normalize

    lon_min, lon_max = lon_range
    lat_min, lat_max = lat_range
    if plot_width <= 0 or plot_height <= 0:
        raise ValueError(
            f"heatmap 尺寸非法：plot_width={plot_width}, plot_height={plot_height}"
        )
    if dpi <= 0:
        raise ValueError(f"heatmap dpi 必须为正数: {dpi}")

    columns = [lon_col, lat_col]
    if allowed_ids is not None:
        if not flight_id_col:
            raise RuntimeError("flight_id_col 为空，无法过滤热力图")
        columns.append(flight_id_col)
    alt_clip_col = "__altitude_clipped_for_heatmap"
    enable_mean_alt = bool(mean_altitude and alt_col)
    if enable_mean_alt:
        columns.append(alt_col)

    ddf = dd.read_parquet(
        [str(p) for p in files],
        columns=columns,
        engine="pyarrow",
    ).dropna(subset=[lon_col, lat_col])
    if allowed_ids is not None:
        ddf = ddf[ddf[flight_id_col].isin(allowed_ids)]
    ddf = ddf[
        (ddf[lon_col] >= lon_min)
        & (ddf[lon_col] <= lon_max)
        & (ddf[lat_col] >= lat_min)
        & (ddf[lat_col] <= lat_max)
    ]
    if enable_mean_alt:
        if alt_max <= alt_min:
            raise ValueError(f"heatmap-alt 范围非法: [{alt_min}, {alt_max}]")
        ddf = ddf.assign(
            **{
                alt_clip_col: ddf[alt_col].where(
                    (ddf[alt_col] >= alt_min) & (ddf[alt_col] <= alt_max)
                )
            }
        )

    cvs = ds.Canvas(
        plot_width=plot_width,
        plot_height=plot_height,
        x_range=(lon_min, lon_max),
        y_range=(lat_min, lat_max),
    )
    if enable_mean_alt:
        agg = cvs.points(
            ddf,
            lon_col,
            lat_col,
            agg=ds.summary(
                count=ds.count(),
                count_alt=ds.count(alt_clip_col),
                mean_altitude=ds.mean(alt_clip_col),
            ),
        )
        agg = agg.compute()
        agg_count = agg["count"]
        agg_count_alt = agg["count_alt"]
        agg_mean_alt = agg["mean_altitude"]
    else:
        agg_count = cvs.points(ddf, lon_col, lat_col, agg=ds.count()).compute()
        agg_count_alt = None
        agg_mean_alt = None

    # 1) 保存原始 datashader 裸图（可用于对比）
    img_count_raw = tf.shade(agg_count, how=color_scale)
    if dynspread:
        img_count_raw = tf.dynspread(
            img_count_raw, threshold=dynspread_threshold, max_px=dynspread_max_px
        )
    img_count_raw = tf.set_background(img_count_raw, "white")
    img_count_raw.to_pil().save(out_dir / "heatmap_lat_lon_raw.png")

    # 2) 输出 matplotlib 板式：坐标轴/标题/colorbar，默认 LogNorm + viridis，0 计数留白
    count = agg_count.values
    origin = "lower"
    try:
        y_dim = agg_count.dims[0]
        y_coords = agg_count.coords[y_dim].values
        if y_coords.size >= 2 and y_coords[0] > y_coords[-1]:
            origin = "upper"
    except Exception:
        origin = "lower"

    count_float = count.astype(np.float32, copy=False)
    count_masked = np.where(count_float > 0, count_float, np.nan)
    vmax = float(np.nanmax(count_masked)) if np.isfinite(count_masked).any() else 0.0
    fig_w = 10.0
    fig_h = max(4.5, fig_w * (plot_height / max(plot_width, 1)) * 0.9)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("white")
    if vmax >= 1.0:
        norm = LogNorm(vmin=1.0, vmax=vmax)
        im = ax.imshow(
            count_masked,
            origin=origin,
            extent=(lon_min, lon_max, lat_min, lat_max),
            cmap=cmap,
            norm=norm,
            aspect="auto",
            interpolation="nearest",
        )
        cbar = fig.colorbar(im, ax=ax, pad=0.02)
        cbar.set_label("Count (log scale)")
    else:
        ax.text(
            0.5,
            0.5,
            "No data",
            ha="center",
            va="center",
            transform=ax.transAxes,
        )
    points = int(np.nansum(count_float))
    ax.set_title(
        f"Lon/Lat Density (step_lon={lon_step:.6f}°, step_lat={lat_step:.6f}°, points={points})"
    )
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    fig.tight_layout()
    fig.savefig(out_dir / "heatmap_lat_lon.png")
    plt.close(fig)

    if agg_mean_alt is not None:
        # datashader 裸图（可用于对比）
        alt_cmap = ["#440154", "#3b528b", "#21908d", "#5dc863", "#fde725"]
        img_alt_raw = tf.shade(
            agg_mean_alt,
            how=mean_alt_color_scale,
            cmap=alt_cmap,
            span=(alt_min, alt_max),
        )
        if dynspread:
            img_alt_raw = tf.dynspread(img_alt_raw, threshold=dynspread_threshold, max_px=2)
        img_alt_raw = tf.set_background(img_alt_raw, "white")
        img_alt_raw.to_pil().save(out_dir / "heatmap_lat_lon_mean_altitude_raw.png")

        mean_alt = agg_mean_alt.values.astype(np.float32, copy=False)
        if agg_count_alt is not None:
            count_alt = agg_count_alt.values.astype(np.float32, copy=False)
            mean_alt = np.where(count_alt > 0, mean_alt, np.nan)
            points_alt = int(np.nansum(count_alt))
        else:
            points_alt = points

        fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=dpi)
        cmap_alt = plt.get_cmap("viridis").copy()
        cmap_alt.set_bad("white")
        norm_alt = Normalize(vmin=float(alt_min), vmax=float(alt_max))
        im = ax.imshow(
            mean_alt,
            origin=origin,
            extent=(lon_min, lon_max, lat_min, lat_max),
            cmap=cmap_alt,
            norm=norm_alt,
            aspect="auto",
            interpolation="nearest",
        )
        cbar = fig.colorbar(im, ax=ax, pad=0.02)
        cbar.set_label("Mean altitude (ft)")
        ax.set_title(
            f"Lon/Lat Mean Altitude (ft) (step_lon={lon_step:.6f}°, step_lat={lat_step:.6f}°, points={points_alt})"
        )
        ax.set_xlabel("Longitude (deg)")
        ax.set_ylabel("Latitude (deg)")
        fig.tight_layout()
        fig.savefig(out_dir / "heatmap_lat_lon_mean_altitude.png")
        plt.close(fig)


def _build_delta_specs(
    available_cols: set[str],
    overrides_bin_width: Sequence[str],
    overrides_max: Sequence[str],
) -> List[DeltaHistogramSpec]:
    delta_bin_widths = {k: float(v["bin_width"]) for k, v in DELTA_DEFAULTS.items()}
    delta_max = {k: float(v["max"]) for k, v in DELTA_DEFAULTS.items()}

    for item in overrides_bin_width:
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError(f"--delta-bin-width 格式错误: {item}（期望 <col>:<width>）")
        col, width_s = parts
        if col not in delta_bin_widths:
            raise ValueError(
                f"--delta-bin-width 不支持列: {col}（可选：{sorted(delta_bin_widths.keys())}）"
            )
        width = float(width_s)
        if not (width > 0):
            raise ValueError(f"--delta-bin-width 宽度必须为正数: {item}")
        delta_bin_widths[col] = width

    for item in overrides_max:
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError(f"--delta-max 格式错误: {item}（期望 <col>:<max>）")
        col, max_s = parts
        if col not in delta_max:
            raise ValueError(
                f"--delta-max 不支持列: {col}（可选：{sorted(delta_max.keys())}）"
            )
        max_v = float(max_s)
        if not (max_v > 0):
            raise ValueError(f"--delta-max 必须为正数: {item}")
        delta_max[col] = max_v

    specs: List[DeltaHistogramSpec] = []
    for src, cfg in DELTA_DEFAULTS.items():
        if src not in available_cols:
            continue
        width = float(delta_bin_widths[src])
        max_v = float(delta_max[src])
        bins = int(math.floor((max_v - 0.0) / width + 1e-12)) + 1
        bins = max(bins, 1)
        out_col = f"delta_{src}"
        UNITS[out_col] = UNITS.get(src, "")
        specs.append(
            DeltaHistogramSpec(
                column=out_col,
                source_column=src,
                start=0.0,
                width=width,
                bins=bins,
                circular=bool(cfg.get("circular", False)),
                max_value=max_v,
            )
        )
    return specs


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
    parser.add_argument(
        "--flight-filter",
        type=str,
        default="eu_meta",
        choices=["none", "eu_meta"],
        help="按航班元数据过滤：none=不过滤，eu_meta=起降均在欧洲",
    )
    parser.add_argument(
        "--flights-meta-path",
        type=Path,
        default=DEFAULT_FLIGHTS_META_PATH,
        help="航班元数据路径（默认：opensky_2024_PRC_dataset/flights/challenge_set.parquet）",
    )
    parser.add_argument(
        "--airports-meta-path",
        type=Path,
        default=DEFAULT_AIRPORTS_META_PATH,
        help="机场元数据路径（默认：opensky_2024_PRC_dataset/airports_tz.parquet）",
    )
    parser.add_argument(
        "--europe-continent",
        type=str,
        default=DEFAULT_EUROPE_CONTINENT,
        help="欧洲 continent 标记（默认：EU）",
    )
    parser.add_argument(
        "--flight-id-col",
        type=str,
        default=None,
        help="过滤时使用的航班 ID 列（默认自动：优先 original_flight_id）",
    )
    parser.add_argument("--date-from", type=str, default="2022-01-01", help="起始日期 YYYY-MM-DD（含）")
    parser.add_argument("--date-to", type=str, default="2022-02-28", help="结束日期 YYYY-MM-DD（含）")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(max(mp.cpu_count() - 2, 1), 28),
        help="并行进程数（默认：min(cpu-2, 8)）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000_000,
        help="pyarrow iter_batches 的 batch_size（默认：1,000,000）",
    )
    parser.add_argument(
        "--bin-width",
        action="append",
        default=[],
        help="覆盖直方图 bin 宽度：<col>:<width>（可重复）",
    )
    parser.add_argument(
        "--no-hist-plots",
        action="store_true",
        help="不输出 1D 直方图 PNG（仍会输出 hist_counts.csv）",
    )
    parser.add_argument(
        "--delta-hist",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否输出相邻点差值（delta）直方图（默认：开启）",
    )
    parser.add_argument(
        "--delta-required-dt-seconds",
        type=float,
        default=1.0,
        help="仅统计相邻点 timestamp 差值等于该秒数的 delta（默认：1.0；即严格 1 秒）",
    )
    parser.add_argument(
        "--delta-bin-width",
        action="append",
        default=[],
        help="覆盖 delta 直方图 bin 宽度：<col>:<width>（col 为原始列名，如 latitude；可重复）",
    )
    parser.add_argument(
        "--delta-max",
        action="append",
        default=[],
        help="覆盖 delta 直方图最大值：<col>:<max>（col 为原始列名；可重复）",
    )
    parser.add_argument(
        "--hist-yscales",
        type=str,
        default="linear,log",
        help="输出直方图 y 轴缩放，逗号分隔（可选：linear,log；默认：linear,log）",
    )
    parser.add_argument(
        "--hist-dpi",
        type=int,
        default=600,
        help="1D 直方图 PNG 的 DPI（默认：600）",
    )
    parser.add_argument(
        "--plot-xlim",
        action="append",
        default=[],
        help="覆盖直方图绘图 x 轴范围：<col>:<min>:<max>（可重复）",
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
        default="full",
        choices=["auto", "full", "bbox"],
        help="热力图范围选择：full=按数据 min/max；bbox=固定中国附近范围；auto=超大时回退 bbox（默认：full）",
    )
    parser.add_argument(
        "--heatmap-max-cells",
        type=int,
        default=60_000_000,
        help="热力图最大像素数上限（超过会自动增大 step；默认：60,000,000）",
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
    parser.add_argument(
        "--heatmap-mean-altitude",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否输出经纬-平均高度热力图（默认：开启）",
    )
    parser.add_argument(
        "--heatmap-alt-min",
        type=float,
        default=DEFAULT_PLOT_XLIMS["altitude"][0],
        help="经纬-高度热力图的高度下限（ft，默认与绘图裁剪一致）",
    )
    parser.add_argument(
        "--heatmap-alt-max",
        type=float,
        default=DEFAULT_PLOT_XLIMS["altitude"][1],
        help="经纬-高度热力图的高度上限（ft，默认与绘图裁剪一致）",
    )
    parser.add_argument(
        "--heatmap-alt-color-scale",
        type=str,
        default="linear",
        choices=["linear", "log", "eq_hist"],
        help="经纬-平均高度热力图颜色映射方式（默认：linear）",
    )
    parser.add_argument(
        "--heatmap-dynspread",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否对稀疏点做 dynspread 增强可见性（默认：开启）",
    )
    parser.add_argument(
        "--heatmap-dynspread-threshold",
        type=float,
        default=0.5,
        help="dynspread threshold（默认：0.5）",
    )
    parser.add_argument(
        "--heatmap-dynspread-max-px",
        type=int,
        default=3,
        help="dynspread max_px（默认：3）",
    )
    parser.add_argument(
        "--heatmap-dpi",
        type=int,
        default=5000,
        help="热力图 PNG 的 DPI（默认：5000）",
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

    if args.flight_id_col is not None and args.flight_id_col not in available_cols:
        raise RuntimeError(
            f"--flight-id-col 指定列不存在: {args.flight_id_col}（可用列：{sorted(available_cols)}）"
        )

    filter_enabled = args.flight_filter != "none"
    allowed_ids: Optional[np.ndarray] = None
    flight_id_col: Optional[str] = None
    if filter_enabled:
        if not args.flights_meta_path.exists():
            raise FileNotFoundError(f"航班元数据不存在: {args.flights_meta_path}")
        if not args.airports_meta_path.exists():
            raise FileNotFoundError(f"机场元数据不存在: {args.airports_meta_path}")
        if args.flight_id_col is not None:
            flight_id_col = args.flight_id_col
        elif "original_flight_id" in available_cols:
            flight_id_col = "original_flight_id"
        elif "flight_id" in available_cols:
            flight_id_col = "flight_id"
        else:
            raise RuntimeError(
                "启用 flight-filter 需要 flight_id/original_flight_id 列"
            )
        allowed_ids = _load_eu_flight_ids(
            args.flights_meta_path, args.airports_meta_path, args.europe_continent
        )
        if allowed_ids.size == 0:
            raise RuntimeError("flight-filter 结果为空，无法继续统计")

    bin_widths: Dict[str, float] = dict(DEFAULT_BIN_WIDTHS)
    for item in args.bin_width:
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError(f"--bin-width 格式错误: {item}（期望 <col>:<width>）")
        col, width_s = parts
        if col not in bin_widths:
            raise ValueError(
                f"--bin-width 不支持列: {col}（可选：{sorted(bin_widths.keys())}）"
            )
        width = float(width_s)
        if not (width > 0):
            raise ValueError(f"--bin-width 宽度必须为正数: {item}")
        bin_widths[col] = width

    columns = [c for c in bin_widths.keys() if c in available_cols]
    if not columns:
        raise RuntimeError(f"在 {files[0].name} 中未找到任何目标列（可用列：{sorted(available_cols)}）")

    label = args.label or data_dir.name
    if filter_enabled and args.label is None:
        label = f"{label}_{args.flight_filter}"
    range_tag = f"{args.date_from or 'all'}__{args.date_to or 'all'}"
    out_dir = args.out_root / label / range_tag
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] data_dir={data_dir}")
    print(f"[INFO] files={len(files)} (date_from={args.date_from}, date_to={args.date_to})")
    print(f"[INFO] columns={columns}")
    print(f"[INFO] workers={args.workers}, batch_size={args.batch_size}")
    print(f"[INFO] out_dir={out_dir}")
    if filter_enabled:
        print(
            "[INFO] flight_filter="
            f"{args.flight_filter}, flight_id_col={flight_id_col}, "
            f"allowed_ids={allowed_ids.size}"
        )

    if filter_enabled:
        scanned_files, total_rows_meta, meta_stats = _scan_column_min_max_filtered(
            files, columns, flight_id_col, allowed_ids, args.batch_size
        )
    else:
        scanned_files, total_rows_meta, meta_stats = _scan_column_min_max(files, columns)
    specs = _build_hist_specs(columns, bin_widths, meta_stats)

    delta_specs: List[DeltaHistogramSpec] = []
    required_dt_ns = int(round(args.delta_required_dt_seconds * 1e9))
    if args.delta_hist:
        delta_fid_col: Optional[str] = None
        if args.flight_id_col is not None:
            delta_fid_col = args.flight_id_col
        elif filter_enabled:
            delta_fid_col = flight_id_col
        elif "flight_id" in available_cols:
            delta_fid_col = "flight_id"
        elif "original_flight_id" in available_cols:
            delta_fid_col = "original_flight_id"
        if delta_fid_col is None:
            print("[WARN] 缺少 flight_id/original_flight_id，无法计算 delta-hist，已自动跳过")
        elif "timestamp" not in available_cols:
            print("[WARN] 缺少 timestamp，无法计算 delta-hist，已自动跳过")
        else:
            delta_specs = _build_delta_specs(
                available_cols, args.delta_bin_width, args.delta_max
            )
    else:
        delta_fid_col = None
    if delta_specs:
        print(f"[INFO] delta_hist_columns={[s.column for s in delta_specs]}")
        print(
            f"[INFO] delta_required_dt_seconds={args.delta_required_dt_seconds} (ns={required_dt_ns})"
        )
        print(f"[INFO] delta_flight_id_col={delta_fid_col}")

    chunks = _split_into_chunks(files, args.workers)
    print(f"[INFO] chunk_count={len(chunks)}")

    total_counts = [np.zeros(spec.bins, dtype=np.uint64) for spec in specs]
    total_valid = np.zeros(len(specs), dtype=np.int64)
    total_missing = np.zeros(len(specs), dtype=np.int64)
    total_sums = np.zeros(len(specs), dtype=np.float64)
    total_sumsq = np.zeros(len(specs), dtype=np.float64)
    total_oor = np.zeros(len(specs), dtype=np.int64)
    total_delta_counts = [np.zeros(spec.bins, dtype=np.uint64) for spec in delta_specs]
    total_delta_valid = np.zeros(len(delta_specs), dtype=np.int64)
    total_delta_missing = np.zeros(len(delta_specs), dtype=np.int64)
    total_delta_sums = np.zeros(len(delta_specs), dtype=np.float64)
    total_delta_sumsq = np.zeros(len(delta_specs), dtype=np.float64)
    total_delta_oor = np.zeros(len(delta_specs), dtype=np.int64)
    total_delta_pairs = 0
    total_rows = 0

    if len(chunks) == 1:
        result = _process_file_chunk(
            (
                chunks[0],
                specs,
                delta_specs,
                args.batch_size,
                required_dt_ns,
                allowed_ids,
                flight_id_col,
                delta_fid_col,
            )
        )
        total_rows += result.total_rows
        total_valid += result.valid
        total_missing += result.missing
        total_sums += result.sums
        total_sumsq += result.sumsq
        total_oor += result.out_of_range
        for idx in range(len(specs)):
            total_counts[idx] += result.counts[idx]
        if delta_specs:
            total_delta_valid += result.delta_valid
            total_delta_missing += result.delta_missing
            total_delta_sums += result.delta_sums
            total_delta_sumsq += result.delta_sumsq
            total_delta_oor += result.delta_out_of_range
            total_delta_pairs += int(result.delta_pairs_total)
            for idx in range(len(delta_specs)):
                total_delta_counts[idx] += result.delta_counts[idx]
    else:
        with ProcessPoolExecutor(max_workers=len(chunks)) as executor:
            futures = [
                executor.submit(
                    _process_file_chunk,
                    (
                        chunk,
                        specs,
                        delta_specs,
                        args.batch_size,
                        required_dt_ns,
                        allowed_ids,
                        flight_id_col,
                        delta_fid_col,
                    ),
                )
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
                if delta_specs:
                    total_delta_valid += result.delta_valid
                    total_delta_missing += result.delta_missing
                    total_delta_sums += result.delta_sums
                    total_delta_sumsq += result.delta_sumsq
                    total_delta_oor += result.delta_out_of_range
                    total_delta_pairs += int(result.delta_pairs_total)
                    for idx in range(len(delta_specs)):
                        total_delta_counts[idx] += result.delta_counts[idx]

    if total_rows != total_rows_meta:
        print(
            f"[WARN] total_rows(meta)={total_rows_meta}, total_rows(read)={total_rows}，两者不一致"
        )

    heatmap_config = None
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
        step_x, step_y, plot_w, plot_h, cells, scale = _adjust_heatmap_steps_for_max_cells(
            (lon_min, lon_max),
            (lat_min, lat_max),
            args.heatmap_lon_step,
            args.heatmap_lat_step,
            args.heatmap_max_cells,
        )
        heatmap_config = {
            "range_mode": range_mode_used,
            "lon_min": lon_min,
            "lon_max": lon_max,
            "lat_min": lat_min,
            "lat_max": lat_max,
            "lon_step_requested": args.heatmap_lon_step,
            "lat_step_requested": args.heatmap_lat_step,
            "lon_step_effective": step_x,
            "lat_step_effective": step_y,
            "plot_width": plot_w,
            "plot_height": plot_h,
            "cells": cells,
            "max_cells": args.heatmap_max_cells,
            "scale_from_requested": scale,
            "color_scale": args.heatmap_color_scale,
            "mean_altitude": args.heatmap_mean_altitude,
            "alt_min": args.heatmap_alt_min,
            "alt_max": args.heatmap_alt_max,
            "alt_color_scale": args.heatmap_alt_color_scale,
            "dynspread": args.heatmap_dynspread,
            "dynspread_threshold": args.heatmap_dynspread_threshold,
            "dynspread_max_px": args.heatmap_dynspread_max_px,
        }

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
        "bin_width_override": args.bin_width,
        "histograms": {
            spec.column: {
                "unit": UNITS.get(spec.column, ""),
                **asdict(spec),
                **asdict(meta_stats[spec.column]),
            }
            for spec in specs
        },
    }
    meta["flight_filter"] = {
        "mode": args.flight_filter,
        "flight_id_col": flight_id_col,
        "flights_meta_path": str(args.flights_meta_path) if filter_enabled else None,
        "airports_meta_path": str(args.airports_meta_path) if filter_enabled else None,
        "europe_continent": args.europe_continent if filter_enabled else None,
        "allowed_flight_ids": int(allowed_ids.size) if allowed_ids is not None else None,
    }
    if delta_specs:
        meta["delta_histograms"] = {
            spec.column: {
                "unit": UNITS.get(spec.column, ""),
                **asdict(spec),
                "required_dt_seconds": args.delta_required_dt_seconds,
                "required_dt_ns": required_dt_ns,
            }
            for spec in delta_specs
        }
        meta["delta_flight_id_col"] = delta_fid_col
        meta["delta_pairs_total"] = int(total_delta_pairs)
    meta["hist_plot"] = {
        "yscales": [s.strip() for s in args.hist_yscales.split(",") if s.strip()],
        "dpi": args.hist_dpi,
        "default_xlims": DEFAULT_PLOT_XLIMS,
        "xlims_override": args.plot_xlim,
    }
    if heatmap_config is not None:
        meta["heatmap_lat_lon"] = heatmap_config
        meta["heatmap_lat_lon"]["dpi"] = args.heatmap_dpi
    (out_dir / "hist_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    legacy_npz = out_dir / "hist_counts.npz"
    if legacy_npz.exists():
        legacy_npz.unlink()
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
    combined_specs: List[HistogramSpec] = list(specs)
    combined_counts: List[np.ndarray] = list(total_counts)
    if delta_specs:
        combined_specs.extend(
            [
                HistogramSpec(
                    column=s.column,
                    start=s.start,
                    width=s.width,
                    bins=s.bins,
                )
                for s in delta_specs
            ]
        )
        combined_counts.extend(list(total_delta_counts))
        delta_summary_path = out_dir / "delta_summary.csv"
        with delta_summary_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "column",
                    "source_column",
                    "unit",
                    "bin_width",
                    "start",
                    "bins",
                    "required_dt_seconds",
                    "pairs_total",
                    "valid",
                    "missing",
                    "mean",
                    "std",
                    "out_of_range",
                ]
            )
            for idx, spec in enumerate(delta_specs):
                v = int(total_delta_valid[idx])
                m = int(total_delta_missing[idx])
                oor = int(total_delta_oor[idx])
                mean = float(total_delta_sums[idx] / v) if v else float("nan")
                var = float(total_delta_sumsq[idx] / v - mean * mean) if v else float(
                    "nan"
                )
                std = float(math.sqrt(var)) if v and var >= 0 else float("nan")
                writer.writerow(
                    [
                        spec.column,
                        spec.source_column,
                        UNITS.get(spec.column, ""),
                        spec.width,
                        spec.start,
                        spec.bins,
                        args.delta_required_dt_seconds,
                        int(total_delta_pairs),
                        v,
                        m,
                        mean,
                        std,
                        oor,
                    ]
                )

    _write_hist_counts_csv(out_dir / "hist_counts.csv", combined_specs, combined_counts)

    if not args.no_hist_plots:
        yscales = [s.strip() for s in args.hist_yscales.split(",") if s.strip()]
        invalid = [s for s in yscales if s not in {"linear", "log"}]
        if invalid:
            raise ValueError(f"--hist-yscales 不支持: {invalid}（可选：linear,log）")

        xlims: Dict[str, Tuple[float, float]] = dict(DEFAULT_PLOT_XLIMS)
        for item in args.plot_xlim:
            parts = item.split(":")
            if len(parts) != 3:
                raise ValueError(f"--plot-xlim 格式错误: {item}（期望 <col>:<min>:<max>）")
            col, lo_s, hi_s = parts
            xlims[col] = (float(lo_s), float(hi_s))

        for yscale in yscales:
            plot_dir = out_dir / f"hist_y_{yscale}"
            _plot_histograms(
                plot_dir,
                combined_specs,
                combined_counts,
                yscale=yscale,
                xlims=xlims,
                dpi=args.hist_dpi,
            )
        for legacy in out_dir.glob("hist_*.png"):
            legacy.unlink()
        print("[INFO] 已生成 1D 直方图 PNG：hist_y_linear/ 与 hist_y_log/（根目录不再输出 hist_<col>.png）")

    if heatmap_config is not None:
        print(
            "[INFO] heatmap range "
            f"mode={heatmap_config['range_mode']}, "
            f"lon=[{heatmap_config['lon_min']},{heatmap_config['lon_max']}], "
            f"lat=[{heatmap_config['lat_min']},{heatmap_config['lat_max']}]"
        )
        if heatmap_config["cells"] > heatmap_config["max_cells"]:
            print(
                f"[WARN] heatmap cells={heatmap_config['cells']} 仍超过上限={heatmap_config['max_cells']}（将继续增大 step 或缩小范围）"
            )
        if heatmap_config["scale_from_requested"] > 1.0 + 1e-9:
            print(
                "[INFO] heatmap step 过细，已自动增大："
                f"({heatmap_config['lon_step_requested']},{heatmap_config['lat_step_requested']})"
                f" -> ({heatmap_config['lon_step_effective']:.6f},{heatmap_config['lat_step_effective']:.6f})"
                f" 以满足 max_cells={heatmap_config['max_cells']}（plot={heatmap_config['plot_width']}x{heatmap_config['plot_height']}）"
            )
        _render_lat_lon_heatmap(
            out_dir,
            files,
            lon_col="longitude",
            lat_col="latitude",
            alt_col="altitude" if "altitude" in available_cols else None,
            mean_altitude=heatmap_config["mean_altitude"],
            alt_min=heatmap_config["alt_min"],
            alt_max=heatmap_config["alt_max"],
            lon_range=(heatmap_config["lon_min"], heatmap_config["lon_max"]),
            lat_range=(heatmap_config["lat_min"], heatmap_config["lat_max"]),
            plot_width=heatmap_config["plot_width"],
            plot_height=heatmap_config["plot_height"],
            lon_step=float(heatmap_config["lon_step_effective"]),
            lat_step=float(heatmap_config["lat_step_effective"]),
            dpi=int(heatmap_config["dpi"]),
            color_scale=heatmap_config["color_scale"],
            mean_alt_color_scale=heatmap_config["alt_color_scale"],
            dynspread=heatmap_config["dynspread"],
            dynspread_threshold=heatmap_config["dynspread_threshold"],
            dynspread_max_px=heatmap_config["dynspread_max_px"],
            allowed_ids=allowed_ids,
            flight_id_col=flight_id_col,
        )
        print("[INFO] 已生成 2D 热力图 PNG：heatmap_lat_lon.png（matplotlib 版）")
        print("[INFO] 已生成 2D 热力图 PNG：heatmap_lat_lon_raw.png（datashader 裸图）")
        if heatmap_config["mean_altitude"] and "altitude" in available_cols:
            print("[INFO] 已生成经纬-平均高度热力图：heatmap_lat_lon_mean_altitude.png（matplotlib 版）")
            print("[INFO] 已生成经纬-平均高度热力图：heatmap_lat_lon_mean_altitude_raw.png（datashader 裸图）")
    elif not args.no_heatmap:
        print("[INFO] 数据中不存在 latitude/longitude，跳过 2D 热力图")

    print("[INFO] done (已生成 hist_meta.json / hist_counts.csv / summary.csv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
