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


def test_partial_coords():
    """测试部分坐标点的清理功能"""

    print("\n" + "=" * 70)
    print("测试部分坐标点清理")
    print("=" * 70)

    # 构造包含部分坐标的测试数据
    data = {
        'flight_id': [1] * 10,
        'timestamp': pd.date_range('2022-02-21 08:40:00', periods=10, freq='1s', tz='UTC'),
        'latitude': [
            41.0,      # 点0 - 正常
            41.1,      # 点1 - 正常
            41.2,      # 点2 - 只有纬度（经度NaN）
            41.3,      # 点3 - 只有纬度（经度NaN）
            np.nan,    # 点4 - 只有经度（纬度NaN）
            41.5,      # 点5 - 正常
            41.6,      # 点6 - 正常
            np.nan,    # 点7 - 经纬度都NaN
            41.8,      # 点8 - 正常
            41.9,      # 点9 - 正常
        ],
        'longitude': [
            120.0,     # 点0
            120.1,     # 点1
            np.nan,    # 点2 - 经度NaN
            np.nan,    # 点3 - 经度NaN
            120.4,     # 点4 - 只有经度
            120.5,     # 点5
            120.6,     # 点6
            np.nan,    # 点7 - 经度NaN
            120.8,     # 点8
            120.9,     # 点9
        ],
        'altitude': [1000.0] * 10,
    }

    df = pd.DataFrame(data)

    print("\n【测试数据】")
    print("点0-1: 正常（经纬度都有）")
    print("点2-3: 只有纬度（经度NaN）← 应该被清理")
    print("点4:   只有经度（纬度NaN）← 应该被清理")
    print("点5-6: 正常（经纬度都有）")
    print("点7:   经纬度都NaN")
    print("点8-9: 正常（经纬度都有）")

    # 应用过滤器
    filter_skipnan = FilterMaxSpeedSkipNaN(max_speed_mps=600, max_iterations=5)
    df_filtered = filter_skipnan.apply(df)

    print("\n【过滤后结果】")
    for i in range(10):
        row = df_filtered.iloc[i]
        lat = row['latitude']
        lon = row['longitude']

        if pd.isna(lat) and pd.isna(lon):
            status = "经纬度都NaN"
        elif pd.isna(lat):
            status = f"只有经度（异常！）"
        elif pd.isna(lon):
            status = f"只有纬度（异常！）"
        else:
            status = f"({lat:.1f}, {lon:.1f})"

        print(f"点{i}: {status}")

    # 验证结果
    print("\n【验证】")
    partial_after = (df_filtered['latitude'].isna() & ~df_filtered['longitude'].isna()) | \
                    (~df_filtered['latitude'].isna() & df_filtered['longitude'].isna())

    if not partial_after.any():
        print("✅ 测试通过：所有部分坐标点都被清理（点2-4）")
        return True
    else:
        print(f"❌ 测试失败：仍有{partial_after.sum()}个部分坐标点")
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

    # 测试1：跨NaN速度检测
    result1 = test_skipnan_filter()

    # 测试2：部分坐标点清理
    result2 = test_partial_coords()

    # 测试3：真实数据测试
    result3 = test_real_data()

    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    print(f"跨NaN速度检测: {'✅ 通过' if result1 else '❌ 失败'}")
    print(f"部分坐标清理: {'✅ 通过' if result2 else '❌ 失败'}")
    print(f"真实数据测试: {'✅ 通过' if result3 else '❌ 失败'}")
    print()
