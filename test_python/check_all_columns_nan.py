#!/usr/bin/env python3
"""
检查所有列的NaN情况
"""

import pandas as pd
import numpy as np
from pathlib import Path


def check_all_columns_nan(segment_flight_id, date_str="2022-12-28", time_start_str=None, time_end_str=None):
    """检查所有列的NaN情况

    Args:
        segment_flight_id: segmented后的flight_id
        date_str: 日期字符串
        time_start_str: 可选，检查的起始时间
        time_end_str: 可选，检查的结束时间
    """

    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
    segmented_dir = base_dir / "segmented_trajs_doublepass_loop_lim20s_inside_v7"
    segmented_file = segmented_dir / f"segmented_{date_str}.parquet"

    print(f"\n{'='*100}")
    print(f"检查 Segment {segment_flight_id} 的所有列NaN情况")
    print(f"{'='*100}\n")

    df = pd.read_parquet(segmented_file)
    df_seg = df[df['flight_id'] == segment_flight_id].copy()
    df_seg = df_seg.sort_values('timestamp').reset_index(drop=True)
    df_seg['timestamp'] = pd.to_datetime(df_seg['timestamp'], utc=True)

    # 如果指定了时间范围，则过滤
    if time_start_str:
        time_start = pd.to_datetime(time_start_str, utc=True)
        df_seg = df_seg[df_seg['timestamp'] >= time_start]
    if time_end_str:
        time_end = pd.to_datetime(time_end_str, utc=True)
        df_seg = df_seg[df_seg['timestamp'] <= time_end]

    print(f"数据点总数: {len(df_seg)}")
    print(f"时间范围: {df_seg['timestamp'].iloc[0]} ~ {df_seg['timestamp'].iloc[-1]}")
    print(f"\n各列的NaN统计:")
    print("-" * 100)

    # 检查每一列的NaN情况
    for col in df_seg.columns:
        if col in ['timestamp', 'flight_id', 'original_flight_id', 'segment_index', 'flight_seg_info']:
            continue  # 跳过ID和时间列

        nan_count = df_seg[col].isna().sum()
        total = len(df_seg)
        pct = 100 * nan_count / total if total > 0 else 0

        if nan_count > 0:
            print(f"  {col:20s}: {nan_count:5d} / {total:5d} ({pct:5.1f}%) NaN")

            # 如果有NaN，显示NaN的时间段
            is_nan = df_seg[col].isna().values
            changes = np.diff(np.concatenate(([False], is_nan, [False])).astype(int))
            hole_starts = np.where(changes == 1)[0]
            hole_ends = np.where(changes == -1)[0]

            if len(hole_starts) > 0 and len(hole_starts) <= 10:  # 只显示前10个空洞
                print(f"    空洞详情:")
                for i, (start, end) in enumerate(zip(hole_starts, hole_ends), 1):
                    hole_len = end - start
                    t_start = df_seg.iloc[start]['timestamp']
                    t_end = df_seg.iloc[end-1]['timestamp']
                    dt = (t_end - t_start).total_seconds()
                    print(f"      #{i}: {t_start} ~ {t_end} ({hole_len} 点, {dt:.1f}秒)")
        else:
            print(f"  {col:20s}: ✅ 无NaN")

    # 详细显示时间范围内的所有数据（如果数据量不大）
    if len(df_seg) <= 30:
        print(f"\n完整数据明细:")
        print("-" * 100)
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 150)
        print(df_seg[['timestamp', 'latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']].to_string(index=True))

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    # 检查整个segment
    check_all_columns_nan(segment_flight_id=2579877640003, date_str="2022-12-28")

    # 也检查用户提到的特定时间范围
    print("\n" + "="*100)
    print("检查用户提到的时间范围: 04:16:47 ~ 04:17:51")
    print("="*100)
    check_all_columns_nan(
        segment_flight_id=2579877640003,
        date_str="2022-12-28",
        time_start_str="2022-12-28 04:16:47",
        time_end_str="2022-12-28 04:17:51"
    )
