#!/usr/bin/env python3
"""
验证OpenSky数据集中各种元数据的具体来源
"""

import pandas as pd
import numpy as np
import os

def verify_flight_metadata():
    """验证航班元数据来源"""
    print("=== 1. 航班元数据分析 (challenge_set.csv) ===")
    
    try:
        # 读取挑战集文件
        challenge_df = pd.read_csv('../opensky_2024_PRC_dataset/challenge_set.csv', nrows=10)
        print(f"文件大小: {challenge_df.shape}")
        print(f"字段数量: {len(challenge_df.columns)}")
        print(f"字段列表:")
        for i, col in enumerate(challenge_df.columns):
            print(f"  {i+1:2d}. {col}")
        
        print(f"\n样本数据:")
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', None)
        print(challenge_df[['flight_id', 'callsign', 'adep', 'ades', 'aircraft_type', 'tow']].head(3))
        
    except Exception as e:
        print(f"❌ 读取challenge_set.csv失败: {e}")

def verify_weather_data():
    """验证天气数据来源"""
    print("\n=== 2. 天气数据分析 (METARs.parquet) ===")
    
    try:
        # 读取METAR天气数据
        metars_df = pd.read_parquet('../opensky_2024_PRC_dataset/METARs.parquet')
        print(f"文件大小: {metars_df.shape}")
        print(f"字段数量: {len(metars_df.columns)}")
        print(f"时间范围: {metars_df['valid'].min()} 到 {metars_df['valid'].max()}")
        print(f"气象站数量: {metars_df['station'].nunique():,}")
        
        print(f"\n字段列表:")
        for i, col in enumerate(metars_df.columns):
            print(f"  {i+1:2d}. {col}")
        
        # 分析气象站地理分布
        print(f"\n气象站地理分布样本:")
        station_sample = metars_df[['station', 'lat', 'lon']].drop_duplicates().head(10)
        print(station_sample)
        
        # 检查主要机场的气象站
        major_airports = ['KJFK', 'KLAX', 'KORD', 'EGLL', 'LFPG', 'EDDF']
        airport_weather = metars_df[metars_df['station'].isin(major_airports)]
        if len(airport_weather) > 0:
            print(f"\n主要机场气象站数据:")
            airport_stats = airport_weather.groupby('station').agg({
                'valid': ['count', 'min', 'max'],
                'lat': 'first',
                'lon': 'first'
            }).round(4)
            print(airport_stats.head())
        
    except Exception as e:
        print(f"❌ 读取METARs.parquet失败: {e}")

def verify_airport_info():
    """验证机场信息来源"""
    print("\n=== 3. 机场信息分析 (airports_tz.parquet) ===")
    
    try:
        # 读取机场信息
        airports_df = pd.read_parquet('../opensky_2024_PRC_dataset/airports_tz.parquet')
        print(f"文件大小: {airports_df.shape}")
        print(f"字段数量: {len(airports_df.columns)}")
        
        print(f"\n字段列表:")
        for i, col in enumerate(airports_df.columns):
            print(f"  {i+1}. {col}")
        
        print(f"\n样本机场信息:")
        print(airports_df.head())
        
        # 检查主要机场
        major_airports = ['KJFK', 'KLAX', 'KORD', 'EGLL', 'LFPG', 'EDDF']
        if 'icao' in airports_df.columns:
            major_airport_info = airports_df[airports_df['icao'].isin(major_airports)]
            if len(major_airport_info) > 0:
                print(f"\n主要机场详细信息:")
                print(major_airport_info[['icao', 'name', 'city', 'country', 'latitude', 'longitude']])
        
    except Exception as e:
        print(f"❌ 读取airports_tz.parquet失败: {e}")

def verify_trajectory_weather():
    """验证轨迹数据中的天气信息"""
    print("\n=== 4. 轨迹数据中的天气信息 ===")
    
    try:
        # 读取轨迹数据
        traj_df = pd.read_parquet('../opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet')
        
        # 找出天气相关字段
        weather_fields = []
        for col in traj_df.columns:
            if any(keyword in col.lower() for keyword in ['wind', 'temp', 'humid']):
                weather_fields.append(col)
        
        print(f"轨迹数据中的天气字段: {weather_fields}")
        
        if weather_fields:
            # 分析天气数据的特征
            print(f"\n天气字段数据特征:")
            for field in weather_fields:
                print(f"  {field}:")
                print(f"    范围: {traj_df[field].min():.3f} 到 {traj_df[field].max():.3f}")
                print(f"    缺失: {traj_df[field].isnull().sum():,} ({traj_df[field].isnull().mean()*100:.2f}%)")
            
            # 检查单个航班的天气数据变化
            sample_flight = traj_df[traj_df.flight_id == traj_df.flight_id.iloc[0]]
            print(f"\n单个航班天气数据变化范围:")
            for field in weather_fields:
                field_range = sample_flight[field].max() - sample_flight[field].min()
                print(f"  {field}: 变化范围 {field_range:.3f}")
        
    except Exception as e:
        print(f"❌ 读取轨迹数据失败: {e}")

def verify_submission_data():
    """验证提交数据格式"""
    print("\n=== 5. 提交集数据分析 ===")
    
    for filename in ['final_submission_set.csv', 'submission_set.csv']:
        try:
            filepath = f'../opensky_2024_PRC_dataset/{filename}'
            if os.path.exists(filepath):
                sub_df = pd.read_csv(filepath, nrows=5)
                print(f"\n{filename}:")
                print(f"  文件大小: {sub_df.shape}")
                print(f"  字段: {list(sub_df.columns)}")
                print(f"  样本:")
                print(sub_df.head())
            else:
                print(f"\n{filename}: 文件不存在")
        except Exception as e:
            print(f"❌ 读取{filename}失败: {e}")

def main():
    """主函数"""
    print("🔍 OpenSky 2022 数据集元数据来源验证")
    print("=" * 60)
    
    # 确保在正确目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # 检查数据目录
    data_dir = "../opensky_2024_PRC_dataset"
    if not os.path.exists(data_dir):
        print(f"❌ 数据目录不存在: {data_dir}")
        return
    
    # 执行各项验证
    verify_flight_metadata()
    verify_weather_data()
    verify_airport_info()
    verify_trajectory_weather()
    verify_submission_data()
    
    print("\n" + "=" * 60)
    print("📋 数据来源总结:")
    print("✈️  航班元数据 (18字段): challenge_set.csv")
    print("🌤️  机场天气数据 (33字段): METARs.parquet")
    print("🛰️  轨迹天气数据 (4字段): rawtrajectories/*.parquet")
    print("🛬 机场信息 (8字段): airports_tz.parquet")
    print("🎯 预测目标: TOW (起飞重量)")

if __name__ == "__main__":
    main()