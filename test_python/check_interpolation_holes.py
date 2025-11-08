#!/usr/bin/env python3
"""
检查插值后的数据是否还有空洞
"""

import pandas as pd
import numpy as np
from pathlib import Path


def check_segment_holes(segment_flight_id, date_str="2022-12-28"):
    """检查特定segment的空洞情况

    Args:
        segment_flight_id: segmented后的flight_id（如2579877640003）
        date_str: 日期字符串
    """

    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")

    # 解析segment信息
    original_flight_id = segment_flight_id // 10000
    segment_index = segment_flight_id % 10000

    print(f"\n{'='*100}")
    print(f"检查 Segment Flight ID: {segment_flight_id}")
    print(f"  原始航班ID: {original_flight_id}")
    print(f"  分段索引: {segment_index}")
    print(f"  日期: {date_str}")
    print(f"{'='*100}\n")

    # 1. 检查过滤后的数据（插值前）
    print("[1] 检查过滤后数据（插值前）")
    print("-" * 100)
    filtered_dir = base_dir / "classic_filtered_trajectories_doublepass_loop_v8"
    filtered_file = filtered_dir / f"{date_str}.parquet"

    if filtered_file.exists():
        df_filtered = pd.read_parquet(filtered_file)
        df_flt = df_filtered[df_filtered['flight_id'] == original_flight_id].copy()
        df_flt = df_flt.sort_values('timestamp').reset_index(drop=True)
        df_flt['timestamp'] = pd.to_datetime(df_flt['timestamp'], utc=True)

        # 找到这个segment对应的时间范围（大致）
        # 我们需要先从segmented数据中获取时间范围
        segmented_dir = base_dir / "segmented_trajs_doublepass_loop_lim20s_inside_v7"
        segmented_file = segmented_dir / f"segmented_{date_str}.parquet"
        df_seg = pd.read_parquet(segmented_file)
        df_seg_target = df_seg[df_seg['flight_id'] == segment_flight_id].copy()

        if not df_seg_target.empty:
            df_seg_target = df_seg_target.sort_values('timestamp').reset_index(drop=True)
            df_seg_target['timestamp'] = pd.to_datetime(df_seg_target['timestamp'], utc=True)
            time_start = df_seg_target['timestamp'].iloc[0]
            time_end = df_seg_target['timestamp'].iloc[-1]

            print(f"Segment时间范围: {time_start} ~ {time_end}")

            # 在过滤后数据中找到这个时间范围
            mask = (df_flt['timestamp'] >= time_start) & (df_flt['timestamp'] <= time_end)
            df_flt_window = df_flt[mask].copy()

            print(f"过滤后数据在此范围内的点数: {len(df_flt_window)}")
            print(f"其中有效点（经纬度非NaN）: {(~df_flt_window['latitude'].isna()).sum()}")

            # 统计连续NaN的情况
            lat_isna = df_flt_window['latitude'].isna().values
            changes = np.diff(np.concatenate(([False], lat_isna, [False])).astype(int))
            hole_starts = np.where(changes == 1)[0]
            hole_ends = np.where(changes == -1)[0]

            if len(hole_starts) > 0:
                print(f"\n过滤后数据的空洞情况：")
                for i, (start, end) in enumerate(zip(hole_starts, hole_ends), 1):
                    hole_len = end - start
                    t_start = df_flt_window.iloc[start-1]['timestamp'] if start > 0 else None
                    t_end = df_flt_window.iloc[end]['timestamp'] if end < len(df_flt_window) else None
                    if t_start and t_end:
                        dt = (t_end - t_start).total_seconds()
                        print(f"  空洞 #{i}: 长度={hole_len} 点, 时间跨度={dt:.1f}秒, 从 {t_start} 到 {t_end}")

    # 2. 检查插值后的数据
    print(f"\n[2] 检查插值后数据（complete）")
    print("-" * 100)
    complete_dir = base_dir / "interpolate_trajs_doublepass_loop_lim20s_inside_v7"
    complete_file = complete_dir / f"complete_{date_str}.parquet"

    if complete_file.exists():
        df_complete = pd.read_parquet(complete_file)
        df_comp_flt = df_complete[df_complete['flight_id'] == original_flight_id].copy()
        df_comp_flt = df_comp_flt.sort_values('timestamp').reset_index(drop=True)
        df_comp_flt['timestamp'] = pd.to_datetime(df_comp_flt['timestamp'], utc=True)

        # 在相同时间范围内
        mask = (df_comp_flt['timestamp'] >= time_start) & (df_comp_flt['timestamp'] <= time_end)
        df_comp_window = df_comp_flt[mask].copy()

        print(f"插值后数据在此范围内的点数: {len(df_comp_window)}")
        print(f"其中有效点（经纬度非NaN）: {(~df_comp_window['latitude'].isna()).sum()}")

        # 统计连续NaN的情况
        lat_isna = df_comp_window['latitude'].isna().values
        changes = np.diff(np.concatenate(([False], lat_isna, [False])).astype(int))
        hole_starts = np.where(changes == 1)[0]
        hole_ends = np.where(changes == -1)[0]

        if len(hole_starts) > 0:
            print(f"\n插值后数据的空洞情况：")
            for i, (start, end) in enumerate(zip(hole_starts, hole_ends), 1):
                hole_len = end - start
                t_start = df_comp_window.iloc[start-1]['timestamp'] if start > 0 else None
                t_end = df_comp_window.iloc[end]['timestamp'] if end < len(df_comp_window) else None
                if t_start and t_end:
                    dt = (t_end - t_start).total_seconds()
                    print(f"  空洞 #{i}: 长度={hole_len} 点, 时间跨度={dt:.1f}秒, 从 {t_start} 到 {t_end}")

                    # 显示空洞前后的点
                    print(f"    空洞前点: {df_comp_window.iloc[start-1]['timestamp']} | ({df_comp_window.iloc[start-1]['latitude']:.6f}, {df_comp_window.iloc[start-1]['longitude']:.6f})")
                    print(f"    空洞后点: {df_comp_window.iloc[end]['timestamp']} | ({df_comp_window.iloc[end]['latitude']:.6f}, {df_comp_window.iloc[end]['longitude']:.6f})")
        else:
            print("✅ 插值后数据没有空洞！")

    # 3. 检查segmented数据
    print(f"\n[3] 检查切段后数据（segmented）")
    print("-" * 100)

    if not df_seg_target.empty:
        print(f"切段后数据的点数: {len(df_seg_target)}")
        print(f"其中有效点（经纬度非NaN）: {(~df_seg_target['latitude'].isna()).sum()}")

        # 统计连续NaN的情况
        lat_isna = df_seg_target['latitude'].isna().values
        changes = np.diff(np.concatenate(([False], lat_isna, [False])).astype(int))
        hole_starts = np.where(changes == 1)[0]
        hole_ends = np.where(changes == -1)[0]

        if len(hole_starts) > 0:
            print(f"\n⚠️  切段后数据仍有空洞（这不应该发生！）：")
            for i, (start, end) in enumerate(zip(hole_starts, hole_ends), 1):
                hole_len = end - start
                t_start = df_seg_target.iloc[start-1]['timestamp'] if start > 0 else None
                t_end = df_seg_target.iloc[end]['timestamp'] if end < len(df_seg_target) else None
                if t_start and t_end:
                    dt = (t_end - t_start).total_seconds()
                    print(f"  空洞 #{i}: 长度={hole_len} 点, 时间跨度={dt:.1f}秒")
                    print(f"    从 {t_start} 到 {t_end}")
                    print(f"    空洞前点: ({df_seg_target.iloc[start-1]['latitude']:.6f}, {df_seg_target.iloc[start-1]['longitude']:.6f})")
                    print(f"    空洞后点: ({df_seg_target.iloc[end]['latitude']:.6f}, {df_seg_target.iloc[end]['longitude']:.6f})")

                    # 显示空洞内的所有时间戳
                    print(f"    空洞内的时间戳:")
                    for j in range(start, end):
                        ts = df_seg_target.iloc[j]['timestamp']
                        lat = df_seg_target.iloc[j]['latitude']
                        lon = df_seg_target.iloc[j]['longitude']
                        alt = df_seg_target.iloc[j]['altitude']
                        print(f"      {ts} | lat={lat}, lon={lon}, alt={alt}")
        else:
            print("✅ 切段后数据没有空洞！")

        # 检查时间连续性
        print(f"\n时间连续性检查:")
        ts_arr = df_seg_target['timestamp'].values.astype('datetime64[s]').astype(float)
        dt_arr = np.diff(ts_arr)
        max_dt = dt_arr.max()
        print(f"  最大时间间隔: {max_dt:.1f} 秒")

        large_gaps = dt_arr > 20
        if large_gaps.any():
            print(f"  ⚠️  发现 {large_gaps.sum()} 个超过20秒的时间间隔（这不应该发生！）")
            for idx in np.where(large_gaps)[0]:
                print(f"    位置 {idx}: {df_seg_target.iloc[idx]['timestamp']} → {df_seg_target.iloc[idx+1]['timestamp']}, 间隔={dt_arr[idx]:.1f}秒")

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    # 检查用户指定的segment
    check_segment_holes(segment_flight_id=2579877640003, date_str="2022-12-28")
