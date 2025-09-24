#!/usr/bin/env python3
"""
检查数据来源和flight_id匹配情况
"""

import pandas as pd
import os

def check_data_sources():
    """检查数据来源"""
    
    print("🔍 检查数据来源和flight_id匹配情况")
    print("=" * 60)
    
    # 1. 检查trajectory_analysis.parquet的数据来源
    analysis_file = 'junguo_analysis_for_opensky2022/analysis_for_interpolation/full_365_analysis_output_v2/trajectory_analysis.parquet'
    df_analysis = pd.read_parquet(analysis_file)
    
    print("📊 trajectory_analysis.parquet 数据概况:")
    print(f"   总轨迹数: {len(df_analysis):,}")
    print(f"   flight_id范围: {df_analysis.flight_id.min():,} - {df_analysis.flight_id.max():,}")
    
    # 2. 检查滤波数据的flight_id范围
    filtered_dir = 'opensky_2024_PRC_dataset/classic_filtered_trajectories'
    sample_file = os.path.join(filtered_dir, '2022-01-01.parquet')
    df_filtered = pd.read_parquet(sample_file)
    
    print(f"\n📊 滤波数据 (2022-01-01) 概况:")
    print(f"   数据点数: {len(df_filtered):,}")
    print(f"   轨迹数: {df_filtered.flight_id.nunique():,}")
    print(f"   flight_id范围: {df_filtered.flight_id.min():,} - {df_filtered.flight_id.max():,}")
    
    # 3. 检查是否有重叠
    analysis_ids = set(df_analysis.flight_id.values)
    filtered_ids = set(df_filtered.flight_id.values)
    overlap = analysis_ids.intersection(filtered_ids)
    
    print(f"\n🔗 数据匹配情况:")
    print(f"   分析数据中的flight_id数量: {len(analysis_ids):,}")
    print(f"   滤波数据中的flight_id数量: {len(filtered_ids):,}")
    print(f"   重叠的flight_id数量: {len(overlap):,}")
    
    if len(overlap) > 0:
        print(f"   重叠的前5个ID: {sorted(list(overlap))[:5]}")
        
        # 测试一个重叠的ID
        test_id = sorted(list(overlap))[0]
        print(f"\n🧪 测试flight_id {test_id}:")
        
        # 在分析数据中的信息
        analysis_info = df_analysis[df_analysis.flight_id == test_id].iloc[0]
        print(f"   分析数据中的缺失率: {analysis_info.get('latitude_missing_rate', 'N/A'):.4f}")
        
        # 在滤波数据中的信息
        filtered_info = df_filtered[df_filtered.flight_id == test_id]
        print(f"   滤波数据中的数据点数: {len(filtered_info)}")
        print(f"   滤波数据中的缺失情况:")
        print(f"     latitude: {filtered_info.latitude.isnull().sum()}/{len(filtered_info)}")
        print(f"     longitude: {filtered_info.longitude.isnull().sum()}/{len(filtered_info)}")
        
    else:
        print("❌ 没有找到重叠的flight_id！")
        print("\n可能的原因:")
        print("1. 分析数据和滤波数据来自不同的数据集")
        print("2. flight_id编码方式不同")
        print("3. 数据处理过程中ID发生了变化")
        
        # 检查更多日期文件
        print("\n🔍 检查更多日期文件...")
        date_files = sorted([f for f in os.listdir(filtered_dir) if f.endswith('.parquet')])[:5]
        
        total_filtered_ids = set()
        for date_file in date_files:
            df_date = pd.read_parquet(os.path.join(filtered_dir, date_file))
            date_ids = set(df_date.flight_id.values)
            total_filtered_ids.update(date_ids)
            
            overlap_date = analysis_ids.intersection(date_ids)
            if len(overlap_date) > 0:
                print(f"   {date_file}: 找到 {len(overlap_date)} 个重叠ID")
                break
        
        print(f"   前5个日期文件总共包含 {len(total_filtered_ids):,} 个唯一flight_id")
        final_overlap = analysis_ids.intersection(total_filtered_ids)
        print(f"   与分析数据的重叠: {len(final_overlap):,} 个")

if __name__ == "__main__":
    check_data_sources()