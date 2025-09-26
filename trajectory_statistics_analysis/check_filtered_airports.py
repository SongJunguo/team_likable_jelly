#!/usr/bin/env python3
"""
检查筛选过的机场数据文件 airports_tz.parquet
"""

import pandas as pd
import numpy as np

def check_filtered_airports():
    """检查筛选过的机场数据文件"""
    
    # 读取筛选过的机场数据
    airports_file = "/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/airports_tz.parquet"
    
    print("正在读取筛选过的机场数据...")
    airports_df = pd.read_parquet(airports_file)
    
    print(f"\n=== 筛选过的机场数据基本信息 ===")
    print(f"总机场数量: {len(airports_df)}")
    print(f"数据列: {list(airports_df.columns)}")
    print(f"数据形状: {airports_df.shape}")
    
    print(f"\n=== 数据类型 ===")
    print(airports_df.dtypes)
    
    print(f"\n=== 前10行数据 ===")
    print(airports_df.head(10))
    
    print(f"\n=== 机场类型分布 ===")
    if 'type' in airports_df.columns:
        print(airports_df['type'].value_counts())
    
    print(f"\n=== 地理分布统计 ===")
    if 'latitude_deg' in airports_df.columns and 'longitude_deg' in airports_df.columns:
        print(f"纬度范围: {airports_df['latitude_deg'].min():.2f} 到 {airports_df['latitude_deg'].max():.2f}")
        print(f"经度范围: {airports_df['longitude_deg'].min():.2f} 到 {airports_df['longitude_deg'].max():.2f}")
    
    print(f"\n=== IATA代码统计 ===")
    if 'iata_code' in airports_df.columns:
        iata_count = airports_df['iata_code'].notna().sum()
        print(f"有IATA代码的机场: {iata_count} ({iata_count/len(airports_df)*100:.1f}%)")
        print(f"IATA代码示例: {airports_df['iata_code'].dropna().head(10).tolist()}")
    
    print(f"\n=== ICAO代码统计 ===")
    if 'ident' in airports_df.columns:
        icao_count = airports_df['ident'].notna().sum()
        print(f"有ICAO代码的机场: {icao_count} ({icao_count/len(airports_df)*100:.1f}%)")
        print(f"ICAO代码示例: {airports_df['ident'].dropna().head(10).tolist()}")
    
    print(f"\n=== 机场名称示例 ===")
    if 'name' in airports_df.columns:
        print("机场名称示例:")
        for i, name in enumerate(airports_df['name'].head(10)):
            print(f"  {i+1}. {name}")
    
    # 检查是否有时区信息
    tz_columns = [col for col in airports_df.columns if 'tz' in col.lower() or 'time' in col.lower()]
    if tz_columns:
        print(f"\n=== 时区相关列 ===")
        print(f"时区相关列: {tz_columns}")
        for col in tz_columns:
            print(f"{col}: {airports_df[col].nunique()} 个不同值")
    
    return airports_df

if __name__ == "__main__":
    airports_df = check_filtered_airports()