#!/usr/bin/env python3
"""
统计整个插值后数据集的总轨迹数量
"""

import pandas as pd
import os
import glob
from datetime import datetime

def count_trajectories_in_file(file_path):
    """统计单个文件中的轨迹数量"""
    try:
        df = pd.read_parquet(file_path)
        unique_flights = df.flight_id.nunique()
        total_points = len(df)
        return unique_flights, total_points
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return 0, 0

def main():
    """主函数"""
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    # 插值后数据目录
    interp_dir = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/'
    
    if not os.path.exists(interp_dir):
        print(f"目录不存在: {interp_dir}")
        return
    
    # 获取所有parquet文件
    parquet_files = glob.glob(os.path.join(interp_dir, '*.parquet'))
    parquet_files.sort()
    
    if not parquet_files:
        print(f"在 {interp_dir} 中没有找到parquet文件")
        return
    
    print(f"找到 {len(parquet_files)} 个parquet文件")
    print("开始统计轨迹数量...")
    
    total_flights = 0
    total_points = 0
    file_stats = []
    
    for i, file_path in enumerate(parquet_files):
        filename = os.path.basename(file_path)
        print(f"处理文件 {i+1}/{len(parquet_files)}: {filename}")
        
        flights, points = count_trajectories_in_file(file_path)
        total_flights += flights
        total_points += points
        
        file_stats.append({
            'filename': filename,
            'flights': flights,
            'points': points
        })
        
        print(f"  航班数: {flights:,}, 轨迹点数: {points:,}")
    
    print("\n" + "="*60)
    print("整个数据集统计结果:")
    print("="*60)
    print(f"总文件数: {len(parquet_files)}")
    print(f"总航班数: {total_flights:,}")
    print(f"总轨迹点数: {total_points:,}")
    print(f"平均每个文件的航班数: {total_flights/len(parquet_files):.0f}")
    print(f"平均每个航班的轨迹点数: {total_points/total_flights:.0f}")
    
    # 保存详细统计
    stats_df = pd.DataFrame(file_stats)
    stats_df.to_csv('trajectory_count_stats.csv', index=False)
    print(f"\n详细统计已保存到: trajectory_count_stats.csv")
    
    # 计算建议的抽样数量
    print("\n建议的抽样方案:")
    for pct in [10, 20, 30]:
        sample_flights = int(total_flights * pct / 100)
        print(f"  {pct}% 抽样: {sample_flights:,} 个航班")

if __name__ == "__main__":
    main()