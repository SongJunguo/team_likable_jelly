#!/usr/bin/env python3
"""
测试新的速度感知切段逻辑

验证：
1. 超速点被正确删除（设为NaN）
2. NaN行被正确删除
3. 切段后每个segment无NaN、无超速、时间连续
"""

import sys
sys.path.insert(0, '/workspace/aircraft_trajectory/team_likable_jelly/junguo_analysis_for_interpolation')

import pandas as pd
import numpy as np
from pathlib import Path
from split_segments_with_speed_check import split_one_flight, haversine_m


def test_segmentation(original_flight_id, date_str):
    """测试单个航班的切段逻辑"""

    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
    complete_dir = base_dir / "interpolate_trajs_doublepass_loop_lim20s_inside_v7"

    print(f"\n{'='*100}")
    print(f"测试航班 {original_flight_id} ({date_str})")
    print(f"{'='*100}\n")

    # 读取插值后的数据（这是切段的输入）
    complete_file = complete_dir / f"complete_{date_str}.parquet"
    if not complete_file.exists():
        print(f"❌ 文件不存在: {complete_file}")
        return

    df = pd.read_parquet(complete_file)
    df_flt = df[df['flight_id'] == original_flight_id].copy()

    if df_flt.empty:
        print(f"❌ 未找到航班 {original_flight_id}")
        return

    df_flt = df_flt.sort_values('timestamp').reset_index(drop=True)
    df_flt['timestamp'] = pd.to_datetime(df_flt['timestamp'], utc=True)

    # 检查原始数据的速度
    print(f"[原始数据（插值后）]")
    print(f"  总点数: {len(df_flt)}")

    valid = (~df_flt['latitude'].isna()) & (~df_flt['longitude'].isna())
    valid_count = valid.sum()
    print(f"  有效点（经纬度非NaN）: {valid_count}")

    if valid_count > 1:
        valid_data = df_flt[valid].copy()
        lat = valid_data['latitude'].to_numpy()
        lon = valid_data['longitude'].to_numpy()
        ts = valid_data['timestamp'].values.astype('datetime64[s]').astype(float)

        dists = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
        dts = np.diff(ts)
        speeds_mps = np.zeros(len(dists))
        mask = dts > 0
        speeds_mps[mask] = dists[mask] / dts[mask]

        max_speed = speeds_mps.max()
        print(f"  最大速度: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")

        # 统计超速点
        overspeed_600 = (speeds_mps >= 600).sum()
        overspeed_1000 = (speeds_mps >= 1000).sum()
        print(f"  超速点 (≥600 m/s): {overspeed_600}")
        print(f"  超速点 (≥1000 m/s): {overspeed_1000}")

    # 执行切段
    print(f"\n[执行切段]")
    print(f"  参数: max_dt=20s, max_speed=600m/s, min_points=30, min_duration=120s")

    segments = split_one_flight(
        df_flt,
        required_cols=['latitude', 'longitude', 'altitude'],
        max_dt=20,
        max_speed_mps=600.0,
        min_points=30,
        min_duration=120
    )

    print(f"  输出segment数: {len(segments)}")

    if len(segments) == 0:
        print(f"  ⚠️  没有生成任何segment")
        return

    # 检查每个segment
    print(f"\n[Segment质量检查]")
    for i, seg in enumerate(segments, 1):
        seg = seg.sort_values('timestamp').reset_index(drop=True)
        seg['timestamp'] = pd.to_datetime(seg['timestamp'], utc=True)

        print(f"\n  Segment #{i}:")
        print(f"    点数: {len(seg)}")
        print(f"    时间范围: {seg['timestamp'].iloc[0]} ~ {seg['timestamp'].iloc[-1]}")

        # 检查NaN
        nan_count = seg[['latitude', 'longitude', 'altitude']].isna().any(axis=1).sum()
        if nan_count > 0:
            print(f"    ❌ 有 {nan_count} 个NaN点（不应该有！）")
        else:
            print(f"    ✅ 无NaN")

        # 检查速度
        if len(seg) > 1:
            lat = seg['latitude'].to_numpy()
            lon = seg['longitude'].to_numpy()
            ts = seg['timestamp'].values.astype('datetime64[s]').astype(float)

            dists = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
            dts = np.diff(ts)
            speeds_mps = np.zeros(len(dists))
            mask = dts > 0
            speeds_mps[mask] = dists[mask] / dts[mask]

            max_speed = speeds_mps.max()
            print(f"    最大速度: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")

            overspeed = (speeds_mps >= 600).sum()
            if overspeed > 0:
                print(f"    ❌ 有 {overspeed} 个超速点 (≥600 m/s)（不应该有！）")
            else:
                print(f"    ✅ 无超速点")

            # 检查时间连续性
            max_dt = dts.max()
            print(f"    最大时间间隔: {max_dt:.1f} s")
            if max_dt > 20:
                print(f"    ❌ 超过20秒阈值（不应该有！）")
            else:
                print(f"    ✅ 时间连续")

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    # 测试几个之前有异常的航班
    test_cases = [
        (257987764, "2022-12-28"),  # 最大异常速度 2353.74 m/s
        (250702687, "2022-04-10"),  # 异常速度 2230.57 m/s
        (253258084, "2022-07-08"),  # 异常速度 1697.71 m/s
    ]

    for fid, date in test_cases:
        test_segmentation(fid, date)
