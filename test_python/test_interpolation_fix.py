#!/usr/bin/env python3
"""
测试修复后的插值算法

目的：验证速度检查能否正确删除超速的插值点
"""

import sys
sys.path.insert(0, '/workspace/aircraft_trajectory/team_likable_jelly/junguo_analysis_for_interpolation')

import pandas as pd
import numpy as np
from pathlib import Path
from regenerate_complete_dataset_fixed import CompleteDatasetGenerator, haversine_m


def test_single_flight(original_flight_id, date_str):
    """测试单个航班的插值修复"""

    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
    filtered_dir = base_dir / "classic_filtered_trajectories_doublepass_loop_v7"

    print(f"\n{'='*100}")
    print(f"测试航班 {original_flight_id} ({date_str})")
    print(f"{'='*100}\n")

    # 读取过滤后的数据
    filtered_file = filtered_dir / f"{date_str}.parquet"
    if not filtered_file.exists():
        print(f"❌ 文件不存在: {filtered_file}")
        return

    df = pd.read_parquet(filtered_file)
    df_flt = df[df['flight_id'] == original_flight_id].copy()

    if df_flt.empty:
        print(f"❌ 未找到航班 {original_flight_id}")
        return

    print(f"原始数据点数: {len(df_flt)}")

    # 使用修复后的插值算法
    generator = CompleteDatasetGenerator()
    df_processed, result = generator.process_trajectory(df_flt)

    if not result['success']:
        print(f"❌ 处理失败: {result.get('reason', 'Unknown')}")
        return

    print(f"\n处理结果:")
    print(f"  处理前点数: {result['points_before']}")
    print(f"  处理后点数: {result['points_after']}")
    print(f"  缺失值: {result['total_missing']}")
    if 'speed_check' in result:
        print(f"  速度检查删除点数: {result['speed_check']['removed_points']}")
        print(f"  速度检查迭代次数: {result['speed_check']['iterations']}")
        print(f"  是否收敛: {result['speed_check']['converged']}")

    # 检查最终数据的速度
    df_processed = df_processed.sort_values('timestamp').reset_index(drop=True)
    df_processed['timestamp'] = pd.to_datetime(df_processed['timestamp'], utc=True)

    valid = (~df_processed['latitude'].isna()) & (~df_processed['longitude'].isna())
    valid_data = df_processed[valid].copy()

    if len(valid_data) > 1:
        lat = valid_data['latitude'].to_numpy()
        lon = valid_data['longitude'].to_numpy()
        ts = valid_data['timestamp'].values.astype('datetime64[s]').astype(float)

        dists = haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
        dts = np.diff(ts)
        speeds_mps = np.zeros(len(dists))
        mask = dts > 0
        speeds_mps[mask] = dists[mask] / dts[mask]

        max_speed = speeds_mps.max() if len(speeds_mps) > 0 else 0
        print(f"\n最终速度统计:")
        print(f"  最大速度: {max_speed:.2f} m/s ({max_speed*3.6:.2f} km/h)")

        # 检查是否还有超速点
        high_speed = speeds_mps >= 1000
        if high_speed.any():
            print(f"  ⚠️  警告：仍有 {high_speed.sum()} 个超速点 (≥1000 m/s)!")
            for idx in np.where(high_speed)[0][:5]:  # 只显示前5个
                print(f"    位置 {idx}: {speeds_mps[idx]:.2f} m/s")
        else:
            print(f"  ✅ 无超速点 (所有点 < 1000 m/s)")

        # 检查600 m/s阈值
        high_speed_600 = speeds_mps >= 600
        if high_speed_600.any():
            print(f"  ⚠️  有 {high_speed_600.sum()} 个点超过600 m/s阈值")
        else:
            print(f"  ✅ 所有点 < 600 m/s（修复阈值）")

    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    # 测试几个之前有异常的航班
    test_cases = [
        (257987764, "2022-12-28"),  # 最大异常速度 2353.74 m/s
        (250702687, "2022-04-10"),  # 异常速度 2230.57 m/s
        (253258084, "2022-07-08"),  # 异常速度 1697.71 m/s
    ]

    for fid, date in test_cases:
        test_single_flight(fid, date)
