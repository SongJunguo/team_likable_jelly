#!/usr/bin/env python3
"""
时间切分单日脚本

功能：
- 读取过滤后的轨迹
- 按时间间隔切分成segments
- 保留必需列非NaN的行
- 过滤掉过短的segments

用法：
    python split_single_day.py \
        -t_in filtered_clean_v1/2022-01-01.parquet \
        -t_out segmented_clean_v1/segmented_2022-01-01.parquet \
        --max-dt 20 \
        --min-points 30 \
        --min-duration 120
"""

import argparse
import os

import numpy as np
import pandas as pd
from airport_proximity_filter import filter_by_airport_proximity


DEFAULT_REQ_COLS = ["latitude", "longitude", "altitude"]


def _parse_req_cols(value):
    if not value:
        return DEFAULT_REQ_COLS
    cols = [c for c in value.split() if c]
    if not cols:
        raise ValueError("req-cols 不能为空")
    return cols


def split_by_time(df, required_cols, max_dt=20, min_points=30, min_duration=120, gap_mode="split"):
    """按时间切分轨迹

    Args:
        df: 过滤后的DataFrame
        required_cols: 必需的列（不能有NaN）
        max_dt: 最大时间间隔（秒）
        min_points: 最小点数
        min_duration: 最小时长（秒）
        gap_mode: gap处理方式，split=切段，drop=存在gap则丢弃整条轨迹

    Returns:
        切分后的DataFrame（带segment标识）
    """
    if df.empty:
        return pd.DataFrame()

    if gap_mode not in {"split", "drop"}:
        raise ValueError(f"gap_mode 必须是 split 或 drop，当前: {gap_mode}")

    segments = []

    for fid, g in df.groupby('flight_id', sort=False):
        # 排序
        g = g.sort_values('timestamp').reset_index(drop=True)

        # 仅保留必需列均非NaN的行
        g_valid = g.dropna(subset=required_cols)
        if g_valid.shape[0] < min_points:
            continue

        # 以Δt大于阈值切段
        ts = g_valid['timestamp'].values.astype('datetime64[ns]')
        if len(ts) == 0:
            continue

        dt = np.r_[0, (ts[1:] - ts[:-1]).astype('timedelta64[s]').astype(np.int64)]
        if gap_mode == "drop" and np.any(dt > max_dt):
            continue

        breaks = dt > max_dt
        group_id = breaks.cumsum()

        # 分组过滤
        for gid, seg in g_valid.groupby(group_id, sort=True):
            if seg.shape[0] < min_points:
                continue

            dur = int((seg['timestamp'].iloc[-1] - seg['timestamp'].iloc[0]) / pd.to_timedelta(1, 's'))
            if dur < min_duration:
                continue

            segments.append(seg.copy())

    if not segments:
        return pd.DataFrame()

    # 按时间排序所有segments并重新编号
    all_segs = []
    seg_idx = 1

    for seg in segments:
        fid = seg['flight_id'].iloc[0]
        seg = seg.copy()
        seg['original_flight_id'] = np.int64(fid)
        seg['segment_index'] = np.int32(seg_idx)
        seg['flight_id'] = np.int64(fid * 10000 + seg_idx)

        t0 = pd.to_datetime(seg['timestamp'].iloc[0], utc=True)
        t1 = pd.to_datetime(seg['timestamp'].iloc[-1], utc=True)
        seg['flight_seg_info'] = (
            f"{int(fid)}_s{seg_idx}_{t0.strftime('%Y%m%dT%H%M%S')}Z_{t1.strftime('%H%M%S')}"
        )

        all_segs.append(seg)
        seg_idx += 1

    return pd.concat(all_segs, ignore_index=True)


def main():
    parser = argparse.ArgumentParser(
        description='按时间切分单日轨迹数据'
    )
    parser.add_argument('-t_in', required=True, help='输入过滤后轨迹文件')
    parser.add_argument('-t_out', required=True, help='输出切分后轨迹文件')
    parser.add_argument('--max-dt', type=int, default=20, help='最大时间间隔（秒）')
    parser.add_argument('--req-cols', default=None, help='必需列列表（空格分隔）')
    parser.add_argument('--min-points', type=int, default=30, help='最小点数')
    parser.add_argument('--min-duration', type=int, default=120, help='最小时长（秒）')
    parser.add_argument('--gap-mode', choices=['split', 'drop'], default='split',
                        help='gap处理方式：split=切段，drop=存在gap则丢弃整条轨迹')
    parser.add_argument('--airport-filter', action='store_true', help='启用机场邻近度过滤')
    parser.add_argument('--airport-threshold-km', type=float, default=10.0,
                        help='机场邻近度阈值（公里）')
    parser.add_argument('--flights-parquet', default="opensky_2024_PRC_dataset/flights/challenge_set.parquet",
                        help='航班元数据（默认 challenge_set.parquet）')
    parser.add_argument('--airports-parquet', default="opensky_2024_PRC_dataset/airports_tz.parquet",
                        help='机场信息（包含坐标）')
    args = parser.parse_args()

    print(f"▶️  切分: {os.path.basename(args.t_in)}")

    # 读取过滤后数据
    df = pd.read_parquet(args.t_in)
    print(f"    输入: {len(df):,} 行, {df['flight_id'].nunique()} 个航班")

    if args.airport_filter:
        print("    机场邻近过滤...")
        df = filter_by_airport_proximity(
            df,
            flights_parquet=args.flights_parquet,
            airports_parquet=args.airports_parquet,
            threshold_km=args.airport_threshold_km,
        )
        if df.empty:
            print("    ⚠️  机场邻近过滤后无有效航班")
            pd.DataFrame().to_parquet(args.t_out, index=False)
            return

    # 切分
    required_cols = _parse_req_cols(args.req_cols)
    df_seg = split_by_time(
        df,
        required_cols=required_cols,
        max_dt=args.max_dt,
        min_points=args.min_points,
        min_duration=args.min_duration,
        gap_mode=args.gap_mode
    )

    if df_seg.empty:
        print("    ⚠️  切分后无有效segment")
        pd.DataFrame().to_parquet(args.t_out, index=False)
        return

    num_segs = df_seg['flight_id'].nunique()
    print(f"    输出: {num_segs} 个segments, {len(df_seg):,} 行")

    # 保存
    os.makedirs(os.path.dirname(args.t_out) or '.', exist_ok=True)
    df_seg.to_parquet(args.t_out, index=False)
    print(f"  ✅ 完成: {args.t_out}")


if __name__ == '__main__':
    main()
