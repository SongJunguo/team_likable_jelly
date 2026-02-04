#!/usr/bin/env python3
"""
扫描相邻点（dt=1s 且同一 flight_id）差分的最小/最大间隔，用于估计 delta bin/max。
"""
from __future__ import annotations

import argparse
import math
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import numpy.typing as npt
import pyarrow as pa
import pyarrow.parquet as pq

EXCLUDE_DEFAULT = {
    "timestamp",
    "flight_id",
    "original_flight_id",
    "icao24",
    "segment_index",
}
CIRCULAR_COLUMNS = {"track"}


@dataclass
class DeltaAgg:
    min_signed: float
    max_signed: float
    min_abs_nonzero: float
    max_abs: float
    count: int


@dataclass
class ReservoirSample:
    values: List[float]
    seen: int


def _init_stats(columns: Sequence[str]) -> Dict[str, DeltaAgg]:
    return {
        c: DeltaAgg(
            min_signed=math.inf,
            max_signed=-math.inf,
            min_abs_nonzero=math.inf,
            max_abs=0.0,
            count=0,
        )
        for c in columns
    }


def _update_stats(stats: DeltaAgg, delta: np.ndarray) -> None:
    if delta.size == 0:
        return
    stats.count += int(delta.size)
    dmin = float(delta.min())
    dmax = float(delta.max())
    if dmin < stats.min_signed:
        stats.min_signed = dmin
    if dmax > stats.max_signed:
        stats.max_signed = dmax

    abs_delta = np.abs(delta)
    max_abs = float(abs_delta.max())
    if max_abs > stats.max_abs:
        stats.max_abs = max_abs
    nonzero = abs_delta[abs_delta > 0]
    if nonzero.size:
        min_abs = float(nonzero.min())
        if min_abs < stats.min_abs_nonzero:
            stats.min_abs_nonzero = min_abs


def _update_reservoir(
    sample: ReservoirSample, values: npt.NDArray[np.float64], rng: np.random.Generator, k: int
) -> None:
    if k <= 0:
        return
    for v in values:
        sample.seen += 1
        if len(sample.values) < k:
            sample.values.append(float(v))
        else:
            j = int(rng.integers(0, sample.seen))
            if j < k:
                sample.values[j] = float(v)


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


def _split_into_chunks(items: Sequence[Path], chunks: int) -> List[List[str]]:
    chunks = max(1, min(chunks, len(items)))
    result: List[List[str]] = [[] for _ in range(chunks)]
    for idx, path in enumerate(items):
        result[idx % chunks].append(str(path))
    return [c for c in result if c]


def _process_chunk(
    args: Tuple[List[str], List[str], str, int, int, set[str], int, int]
) -> Tuple[Dict[str, DeltaAgg], Optional[Dict[str, ReservoirSample]]]:
    (
        file_paths,
        columns,
        flight_id_col,
        required_dt_ns,
        batch_size,
        circular_cols,
        sample_size,
        seed,
    ) = args
    stats = _init_stats(columns)
    samples: Optional[Dict[str, ReservoirSample]] = None
    if sample_size > 0:
        samples = {c: ReservoirSample(values=[], seen=0) for c in columns}
        rng = np.random.default_rng(seed)
    else:
        rng = None

    for file_path_str in file_paths:
        parquet = pq.ParquetFile(file_path_str)
        read_columns = [flight_id_col, "timestamp"] + list(columns)
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
            fid = arrays[flight_id_col]
            ts = arrays["timestamp"]
            if fid.size == 0 or ts.size == 0:
                continue
            if fid.dtype.kind not in {"i", "u"}:
                fid = fid.astype(np.int64, copy=False)

            fid_prev = fid[:-1]
            fid_curr = fid[1:]
            ts_prev = ts[:-1]
            ts_curr = ts[1:]
            dt_ns = (ts_curr - ts_prev).astype("timedelta64[ns]").astype(np.int64)
            base_mask = (fid_curr == fid_prev) & (dt_ns == required_dt_ns)

            cross_mask = False
            if last_fid is not None and last_ts is not None and fid.size > 0:
                dt0 = (ts[0] - last_ts).astype("timedelta64[ns]").astype(np.int64)
                cross_mask = bool(fid[0] == last_fid and dt0 == required_dt_ns)

            for col in columns:
                arr = arrays[col].astype(np.float64, copy=False)
                if arr.size == 0:
                    continue
                val_prev = arr[:-1]
                val_curr = arr[1:]
                finite_pair = np.isfinite(val_prev) & np.isfinite(val_curr)
                mask = base_mask & finite_pair
                if mask.any():
                    delta = val_curr[mask] - val_prev[mask]
                    if col in circular_cols:
                        delta = ((delta + 180.0) % 360.0) - 180.0
                    _update_stats(stats[col], delta)
                    if samples is not None:
                        abs_delta = np.abs(delta)
                        _update_reservoir(
                            samples[col],
                            abs_delta,
                            rng,
                            sample_size,
                        )

                if cross_mask:
                    v_prev = float(last_values.get(col, float("nan")))
                    v_curr = float(arr[0])
                    if math.isfinite(v_prev) and math.isfinite(v_curr):
                        delta0 = v_curr - v_prev
                        if col in circular_cols:
                            delta0 = ((delta0 + 180.0) % 360.0) - 180.0
                        _update_stats(stats[col], np.array([delta0], dtype=np.float64))
                        if samples is not None:
                            _update_reservoir(
                                samples[col],
                                np.array([abs(delta0)], dtype=np.float64),
                                rng,
                                sample_size,
                            )

                last_values[col] = float(arr[-1])

            last_fid = fid[-1]
            last_ts = ts[-1]

    return stats, samples


def _merge_stats(base: Dict[str, DeltaAgg], other: Dict[str, DeltaAgg]) -> None:
    for col, o in other.items():
        b = base[col]
        if o.count == 0:
            continue
        b.count += o.count
        if o.min_signed < b.min_signed:
            b.min_signed = o.min_signed
        if o.max_signed > b.max_signed:
            b.max_signed = o.max_signed
        if o.max_abs > b.max_abs:
            b.max_abs = o.max_abs
        if o.min_abs_nonzero < b.min_abs_nonzero:
            b.min_abs_nonzero = o.min_abs_nonzero


def _merge_samples(
    samples_list: List[Dict[str, ReservoirSample]],
    columns: Sequence[str],
    sample_size: int,
    seed: int,
) -> Dict[str, ReservoirSample]:
    merged: Dict[str, ReservoirSample] = {
        c: ReservoirSample(values=[], seen=0) for c in columns
    }
    for samples in samples_list:
        for col in columns:
            s = samples[col]
            merged[col].seen += s.seen
            merged[col].values.extend(s.values)

    if sample_size > 0:
        rng = np.random.default_rng(seed)
        for col in columns:
            values = merged[col].values
            if len(values) > sample_size:
                idx = rng.choice(len(values), size=sample_size, replace=False)
                merged[col].values = [values[i] for i in idx]
    return merged


def _parse_quantiles(text: str) -> List[float]:
    if not text or text.lower() in {"none", "null"}:
        return []
    values: List[float] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        q = float(part)
        if not (0.0 < q < 1.0):
            raise ValueError(f"quantile 必须在 (0,1) 内: {q}")
        values.append(q)
    return sorted(set(values))


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描 delta 差分区间（min/max）")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("opensky_2024_PRC_dataset/interpolated_clean_eu_v5"),
        help="包含 *.parquet 的目录",
    )
    parser.add_argument("--date-from", type=str, default=None)
    parser.add_argument("--date-to", type=str, default=None)
    parser.add_argument(
        "--flight-id-col",
        type=str,
        default=None,
        help="flight_id 列名（默认自动：优先 original_flight_id）",
    )
    parser.add_argument(
        "--delta-required-dt-seconds",
        type=float,
        default=1.0,
        help="仅统计相邻点 timestamp 差值等于该秒数的 delta（默认：1.0）",
    )
    parser.add_argument(
        "--columns",
        action="append",
        default=[],
        help="指定列（可重复或逗号分隔；默认：所有数值列，排除 ID/索引列）",
    )
    parser.add_argument(
        "--quantiles",
        type=str,
        default="0.95,0.99,0.995,0.999,0.9999",
        help="输出 |delta| 分位数（逗号分隔；设为 none 可关闭）",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=2_000_000,
        help="每列 |delta| 抽样上限（默认：2,000,000；0 表示不抽样）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20240204,
        help="抽样随机种子（默认：20240204）",
    )
    parser.add_argument(
        "--quantiles-out",
        type=Path,
        default=Path("test_python/delta_scan/delta_quantiles.csv"),
        help="分位数输出 CSV 路径",
    )
    parser.add_argument(
        "--plot-pdf",
        action="store_true",
        help="生成 |delta| 分布可视化 PDF",
    )
    parser.add_argument(
        "--pdf-out",
        type=Path,
        default=Path("test_python/delta_scan/delta_abs_dist.pdf"),
        help="PDF 输出路径",
    )
    parser.add_argument(
        "--hist-bins",
        type=int,
        default=200,
        help="PDF 直方图 bins（默认：200）",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("test_python/delta_scan/delta_interval_stats.csv"),
        help="输出 CSV 路径",
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
        raise RuntimeError("缺少 flight_id/original_flight_id 列，无法计算 delta")

    requested: List[str] = []
    for item in args.columns:
        for part in item.split(","):
            name = part.strip()
            if name:
                requested.append(name)

    if requested:
        columns = list(dict.fromkeys(requested))
    else:
        columns = [c for c in numeric_cols if c not in EXCLUDE_DEFAULT]

    if not columns:
        raise RuntimeError("列为空，无法计算")

    non_numeric = [c for c in columns if c not in set(numeric_cols)]
    if non_numeric:
        raise ValueError(f"包含非数值列: {non_numeric}")
    missing = [c for c in columns if c not in available_cols]
    if missing:
        raise ValueError(f"列不存在: {missing}")

    required_dt_ns = int(round(args.delta_required_dt_seconds * 1e9))
    quantiles = _parse_quantiles(args.quantiles)
    quantile_enabled = bool(quantiles)
    plot_enabled = bool(args.plot_pdf)
    sample_size = int(max(args.sample_size, 0))
    if (quantile_enabled or plot_enabled) and sample_size <= 0:
        raise ValueError("--sample-size 必须 > 0 才能计算分位数或生成 PDF")

    approx_sampling = (quantile_enabled or plot_enabled) and args.workers > 1

    chunks = _split_into_chunks(files, args.workers)

    print(f"[INFO] files={len(files)} chunk_count={len(chunks)}")
    print(f"[INFO] columns={columns}")
    print(f"[INFO] required_dt_seconds={args.delta_required_dt_seconds}")
    if approx_sampling:
        print(
            "[WARN] 分位数/可视化使用多进程近似抽样（每进程抽样后合并），结果为近似分位数"
        )

    total_stats = _init_stats(columns)
    samples: Optional[Dict[str, ReservoirSample]] = None
    if len(chunks) == 1:
        result_stats, result_samples = _process_chunk(
            (
                chunks[0],
                columns,
                flight_id_col,
                required_dt_ns,
                args.batch_size,
                CIRCULAR_COLUMNS,
                sample_size if (quantile_enabled or plot_enabled) else 0,
                args.seed,
            )
        )
        _merge_stats(total_stats, result_stats)
        samples = result_samples
    else:
        per_worker_sample = 0
        if quantile_enabled or plot_enabled:
            per_worker_sample = max(1, math.ceil(sample_size / len(chunks)))
        samples_list: List[Dict[str, ReservoirSample]] = []
        with ProcessPoolExecutor(max_workers=len(chunks)) as executor:
            futures = []
            for idx, chunk in enumerate(chunks):
                futures.append(
                    executor.submit(
                        _process_chunk,
                        (
                            chunk,
                            columns,
                            flight_id_col,
                            required_dt_ns,
                            args.batch_size,
                            CIRCULAR_COLUMNS,
                            per_worker_sample if (quantile_enabled or plot_enabled) else 0,
                            args.seed + idx,
                        ),
                    )
                )
            for future in as_completed(futures):
                result_stats, result_samples = future.result()
                _merge_stats(total_stats, result_stats)
                if result_samples is not None:
                    samples_list.append(result_samples)
        if quantile_enabled or plot_enabled:
            if not samples_list:
                raise RuntimeError("未生成样本，无法计算分位数/绘图")
            samples = _merge_samples(samples_list, columns, sample_size, args.seed)

    out_path: Path = args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        f.write(
            "column,count,min_signed,max_signed,min_abs_nonzero,max_abs\n"
        )
        for col in columns:
            s = total_stats[col]
            min_signed = s.min_signed if math.isfinite(s.min_signed) else float("nan")
            max_signed = s.max_signed if math.isfinite(s.max_signed) else float("nan")
            min_abs_nonzero = (
                s.min_abs_nonzero if math.isfinite(s.min_abs_nonzero) else float("nan")
            )
            f.write(
                f"{col},{s.count},{min_signed},{max_signed},{min_abs_nonzero},{s.max_abs}\n"
            )

    print(f"[INFO] wrote {out_path}")

    if quantile_enabled or plot_enabled:
        if samples is None:
            raise RuntimeError("未生成样本，无法计算分位数/绘图")
        q_out = args.quantiles_out
        q_out.parent.mkdir(parents=True, exist_ok=True)
        with q_out.open("w", encoding="utf-8") as f:
            f.write("column,count,sample_size,quantile,value\n")
            for col in columns:
                s = samples[col]
                if not s.values:
                    continue
                arr = np.array(s.values, dtype=np.float64)
                qs = np.quantile(arr, quantiles)
                for q, v in zip(quantiles, qs):
                    f.write(f"{col},{s.seen},{len(s.values)},{q},{float(v)}\n")
        print(f"[INFO] wrote {q_out}")

        if plot_enabled:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages

            pdf_path = args.pdf_out
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            with PdfPages(pdf_path) as pdf:
                for col in columns:
                    s = samples[col]
                    if not s.values:
                        continue
                    arr = np.array(s.values, dtype=np.float64)
                    qs = np.quantile(arr, quantiles) if quantiles else []

                    fig, axes = plt.subplots(2, 1, figsize=(11, 7), dpi=120)
                    axes[0].hist(arr, bins=args.hist_bins, color="#4C72B0", alpha=0.8)
                    axes[0].set_title(f"|delta| histogram: {col} (sample={len(arr)})")
                    axes[0].set_ylabel("count")
                    axes[0].grid(True, linestyle="--", alpha=0.3)

                    sorted_arr = np.sort(arr)
                    cdf = np.linspace(0, 1, len(sorted_arr), endpoint=False)
                    axes[1].plot(sorted_arr, cdf, color="#55A868", linewidth=1.0)
                    axes[1].set_title(f"|delta| CDF: {col}")
                    axes[1].set_xlabel("|delta|")
                    axes[1].set_ylabel("cdf")
                    axes[1].grid(True, linestyle="--", alpha=0.3)

                    for qv in qs:
                        axes[0].axvline(qv, color="#C44E52", linewidth=0.8, alpha=0.8)
                        axes[1].axvline(qv, color="#C44E52", linewidth=0.8, alpha=0.8)

                    fig.tight_layout()
                    pdf.savefig(fig)
                    plt.close(fig)
            print(f"[INFO] wrote {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
