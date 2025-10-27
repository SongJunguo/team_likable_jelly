#!/usr/bin/env python3
"""
perfect_trajectories 跳变扫描脚本
================================

用途
----
遍历 ``perfect_trajectories`` 目录下的日度 parquet 文件，识别“短时间内跨越超远距离”
的观测跳变。输出结果包含：

1. 每日详细事件清单：``reports/perfect_jump_events/perfect_jumps_YYYY-MM-DD.csv``
2. 全局汇总表：``reports/perfect_jump_events_summary.csv``（按 flight_id 聚合）

判定规则（默认值，可命令行覆盖）：
- `Δt ≤ 120s 且 Δs ≥ 10km`
- `Δt ≤ 300s 且 Δs ≥ 50km`
- `瞬时速度 ≥ 1500 km/h`
满足任一条件即认定为跳变。

运行示例
--------
.. code-block:: bash

    conda activate opensky
    python analysis/detect_perfect_jumps.py \
        --data-dir perfect_trajectories \
        --out-dir reports/perfect_jump_events

"""

from __future__ import annotations

import argparse
import csv
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# --------------------------- 数据结构 & 配置 --------------------------- #


@dataclass
class JumpThresholds:
    """跳变判定阈值集合。"""

    max_dt_short_s: float = 120.0
    min_dist_short_km: float = 10.0
    max_dt_long_s: float = 300.0
    min_dist_long_km: float = 50.0
    min_speed_kmh: float = 1500.0

    def explain(self) -> str:
        return (
            f"Δt ≤ {self.max_dt_short_s:.0f}s 且 Δs ≥ {self.min_dist_short_km:.0f}km；"
            f"Δt ≤ {self.max_dt_long_s:.0f}s 且 Δs ≥ {self.min_dist_long_km:.0f}km；"
            f"或瞬时速度 ≥ {self.min_speed_kmh:.0f} km/h"
        )


# --------------------------- 算法实现 --------------------------- #


def haversine_km(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """计算一批点对之间的大圆距离（km）。输入输出均为 numpy 向量。"""
    # 防止 NaN 影响：只在调用侧保证输入位置正确
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    sin_dlat = np.sin(dlat / 2.0)
    sin_dlon = np.sin(dlon / 2.0)
    a = sin_dlat * sin_dlat + np.cos(lat1) * np.cos(lat2) * sin_dlon * sin_dlon
    # 数值误差可能导致 a 略超出 [0,1]，使用 clip 稳定
    a = np.clip(a, 0.0, 1.0)
    c = 2.0 * np.arcsin(np.sqrt(a))
    return 6371.0 * c  # 地球平均半径约 6371km


def detect_jumps_for_day(
    df: pd.DataFrame,
    day_file: str,
    thresholds: JumpThresholds,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """对单日 DataFrame 进行跳变检测，返回详细事件表与按航班聚合表。"""
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 类型与排序
    df["flight_id"] = df["flight_id"].astype("int64", copy=False)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp", "latitude", "longitude"]).copy()
    df = df.sort_values(["flight_id", "timestamp"], kind="mergesort")
    if df.empty:
        return pd.DataFrame(), pd.DataFrame()

    # 准备向量
    lat_rad = np.radians(df["latitude"].to_numpy(dtype="float64", copy=False))
    lon_rad = np.radians(df["longitude"].to_numpy(dtype="float64", copy=False))
    flight_ids = df["flight_id"].to_numpy(copy=False)
    timestamps_ns = df["timestamp"].astype("int64").to_numpy(copy=False)  # ns since epoch

    prev_same = np.concatenate(([False], flight_ids[1:] == flight_ids[:-1]))

    lat_prev = np.roll(lat_rad, 1)
    lon_prev = np.roll(lon_rad, 1)
    ts_prev_ns = np.roll(timestamps_ns, 1)

    lat_prev[~prev_same] = np.nan
    lon_prev[~prev_same] = np.nan
    ts_prev_ns[~prev_same] = np.int64(0)

    delta_t_s = np.full(flight_ids.shape, np.nan, dtype="float64")
    dist_km = np.full(flight_ids.shape, np.nan, dtype="float64")

    valid_mask = prev_same.copy()
    delta_t_s[valid_mask] = (timestamps_ns[valid_mask] - ts_prev_ns[valid_mask]) / 1e9

    # 避免 0 或负数带来的除法问题
    valid_mask &= delta_t_s > 0.0
    if not np.any(valid_mask):
        return pd.DataFrame(), pd.DataFrame()

    dist_km[valid_mask] = haversine_km(
        lat_prev[valid_mask],
        lon_prev[valid_mask],
        lat_rad[valid_mask],
        lon_rad[valid_mask],
    )

    speed_kmh = np.full(flight_ids.shape, np.nan, dtype="float64")
    speed_kmh[valid_mask] = dist_km[valid_mask] / (delta_t_s[valid_mask] / 3600.0)
    speed_mps = speed_kmh / 3.6

    # 触发条件
    cond_short = (delta_t_s <= thresholds.max_dt_short_s) & (dist_km >= thresholds.min_dist_short_km)
    cond_long = (delta_t_s <= thresholds.max_dt_long_s) & (dist_km >= thresholds.min_dist_long_km)
    cond_speed = speed_kmh >= thresholds.min_speed_kmh

    event_mask = valid_mask & (cond_short | cond_long | cond_speed)
    if not np.any(event_mask):
        return pd.DataFrame(), pd.DataFrame()

    arr_ts = pd.to_datetime(timestamps_ns[event_mask])
    arr_ts_prev = pd.to_datetime(ts_prev_ns[event_mask])
    arr_flight = flight_ids[event_mask]

    triggers = []
    if np.any(event_mask):
        # 逐事件判定触发类型
        short_now = cond_short[event_mask]
        long_now = cond_long[event_mask]
        speed_now = cond_speed[event_mask]
        for s, l, v in zip(short_now, long_now, speed_now):
            reasons: List[str] = []
            if s:
                reasons.append("Δt≤120s且Δs≥10km")
            if l:
                reasons.append("Δt≤300s且Δs≥50km")
            if v:
                reasons.append("速度≥1500km/h")
            triggers.append(";".join(reasons))

    detail_df = pd.DataFrame(
        {
            "day_file": day_file,
            "flight_id": arr_flight,
            "ts_prev": arr_ts_prev,
            "ts_curr": arr_ts,
            "delta_t_s": delta_t_s[event_mask],
            "distance_km": dist_km[event_mask],
            "speed_kmh": speed_kmh[event_mask],
            "speed_mps": speed_mps[event_mask],
            "trigger": triggers,
        }
    )

    # 聚合：每个 flight_id 的事件条数与最大指标
    agg_df = (
        detail_df.groupby("flight_id", as_index=False)
        .agg(
            day_files=("day_file", lambda x: ",".join(sorted(set(x)))),
            event_count=("flight_id", "size"),
            max_speed_kmh=("speed_kmh", "max"),
            max_distance_km=("distance_km", "max"),
            max_speed_mps=("speed_mps", "max"),
            first_event_ts=("ts_curr", "min"),
            last_event_ts=("ts_curr", "max"),
        )
        .assign(day_file=day_file)
    )

    return detail_df, agg_df


# --------------------------- 主流程 --------------------------- #


def enumerate_parquet_files(data_dir: Path) -> List[Path]:
    files = sorted(p for p in data_dir.glob("*.parquet") if p.name.startswith("complete_"))
    return files


def write_csv(df: pd.DataFrame, path: Path) -> None:
    if df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描 perfect_trajectories 跳变事件")
    parser.add_argument("--data-dir", default="perfect_trajectories", help="输入目录（默认：perfect_trajectories）")
    parser.add_argument("--out-dir", default="reports/jump_reports", help="输出目录（默认：reports/jump_reports）")
    parser.add_argument("--limit", type=int, default=0, help="可选：限制处理的文件数量（按日期排序），0 表示全部")
    parser.add_argument("--max-dt-short", type=float, default=120.0, help="短时间阈值 Δt（秒），默认 120")
    parser.add_argument("--min-dist-short", type=float, default=10.0, help="短时间对应距离阈值 Δs（公里），默认 10")
    parser.add_argument("--max-dt-long", type=float, default=300.0, help="较长时间阈值 Δt（秒），默认 300")
    parser.add_argument("--min-dist-long", type=float, default=50.0, help="较长时间对应距离阈值 Δs（公里），默认 50")
    parser.add_argument("--min-speed", type=float, default=1500.0, help="速度阈值（km/h），默认 1500")
    parser.add_argument("--log-file", default=None, help="可选：日志输出路径（默认写入 out-dir/detect_perfect_jumps.log）")
    parser.add_argument("--verbose", action="store_true", help="输出更详细的日志")
    return parser.parse_args()


def setup_logger(log_path: Path, verbose: bool) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("detect_perfect_jumps")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    thresholds = JumpThresholds(
        max_dt_short_s=args.max_dt_short,
        min_dist_short_km=args.min_dist_short,
        max_dt_long_s=args.max_dt_long,
        min_dist_long_km=args.min_dist_long,
        min_speed_kmh=args.min_speed,
    )

    files = enumerate_parquet_files(data_dir)
    if not files:
        raise FileNotFoundError(f"未在 {data_dir} 找到 parquet 文件")

    if args.limit and args.limit > 0:
        files = files[: args.limit]

    default_log_path = out_dir / "detect_perfect_jumps.log"
    log_path = Path(args.log_file) if args.log_file else default_log_path
    logger = setup_logger(log_path, args.verbose)

    logger.info("输入目录: %s", data_dir)
    logger.info("待扫描文件数: %d", len(files))
    logger.info("判定阈值: %s", thresholds.explain())

    all_events: List[pd.DataFrame] = []
    all_aggs: List[pd.DataFrame] = []

    for idx, fp in enumerate(files, 1):
        day_file = fp.name
        try:
            df = pd.read_parquet(fp, columns=["flight_id", "timestamp", "latitude", "longitude"])
        except Exception as exc:  # pragma: no cover - I/O 错误情况下给出提示
            logger.warning("读取 %s 失败: %s", day_file, exc)
            continue

        detail_df, agg_df = detect_jumps_for_day(df, day_file, thresholds)

        if args.verbose:
            logger.debug("%s: 行数 %d, 事件 %d", day_file, len(df), len(detail_df))

        if not detail_df.empty:
            day_out = out_dir / f"perfect_jumps_{day_file.replace('.parquet', '.csv')}"
            write_csv(detail_df, day_out)
            all_events.append(detail_df)
            all_aggs.append(agg_df)
            logger.info("%d/%d %s → 检出 %d 条跳变事件", idx, len(files), day_file, len(detail_df))
        else:
            logger.info("%d/%d %s → 未发现跳变", idx, len(files), day_file)

    if not all_events:
        logger.info("全量扫描未发现跳变事件")
        return

    events_df = pd.concat(all_events, ignore_index=True)
    aggs_df = pd.concat(all_aggs, ignore_index=True)

    summary_path = out_dir / "jump_events_summary.csv"
    write_csv(aggs_df.sort_values(["event_count", "max_speed_kmh"], ascending=[False, False]), summary_path)

    detail_path = out_dir / "jump_events_all.csv"
    write_csv(events_df, detail_path)

    logger.info("跳变事件总数: %d，涉及航班 %d 架次", len(events_df), aggs_df["flight_id"].nunique())
    logger.info("汇总表已写入: %s", summary_path)
    logger.info("事件明细总表: %s", detail_path)
    logger.info("日志输出: %s", log_path)


if __name__ == "__main__":  # pragma: no cover - 脚本入口
    main()
