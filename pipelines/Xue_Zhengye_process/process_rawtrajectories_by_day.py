# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from concurrent.futures import ProcessPoolExecutor
from functools import partial
import multiprocessing as mp

from .flight_processor_core import setup_logging, worker_process_flight
from pipelines.common import meta_filters


FINAL_COLUMNS = [
    "timestamp",
    "flight_id",
    "latitude",
    "longitude",
    "altitude",
    "TAS",
    "track",
    "adep",
    "ades",
    "aircraft_type",
    "adep_latitude_deg",
    "adep_longitude_deg",
    "ades_latitude_deg",
    "ades_longitude_deg",
]


@dataclass(frozen=True)
class DayPointStats:
    day: str
    raw_rows: int | None
    out_rows: int | None
    raw_gb: float | None
    out_gb: float | None
    ratio_out_raw: float | None
    ratio_out_raw_size: float | None
    status: str
    message: str


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_stats_csv = repo_root / "reports" / "xue_processed_raw__v1" / "xue_process_point_stats.csv"

    parser = argparse.ArgumentParser(description="薛正烨方案：rawtrajectories 按天处理 + 合并 challenge_set 元数据")

    parser.add_argument(
        "--raw_dir",
        default="opensky_2024_PRC_dataset/rawtrajectories",
        help="原始轨迹目录（按天 parquet）",
    )
    parser.add_argument(
        "--out_dir",
        default="opensky_2024_PRC_dataset/xue_processed_raw__v1",
        help="输出目录（按天 xue_<date>.parquet）",
    )
    parser.add_argument(
        "--flights_parquet",
        default="opensky_2024_PRC_dataset/flights/challenge_set.parquet",
        help="航班元数据（challenge_set.parquet）",
    )
    parser.add_argument(
        "--airports_parquet",
        default="opensky_2024_PRC_dataset/airports_tz.parquet",
        help="机场信息（用于补充 adep/ades 经纬度）",
    )
    parser.add_argument(
        "--europe_only",
        "--europe-only",
        action="store_true",
        help="仅保留起降都在欧洲的航班（可选）",
    )
    parser.add_argument(
        "--top_airports",
        "--top-airports",
        type=int,
        default=0,
        help="按机场出现次数 Top-N 筛选（adep+ades 合并统计，可选）",
    )
    parser.add_argument(
        "--top_aircraft",
        "--top-aircraft",
        type=int,
        default=0,
        help="按机型出现次数 Top-N 筛选（可选）",
    )
    parser.add_argument(
        "--include_submission",
        "--include-submission",
        action="store_true",
        help="合并 submission_set.parquet 参与统计（可选）",
    )
    parser.add_argument(
        "--include_final",
        "--include-final",
        action="store_true",
        help="合并 final_submission_set.parquet 参与统计（可选）",
    )
    parser.add_argument(
        "--europe_continent",
        "--europe-continent",
        default=meta_filters.DEFAULT_EUROPE_CONTINENT,
        help="Europe 大洲编码（默认 EU）",
    )
    parser.add_argument(
        "--meta_procs",
        "--meta-procs",
        type=int,
        default=4,
        help="元数据读取并发数（仅多源时生效）",
    )

    parser.add_argument("--from", dest="date_from", default="", help="起始日期 YYYY-MM-DD（留空=自动）")
    parser.add_argument("--to", dest="date_to", default="", help="截止日期 YYYY-MM-DD（留空=自动）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在输出文件")
    parser.add_argument("--dry_run", action="store_true", help="只打印将处理的文件，不实际处理/写盘")
    parser.add_argument("--limit_days", type=int, default=0, help="仅处理前 N 天（测试用）")
    parser.add_argument("--limit_flights", type=int, default=0, help="每个日文件仅处理前 N 条航迹（测试用）")
    parser.add_argument(
        "--stats_csv",
        default=default_stats_csv.as_posix(),
        help="点数统计输出 CSV（默认写入 reports/xue_processed_raw__v1/）",
    )

    # 算法参数（沿用 legacy 脚本参数名/含义）
    parser.add_argument("--resample_freq", default="1s", help="重采样频率")
    parser.add_argument("--min_len", type=int, default=792, help="最小有效长度（点数）")
    parser.add_argument("--gaussian_sigma", type=float, default=2.0, help="平滑 sigma")
    parser.add_argument("--h_min", type=float, default=-1000.0)
    parser.add_argument("--h_max", type=float, default=42000.0)
    parser.add_argument("--vr_min", type=float, default=-6000.0)
    parser.add_argument("--vr_max", type=float, default=6000.0)
    parser.add_argument("--gs_min", type=float, default=50.0)
    parser.add_argument("--gs_max", type=float, default=600.0)
    parser.add_argument("--alt_fusion_weight", type=float, default=0.60)

    # 并行与写盘
    parser.add_argument("--max_workers", type=int, default=14, help="并行进程数")
    parser.add_argument("--flush_rows", type=int, default=2_000_000, help="累计到多少行就写盘一次（降内存）")
    parser.add_argument("--start_method", default="spawn", choices=["spawn", "fork", "forkserver"])
    parser.add_argument("--log_level", default="INFO")

    return parser.parse_args()


def _parquet_num_rows(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(pq.ParquetFile(path).metadata.num_rows)
    except Exception as exc:  # noqa: BLE001
        logging.warning("读取 parquet 行数失败: %s (%s)", path, exc)
        return None


def _file_size_bytes(path: Path) -> int | None:
    try:
        return int(path.stat().st_size) if path.exists() else None
    except Exception as exc:  # noqa: BLE001
        logging.warning("读取文件大小失败: %s (%s)", path, exc)
        return None


def _file_size_gb(path: Path) -> float | None:
    size_bytes = _file_size_bytes(path)
    if size_bytes is None:
        return None
    return float(size_bytes) / 1_000_000_000


def _list_day_strings(raw_dir: Path) -> list[str]:
    files = sorted(raw_dir.glob("2022-*.parquet"))
    return [f.stem for f in files]


def _filter_dates(days: list[str], date_from: str, date_to: str) -> list[str]:
    if date_from:
        days = [d for d in days if d >= date_from]
    if date_to:
        days = [d for d in days if d <= date_to]
    return days


def _load_flights_meta(
    flights_parquet: Path,
    airports_parquet: Path,
    *,
    europe_only: bool = False,
    top_airports: int = 0,
    top_aircraft: int = 0,
    include_submission: bool = False,
    include_final: bool = False,
    europe_continent: str = meta_filters.DEFAULT_EUROPE_CONTINENT,
    meta_procs: int = 4,
) -> pd.DataFrame:
    sources = meta_filters.build_flights_sources(
        flights_parquet,
        include_submission=include_submission,
        include_final=include_final,
    )
    flights = meta_filters.load_flights_meta(sources, procs=meta_procs)
    airports = meta_filters.load_airports_table(
        airports_parquet,
        columns=["icao_code", "continent", "latitude_deg", "longitude_deg"],
    )

    if europe_only or top_airports or top_aircraft:
        flights, stats = meta_filters.apply_filters(
            flights,
            airports,
            europe_only=europe_only,
            top_airports=top_airports,
            top_aircraft=top_aircraft,
            europe_continent=europe_continent,
            drop_unknown=True,
        )
        meta_filters.log_stats(stats, logger=logging.getLogger(__name__))

    airports_adep = airports.rename(
        columns={
            "icao_code": "adep",
            "latitude_deg": "adep_latitude_deg",
            "longitude_deg": "adep_longitude_deg",
        }
    )
    airports_ades = airports.rename(
        columns={
            "icao_code": "ades",
            "latitude_deg": "ades_latitude_deg",
            "longitude_deg": "ades_longitude_deg",
        }
    )

    flights = flights.merge(airports_adep, on="adep", how="left")
    flights = flights.merge(airports_ades, on="ades", how="left")

    miss_adep = int(flights["adep_latitude_deg"].isna().sum())
    miss_ades = int(flights["ades_latitude_deg"].isna().sum())
    if miss_adep or miss_ades:
        logging.warning(
            "机场坐标缺失：adep=%s, ades=%s（将以 NaN 输出）",
            miss_adep,
            miss_ades,
        )

    return flights.set_index("flight_id")


def _flush_to_parquet(
    buffer: list[pd.DataFrame],
    writer: pq.ParquetWriter | None,
    tmp_path: Path,
    flights_meta: pd.DataFrame,
) -> tuple[pq.ParquetWriter | None, int]:
    if not buffer:
        return writer, 0

    chunk = pd.concat(buffer, ignore_index=True)
    chunk["flight_id"] = chunk["flight_id"].astype(np.int64)
    chunk = chunk.join(flights_meta, on="flight_id", how="left")

    for col in FINAL_COLUMNS:
        if col not in chunk.columns:
            chunk[col] = pd.NA
    chunk = chunk[FINAL_COLUMNS]

    table = pa.Table.from_pandas(chunk, preserve_index=False)
    if writer is None:
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        writer = pq.ParquetWriter(tmp_path.as_posix(), table.schema, compression="zstd")
    writer.write_table(table)
    return writer, int(table.num_rows)


def process_one_day(
    day: str,
    in_path: Path,
    out_path: Path,
    flights_meta: pd.DataFrame,
    args: argparse.Namespace,
) -> DayPointStats:
    raw_rows = _parquet_num_rows(in_path)
    raw_gb = _file_size_gb(in_path)
    if out_path.exists() and not args.force:
        logging.info("↪︎ 跳过已存在: %s", out_path)
        out_rows = _parquet_num_rows(out_path)
        out_gb = _file_size_gb(out_path)
        ratio_out_raw = (out_rows / raw_rows) if (out_rows is not None and raw_rows) else None
        ratio_out_raw_size = (out_gb / raw_gb) if (out_gb is not None and raw_gb) else None
        logging.info(
            "统计 %s（跳过）: raw_rows=%s, out_rows=%s, out/raw=%s, raw_gb=%s, out_gb=%s, out_gb/raw_gb=%s",
            day,
            raw_rows,
            out_rows,
            f"{ratio_out_raw:.6f}" if ratio_out_raw is not None else "NA",
            f"{raw_gb:.6f}" if raw_gb is not None else "NA",
            f"{out_gb:.6f}" if out_gb is not None else "NA",
            f"{ratio_out_raw_size:.6f}" if ratio_out_raw_size is not None else "NA",
        )
        return DayPointStats(
            day=day,
            raw_rows=raw_rows,
            out_rows=out_rows,
            raw_gb=raw_gb,
            out_gb=out_gb,
            ratio_out_raw=ratio_out_raw,
            ratio_out_raw_size=ratio_out_raw_size,
            status="skipped",
            message="输出已存在，未覆盖",
        )

    if args.dry_run:
        logging.info("DRYRUN: %s -> %s", in_path, out_path)
        return DayPointStats(
            day=day,
            raw_rows=raw_rows,
            out_rows=None,
            raw_gb=raw_gb,
            out_gb=None,
            ratio_out_raw=None,
            ratio_out_raw_size=None,
            status="dry-run",
            message="仅打印，不处理/写盘",
        )

    if not in_path.exists():
        logging.warning("缺失日文件：%s", in_path)
        return DayPointStats(
            day=day,
            raw_rows=None,
            out_rows=None,
            raw_gb=None,
            out_gb=None,
            ratio_out_raw=None,
            ratio_out_raw_size=None,
            status="missing",
            message="输入日文件缺失",
        )

    logging.info("读取 %s ...", in_path)
    cols = [
        "flight_id",
        "timestamp",
        "latitude",
        "longitude",
        "altitude",
        "groundspeed",
        "track",
        "vertical_rate",
        "u_component_of_wind",
        "v_component_of_wind",
    ]
    df = pd.read_parquet(in_path, columns=cols, engine="pyarrow")
    df["flight_id"] = df["flight_id"].astype(np.int64)

    challenge_ids = flights_meta.index
    before_rows = len(df)
    raw_rows = before_rows if raw_rows is None else raw_rows
    df = df[df["flight_id"].isin(challenge_ids)].copy()
    logging.info("challenge_set 过滤：%s -> %s 行", before_rows, len(df))
    if df.empty:
        logging.warning("该日无 challenge_set 航迹：%s", day)
        return DayPointStats(
            day=day,
            raw_rows=raw_rows,
            out_rows=0,
            raw_gb=raw_gb,
            out_gb=0.0,
            ratio_out_raw=0.0 if raw_rows else None,
            ratio_out_raw_size=0.0 if raw_gb else None,
            status="empty",
            message="challenge_set 过滤后为空",
        )

    # 内存优化
    f32_cols = [
        "latitude",
        "longitude",
        "altitude",
        "groundspeed",
        "track",
        "vertical_rate",
        "u_component_of_wind",
        "v_component_of_wind",
    ]
    for c in f32_cols:
        if c in df.columns:
            df[c] = df[c].astype("float32")

    df["flight_id"] = df["flight_id"].astype("category")
    total = int(df["flight_id"].nunique())
    if args.limit_flights and args.limit_flights > 0:
        keep_ids = df["flight_id"].cat.categories[: args.limit_flights]
        df = df[df["flight_id"].isin(keep_ids)].copy()
        total = int(df["flight_id"].nunique())
        logging.warning("测试模式：仅处理前 %s 条航迹", total)

    logging.info("开始处理 %s 条航迹（max_workers=%s）", total, args.max_workers)

    flight_groups = df.groupby("flight_id", observed=True)
    chunksize = max(1, total // (args.max_workers * 4))

    ctx = mp.get_context(args.start_method)
    worker = partial(worker_process_flight, config=args)

    tmp_path = out_path.with_suffix(out_path.suffix + f".tmp_{uuid.uuid4().hex}")
    writer: pq.ParquetWriter | None = None
    buffer: list[pd.DataFrame] = []
    buffer_rows = 0
    out_rows = 0
    kept = 0

    try:
        with ProcessPoolExecutor(max_workers=args.max_workers, mp_context=ctx) as executor:
            for i, res in enumerate(executor.map(worker, flight_groups, chunksize=chunksize), start=1):
                if res is None or res.empty:
                    continue
                buffer.append(res)
                buffer_rows += len(res)
                kept += 1

                if buffer_rows >= args.flush_rows:
                    writer, wrote = _flush_to_parquet(buffer, writer, tmp_path, flights_meta)
                    out_rows += wrote
                    buffer.clear()
                    buffer_rows = 0

                if i % 2000 == 0:
                    logging.info("进度: %s/%s（已保留 %s 条）", i, total, kept)

        if buffer:
            writer, wrote = _flush_to_parquet(buffer, writer, tmp_path, flights_meta)
            out_rows += wrote
            buffer.clear()

        if writer is None:
            logging.warning("该日没有数据保留下来：%s", day)
            ratio_out_raw = (out_rows / raw_rows) if raw_rows else None
            ratio_out_raw_size = 0.0 if raw_gb else None
            logging.info(
                "统计 %s（无输出）: raw_rows=%s, out_rows=%s, out/raw=%s, raw_gb=%s, out_gb=%s, out_gb/raw_gb=%s",
                day,
                raw_rows,
                out_rows,
                f"{ratio_out_raw:.6f}" if ratio_out_raw is not None else "NA",
                f"{raw_gb:.6f}" if raw_gb is not None else "NA",
                "0.000000",
                f"{ratio_out_raw_size:.6f}" if ratio_out_raw_size is not None else "NA",
            )
            return DayPointStats(
                day=day,
                raw_rows=raw_rows,
                out_rows=0,
                raw_gb=raw_gb,
                out_gb=0.0,
                ratio_out_raw=0.0 if raw_rows else None,
                ratio_out_raw_size=ratio_out_raw_size,
                status="empty",
                message="无任何航迹通过过滤/处理",
            )

        writer.close()
        writer = None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_path, out_path)
        logging.info("✅ 完成: %s", out_path)

        out_gb = _file_size_gb(out_path)
        ratio_out_raw = (out_rows / raw_rows) if raw_rows else None
        ratio_out_raw_size = (out_gb / raw_gb) if (out_gb is not None and raw_gb) else None
        logging.info(
            "统计 %s: raw_rows=%s, out_rows=%s, out/raw=%s, raw_gb=%s, out_gb=%s, out_gb/raw_gb=%s",
            day,
            raw_rows,
            out_rows,
            f"{ratio_out_raw:.6f}" if ratio_out_raw is not None else "NA",
            f"{raw_gb:.6f}" if raw_gb is not None else "NA",
            f"{out_gb:.6f}" if out_gb is not None else "NA",
            f"{ratio_out_raw_size:.6f}" if ratio_out_raw_size is not None else "NA",
        )
        return DayPointStats(
            day=day,
            raw_rows=raw_rows,
            out_rows=out_rows,
            raw_gb=raw_gb,
            out_gb=out_gb,
            ratio_out_raw=ratio_out_raw,
            ratio_out_raw_size=ratio_out_raw_size,
            status="processed",
            message="ok",
        )
    finally:
        if writer is not None:
            writer.close()
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def main() -> int:
    args = parse_args()

    setup_logging(args.log_level)

    log_path = Path(args.out_dir).resolve() / "xue_process.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(getattr(logging, str(args.log_level).upper(), logging.INFO))
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s - [%(levelname)s] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logging.getLogger().addHandler(file_handler)

    raw_dir = Path(args.raw_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    flights_parquet = Path(args.flights_parquet).resolve()
    airports_parquet = Path(args.airports_parquet).resolve()

    if not raw_dir.is_dir():
        logging.error("raw_dir 不存在：%s", raw_dir)
        return 2
    if not flights_parquet.is_file():
        logging.error("flights_parquet 不存在：%s", flights_parquet)
        return 2
    if not airports_parquet.is_file():
        logging.error("airports_parquet 不存在：%s", airports_parquet)
        return 2

    logging.info("加载航班元数据: %s", flights_parquet)
    flights_meta = _load_flights_meta(
        flights_parquet,
        airports_parquet,
        europe_only=args.europe_only,
        top_airports=args.top_airports,
        top_aircraft=args.top_aircraft,
        include_submission=args.include_submission,
        include_final=args.include_final,
        europe_continent=args.europe_continent,
        meta_procs=args.meta_procs,
    )
    logging.info("航班元数据筛选后航班数: %s", len(flights_meta))
    if flights_meta.empty:
        logging.error("筛选后无可用航班，请检查过滤条件。")
        return 2

    days = _list_day_strings(raw_dir)
    days = _filter_dates(days, args.date_from, args.date_to)
    if args.limit_days and args.limit_days > 0:
        days = days[: args.limit_days]

    if not days:
        logging.warning("未找到需要处理的日文件（raw_dir=%s, from=%s, to=%s）", raw_dir, args.date_from, args.date_to)
        return 0

    logging.info("待处理天数: %s", len(days))
    logging.info("输出目录: %s", out_dir)

    start = datetime.now()
    stats: list[DayPointStats] = []
    for day in days:
        in_path = raw_dir / f"{day}.parquet"
        out_path = out_dir / f"xue_{day}.parquet"
        stats.append(process_one_day(day, in_path, out_path, flights_meta, args))

    stats_df = pd.DataFrame([asdict(s) for s in stats])
    if not stats_df.empty:
        total_raw = stats_df["raw_rows"].dropna().sum()
        total_out = stats_df["out_rows"].dropna().sum()
        ratio_out_raw = (total_out / total_raw) if total_raw else None

        total_raw_gb = stats_df["raw_gb"].dropna().sum()
        total_out_gb = stats_df["out_gb"].dropna().sum()
        ratio_out_raw_size = (total_out_gb / total_raw_gb) if total_raw_gb else None

        logging.info(
            "总计点数: raw_rows=%s, out_rows=%s, out/raw=%s",
            int(total_raw),
            int(total_out),
            f"{ratio_out_raw:.6f}" if ratio_out_raw is not None else "NA",
        )
        logging.info(
            "总计文件大小(GB): raw_gb=%s, out_gb=%s, out_gb/raw_gb=%s",
            f"{total_raw_gb:.6f}",
            f"{total_out_gb:.6f}",
            f"{ratio_out_raw_size:.6f}" if ratio_out_raw_size is not None else "NA",
        )

        stats_csv = Path(args.stats_csv).resolve()
        stats_csv.parent.mkdir(parents=True, exist_ok=True)
        stats_df.to_csv(stats_csv, index=False)
        logging.info("点数统计 CSV 已写入: %s", stats_csv)

    logging.info("全部完成，用时: %s", datetime.now() - start)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
