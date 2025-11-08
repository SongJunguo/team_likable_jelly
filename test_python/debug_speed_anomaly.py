#!/usr/bin/env python3
"""
调试速度异常问题的测试脚本

目的：提取异常轨迹样本，对比各个处理阶段的数据，找出异常点产生的根本原因
"""

import pandas as pd
import numpy as np
from pathlib import Path


def haversine_km(lat1, lon1, lat2, lon2):
    """计算两点间的Haversine距离（千米）"""
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return 6371.0 * c


def analyze_trajectory_stages(original_flight_id, date_str, version="v7"):
    """对比分析轨迹在各个处理阶段的状态

    Args:
        original_flight_id: 原始航班ID
        date_str: 日期字符串，如 "2022-12-28"
        version: 版本号，如 "v7"
    """

    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")

    # 各个阶段的数据目录
    filtered_dir = base_dir / f"classic_filtered_trajectories_doublepass_loop_{version}"
    complete_dir = base_dir / f"interpolate_trajs_doublepass_loop_lim20s_inside_{version}"
    segmented_dir = base_dir / f"segmented_trajs_doublepass_loop_lim20s_inside_{version}"

    print(f"\n{'='*80}")
    print(f"分析航班 {original_flight_id} 在 {date_str} 的处理过程")
    print(f"{'='*80}\n")

    # 1. 读取过滤后的数据
    filtered_file = filtered_dir / f"{date_str}.parquet"
    if filtered_file.exists():
        print(f"[1] 读取过滤后数据: {filtered_file}")
        df_filtered = pd.read_parquet(filtered_file)
        df_filtered_flt = df_filtered[df_filtered['flight_id'] == original_flight_id].copy()
        print(f"    - 过滤后该航班点数: {len(df_filtered_flt)}")
        if not df_filtered_flt.empty:
            print(f"    - 经纬度缺失: {df_filtered_flt[['latitude', 'longitude']].isna().any(axis=1).sum()}")
            print(f"    - 高度缺失: {df_filtered_flt['altitude'].isna().sum()}")

            # 计算速度
            df_filtered_flt = df_filtered_flt.sort_values('timestamp').reset_index(drop=True)
            df_filtered_flt['timestamp'] = pd.to_datetime(df_filtered_flt['timestamp'], utc=True)

            # 只对有效点计算速度
            valid = (~df_filtered_flt['latitude'].isna()) & (~df_filtered_flt['longitude'].isna())
            valid_data = df_filtered_flt[valid].copy()

            if len(valid_data) > 1:
                lat = valid_data['latitude'].to_numpy()
                lon = valid_data['longitude'].to_numpy()
                ts = valid_data['timestamp'].values.astype('datetime64[s]').astype(float)

                dist = haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
                dt = np.diff(ts)
                speed_mps = np.zeros(len(dist))
                mask = dt > 0
                speed_mps[mask] = (dist[mask] * 1000) / dt[mask]

                max_speed = speed_mps.max() if len(speed_mps) > 0 else 0
                print(f"    - 最大速度: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")

                # 显示超速点
                high_speed = speed_mps >= 1000
                if high_speed.any():
                    print(f"    ⚠️  发现 {high_speed.sum()} 个超速点 (≥1000 m/s) 在过滤后数据中！")
    else:
        print(f"[1] ❌ 过滤后数据不存在: {filtered_file}")
        df_filtered_flt = None

    # 2. 读取插值后的数据
    complete_file = complete_dir / f"complete_{date_str}.parquet"
    if complete_file.exists():
        print(f"\n[2] 读取插值后数据: {complete_file}")
        df_complete = pd.read_parquet(complete_file)
        df_complete_flt = df_complete[df_complete['flight_id'] == original_flight_id].copy()
        print(f"    - 插值后该航班点数: {len(df_complete_flt)}")
        if not df_complete_flt.empty:
            print(f"    - 经纬度缺失: {df_complete_flt[['latitude', 'longitude']].isna().any(axis=1).sum()}")
            print(f"    - 高度缺失: {df_complete_flt['altitude'].isna().sum()}")

            # 计算速度
            df_complete_flt = df_complete_flt.sort_values('timestamp').reset_index(drop=True)
            df_complete_flt['timestamp'] = pd.to_datetime(df_complete_flt['timestamp'], utc=True)

            valid = (~df_complete_flt['latitude'].isna()) & (~df_complete_flt['longitude'].isna())
            valid_data = df_complete_flt[valid].copy()

            if len(valid_data) > 1:
                lat = valid_data['latitude'].to_numpy()
                lon = valid_data['longitude'].to_numpy()
                ts = valid_data['timestamp'].values.astype('datetime64[s]').astype(float)

                dist = haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
                dt = np.diff(ts)
                speed_mps = np.zeros(len(dist))
                mask = dt > 0
                speed_mps[mask] = (dist[mask] * 1000) / dt[mask]

                max_speed = speed_mps.max() if len(speed_mps) > 0 else 0
                print(f"    - 最大速度: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")

                # 显示超速点
                high_speed = speed_mps >= 1000
                if high_speed.any():
                    print(f"    ⚠️  发现 {high_speed.sum()} 个超速点 (≥1000 m/s)！")

                    # 显示详细信息
                    for idx in np.where(high_speed)[0]:
                        print(f"\n    超速点详情 #{idx}:")
                        print(f"      时刻1: {valid_data.iloc[idx]['timestamp']}")
                        print(f"      时刻2: {valid_data.iloc[idx+1]['timestamp']}")
                        print(f"      位置1: ({lat[idx]:.6f}, {lon[idx]:.6f})")
                        print(f"      位置2: ({lat[idx+1]:.6f}, {lon[idx+1]:.6f})")
                        print(f"      距离: {dist[idx]:.3f} km")
                        print(f"      时间差: {dt[idx]:.1f} s")
                        print(f"      速度: {speed_mps[idx]:.2f} m/s ({speed_mps[idx]*3.6:.2f} km/h)")
    else:
        print(f"\n[2] ❌ 插值后数据不存在: {complete_file}")
        df_complete_flt = None

    # 3. 读取切段后的数据
    segmented_file = segmented_dir / f"segmented_{date_str}.parquet"
    if segmented_file.exists():
        print(f"\n[3] 读取切段后数据: {segmented_file}")
        df_segmented = pd.read_parquet(segmented_file)
        df_segmented_flt = df_segmented[df_segmented['original_flight_id'] == original_flight_id].copy()
        print(f"    - 切段后该航班点数: {len(df_segmented_flt)}")
        print(f"    - 切段数: {df_segmented_flt['segment_index'].nunique() if not df_segmented_flt.empty else 0}")

        if not df_segmented_flt.empty:
            # 对每个segment分析
            for seg_idx, seg_group in df_segmented_flt.groupby('segment_index'):
                seg_group = seg_group.sort_values('timestamp').reset_index(drop=True)
                seg_group['timestamp'] = pd.to_datetime(seg_group['timestamp'], utc=True)

                print(f"\n    Segment {seg_idx}:")
                print(f"      点数: {len(seg_group)}")
                print(f"      时间范围: {seg_group['timestamp'].iloc[0]} ~ {seg_group['timestamp'].iloc[-1]}")

                if len(seg_group) > 1:
                    lat = seg_group['latitude'].to_numpy()
                    lon = seg_group['longitude'].to_numpy()
                    ts = seg_group['timestamp'].values.astype('datetime64[s]').astype(float)

                    dist = haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
                    dt = np.diff(ts)
                    speed_mps = np.zeros(len(dist))
                    mask = dt > 0
                    speed_mps[mask] = (dist[mask] * 1000) / dt[mask]

                    max_speed = speed_mps.max() if len(speed_mps) > 0 else 0
                    print(f"      最大速度: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")

                    # 显示超速点
                    high_speed = speed_mps >= 1000
                    if high_speed.any():
                        print(f"      ⚠️  发现 {high_speed.sum()} 个超速点 (≥1000 m/s)！")

                        # 显示详细信息
                        for idx in np.where(high_speed)[0]:
                            print(f"\n      超速点详情 #{idx}:")
                            print(f"        时刻1: {seg_group.iloc[idx]['timestamp']}")
                            print(f"        时刻2: {seg_group.iloc[idx+1]['timestamp']}")
                            print(f"        位置1: ({lat[idx]:.6f}, {lon[idx]:.6f})")
                            print(f"        位置2: ({lat[idx+1]:.6f}, {lon[idx+1]:.6f})")
                            print(f"        距离: {dist[idx]:.3f} km")
                            print(f"        时间差: {dt[idx]:.1f} s")
                            print(f"        速度: {speed_mps[idx]:.2f} m/s ({speed_mps[idx]*3.6:.2f} km/h)")
    else:
        print(f"\n[3] ❌ 切段后数据不存在: {segmented_file}")

    print(f"\n{'='*80}\n")

    return df_filtered_flt, df_complete_flt


if __name__ == "__main__":
    # 测试几个异常航班
    test_cases = [
        (257987764, "2022-12-28"),  # 最大异常速度 2353.74 m/s
        (250702687, "2022-04-10"),  # 异常速度 2230.57 m/s
        (253258084, "2022-07-08"),  # 异常速度 1697.71 m/s
    ]

    for fid, date in test_cases:
        analyze_trajectory_stages(fid, date)
