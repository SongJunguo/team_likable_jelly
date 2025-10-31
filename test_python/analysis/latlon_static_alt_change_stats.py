#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
并行统计：相邻采样中“经纬度未变但高度变化”的事件比例

定义（与 FilterCstLatLon/FilterCstPosition 逻辑一致）：
- isvar(v): 仅在两端均非 NaN 时比较 v[i] != v[i-1]，否则视为“未知”（不算变化）
- 事件：(~(isvar(lat) | isvar(lon)) & isvar(alt))，且四个经纬点与两个高度点均非 NaN

分相位统计：使用相邻两点 groundspeed 的平均值阈值（缺省 60 kt）划分地面/空中。

使用方式（建议在 opensky 环境）：
  conda activate opensky
  python test_python/analysis/latlon_static_alt_change_stats.py \
    --data_dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories \
    --out_csv  test_python/analysis/reports/latlon_static_alt_change_summary.csv \
    --n_workers 32 --max_files 50 --gs_threshold 60

备注：默认不限制文件数（--max_files=0 表示全部），考虑到机械硬盘 IO，建议先小样本验证。
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from multiprocessing import Pool, cpu_count


def isvar(v: np.ndarray) -> np.ndarray:
    """与 filterclassic.isvar 等价的“是否变化”检测（忽略 NaN 比较）。

    返回长度 len(v)-1 的布尔数组，表示相邻两点是否“发生了变化”。
    """
    v = v.astype(np.float64, copy=False)
    isnotnan = ~np.isnan(v)
    diffnotnan = np.logical_and(isnotnan[1:], isnotnan[:-1])
    diff = v[1:] != v[:-1]
    return np.logical_and(diff, diffnotnan)


@dataclass
class FileStats:
    file: str
    ok: bool
    error: str = ""
    pairs_valid: int = 0
    events_total: int = 0
    pairs_ground: int = 0
    events_ground: int = 0
    pairs_air: int = 0
    events_air: int = 0

    def to_dict(self) -> Dict:
        d = asdict(self)
        # 添加速率字段（防除零）
        d["rate_total"] = (self.events_total / self.pairs_valid) if self.pairs_valid > 0 else np.nan
        d["rate_ground"] = (self.events_ground / self.pairs_ground) if self.pairs_ground > 0 else np.nan
        d["rate_air"] = (self.events_air / self.pairs_air) if self.pairs_air > 0 else np.nan
        return d


def list_parquet_files(data_dir: str, max_files: int = 0) -> List[str]:
    files = [
        os.path.join(data_dir, f)
        for f in sorted(os.listdir(data_dir))
        if f.endswith(".parquet")
    ]
    if max_files and max_files > 0:
        return files[:max_files]
    return files


def process_one_file(args: Tuple[str, float]) -> FileStats:
    path, gs_threshold = args
    try:
        cols = [
            "flight_id",
            "timestamp",
            "latitude",
            "longitude",
            "altitude",
            "groundspeed",
        ]
        df = pd.read_parquet(path, columns=[c for c in cols if c])

        if "flight_id" not in df.columns or "timestamp" not in df.columns:
            return FileStats(path, ok=False, error="missing flight_id/timestamp")

        # 严格去重 + 排序，保证与主流程一致
        df = (
            df.dropna(subset=["flight_id", "timestamp"]).copy()
            .drop_duplicates(["flight_id", "timestamp"])  # 防重复帧
            .sort_values(["flight_id", "timestamp"])      # 时间递增
        )

        # 统一转换为 pandas 的 datetime（UTC），兼容 tz-aware/tz-naive/str 等多种情况
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values(["flight_id", "timestamp"])  # 重新排序

        pairs_valid = events_total = 0
        pairs_ground = events_ground = 0
        pairs_air = events_air = 0

        # 分航班统计
        for _, g in df.groupby("flight_id", sort=False):
            if len(g) < 2:
                continue

            lat = g["latitude"].values.astype(np.float64, copy=False) if "latitude" in g else np.full(len(g), np.nan)
            lon = g["longitude"].values.astype(np.float64, copy=False) if "longitude" in g else np.full(len(g), np.nan)
            alt = g["altitude"].values.astype(np.float64, copy=False) if "altitude" in g else np.full(len(g), np.nan)

            lat_upd = isvar(lat)
            lon_upd = isvar(lon)
            alt_upd = isvar(alt)

            latlon_both = (~np.isnan(lat[1:]) & ~np.isnan(lat[:-1]) & ~np.isnan(lon[1:]) & ~np.isnan(lon[:-1]))
            alt_both = (~np.isnan(alt[1:]) & ~np.isnan(alt[:-1]))
            valid_pairs = latlon_both & alt_both

            event = (~(lat_upd | lon_upd) & alt_upd & valid_pairs)

            pairs_valid += int(valid_pairs.sum())
            events_total += int(event.sum())

            if "groundspeed" in g:
                gs = g["groundspeed"].values.astype(np.float64, copy=False)
                gs_pair = (gs[1:] + gs[:-1]) / 2.0
                is_gs_ok = ~np.isnan(gs_pair)
                ground_mask = (gs_pair < gs_threshold)
                air_mask = (gs_pair >= gs_threshold)

                valid_ground = valid_pairs & is_gs_ok & ground_mask
                valid_air = valid_pairs & is_gs_ok & air_mask

                pairs_ground += int(valid_ground.sum())
                pairs_air += int(valid_air.sum())
                events_ground += int((event & is_gs_ok & ground_mask).sum())
                events_air += int((event & is_gs_ok & air_mask).sum())

        return FileStats(
            file=os.path.basename(path),
            ok=True,
            pairs_valid=pairs_valid,
            events_total=events_total,
            pairs_ground=pairs_ground,
            events_ground=events_ground,
            pairs_air=pairs_air,
            events_air=events_air,
        )

    except Exception as e:
        return FileStats(path, ok=False, error=str(e))


def aggregate(stats: List[FileStats]) -> Dict:
    agg = dict(
        files_processed=0,
        files_ok=0,
        files_failed=0,
        pairs_valid=0,
        events_total=0,
        pairs_ground=0,
        events_ground=0,
        pairs_air=0,
        events_air=0,
    )
    for s in stats:
        agg["files_processed"] += 1
        agg["files_ok"] += int(s.ok)
        agg["files_failed"] += int(not s.ok)
        agg["pairs_valid"] += s.pairs_valid
        agg["events_total"] += s.events_total
        agg["pairs_ground"] += s.pairs_ground
        agg["events_ground"] += s.events_ground
        agg["pairs_air"] += s.pairs_air
        agg["events_air"] += s.events_air

    # 速率
    agg["rate_total"] = (agg["events_total"] / agg["pairs_valid"]) if agg["pairs_valid"] > 0 else np.nan
    agg["rate_ground"] = (agg["events_ground"] / agg["pairs_ground"]) if agg["pairs_ground"] > 0 else np.nan
    agg["rate_air"] = (agg["events_air"] / agg["pairs_air"]) if agg["pairs_air"] > 0 else np.nan
    return agg


def main():
    parser = argparse.ArgumentParser(description="统计：经纬不变但高度变化的事件比例（并行）")
    parser.add_argument("--data_dir", required=True, help="输入 Parquet 日文件目录")
    parser.add_argument("--out_csv", required=True, help="输出汇总 CSV 路径")
    parser.add_argument("--n_workers", type=int, default=min(32, cpu_count() or 8), help="并行进程数")
    parser.add_argument("--max_files", type=int, default=0, help="最多处理多少个文件（0 表示全部）")
    parser.add_argument("--gs_threshold", type=float, default=60.0, help="地面/空中分界的 groundspeed 阈值（kt）")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out_csv), exist_ok=True)

    files = list_parquet_files(args.data_dir, args.max_files)
    if not files:
        print(f"❌ 未找到 parquet 文件: {args.data_dir}")
        return

    tasks = [(f, args.gs_threshold) for f in files]

    results: List[FileStats] = []
    with Pool(processes=args.n_workers) as pool:
        for s in pool.imap_unordered(process_one_file, tasks, chunksize=1):
            results.append(s)
            status = "OK" if s.ok else f"FAIL({s.error})"
            print(f"[{len(results)}/{len(files)}] {os.path.basename(s.file)} -> {status}")

    # 写出 per-file 明细
    df_files = pd.DataFrame([s.to_dict() for s in results])
    per_file_csv = args.out_csv.replace(".csv", ".per_file.csv")
    df_files.to_csv(per_file_csv, index=False)

    # 汇总
    agg = aggregate(results)
    df_agg = pd.DataFrame([agg])
    df_agg.to_csv(args.out_csv, index=False)

    print("\n=== 汇总 ===")
    print(df_agg.to_string(index=False))
    print(f"\n已保存: {args.out_csv}\n明细: {per_file_csv}")


if __name__ == "__main__":
    main()
