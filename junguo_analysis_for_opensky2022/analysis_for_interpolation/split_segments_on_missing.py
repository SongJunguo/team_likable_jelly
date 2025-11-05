#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
按缺失与时间间隔切断轨迹，生成“无缺失的连续片段”。

规则（默认）：
- 基础必需列：latitude, longitude, altitude（均非 NaN）
- 相邻时间差 Δt ≤ 20s，否则切断
- 片段保留阈值：min_points=30，min_duration=120s

重命名与标识：
- original_flight_id：原始航班 ID（int64）
- segment_index：从 1 开始的片段序号（按时间排序）
- flight_id：original_flight_id*10000 + segment_index（int64，唯一、稳定）
- flight_seg_info："{original_flight_id}_s{segment_index}_{startUTC}_{endUTC}"

用法示例：
  python split_segments_on_missing.py \
    --input-file /path/complete_2022-01-01.parquet \
    --output-file /path/segmented_2022-01-01.parquet \
    --required-cols latitude longitude altitude \
    --max-dt 20 --min-points 30 --min-duration 120
"""

from __future__ import annotations

import argparse
import os
from typing import List

import numpy as np
import pandas as pd


def to_seconds(x: pd.Series) -> np.ndarray:
    return (x.values.astype('datetime64[ns]') - x.values.astype('datetime64[ns]')[0]).astype('timedelta64[s]').astype(np.int64)


def split_one_flight(df: pd.DataFrame, required_cols: List[str], max_dt: int,
                     min_points: int, min_duration: int) -> List[pd.DataFrame]:
    if df.empty:
        return []

    df = df.sort_values('timestamp').reset_index(drop=True)
    # 仅保留“必需列均非 NaN”的行
    df_valid = df.dropna(subset=required_cols)
    if df_valid.shape[0] < min_points:
        return []

    # 以 Δt 大于阈值切段
    ts = df_valid['timestamp'].values.astype('datetime64[ns]')
    if len(ts) == 0:
        return []
    dt = np.r_[0, (ts[1:] - ts[:-1]).astype('timedelta64[s]').astype(np.int64)]
    breaks = dt > max_dt
    group_id = breaks.cumsum()

    segs: List[pd.DataFrame] = []
    for gid, seg in df_valid.groupby(group_id, sort=True):
        if seg.shape[0] < min_points:
            continue
        dur = int((seg['timestamp'].iloc[-1] - seg['timestamp'].iloc[0]) / pd.to_timedelta(1, 's'))
        if dur < min_duration:
            continue
        segs.append(seg.copy())
    return segs


def process_file(input_file: str, output_file: str, required_cols: List[str],
                 max_dt: int, min_points: int, min_duration: int) -> None:
    df = pd.read_parquet(input_file)
    if df.empty:
        pd.DataFrame().to_parquet(output_file, index=False)
        return

    out_parts: List[pd.DataFrame] = []
    for fid, g in df.groupby('flight_id', sort=False):
        segs = split_one_flight(g, required_cols, max_dt, min_points, min_duration)
        if not segs:
            continue
        # 片段按时间排序并重排 segment_index
        segs.sort(key=lambda x: x['timestamp'].iloc[0])
        for k, seg in enumerate(segs, start=1):
            seg = seg.copy()
            seg['original_flight_id'] = np.int64(fid)
            seg['segment_index'] = np.int32(k)
            seg['flight_id'] = np.int64(fid * 10000 + k)
            t0 = pd.to_datetime(seg['timestamp'].iloc[0], utc=True)
            t1 = pd.to_datetime(seg['timestamp'].iloc[-1], utc=True)
            seg['flight_seg_info'] = (
                f"{int(fid)}_s{k}_{t0.strftime('%Y%m%dT%H%M%S')}Z_{t1.strftime('%H%M%S')}"
            )
            out_parts.append(seg)

    if out_parts:
        out = pd.concat(out_parts, ignore_index=True)
        # 选择列顺序：新 ID 在前、原始 ID 与标识保留
        cols_front = ['flight_id', 'original_flight_id', 'segment_index', 'flight_seg_info']
        cols_all = cols_front + [c for c in out.columns if c not in cols_front]
        out = out[cols_all]
        out.to_parquet(output_file, index=False)
    else:
        # 输出空文件，便于后续管线识别
        pd.DataFrame().to_parquet(output_file, index=False)


def main():
    ap = argparse.ArgumentParser(description='Split trajectories into NaN-free segments')
    ap.add_argument('--input-file', required=True)
    ap.add_argument('--output-file', required=True)
    ap.add_argument('--required-cols', nargs='+', default=['latitude', 'longitude', 'altitude'])
    ap.add_argument('--max-dt', type=int, default=20)
    ap.add_argument('--min-points', type=int, default=30)
    ap.add_argument('--min-duration', type=int, default=120)
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    process_file(
        args.input_file,
        args.output_file,
        args.required_cols,
        args.max_dt,
        args.min_points,
        args.min_duration,
    )


if __name__ == '__main__':
    main()

