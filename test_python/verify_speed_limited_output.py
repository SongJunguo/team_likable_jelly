#!/usr/bin/env python3
"""
验证速度限制后的输出文件质量
"""

import pandas as pd
import numpy as np
import sys

sys.path.insert(0, '/workspace/aircraft_trajectory/team_likable_jelly/junguo_analysis_for_interpolation')
from split_segments_with_speed_check import haversine_m


def verify_segmented_file(file_path, max_speed_mps=600):
    """验证切段文件的质量"""

    print(f"\n{'='*100}")
    print(f"验证文件: {file_path}")
    print(f"{'='*100}\n")

    df = pd.read_parquet(file_path)

    if df.empty:
        print("⚠️  文件为空")
        return

    print(f"总点数: {len(df)}")
    print(f"Segment数: {df['segment_index'].nunique() if 'segment_index' in df.columns else 'N/A'}")
    print(f"航班数: {df['original_flight_id'].nunique() if 'original_flight_id' in df.columns else 'N/A'}")

    # 检查每个segment
    issues = []
    total_segments = 0
    max_speed_overall = 0

    for flight_id, seg in df.groupby('flight_id'):
        total_segments += 1
        seg = seg.sort_values('timestamp').reset_index(drop=True)
        seg['timestamp'] = pd.to_datetime(seg['timestamp'], utc=True)

        # 检查NaN
        nan_count = seg[['latitude', 'longitude', 'altitude']].isna().any(axis=1).sum()
        if nan_count > 0:
            issues.append(f"Segment {flight_id}: 有 {nan_count} 个NaN点")

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

            max_speed = speeds_mps.max() if len(speeds_mps) > 0 else 0
            max_speed_overall = max(max_speed_overall, max_speed)

            overspeed = speeds_mps >= max_speed_mps
            if overspeed.any():
                issues.append(f"Segment {flight_id}: 有 {overspeed.sum()} 个超速点 (最大: {speeds_mps.max():.2f} m/s)")

            # 检查时间间隔
            max_dt = dts.max()
            if max_dt > 20:
                issues.append(f"Segment {flight_id}: 最大时间间隔 {max_dt:.1f}s > 20s")

    print(f"\n检查结果:")
    print(f"  检查了 {total_segments} 个segment")
    print(f"  最大速度: {max_speed_overall:.2f} m/s ({max_speed_overall*3.6:.2f} km/h)")

    if issues:
        print(f"\n⚠️  发现 {len(issues)} 个问题:")
        for issue in issues[:10]:  # 只显示前10个
            print(f"    - {issue}")
        if len(issues) > 10:
            print(f"    ... 还有 {len(issues)-10} 个问题")
    else:
        print(f"\n✅ 所有segment质量检查通过！")
        print(f"   - 无NaN")
        print(f"   - 无超速点 (所有点 < {max_speed_mps} m/s)")
        print(f"   - 时间连续 (所有间隔 ≤ 20s)")


if __name__ == "__main__":
    verify_segmented_file("/tmp/test_speed_limit_segmentation/segmented_2022-12-28.parquet")
