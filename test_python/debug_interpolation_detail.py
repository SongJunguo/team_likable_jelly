#!/usr/bin/env python3
"""
详细对比插值前后的数据点，查看异常速度是如何产生的
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


def analyze_interpolation_around_anomaly(original_flight_id, date_str, anomaly_time_str, window=10):
    """详细分析异常点附近的插值前后对比

    Args:
        original_flight_id: 原始航班ID
        date_str: 日期字符串
        anomaly_time_str: 异常时刻（如 "2022-12-28 04:16:46"）
        window: 异常点前后的时间窗口（秒）
    """

    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
    filtered_dir = base_dir / "classic_filtered_trajectories_doublepass_loop_v7"
    complete_dir = base_dir / "interpolate_trajs_doublepass_loop_lim20s_inside_v7"

    print(f"\n{'='*100}")
    print(f"详细分析航班 {original_flight_id} 在 {anomaly_time_str} 附近的插值过程")
    print(f"{'='*100}\n")

    anomaly_time = pd.to_datetime(anomaly_time_str, utc=True)

    # 读取过滤后的数据
    filtered_file = filtered_dir / f"{date_str}.parquet"
    df_filtered = pd.read_parquet(filtered_file)
    df_filtered_flt = df_filtered[df_filtered['flight_id'] == original_flight_id].copy()
    df_filtered_flt = df_filtered_flt.sort_values('timestamp').reset_index(drop=True)
    df_filtered_flt['timestamp'] = pd.to_datetime(df_filtered_flt['timestamp'], utc=True)

    # 读取插值后的数据
    complete_file = complete_dir / f"complete_{date_str}.parquet"
    df_complete = pd.read_parquet(complete_file)
    df_complete_flt = df_complete[df_complete['flight_id'] == original_flight_id].copy()
    df_complete_flt = df_complete_flt.sort_values('timestamp').reset_index(drop=True)
    df_complete_flt['timestamp'] = pd.to_datetime(df_complete_flt['timestamp'], utc=True)

    # 找到异常时刻附近的数据
    time_lower = anomaly_time - pd.Timedelta(seconds=window)
    time_upper = anomaly_time + pd.Timedelta(seconds=window)

    # 过滤后数据的窗口
    mask_filtered = (df_filtered_flt['timestamp'] >= time_lower) & (df_filtered_flt['timestamp'] <= time_upper)
    window_filtered = df_filtered_flt[mask_filtered].copy()

    # 插值后数据的窗口
    mask_complete = (df_complete_flt['timestamp'] >= time_lower) & (df_complete_flt['timestamp'] <= time_upper)
    window_complete = df_complete_flt[mask_complete].copy()

    print(f"[过滤后数据] 在窗口 [{time_lower} ~ {time_upper}] 的数据点:")
    print("-" * 100)
    for idx, row in window_filtered.iterrows():
        lat_str = f"{row['latitude']:.6f}" if pd.notna(row['latitude']) else "NaN"
        lon_str = f"{row['longitude']:.6f}" if pd.notna(row['longitude']) else "NaN"
        alt_str = f"{row['altitude']:.1f}" if pd.notna(row['altitude']) else "NaN"
        print(f"  {row['timestamp']}  |  lat={lat_str:>11}  lon={lon_str:>12}  alt={alt_str:>8}")

    print(f"\n[插值后数据] 在窗口 [{time_lower} ~ {time_upper}] 的数据点:")
    print("-" * 100)
    for idx, row in window_complete.iterrows():
        lat_str = f"{row['latitude']:.6f}" if pd.notna(row['latitude']) else "NaN"
        lon_str = f"{row['longitude']:.6f}" if pd.notna(row['longitude']) else "NaN"
        alt_str = f"{row['altitude']:.1f}" if pd.notna(row['altitude']) else "NaN"
        print(f"  {row['timestamp']}  |  lat={lat_str:>11}  lon={lon_str:>12}  alt={alt_str:>8}")

    # 计算插值后数据的速度
    print(f"\n[速度分析] 插值后数据的逐点速度:")
    print("-" * 100)
    valid = (~window_complete['latitude'].isna()) & (~window_complete['longitude'].isna())
    if valid.sum() > 1:
        valid_data = window_complete[valid].copy().reset_index(drop=True)
        for i in range(len(valid_data) - 1):
            t1 = valid_data.loc[i, 'timestamp']
            t2 = valid_data.loc[i+1, 'timestamp']
            lat1 = valid_data.loc[i, 'latitude']
            lon1 = valid_data.loc[i, 'longitude']
            lat2 = valid_data.loc[i+1, 'latitude']
            lon2 = valid_data.loc[i+1, 'longitude']

            dt = (t2 - t1).total_seconds()
            dist_km = haversine_km(lat1, lon1, lat2, lon2)
            speed_mps = (dist_km * 1000) / dt if dt > 0 else 0

            marker = " ⚠️ 超速!" if speed_mps >= 1000 else ""
            print(f"  {t1} → {t2}")
            print(f"    距离: {dist_km:.3f} km  |  时间差: {dt:.1f} s  |  速度: {speed_mps:.2f} m/s ({speed_mps*3.6:.2f} km/h){marker}")

    # 分析：过滤阶段删除了哪些点
    print(f"\n[关键分析] 插值填补了哪些被过滤器删除的点:")
    print("-" * 100)

    # 找到所有时间戳
    all_times = sorted(set(window_filtered['timestamp'].tolist() + window_complete['timestamp'].tolist()))

    for t in all_times:
        in_filtered = t in window_filtered['timestamp'].values
        in_complete = t in window_complete['timestamp'].values

        if in_filtered and in_complete:
            # 两边都有
            filt_row = window_filtered[window_filtered['timestamp'] == t].iloc[0]
            comp_row = window_complete[window_complete['timestamp'] == t].iloc[0]

            filt_valid = pd.notna(filt_row['latitude']) and pd.notna(filt_row['longitude'])
            comp_valid = pd.notna(comp_row['latitude']) and pd.notna(comp_row['longitude'])

            if not filt_valid and comp_valid:
                # 过滤阶段是NaN，插值后有值 → 这是插值填补的点
                print(f"  {t}  |  过滤阶段: NaN  →  插值后: ({comp_row['latitude']:.6f}, {comp_row['longitude']:.6f})  [插值填补]")
            elif filt_valid and comp_valid:
                # 两边都有效 → 检查是否一致
                lat_diff = abs(filt_row['latitude'] - comp_row['latitude'])
                lon_diff = abs(filt_row['longitude'] - comp_row['longitude'])
                if lat_diff > 1e-6 or lon_diff > 1e-6:
                    print(f"  {t}  |  过滤: ({filt_row['latitude']:.6f}, {filt_row['longitude']:.6f})  →  插值: ({comp_row['latitude']:.6f}, {comp_row['longitude']:.6f})  [值变化!]")
                else:
                    print(f"  {t}  |  有效点，未变化")
            elif filt_valid and not comp_valid:
                # 过滤阶段有效，插值后无效 → 可能被洞宽遮蔽
                print(f"  {t}  |  过滤阶段: ({filt_row['latitude']:.6f}, {filt_row['longitude']:.6f})  →  插值后: NaN  [洞宽遮蔽]")
            else:
                # 两边都无效
                print(f"  {t}  |  两阶段均为 NaN")

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    # 分析第一个异常案例
    analyze_interpolation_around_anomaly(
        original_flight_id=257987764,
        date_str="2022-12-28",
        anomaly_time_str="2022-12-28 04:16:46",
        window=10
    )
