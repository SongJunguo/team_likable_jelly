#!/usr/bin/env python3
"""
测试插值功能，调试失败原因
"""

import pandas as pd
import sys
import traceback
sys.path.append('/workspace/aircraft_trajectory/team_likable_jelly')
import interpolate

def test_interpolation():
    """测试插值功能"""
    
    print("🔍 测试插值功能")
    print("=" * 50)
    
    # 读取第一个高质量轨迹ID
    with open('high_quality_flight_ids.txt', 'r') as f:
        first_flight_id = int(f.readline().strip())
    
    print(f"测试flight_id: {first_flight_id}")
    
    # 从第一个日期文件中找到这个轨迹
    df_day = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet')
    df_trajectory = df_day[df_day['flight_id'] == first_flight_id]
    
    if len(df_trajectory) == 0:
        print("❌ 在第一个日期文件中未找到该轨迹")
        return
    
    print(f"✅ 找到轨迹，数据量: {len(df_trajectory)}")
    print("\n📊 轨迹数据结构:")
    print(df_trajectory.head())
    
    print("\n📊 缺失情况:")
    missing_info = df_trajectory.isnull().sum()
    print(missing_info)
    
    print("\n📊 数据类型:")
    print(df_trajectory.dtypes)
    
    # 检查必需的列
    required_columns = ['timestamp', 'latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    missing_columns = [col for col in required_columns if col not in df_trajectory.columns]
    if missing_columns:
        print(f"❌ 缺少必需的列: {missing_columns}")
        return
    
    # 按时间排序
    df_trajectory = df_trajectory.sort_values('timestamp').reset_index(drop=True)
    
    print("\n🔧 尝试插值...")
    try:
        # 设置插值参数
        interpolate.MAX_HOLE_SIZE = 10
        
        result = interpolate.interpolate(df_trajectory, 1e-2)
        print("✅ 插值成功！")
        print(f"插值后数据量: {len(result)}")
        
        # 检查插值后的缺失情况
        print("\n📊 插值后缺失情况:")
        print(result.isnull().sum())
        
        return result
        
    except Exception as e:
        print(f"❌ 插值失败: {e}")
        print("\n详细错误信息:")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_interpolation()