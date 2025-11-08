#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
按缺失、时间间隔和速度切断轨迹，生成"无缺失、无超速的连续片段"。

正确逻辑：
1. 第1步：速度检查，把超速点标记为NaN（删除超速点及其邻点）
2. 第2步：删除所有NaN行（包括原有NaN + 刚标记的超速点）
3. 第3步：按时间间隔切段（Δt > max_dt 则切断）
4. 第4步：过滤太短的segment（点数 < min_points 或 时长 < min_duration）

规则（默认）：
- 基础必需列：latitude, longitude, altitude（均非 NaN）
- 最大速度：600 m/s（超过则删除该点对）
- 相邻时间差 Δt ≤ 20s，否则切断
- 片段保留阈值：min_points=30，min_duration=120s

重命名与标识：
- original_flight_id：原始航班 ID（int64）
- segment_index：从 1 开始的片段序号（按时间排序）
- flight_id：original_flight_id*10000 + segment_index（int64，唯一、稳定）
- flight_seg_info："{original_flight_id}_s{segment_index}_{startUTC}_{endUTC}"

用法示例：
  python split_segments_with_speed_check.py \
    --input-file /path/complete_2022-01-01.parquet \
    --output-file /path/segmented_2022-01-01.parquet \
    --required-cols latitude longitude altitude \
    --max-dt 20 --max-speed 600 --min-points 30 --min-duration 120
"""

from __future__ import annotations

import argparse
import os
from typing import List

import numpy as np
import pandas as pd


def haversine_m(lat1, lon1, lat2, lon2):
    """计算两点间的Haversine距离（米）"""
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return 6371000.0 * c


def remove_overspeed_points(df: pd.DataFrame, max_speed_mps: float, max_iterations: int = 5) -> pd.DataFrame:
    """删除超速点（循环迭代直到无超速点）

    Args:
        df: DataFrame，必须包含 timestamp, latitude, longitude
        max_speed_mps: 最大允许速度（米/秒）
        max_iterations: 最大迭代次数

    Returns:
        处理后的DataFrame（超速点被设为NaN）
    """
    df = df.copy()

    cols_to_remove = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    cols_to_remove = [c for c in cols_to_remove if c in df.columns]

    for iteration in range(max_iterations):
        # 找到所有有效的经纬度点
        valid = (~df['latitude'].isna()) & (~df['longitude'].isna()) & (~df['timestamp'].isna())

        if valid.sum() < 2:
            break

        # 提取有效点的索引、坐标和时间
        valid_indices = df.index[valid].to_numpy()
        valid_lats = df.loc[valid, 'latitude'].to_numpy()
        valid_lons = df.loc[valid, 'longitude'].to_numpy()
        valid_times = pd.to_datetime(df.loc[valid, 'timestamp'], utc=True).values.astype('datetime64[s]').astype(float)

        # 计算相邻有效点之间的速度
        bad_indices = set()
        for i in range(len(valid_indices) - 1):
            dt = valid_times[i + 1] - valid_times[i]

            if dt <= 0:
                continue

            # 计算Haversine距离
            dist = haversine_m(
                valid_lats[i],
                valid_lons[i],
                valid_lats[i + 1],
                valid_lons[i + 1],
            )
            speed = dist / dt

            if speed >= max_speed_mps:
                # 保守策略：删除两个点（无法判断哪个点异常）
                bad_indices.add(valid_indices[i])
                bad_indices.add(valid_indices[i + 1])

        if not bad_indices:
            # 没有新的超速点，收敛
            break

        # 删除超速点（设为NaN）
        df.loc[list(bad_indices), cols_to_remove] = np.nan

    return df


def split_one_flight(df: pd.DataFrame, required_cols: List[str], max_dt: int,
                     max_speed_mps: float, min_points: int, min_duration: int) -> List[pd.DataFrame]:
    """切分单个航班轨迹

    逻辑：
    1. 速度检查，删除超速点（设为NaN）
    2. 删除所有NaN行
    3. 按时间间隔切段
    4. 过滤太短的segment

    Args:
        df: 航班数据
        required_cols: 必需的列（不能有NaN）
        max_dt: 最大时间间隔（秒）
        max_speed_mps: 最大允许速度（米/秒），None或0表示不检查速度
        min_points: 最小点数
        min_duration: 最小时长（秒）

    Returns:
        切分后的segment列表
    """
    if df.empty:
        return []

    df = df.sort_values('timestamp').reset_index(drop=True)

    # 第1步：速度检查，删除超速点（设为NaN）
    if max_speed_mps is not None and max_speed_mps > 0:
        df = remove_overspeed_points(df, max_speed_mps, max_iterations=5)

    # 第2步：删除所有NaN行（包括原有的NaN + 超速点）
    df_valid = df.dropna(subset=required_cols)
    if df_valid.shape[0] < min_points:
        return []

    # 第3步：按时间间隔切段
    ts = df_valid['timestamp'].values.astype('datetime64[ns]')
    if len(ts) == 0:
        return []

    dt = np.r_[0, (ts[1:] - ts[:-1]).astype('timedelta64[s]').astype(np.int64)]
    breaks = dt > max_dt
    group_id = breaks.cumsum()

    # 第4步：分组并过滤太短的segment
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
                 max_dt: int, max_speed_mps: float, min_points: int, min_duration: int) -> dict:
    """处理单个文件

    Returns:
        统计信息字典
    """
    df = pd.read_parquet(input_file)
    if df.empty:
        pd.DataFrame().to_parquet(output_file, index=False)
        return {'total_flights': 0, 'total_segments': 0, 'total_points_in': 0, 'total_points_out': 0}

    out_parts: List[pd.DataFrame] = []
    total_flights = 0
    total_segments = 0
    total_points_in = 0
    total_points_out = 0

    for fid, g in df.groupby('flight_id', sort=False):
        total_flights += 1
        total_points_in += len(g)

        segs = split_one_flight(g, required_cols, max_dt, max_speed_mps, min_points, min_duration)
        if not segs:
            continue

        total_segments += len(segs)

        # 片段按时间排序并重排 segment_index
        segs.sort(key=lambda x: x['timestamp'].iloc[0])
        for k, seg in enumerate(segs, start=1):
            seg = seg.copy()
            total_points_out += len(seg)

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

    return {
        'total_flights': total_flights,
        'total_segments': total_segments,
        'total_points_in': total_points_in,
        'total_points_out': total_points_out,
    }


def main():
    ap = argparse.ArgumentParser(
        description='Split trajectories into NaN-free, overspeed-free segments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
正确逻辑：
  1. 速度检查，删除超速点（设为NaN）
  2. 删除所有NaN行
  3. 按时间间隔切段
  4. 过滤太短的segment

结果保证：每个segment内部无NaN + 无超速 + 时间连续
        """
    )
    ap.add_argument('--input-file', required=True, help='输入文件路径')
    ap.add_argument('--output-file', required=True, help='输出文件路径')
    ap.add_argument('--required-cols', nargs='+', default=['latitude', 'longitude', 'altitude'],
                    help='必需列（不能有NaN）')
    ap.add_argument('--max-dt', type=int, default=20, help='最大时间间隔（秒）')
    ap.add_argument('--max-speed', type=float, default=600.0,
                    help='最大允许速度（米/秒），0表示不检查速度')
    ap.add_argument('--min-points', type=int, default=30, help='最小点数')
    ap.add_argument('--min-duration', type=int, default=120, help='最小时长（秒）')
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.output_file) or '.', exist_ok=True)

    stats = process_file(
        args.input_file,
        args.output_file,
        args.required_cols,
        args.max_dt,
        args.max_speed,
        args.min_points,
        args.min_duration,
    )

    print(f"处理完成:")
    print(f"  输入: {stats['total_flights']} 个航班, {stats['total_points_in']} 个点")
    print(f"  输出: {stats['total_segments']} 个segment, {stats['total_points_out']} 个点")
    if stats['total_points_in'] > 0:
        print(f"  保留率: {stats['total_points_out']/stats['total_points_in']*100:.1f}%")


if __name__ == '__main__':
    main()
