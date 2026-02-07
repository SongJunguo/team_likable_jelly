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
import pyarrow as pa
import pyarrow.parquet as pq

DEFAULT_DATA_DIR = Path("opensky_2024_PRC_dataset/rawtrajectories")
# DEFAULT_DATA_DIR = Path("opensky_2024_PRC_dataset/xue_processed_raw__v1")
DEFAULT_FLIGHTS_META_PATH = Path(
    "opensky_2024_PRC_dataset/flights/challenge_set.parquet"
)
DEFAULT_AIRPORTS_META_PATH = Path("opensky_2024_PRC_dataset/airports_tz.parquet")
DEFAULT_EUROPE_CONTINENT = "EU"
NS_PER_SECOND = 1_000_000_000


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
    "daltitude": 25.0,
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
    "latitude": {"bin_width": 1e-6, "max": 0.005, "circular": False},
    "longitude": {"bin_width": 1e-6, "max": 0.006, "circular": False},
    "track": {"bin_width": 0.01, "max": 10.0, "circular": True},
    "altitude": {"bin_width": 1.0, "max": 250.0, "circular": False},
    "groundspeed": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "vertical_rate": {"bin_width": 0.1, "max": 200.0, "circular": False},
    "daltitude": {"bin_width": 1.0, "max": 2000.0, "circular": False},
    "gsx": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "gsy": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "tasx": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "tasy": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "tas": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "TAS": {"bin_width": 0.01, "max": 20.0, "circular": False},
    "wind": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "u_component_of_wind": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "v_component_of_wind": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "temperature": {"bin_width": 0.05, "max": 5.0, "circular": False},
    "specific_humidity": {"bin_width": 1e-4, "max": 0.01, "circular": False},
}
DELTA_ALL_EXCLUDED = {
    "timestamp",
    "flight_id",
    "original_flight_id",
    "icao24",
    "segment_index",
}

MOTION_COLUMNS = {
    "latitude",
    "longitude",
    "altitude",
    "groundspeed",
    "track",
    "vertical_rate",
    "daltitude",
    "gsx",
    "gsy",
    "tasx",
    "tasy",
    "tas",
    "TAS",
}

WEATHER_COLUMNS = {
    "u_component_of_wind",
    "v_component_of_wind",
    "wind",
    "temperature",
    "specific_humidity",
}

_CONTINENTS_GDF_CACHE: Optional[object] = None
_CONTINENTS_LOAD_FAILED = False
_COUNTRY_LABELS_WARNED = False


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
    sample_step_ns: Optional[int] = None,
) -> Tuple[int, int, Dict[str, ColumnMetaStats]]:
    total_rows = 0
    files_scanned = 0
    min_values: Dict[str, Optional[float]] = {c: None for c in columns}
    max_values: Dict[str, Optional[float]] = {c: None for c in columns}
    sample_enabled = sample_step_ns is not None

    for file_path in files:
        parquet = pq.ParquetFile(str(file_path))
        files_scanned += 1
        read_columns = [flight_id_col] + list(columns)
        if sample_enabled:
            read_columns.append("timestamp")
        for batch in parquet.iter_batches(columns=read_columns, batch_size=batch_size):
            fid = batch.column(0).to_numpy(zero_copy_only=False)
            if fid.size == 0:
                continue
            if fid.dtype.kind not in {"i", "u"}:
                fid = fid.astype(np.int64, copy=False)
            allowed_mask = np.isin(fid, allowed_ids)
            if not allowed_mask.any():
                continue
            sample_mask = None
            if sample_enabled:
                ts = batch.column(len(read_columns) - 1).to_numpy(zero_copy_only=False)
                ts = ts[allowed_mask]
                sample_mask = _compute_time_sampling_mask(ts, sample_step_ns)
                if sample_mask is not None and not sample_mask.any():
                    continue
                total_rows += int(sample_mask.sum())
            else:
                total_rows += int(allowed_mask.sum())
            for idx, col in enumerate(columns, start=1):
                arr = batch.column(idx).to_numpy(zero_copy_only=False)
                arr = arr[allowed_mask]
                if sample_mask is not None:
                    arr = arr[sample_mask]
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


def _scan_column_min_max_sampled(
    files: Sequence[Path],
    columns: Sequence[str],
    batch_size: int,
    sample_step_ns: int,
) -> Tuple[int, int, Dict[str, ColumnMetaStats]]:
    total_rows = 0
    files_scanned = 0
    min_values: Dict[str, Optional[float]] = {c: None for c in columns}
    max_values: Dict[str, Optional[float]] = {c: None for c in columns}
    read_columns = ["timestamp"] + list(columns)

    for file_path in files:
        parquet = pq.ParquetFile(str(file_path))
        files_scanned += 1
        for batch in parquet.iter_batches(columns=read_columns, batch_size=batch_size):
            ts = batch.column(0).to_numpy(zero_copy_only=False)
            sample_mask = _compute_time_sampling_mask(ts, sample_step_ns)
            if sample_mask is not None and not sample_mask.any():
                continue
            if sample_mask is None:
                raise RuntimeError("sample_mask 不应为空")
            total_rows += int(sample_mask.sum())
            for idx, col in enumerate(columns, start=1):
                arr = batch.column(idx).to_numpy(zero_copy_only=False)
                arr = arr[sample_mask]
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
        raise RuntimeError("抽样后无有效轨迹点，无法统计分布")

    out: Dict[str, ColumnMetaStats] = {}
    for col in columns:
        lo = min_values[col]
        hi = max_values[col]
        if lo is None or hi is None:
            raise RuntimeError(f"抽样后列 {col} 无有效数据，无法生成直方图")
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


def _infer_numeric_columns(schema: pa.Schema) -> List[str]:
    numeric: List[str] = []
    for field in schema:
        ftype = field.type
        if pa.types.is_integer(ftype) or pa.types.is_floating(ftype) or pa.types.is_decimal(
            ftype
        ):
            numeric.append(field.name)
    return numeric


def _parse_column_list(items: Sequence[str]) -> List[str]:
    cols: List[str] = []
    for item in items:
        for part in item.split(","):
            name = part.strip()
            if name:
                cols.append(name)
    return cols


def _parse_delta_overrides(items: Sequence[str], flag: str) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for item in items:
        parts = item.split(":")
        if len(parts) != 2:
            raise ValueError(f"{flag} 格式错误: {item}（期望 <col>:<value>）")
        col, value_s = parts
        if not col:
            raise ValueError(f"{flag} 列名为空: {item}")
        value = float(value_s)
        if not (value > 0):
            raise ValueError(f"{flag} 必须为正数: {item}")
        values[col] = value
    return values


def _resolve_plot_xlims(
    items: Sequence[str],
) -> Tuple[Dict[str, Tuple[float, float]], Dict[str, Tuple[float, float]]]:
    xlims: Dict[str, Tuple[float, float]] = dict(DEFAULT_PLOT_XLIMS)
    overrides: Dict[str, Tuple[float, float]] = {}
    for item in items:
        parts = item.split(":")
        if len(parts) != 3:
            raise ValueError(f"--plot-xlim 格式错误: {item}（期望 <col>:<min>:<max>）")
        col, lo_s, hi_s = parts
        lo = float(lo_s)
        hi = float(hi_s)
        if not (lo < hi):
            raise ValueError(f"--plot-xlim 非法范围: {item}（要求 min < max）")
        xlims[col] = (lo, hi)
        overrides[col] = (lo, hi)
    return xlims, overrides


def _compute_time_sampling_mask(
    ts: np.ndarray, sample_step_ns: Optional[int]
) -> Optional[np.ndarray]:
    if sample_step_ns is None:
        return None
    if ts.size == 0:
        return np.zeros(0, dtype=bool)
    ts_ns = ts.astype("datetime64[ns]").astype(np.int64, copy=False)
    nat_mask = ts_ns != np.iinfo(np.int64).min
    return nat_mask & ((ts_ns % sample_step_ns) == 0)


def _process_file_chunk(
    args: Tuple[
        List[str],
        List[HistogramSpec],
        List[DeltaHistogramSpec],
        int,
        int,
        Optional[int],
        Optional[np.ndarray],
        Optional[str],
        Optional[str],
        str,
    ]
) -> ChunkResult:
    (
        file_paths,
        specs,
        delta_specs,
        batch_size,
        required_dt_ns,
        sample_step_ns,
        allowed_ids,
        flight_id_col,
        delta_fid_col,
        delta_diff_mode,
    ) = args
    columns_hist = [spec.column for spec in specs]
    delta_enabled = bool(delta_specs)
    filter_enabled = allowed_ids is not None
    sample_enabled = sample_step_ns is not None
    delta_signed = delta_diff_mode == "signed"
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
        elif sample_enabled:
            read_columns.append("timestamp")
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
            sample_mask = None
            if sample_enabled:
                ts_for_sample = arrays["timestamp"]
                if allowed_mask is not None:
                    ts_for_sample = ts_for_sample[allowed_mask]
                sample_mask = _compute_time_sampling_mask(ts_for_sample, sample_step_ns)
                if sample_mask is not None and not sample_mask.any():
                    continue
            if allowed_mask is not None:
                total_rows += int(sample_mask.sum() if sample_mask is not None else allowed_mask.sum())
            else:
                sample_arr = arrays[columns_hist[0]] if columns_hist else arrays[delta_fid_col]
                total_rows += int(sample_mask.sum() if sample_mask is not None else sample_arr.size)

            for idx, spec in enumerate(specs):
                arr = arrays[spec.column]
                if allowed_mask is not None:
                    arr = arr[allowed_mask]
                if sample_mask is not None:
                    arr = arr[sample_mask]
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
                if sample_mask is not None:
                    fid = fid[sample_mask]
                    ts = ts[sample_mask]
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
                    if sample_mask is not None:
                        arr = arr[sample_mask]

                    val_prev = arr[:-1]
                    val_curr = arr[1:]
                    finite_pair = np.isfinite(val_prev) & np.isfinite(val_curr)
                    mask = base_mask & finite_pair
                    if not finite_pair.all():
                        delta_missing[d_idx] += int((base_mask & ~finite_pair).sum())

                    if mask.any():
                        if dspec.circular:
                            diff = val_curr[mask] - val_prev[mask]
                            if delta_signed:
                                delta = ((diff + 180.0) % 360.0) - 180.0
                            else:
                                delta = np.abs(((diff + 180.0) % 360.0) - 180.0)
                        else:
                            if delta_signed:
                                delta = val_curr[mask] - val_prev[mask]
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
                                if delta_signed:
                                    delta0 = ((diff + 180.0) % 360.0) - 180.0
                                else:
                                    delta0 = abs(((diff + 180.0) % 360.0) - 180.0)
                            else:
                                if delta_signed:
                                    delta0 = v_curr - v_prev
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


def _round_up_to_step(value: float, step: float) -> float:
    if not math.isfinite(value):
        return float("nan")
    if step <= 0:
        return value
    return math.ceil(value / step) * step


def _hist_quantile_from_counts(spec: HistogramSpec, counts: np.ndarray, q: float) -> float:
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"quantile 必须在 [0,1] 内，当前: {q}")
    total = int(np.sum(counts, dtype=np.int64))
    if total <= 0:
        return float("nan")
    target = q * float(total)
    if target <= 0:
        return float(spec.start)
    cum = np.cumsum(counts, dtype=np.int64)
    idx = int(np.searchsorted(cum, target, side="left"))
    idx = min(max(idx, 0), spec.bins - 1)
    left = spec.start + spec.width * idx
    prev = int(cum[idx - 1]) if idx > 0 else 0
    bin_count = int(counts[idx])
    if bin_count <= 0:
        return float(left)
    frac = (target - float(prev)) / float(bin_count)
    frac = min(max(frac, 0.0), 1.0)
    return float(left + frac * spec.width)


def _hist_abs_quantile_from_counts(spec: HistogramSpec, counts: np.ndarray, q: float) -> float:
    if not (0.0 <= q <= 1.0):
        raise ValueError(f"quantile 必须在 [0,1] 内，当前: {q}")
    total = int(np.sum(counts, dtype=np.int64))
    if total <= 0:
        return float("nan")
    centers = spec.start + (np.arange(spec.bins, dtype=np.float64) + 0.5) * spec.width
    abs_centers = np.abs(centers)
    order = np.argsort(abs_centers, kind="mergesort")
    sorted_abs = abs_centers[order]
    sorted_counts = counts[order].astype(np.int64, copy=False)
    target = q * float(total)
    if target <= 0:
        return float(sorted_abs[0])
    cum = np.cumsum(sorted_counts, dtype=np.int64)
    idx = int(np.searchsorted(cum, target, side="left"))
    idx = min(max(idx, 0), len(sorted_abs) - 1)
    return float(sorted_abs[idx])


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
        if spec.column.startswith("delta_"):
            out_name = f"delta_hist_{spec.column[len('delta_'):]}.png"
        else:
            out_name = f"hist_{spec.column}.png"
        fig.savefig(out_dir / out_name)
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


def _fallback_continents_polygons() -> List[List[Tuple[float, float]]]:
    # 简化大陆轮廓，仅用于背景提示。
    return [
        [(-168.0, 12.0), (-160.0, 50.0), (-140.0, 72.0), (-110.0, 70.0), (-90.0, 60.0),
         (-70.0, 50.0), (-50.0, 25.0), (-82.0, 12.0), (-120.0, 12.0), (-168.0, 12.0)],
        [(-82.0, 12.0), (-74.0, -5.0), (-70.0, -20.0), (-64.0, -35.0), (-58.0, -55.0),
         (-35.0, -55.0), (-35.0, -10.0), (-50.0, 5.0), (-70.0, 12.0), (-82.0, 12.0)],
        [(-20.0, 35.0), (10.0, 35.0), (40.0, 30.0), (50.0, 10.0), (45.0, -35.0),
         (10.0, -35.0), (-10.0, -10.0), (-20.0, 10.0), (-20.0, 35.0)],
        [(-10.0, 35.0), (10.0, 70.0), (40.0, 70.0), (40.0, 45.0), (30.0, 35.0),
         (10.0, 35.0), (-10.0, 35.0)],
        [(30.0, 5.0), (40.0, 20.0), (60.0, 55.0), (90.0, 70.0), (140.0, 60.0),
         (160.0, 45.0), (150.0, 5.0), (110.0, 0.0), (70.0, 0.0), (40.0, 5.0),
         (30.0, 5.0)],
        [(110.0, -10.0), (115.0, -40.0), (155.0, -40.0), (155.0, -10.0), (110.0, -10.0)],
        [(-180.0, -60.0), (-180.0, -90.0), (180.0, -90.0), (180.0, -60.0), (-180.0, -60.0)],
    ]


def _load_continents_geometry():
    global _CONTINENTS_GDF_CACHE, _CONTINENTS_LOAD_FAILED
    if _CONTINENTS_LOAD_FAILED:
        return None
    if _CONTINENTS_GDF_CACHE is not None:
        return _CONTINENTS_GDF_CACHE
    try:
        import geopandas as gpd
    except Exception as exc:
        print(f"[WARN] geopandas 不可用，使用内置简化轮廓：{exc}")
        _CONTINENTS_GDF_CACHE = _fallback_continents_polygons()
        return _CONTINENTS_GDF_CACHE
    base_dir = Path(__file__).resolve().parent
    shp_10m = base_dir / "ne_10m_admin_0_countries" / "ne_10m_admin_0_countries.shp"
    zip_10m = base_dir / "ne_10m_admin_0_countries.zip"
    shp_110m = base_dir / "ne_110m_admin_0_countries" / "ne_110m_admin_0_countries.shp"
    zip_110m = base_dir / "ne_110m_admin_0_countries.zip"

    candidates: List[Tuple[str, str]] = []
    if shp_10m.exists():
        candidates.append(("10m_shp", str(shp_10m)))
    if zip_10m.exists():
        candidates.append(
            ("10m_zip", f"zip://{zip_10m.resolve()}!ne_10m_admin_0_countries.shp")
        )
    if shp_110m.exists():
        candidates.append(("110m_shp", str(shp_110m)))
    if zip_110m.exists():
        candidates.append(
            ("110m_zip", f"zip://{zip_110m.resolve()}!ne_110m_admin_0_countries.shp")
        )

    for label, path in candidates:
        try:
            _CONTINENTS_GDF_CACHE = gpd.read_file(path)
            return _CONTINENTS_GDF_CACHE
        except Exception as exc:
            print(f"[WARN] 本地 {label} 读取失败，回退其他方案：{exc}")
    try:
        world_path = gpd.datasets.get_path("naturalearth_lowres")
    except Exception as exc:
        print(f"[WARN] naturalearth_lowres 不可用，使用内置简化轮廓：{exc}")
        _CONTINENTS_GDF_CACHE = _fallback_continents_polygons()
        return _CONTINENTS_GDF_CACHE
    try:
        _CONTINENTS_GDF_CACHE = gpd.read_file(world_path)
        return _CONTINENTS_GDF_CACHE
    except Exception as exc:  # pragma: no cover
        print(f"[WARN] 无法读取大洲背景数据，使用内置简化轮廓：{exc}")
        _CONTINENTS_GDF_CACHE = _fallback_continents_polygons()
        return _CONTINENTS_GDF_CACHE


def _add_continents_background(
    ax,
    lon_range: Tuple[float, float],
    lat_range: Tuple[float, float],
    alpha: float,
) -> None:
    if alpha <= 0:
        return
    geom = _load_continents_geometry()
    if geom is None:
        return

    lon_min, lon_max = lon_range
    lat_min, lat_max = lat_range
    if hasattr(geom, "plot"):
        try:
            from shapely.geometry import box
        except Exception as exc:  # pragma: no cover
            print(f"[WARN] 缺少 shapely，使用未裁剪轮廓：{exc}")
            clipped = geom
        else:
            bbox = box(lon_min, lat_min, lon_max, lat_max)
            try:
                clipped = geom[geom.geometry.intersects(bbox)].copy()
                clipped["geometry"] = clipped.geometry.intersection(bbox)
                clipped = clipped[~clipped.geometry.is_empty]
            except Exception:
                clipped = geom

        clipped.plot(
            ax=ax,
            color="black",
            alpha=alpha,
            edgecolor="black",
            linewidth=0.3,
            zorder=1,
            aspect="auto",
        )
    else:
        from matplotlib.patches import Polygon

        for poly in geom:
            patch = Polygon(
                poly,
                closed=True,
                facecolor="black",
                edgecolor="black",
                linewidth=0.3,
                alpha=alpha,
                zorder=1,
            )
            ax.add_patch(patch)

    ax.set_xlim(lon_min, lon_max)
    ax.set_ylim(lat_min, lat_max)
    ax.set_aspect("auto")


def _choose_country_label_field(columns: Iterable[str]) -> Optional[str]:
    preferred = [
        "NAME",
        "ADMIN",
        "NAME_EN",
        "NAME_LONG",
        "SOVEREIGNT",
        "FORMAL_EN",
        "NAME_LOCAL",
        "BRK_NAME",
        "NAME_SORT",
    ]
    for col in preferred:
        if col in columns:
            return col
    for col in columns:
        if "name" in col.lower():
            return col
    return None


def _add_country_labels(
    ax,
    lon_range: Tuple[float, float],
    lat_range: Tuple[float, float],
) -> None:
    global _COUNTRY_LABELS_WARNED
    geom = _load_continents_geometry()
    if geom is None or not hasattr(geom, "geometry") or not hasattr(geom, "columns"):
        if not _COUNTRY_LABELS_WARNED:
            print("[WARN] 当前背景无法标注国家名（缺少矢量国家数据）")
            _COUNTRY_LABELS_WARNED = True
        return

    label_col = _choose_country_label_field(geom.columns)
    if label_col is None:
        if not _COUNTRY_LABELS_WARNED:
            print("[WARN] 找不到国家名称字段，跳过国家名标注")
            _COUNTRY_LABELS_WARNED = True
        return

    try:
        from shapely.geometry import box
    except Exception as exc:  # pragma: no cover
        if not _COUNTRY_LABELS_WARNED:
            print(f"[WARN] 缺少 shapely，跳过国家名标注：{exc}")
            _COUNTRY_LABELS_WARNED = True
        return

    lon_min, lon_max = lon_range
    lat_min, lat_max = lat_range
    bbox = box(lon_min, lat_min, lon_max, lat_max)
    try:
        view = geom[geom.geometry.intersects(bbox)].copy()
    except Exception:
        view = geom

    if view.empty:
        return

    try:
        import matplotlib.patheffects as pe
    except Exception:
        pe = None

    for _, row in view.iterrows():
        name = row.get(label_col)
        if not isinstance(name, str) or not name.strip():
            continue
        geometry = row.geometry
        if geometry is None:
            continue
        try:
            point = geometry.representative_point()
        except Exception:
            try:
                point = geometry.centroid
            except Exception:
                continue
        if point is None:
            continue
        x, y = point.x, point.y
        if x < lon_min or x > lon_max or y < lat_min or y > lat_max:
            continue
        text = ax.text(
            x,
            y,
            name,
            fontsize=5,
            color="black",
            alpha=0.85,
            ha="center",
            va="center",
            zorder=5,
        )
        if pe is not None:
            text.set_path_effects([pe.withStroke(linewidth=1, foreground="white")])


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
    heatmap_background: str,
    heatmap_background_alpha: float,
    heatmap_country_labels: bool,
    sample_step_ns: Optional[int],
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
    if not (0.0 <= heatmap_background_alpha <= 1.0):
        raise ValueError(
            "heatmap-background-alpha 必须在 [0, 1] 范围内"
        )

    columns = [lon_col, lat_col]
    if sample_step_ns is not None:
        columns.append("timestamp")
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
    if sample_step_ns is not None:
        ts_ns = ddf["timestamp"].astype("int64")
        ddf = ddf[(ts_ns != np.iinfo(np.int64).min) & ((ts_ns % sample_step_ns) == 0)]
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
    if heatmap_background == "continents":
        _add_continents_background(
            ax,
            (lon_min, lon_max),
            (lat_min, lat_max),
            heatmap_background_alpha,
        )
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad((1.0, 1.0, 1.0, 0.0))
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
            zorder=2,
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
            zorder=4,
        )
    points = int(np.nansum(count_float))
    ax.set_title(
        f"Lon/Lat Density (step_lon={lon_step:.6f}°, step_lat={lat_step:.6f}°, points={points})"
    )
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    if heatmap_country_labels:
        _add_country_labels(ax, (lon_min, lon_max), (lat_min, lat_max))
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
        if heatmap_background == "continents":
            _add_continents_background(
                ax,
                (lon_min, lon_max),
                (lat_min, lat_max),
                heatmap_background_alpha,
            )
        cmap_alt = plt.get_cmap("viridis").copy()
        cmap_alt.set_bad((1.0, 1.0, 1.0, 0.0))
        norm_alt = Normalize(vmin=float(alt_min), vmax=float(alt_max))
        im = ax.imshow(
            mean_alt,
            origin=origin,
            extent=(lon_min, lon_max, lat_min, lat_max),
            cmap=cmap_alt,
            norm=norm_alt,
            aspect="auto",
            interpolation="nearest",
            zorder=2,
        )
        cbar = fig.colorbar(im, ax=ax, pad=0.02)
        cbar.set_label("Mean altitude (ft)")
        ax.set_title(
            f"Lon/Lat Mean Altitude (ft) (step_lon={lon_step:.6f}°, step_lat={lat_step:.6f}°, points={points_alt})"
        )
        ax.set_xlabel("Longitude (deg)")
        ax.set_ylabel("Latitude (deg)")
        if heatmap_country_labels:
            _add_country_labels(ax, (lon_min, lon_max), (lat_min, lat_max))
        fig.tight_layout()
        fig.savefig(out_dir / "heatmap_lat_lon_mean_altitude.png")
        plt.close(fig)


def _build_delta_specs(
    selected_columns: Sequence[str],
    available_cols: set[str],
    overrides_bin_width: Sequence[str],
    overrides_max: Sequence[str],
    diff_mode: str,
    require_overrides: bool,
) -> List[DeltaHistogramSpec]:
    if diff_mode not in {"abs", "signed"}:
        raise ValueError(f"不支持的 delta_diff_mode: {diff_mode}（可选：abs,signed）")
    delta_bin_widths = _parse_delta_overrides(overrides_bin_width, "--delta-bin-width")
    delta_max = _parse_delta_overrides(overrides_max, "--delta-max")

    selected = list(dict.fromkeys(selected_columns))
    if not selected:
        return []
    selected_set = set(selected)

    extra_width = sorted(set(delta_bin_widths.keys()) - selected_set)
    extra_max = sorted(set(delta_max.keys()) - selected_set)
    if extra_width:
        raise ValueError(f"--delta-bin-width 包含未选择的列: {extra_width}")
    if extra_max:
        raise ValueError(f"--delta-max 包含未选择的列: {extra_max}")

    signed = diff_mode == "signed"
    missing_width: List[str] = []
    missing_max: List[str] = []

    specs: List[DeltaHistogramSpec] = []
    for src in selected:
        if src not in available_cols:
            raise ValueError(f"delta 列不存在于数据中: {src}")
        cfg = DELTA_DEFAULTS.get(src, {})
        width = delta_bin_widths.get(src)
        max_v = delta_max.get(src)
        if width is None:
            if require_overrides:
                missing_width.append(src)
            elif "bin_width" in cfg:
                width = float(cfg["bin_width"])
            else:
                missing_width.append(src)
        if max_v is None:
            if require_overrides:
                missing_max.append(src)
            elif "max" in cfg:
                max_v = float(cfg["max"])
            else:
                missing_max.append(src)
        if width is None or max_v is None:
            continue
        width = float(width)
        max_v = float(max_v)
        if not (width > 0):
            raise ValueError(f"delta bin 宽度必须为正数: {src}={width}")
        if not (max_v > 0):
            raise ValueError(f"delta max 必须为正数: {src}={max_v}")
        if signed:
            start = -max_v
            bins = int(math.floor((2.0 * max_v) / width + 1e-12)) + 1
        else:
            start = 0.0
            bins = int(math.floor((max_v - 0.0) / width + 1e-12)) + 1
        bins = max(bins, 1)
        out_col = f"delta_{src}"
        UNITS[out_col] = UNITS.get(src, "")
        specs.append(
            DeltaHistogramSpec(
                column=out_col,
                source_column=src,
                start=start,
                width=width,
                bins=bins,
                circular=bool(cfg.get("circular", False)),
                max_value=max_v,
            )
        )
    if require_overrides:
        if missing_width:
            raise ValueError(
                "缺少 --delta-bin-width: "
                f"{sorted(missing_width)}（已选 delta 列需要显式指定）"
            )
        if missing_max:
            raise ValueError(
                "缺少 --delta-max: "
                f"{sorted(missing_max)}（已选 delta 列需要显式指定）"
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
        "--sample-step-seconds",
        type=float,
        default=1.0,
        help=(
            "时间抽样步长（秒）。默认 1（不抽样）；>1 时仅保留 "
            "timestamp 落在该步长网格上的点（例如 20=约每20秒1点）"
        ),
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
        "--delta-columns",
        action="append",
        default=[],
        help=(
            "指定参与 delta 直方图的列（逗号分隔或可重复），"
            "使用 all 表示所有数值列（默认：所有数值列，排除 ID/索引列）"
        ),
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
        help=(
            "delta 直方图 bin 宽度：<col>:<width>（col 为原始列名，如 latitude；可重复；"
            "当使用 --delta-columns 时需为每列显式提供）"
        ),
    )
    parser.add_argument(
        "--delta-max",
        action="append",
        default=[],
        help=(
            "delta 直方图最大值：<col>:<max>（col 为原始列名；可重复；"
            "当使用 --delta-columns 时需为每列显式提供）"
        ),
    )
    parser.add_argument(
        "--delta-diff-mode",
        type=str,
        default="abs",
        choices=["abs", "signed"],
        help="delta 差值计算方式：abs=绝对值，signed=保留正负（默认：abs）",
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
        default=30_000_000,
        help="热力图最大像素数上限（超过会自动增大 step；默认：60,000,000）",
    )
    parser.add_argument("--heatmap-lon-min", type=float, default=None)
    parser.add_argument("--heatmap-lon-max", type=float, default=None)
    parser.add_argument("--heatmap-lat-min", type=float, default=None)
    parser.add_argument("--heatmap-lat-max", type=float, default=None)
    parser.add_argument(
        "--heatmap-background",
        type=str,
        default="continents",
        choices=["none", "continents"],
        help="热力图背景：none=不画，continents=大洲轮廓（默认：continents）",
    )
    parser.add_argument(
        "--heatmap-background-alpha",
        type=float,
        default=0.12,
        help="大洲背景遮罩透明度（默认：0.12）",
    )
    parser.add_argument(
        "--heatmap-country-labels",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="是否在热力图上标注国家名（默认：开启）",
    )
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
        default=1000,
        help="热力图 PNG 的 DPI（默认：1000）",
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
    numeric_cols = _infer_numeric_columns(parquet0.schema_arrow)

    if args.sample_step_seconds < 1.0:
        raise ValueError("--sample-step-seconds 必须 >= 1")
    sample_step_ns: Optional[int] = None
    if args.sample_step_seconds > 1.0 + 1e-12:
        sample_step_ns = int(round(args.sample_step_seconds * NS_PER_SECOND))
        if sample_step_ns <= 0:
            raise ValueError("--sample-step-seconds 非法，换算纳秒后必须为正数")
        if "timestamp" not in available_cols:
            raise RuntimeError("启用时间抽样需要 timestamp 列")

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
    if sample_step_ns is not None:
        print(
            "[INFO] time_sampling="
            f"enabled(step_seconds={args.sample_step_seconds}, step_ns={sample_step_ns}, rule=timestamp_ns%step_ns==0)"
        )
    if filter_enabled:
        print(
            "[INFO] flight_filter="
            f"{args.flight_filter}, flight_id_col={flight_id_col}, "
            f"allowed_ids={allowed_ids.size}"
        )

    if filter_enabled:
        scanned_files, total_rows_meta, meta_stats = _scan_column_min_max_filtered(
            files, columns, flight_id_col, allowed_ids, args.batch_size, sample_step_ns
        )
    elif sample_step_ns is not None:
        scanned_files, total_rows_meta, meta_stats = _scan_column_min_max_sampled(
            files, columns, args.batch_size, sample_step_ns
        )
    else:
        scanned_files, total_rows_meta, meta_stats = _scan_column_min_max(files, columns)
    specs = _build_hist_specs(columns, bin_widths, meta_stats)

    delta_specs: List[DeltaHistogramSpec] = []
    delta_required_dt_seconds_effective = args.delta_required_dt_seconds
    if sample_step_ns is not None and math.isclose(args.delta_required_dt_seconds, 1.0):
        delta_required_dt_seconds_effective = args.sample_step_seconds
        print(
            "[INFO] 检测到时间抽样且 delta-required-dt-seconds 使用默认值 1，"
            f"已自动调整为 {delta_required_dt_seconds_effective}"
        )
    required_dt_ns = int(round(delta_required_dt_seconds_effective * NS_PER_SECOND))
    if args.delta_hist:
        delta_columns_requested = _parse_column_list(args.delta_columns)
        numeric_set = set(numeric_cols)
        if delta_columns_requested:
            requested = list(dict.fromkeys(delta_columns_requested))
            if "all" in requested:
                if len(requested) > 1:
                    raise ValueError("--delta-columns all 不能与其他列同时使用")
                selected_delta_cols = [
                    c for c in numeric_cols if c not in DELTA_ALL_EXCLUDED
                ]
            else:
                selected_delta_cols = requested
            if not selected_delta_cols:
                raise RuntimeError("delta-columns 为空，无法计算 delta-hist")
            non_numeric = [c for c in selected_delta_cols if c not in numeric_set]
            if non_numeric:
                raise ValueError(f"--delta-columns 包含非数值列: {non_numeric}")
            delta_require_overrides = True
        else:
            selected_delta_cols = [
                c for c in numeric_cols if c not in DELTA_ALL_EXCLUDED
            ]
            delta_require_overrides = False

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
                selected_delta_cols,
                available_cols,
                args.delta_bin_width,
                args.delta_max,
                args.delta_diff_mode,
                delta_require_overrides,
            )
    else:
        delta_fid_col = None
    if delta_specs:
        print(f"[INFO] delta_hist_columns={[s.column for s in delta_specs]}")
        print(
            f"[INFO] delta_required_dt_seconds={delta_required_dt_seconds_effective} (ns={required_dt_ns})"
        )
        print(f"[INFO] delta_diff_mode={args.delta_diff_mode}")
        print(f"[INFO] delta_flight_id_col={delta_fid_col}")
        print(
            "[INFO] effective delta-max: "
            + ", ".join(f"{s.source_column}:{s.max_value:g}" for s in delta_specs)
        )

    effective_xlims: Dict[str, Tuple[float, float]] = dict(DEFAULT_PLOT_XLIMS)
    plot_xlim_overrides: Dict[str, Tuple[float, float]] = {}
    if not args.no_hist_plots:
        effective_xlims, plot_xlim_overrides = _resolve_plot_xlims(args.plot_xlim)
        if plot_xlim_overrides:
            print(
                "[INFO] effective plot-xlim override: "
                + ", ".join(
                    f"{k}:{v[0]:g}:{v[1]:g}" for k, v in sorted(plot_xlim_overrides.items())
                )
            )

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
                sample_step_ns,
                allowed_ids,
                flight_id_col,
                delta_fid_col,
                args.delta_diff_mode,
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
                        sample_step_ns,
                        allowed_ids,
                        flight_id_col,
                        delta_fid_col,
                        args.delta_diff_mode,
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
            "background": args.heatmap_background,
            "background_alpha": args.heatmap_background_alpha,
            "country_labels": args.heatmap_country_labels,
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
        "sample_step_seconds": args.sample_step_seconds,
        "sample_step_ns": sample_step_ns,
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
                "diff_mode": args.delta_diff_mode,
                "required_dt_seconds": delta_required_dt_seconds_effective,
                "required_dt_ns": required_dt_ns,
            }
            for spec in delta_specs
        }
        meta["delta_flight_id_col"] = delta_fid_col
        meta["delta_pairs_total"] = int(total_delta_pairs)
        meta["delta_diff_mode"] = args.delta_diff_mode
        meta["delta_required_dt_seconds_requested"] = args.delta_required_dt_seconds
        meta["delta_required_dt_seconds_effective"] = delta_required_dt_seconds_effective
        meta["delta_config_effective"] = {
            "bin_width": {s.source_column: float(s.width) for s in delta_specs},
            "max_value": {s.source_column: float(s.max_value) for s in delta_specs},
        }
    meta["hist_plot"] = {
        "yscales": [s.strip() for s in args.hist_yscales.split(",") if s.strip()],
        "dpi": args.hist_dpi,
        "default_xlims": DEFAULT_PLOT_XLIMS,
        "xlims_override_raw": args.plot_xlim,
        "xlims_override_effective": {
            k: [float(v[0]), float(v[1])] for k, v in sorted(plot_xlim_overrides.items())
        },
        "xlims_effective": {
            k: [float(v[0]), float(v[1])] for k, v in sorted(effective_xlims.items())
        },
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
        delta_analysis_rows: List[Dict[str, float]] = []
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
                    "out_of_range_ratio",
                    "in_range_ratio",
                    "p99",
                    "p99_9",
                    "abs_p99",
                    "abs_p99_9",
                    "recommended_delta_max",
                    "recommended_delta_max_conservative",
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
                pair_base = int(v + m + oor)
                if pair_base <= 0:
                    pair_base = int(total_delta_pairs)
                out_of_range_ratio = (
                    float(oor / pair_base) if pair_base > 0 else float("nan")
                )
                in_range_ratio = float(v / pair_base) if pair_base > 0 else float("nan")
                hspec = HistogramSpec(
                    column=spec.column,
                    start=spec.start,
                    width=spec.width,
                    bins=spec.bins,
                )
                p99 = _hist_quantile_from_counts(hspec, total_delta_counts[idx], 0.99)
                p99_9 = _hist_quantile_from_counts(hspec, total_delta_counts[idx], 0.999)
                abs_p99 = _hist_abs_quantile_from_counts(
                    hspec, total_delta_counts[idx], 0.99
                )
                abs_p99_9 = _hist_abs_quantile_from_counts(
                    hspec, total_delta_counts[idx], 0.999
                )
                rec_max = _round_up_to_step(abs_p99_9 * 1.10, spec.width)
                rec_max_conservative = _round_up_to_step(abs_p99_9 * 1.25, spec.width)
                delta_analysis_rows.append(
                    {
                        "column": spec.column,
                        "source_column": spec.source_column,
                        "out_of_range_ratio": out_of_range_ratio,
                        "p99": p99,
                        "p99_9": p99_9,
                        "abs_p99": abs_p99,
                        "abs_p99_9": abs_p99_9,
                        "recommended_delta_max": rec_max,
                        "recommended_delta_max_conservative": rec_max_conservative,
                    }
                )
                writer.writerow(
                    [
                        spec.column,
                        spec.source_column,
                        UNITS.get(spec.column, ""),
                        spec.width,
                        spec.start,
                        spec.bins,
                        delta_required_dt_seconds_effective,
                        int(total_delta_pairs),
                        v,
                        m,
                        mean,
                        std,
                        oor,
                        out_of_range_ratio,
                        in_range_ratio,
                        p99,
                        p99_9,
                        abs_p99,
                        abs_p99_9,
                        rec_max,
                        rec_max_conservative,
                    ]
                )
        delta_recommend_path = out_dir / "delta_recommendations.csv"
        with delta_recommend_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "column",
                    "source_column",
                    "out_of_range_ratio",
                    "p99",
                    "p99_9",
                    "abs_p99",
                    "abs_p99_9",
                    "recommended_delta_max",
                    "recommended_delta_max_conservative",
                ]
            )
            for row in sorted(
                delta_analysis_rows,
                key=lambda r: float(r["out_of_range_ratio"]),
                reverse=True,
            ):
                writer.writerow(
                    [
                        row["column"],
                        row["source_column"],
                        row["out_of_range_ratio"],
                        row["p99"],
                        row["p99_9"],
                        row["abs_p99"],
                        row["abs_p99_9"],
                        row["recommended_delta_max"],
                        row["recommended_delta_max_conservative"],
                    ]
                )
        print("[INFO] delta 分析已输出: delta_summary.csv / delta_recommendations.csv")
        if delta_analysis_rows:
            print("[INFO] delta 截断率 Top10（按 out_of_range_ratio 降序）:")
            for row in sorted(
                delta_analysis_rows,
                key=lambda r: float(r["out_of_range_ratio"]),
                reverse=True,
            )[:10]:
                print(
                    "  "
                    f"{row['column']}: "
                    f"oor_ratio={row['out_of_range_ratio']:.6f}, "
                    f"p99={row['p99']:.6g}, p99.9={row['p99_9']:.6g}, "
                    f"rec_max={row['recommended_delta_max']:.6g}"
                )

    _write_hist_counts_csv(out_dir / "hist_counts.csv", combined_specs, combined_counts)

    if not args.no_hist_plots:
        delta_source_by_col = {s.column: s.source_column for s in delta_specs}
        motion_specs: List[HistogramSpec] = []
        motion_counts: List[np.ndarray] = []
        weather_specs: List[HistogramSpec] = []
        weather_counts: List[np.ndarray] = []
        unknown_cols: set[str] = set()
        for spec, counts in zip(combined_specs, combined_counts):
            base_col = delta_source_by_col.get(spec.column, spec.column)
            if base_col in WEATHER_COLUMNS:
                weather_specs.append(spec)
                weather_counts.append(counts)
            else:
                if base_col not in MOTION_COLUMNS and base_col not in WEATHER_COLUMNS:
                    unknown_cols.add(base_col)
                motion_specs.append(spec)
                motion_counts.append(counts)
        if unknown_cols:
            print(
                "[WARN] 未归类列默认归入 motion："
                f"{sorted(unknown_cols)}"
            )

        yscales = [s.strip() for s in args.hist_yscales.split(",") if s.strip()]
        invalid = [s for s in yscales if s not in {"linear", "log"}]
        if invalid:
            raise ValueError(f"--hist-yscales 不支持: {invalid}（可选：linear,log）")

        for yscale in yscales:
            if motion_specs:
                plot_dir = out_dir / "motion" / f"hist_y_{yscale}"
                _plot_histograms(
                    plot_dir,
                    motion_specs,
                    motion_counts,
                    yscale=yscale,
                    xlims=effective_xlims,
                    dpi=args.hist_dpi,
                )
            if weather_specs:
                plot_dir = out_dir / "weather" / f"hist_y_{yscale}"
                _plot_histograms(
                    plot_dir,
                    weather_specs,
                    weather_counts,
                    yscale=yscale,
                    xlims=effective_xlims,
                    dpi=args.hist_dpi,
                )
        for legacy in out_dir.glob("hist_*.png"):
            legacy.unlink()
        print(
            "[INFO] 已生成 1D 直方图 PNG：motion/hist_y_*/ 与 weather/hist_y_*/（根目录不再输出 hist_<col>.png）"
        )

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
            heatmap_background=heatmap_config["background"],
            heatmap_background_alpha=heatmap_config["background_alpha"],
            heatmap_country_labels=heatmap_config["country_labels"],
            sample_step_ns=sample_step_ns,
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

    done_files = "hist_meta.json / hist_counts.csv / summary.csv"
    if delta_specs:
        done_files += " / delta_summary.csv / delta_recommendations.csv"
    print(f"[INFO] done (已生成 {done_files})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
