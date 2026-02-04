#!/usr/bin/env python3
"""
可视化某个航班的完整轨迹：每个数值列一页，包含原始值与相邻点差分。
"""
from __future__ import annotations

import argparse
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

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

EXCLUDE_COLUMNS = {
    "timestamp",
    "flight_id",
    "original_flight_id",
    "icao24",
    "segment_index",
}

CIRCULAR_COLUMNS = {"track"}

DEFAULT_DATA_DIR = Path("opensky_2024_PRC_dataset/interpolated_clean_eu_v5")


def _extract_date_yyyy_mm_dd(file_name: str) -> Optional[str]:
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


def _load_flight_from_file(
    args: Tuple[str, List[str], str, int, int]
) -> Optional[Dict[str, np.ndarray]]:
    file_path_str, columns, flight_id_col, flight_id, batch_size = args
    parquet = pq.ParquetFile(file_path_str)
    read_columns = [flight_id_col, "timestamp"] + list(columns)
    read_columns = sorted(set(read_columns))
    col_to_idx = {col: idx for idx, col in enumerate(read_columns)}

    buffers: Dict[str, List[np.ndarray]] = {"timestamp": []}
    for col in columns:
        buffers[col] = []

    for batch in parquet.iter_batches(columns=read_columns, batch_size=batch_size):
        fid = batch.column(col_to_idx[flight_id_col]).to_numpy(zero_copy_only=False)
        if fid.size == 0:
            continue
        if fid.dtype.kind not in {"i", "u"}:
            fid = fid.astype(np.int64, copy=False)
        mask = fid == flight_id
        if not mask.any():
            continue
        ts = batch.column(col_to_idx["timestamp"]).to_numpy(zero_copy_only=False)
        buffers["timestamp"].append(ts[mask])
        for col in columns:
            arr = batch.column(col_to_idx[col]).to_numpy(zero_copy_only=False)
            buffers[col].append(arr[mask])

    if not buffers["timestamp"]:
        return None

    result: Dict[str, np.ndarray] = {}
    result["timestamp"] = np.concatenate(buffers["timestamp"])
    for col in columns:
        if buffers[col]:
            result[col] = np.concatenate(buffers[col]).astype(np.float64, copy=False)
        else:
            result[col] = np.array([], dtype=np.float64)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="可视化某航班的完整轨迹（PDF）")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--flight-id", type=int, required=True, help="flight_id 数值")
    parser.add_argument(
        "--flight-id-col",
        type=str,
        default=None,
        help="flight_id 列名（默认自动：优先 original_flight_id）",
    )
    parser.add_argument("--date-from", type=str, default=None)
    parser.add_argument("--date-to", type=str, default=None)
    parser.add_argument(
        "--columns",
        action="append",
        default=[],
        help="指定列（可重复或逗号分隔；默认：所有数值列）",
    )
    parser.add_argument(
        "--delta-required-dt-seconds",
        type=float,
        default=1.0,
        help="差分仅统计 dt=该秒数的相邻点（默认：1.0）",
    )
    parser.add_argument(
        "--delta-diff-mode",
        type=str,
        default="signed",
        choices=["abs", "signed"],
        help="差分模式：abs 或 signed（默认：signed）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="输出 PDF 路径（默认：reports/trajectory_visualization/<flight>_<range>.pdf）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=min(max(mp.cpu_count() - 2, 1), 28),
        help="并行进程数（默认：min(cpu-2, 28)）",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1_000_000,
        help="pyarrow iter_batches 的 batch_size（默认：1,000,000）",
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

    if args.flight_id_col is not None:
        if args.flight_id_col not in available_cols:
            raise RuntimeError(
                f"--flight-id-col 指定列不存在: {args.flight_id_col}（可用列：{sorted(available_cols)}）"
            )
        flight_id_col = args.flight_id_col
    elif "original_flight_id" in available_cols:
        flight_id_col = "original_flight_id"
    elif "flight_id" in available_cols:
        flight_id_col = "flight_id"
    else:
        raise RuntimeError("缺少 flight_id/original_flight_id 列，无法继续")

    requested_cols = _parse_column_list(args.columns)
    if requested_cols:
        columns = list(dict.fromkeys(requested_cols))
    else:
        columns = [c for c in numeric_cols if c not in EXCLUDE_COLUMNS]
    if not columns:
        raise RuntimeError("未选择任何列")

    non_numeric = [c for c in columns if c not in set(numeric_cols)]
    if non_numeric:
        raise ValueError(f"包含非数值列: {non_numeric}")
    missing = [c for c in columns if c not in available_cols]
    if missing:
        raise ValueError(f"列不存在: {missing}")

    chunks = files
    print(f"[INFO] files={len(chunks)}")
    print(f"[INFO] flight_id={args.flight_id}, flight_id_col={flight_id_col}")
    print(f"[INFO] columns={columns}")

    data_buffers: Dict[str, List[np.ndarray]] = {"timestamp": []}
    for col in columns:
        data_buffers[col] = []

    if args.workers <= 1:
        for file_path in chunks:
            result = _load_flight_from_file(
                (str(file_path), columns, flight_id_col, args.flight_id, args.batch_size)
            )
            if result is None:
                continue
            data_buffers["timestamp"].append(result["timestamp"])
            for col in columns:
                data_buffers[col].append(result[col])
    else:
        with ProcessPoolExecutor(max_workers=min(args.workers, len(chunks))) as executor:
            futures = [
                executor.submit(
                    _load_flight_from_file,
                    (str(fp), columns, flight_id_col, args.flight_id, args.batch_size),
                )
                for fp in chunks
            ]
            for future in as_completed(futures):
                result = future.result()
                if result is None:
                    continue
                data_buffers["timestamp"].append(result["timestamp"])
                for col in columns:
                    data_buffers[col].append(result[col])

    if not data_buffers["timestamp"]:
        raise RuntimeError("未找到该 flight_id 的数据")

    ts = np.concatenate(data_buffers["timestamp"])
    order = np.argsort(ts)
    ts = ts[order]
    series: Dict[str, np.ndarray] = {}
    for col in columns:
        arr = np.concatenate(data_buffers[col])
        series[col] = arr[order]

    required_dt_ns = int(round(args.delta_required_dt_seconds * 1e9))
    diff_mode = args.delta_diff_mode

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    range_tag = f"{args.date_from or 'all'}__{args.date_to or 'all'}"
    out_path = (
        args.out
        if args.out is not None
        else Path("reports/trajectory_visualization")
        / f"flight_{args.flight_id}_{range_tag}.pdf"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dt_ns = (ts[1:] - ts[:-1]).astype("timedelta64[ns]").astype(np.int64)
    base_mask = dt_ns == required_dt_ns

    with PdfPages(out_path) as pdf:
        for col in columns:
            values = series[col].astype(np.float64, copy=False)
            val_prev = values[:-1]
            val_curr = values[1:]
            finite_pair = np.isfinite(val_prev) & np.isfinite(val_curr)
            mask = base_mask & finite_pair

            if mask.any():
                diff = val_curr[mask] - val_prev[mask]
                if col in CIRCULAR_COLUMNS:
                    diff = ((diff + 180.0) % 360.0) - 180.0
                if diff_mode == "abs":
                    diff = np.abs(diff)
                diff_ts = ts[1:][mask]
            else:
                diff = np.array([], dtype=np.float64)
                diff_ts = np.array([], dtype=ts.dtype)

            fig, axes = plt.subplots(2, 1, figsize=(11, 7), dpi=120, sharex=True)
            axes[0].plot(ts, values, linewidth=0.6)
            axes[0].set_title(f"{col} ({UNITS.get(col, '')})")
            axes[0].set_ylabel("value")
            axes[0].grid(True, linestyle="--", alpha=0.3)

            if diff.size:
                axes[1].plot(diff_ts, diff, linewidth=0.6, color="#C44E52")
                axes[1].set_ylabel("delta")
            else:
                axes[1].text(0.5, 0.5, "no delta (dt=1s) pairs", ha="center", va="center")
            axes[1].set_xlabel("timestamp")
            axes[1].grid(True, linestyle="--", alpha=0.3)

            fig.suptitle(
                f"flight_id={args.flight_id}  dt={args.delta_required_dt_seconds}s  mode={diff_mode}",
                fontsize=10,
            )
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

    print(f"[INFO] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
