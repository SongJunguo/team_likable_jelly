#!/usr/bin/env python3
"""测试 FilterMaxSpeedSkipNaN 过滤器"""

import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '/workspace/aircraft_trajectory/team_likable_jelly')

from filterclassic import FilterMaxSpeedSkipNaN

def test_skipnan_filter():
    """测试跨NaN速度检测"""

    # 构造测试数据：模拟你的案例
    data = {
        'flight_id': [1] * 11,
        'timestamp': pd.date_range('2022-02-21 08:40:00', periods=11, freq='1s', tz='UTC'),
        'latitude': [
            41.287445,   # 点0 - 保留
            np.nan,      # 点1 - 被卡死过滤器删除
            np.nan,      # 点2 - 被卡死过滤器删除
            np.nan,      # 点3 - 被超速过滤器删除
            np.nan,      # 点4 - 被其他过滤器删除
            np.nan,      # 点5 - 被其他过滤器删除
            np.nan,      # 点6 - 被其他过滤器删除
            41.321960,   # 点7 - 保留（但与点0形成间接超速！）
            41.322372,   # 点8
            41.322792,   # 点9
            41.323220,   # 点10
        ],
        'longitude': [
            29.408020,   # 点0
            np.nan,
            np.nan,
            np.nan,
            np.nan,
            np.nan,
            np.nan,
            29.286499,   # 点7
            29.284912,
            29.283433,
            29.281954,
        ],
        'altitude': [8925.0] * 11,
    }

    df = pd.DataFrame(data)

    print("=" * 70)
    print("测试 FilterMaxSpeedSkipNaN")
    print("=" * 70)

    print("\n【测试数据】")
    print("点0 (08:40:00): (41.287445, 29.408020)")
    print("点1-6: 全部NaN（被前面的过滤器删除）")
    print("点7 (08:40:07): (41.321960, 29.286499)")
    print("\n点0→点7:")
    print("  - 时间间隔: 7秒")
    print("  - 距离: 约10.0 km")
    print("  - 速度: 约1428 m/s >> 600 m/s ✗ 应该被删除")

    # 应用过滤器
    filter_skipnan = FilterMaxSpeedSkipNaN(max_speed_mps=600, max_iterations=5)
    df_filtered = filter_skipnan.apply(df)

    print("\n【过滤后结果】")
    for i in [0, 7, 8, 9]:
        row = df_filtered.iloc[i]
        lat = row['latitude']
        lon = row['longitude']
        status = "NaN（被删除）" if pd.isna(lat) else f"({lat:.6f}, {lon:.6f})"
        print(f"点{i}: {status}")

    # 验证结果
    print("\n【验证】")
    if pd.isna(df_filtered.iloc[0]['latitude']) and pd.isna(df_filtered.iloc[7]['latitude']):
        print("✅ 测试通过：点0和点7都被删除（间接超速被捕获）")
        return True
    elif pd.isna(df_filtered.iloc[0]['latitude']):
        print("⚠️  部分通过：点0被删除，但点7未删除")
        return False
    elif pd.isna(df_filtered.iloc[7]['latitude']):
        print("⚠️  部分通过：点7被删除，但点0未删除")
        return False
    else:
        print("❌ 测试失败：点0和点7都未被删除（间接超速未被捕获）")
        return False


def test_real_data():
    """测试真实数据中的异常航班"""

    print("\n" + "=" * 70)
    print("测试真实数据：2022-02-21 航班 249659588")
    print("=" * 70)

    try:
        # 读取过滤后的数据
        filtered_file = "/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v5/2022-02-21.parquet"
        df = pd.read_parquet(filtered_file)

        flight = df[df['flight_id'] == 249659588].sort_values('timestamp')
        subset = flight[(flight['timestamp'] >= '2022-02-21 08:40:00') &
                       (flight['timestamp'] <= '2022-02-21 08:40:10')].copy()

        print(f"\n【过滤前】（经过前面的过滤器但未经过FilterMaxSpeedSkipNaN）")
        print(f"点数: {len(subset)}")

        # 统计有效点
        valid = (~subset['latitude'].isna()) & (~subset['longitude'].isna())
        print(f"有效点数: {valid.sum()}")
        print(f"有效点索引: {list(subset.index[valid].values - subset.index[0])}")

        # 应用FilterMaxSpeedSkipNaN
        filter_skipnan = FilterMaxSpeedSkipNaN(max_speed_mps=600, max_iterations=5)
        subset_filtered = filter_skipnan.apply(subset)

        # 统计过滤后的有效点
        valid_after = (~subset_filtered['latitude'].isna()) & (~subset_filtered['longitude'].isna())
        print(f"\n【过滤后】（经过FilterMaxSpeedSkipNaN）")
        print(f"有效点数: {valid_after.sum()}")
        print(f"有效点索引: {list(subset_filtered.index[valid_after].values - subset_filtered.index[0])}")

        deleted = valid.sum() - valid_after.sum()
        print(f"\n删除了 {deleted} 个点")

        if deleted > 0:
            print("✅ FilterMaxSpeedSkipNaN 成功删除了间接超速点")
            return True
        else:
            print("⚠️  FilterMaxSpeedSkipNaN 没有删除任何点")
            return False

    except FileNotFoundError as e:
        print(f"❌ 文件未找到: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    print("\n" + "🔬 " + "测试 FilterMaxSpeedSkipNaN 过滤器".center(66) + " 🔬\n")

    # 测试1：构造数据测试
    result1 = test_skipnan_filter()

    # 测试2：真实数据测试
    result2 = test_real_data()

    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    print(f"构造数据测试: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"真实数据测试: {'✅ 通过' if result2 else '❌ 失败'}")
    print()
