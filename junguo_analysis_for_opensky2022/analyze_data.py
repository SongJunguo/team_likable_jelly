#!/usr/bin/env python3
"""
分析OpenSky数据集的结构和内容
"""

import pandas as pd
import numpy as np
import os

def analyze_raw_trajectories():
    """分析原始轨迹数据"""
    print("=== 原始轨迹数据分析 ===")
    
    # 读取一个轨迹文件样本
    traj_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df = pd.read_parquet(traj_file)
    
    print(f"数据形状: {df.shape}")
    print(f"列名: {df.columns.tolist()}")
    print(f"总记录数: {len(df):,}")
    print(f"独特航班数: {df.flight_id.nunique():,}")
    print(f"时间范围: {df.timestamp.min()} 到 {df.timestamp.max()}")
    
    print("\n各列数据范围:")
    for col in df.select_dtypes(include=[np.number]).columns:
        if col not in ['flight_id', 'icao24']:
            print(f"  {col}: {df[col].min():.2f} 到 {df[col].max():.2f}")
    
    # 分析单个航班轨迹
    sample_flight = df[df.flight_id == df.flight_id.iloc[0]]
    print(f"\n单个航班轨迹示例:")
    print(f"  航班ID: {sample_flight.flight_id.iloc[0]}")
    print(f"  轨迹点数: {len(sample_flight)}")
    print(f"  时间跨度: {sample_flight.timestamp.max() - sample_flight.timestamp.min()}")
    
    return df

def analyze_interpolated_trajectories():
    """分析插值后轨迹数据"""
    print("\n=== 插值后轨迹数据分析 ===")
    
    interp_file = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/2022-01-01.parquet'
    if os.path.exists(interp_file):
        df_interp = pd.read_parquet(interp_file)
        print(f"插值后数据形状: {df_interp.shape}")
        print(f"列名: {df_interp.columns.tolist()}")
        print(f"插值后航班数: {df_interp.flight_id.nunique():,}")
        
        sample_flight_interp = df_interp[df_interp.flight_id == df_interp.flight_id.iloc[0]]
        print(f"单个航班轨迹点数 (插值后): {len(sample_flight_interp)}")
        
        return df_interp
    else:
        print("插值数据文件不存在")
        return None

def analyze_flight_metadata():
    """分析航班元数据"""
    print("\n=== 航班元数据分析 ===")
    
    # 使用head命令查看CSV文件结构
    import subprocess
    result = subprocess.run(['head', '-2', 'opensky_2024_PRC_dataset/challenge_set.csv'], 
                          capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')
    if len(lines) >= 2:
        headers = lines[0].split(',')
        print(f"航班元数据列数: {len(headers)}")
        print(f"主要字段: {headers}")

def analyze_weather_data():
    """分析天气数据"""
    print("\n=== 天气数据分析 ===")
    
    metars = pd.read_parquet('opensky_2024_PRC_dataset/METARs.parquet')
    print(f"METAR记录数: {len(metars):,}")
    print(f"METAR时间范围: {metars.valid.min()} 到 {metars.valid.max()}")
    print(f"气象站数量: {metars.station.nunique():,}")
    
    # 主要天气参数
    weather_params = ['tmpf', 'dwpf', 'relh', 'drct', 'sknt', 'vsby', 'mslp']
    print("\n主要天气参数范围:")
    for param in weather_params:
        if param in metars.columns:
            print(f"  {param}: {metars[param].min():.2f} 到 {metars[param].max():.2f}")

def analyze_dataset_completeness():
    """分析数据集完整性"""
    print("\n=== 数据集完整性分析 ===")
    
    # 统计原始轨迹文件数量
    raw_traj_dir = 'opensky_2024_PRC_dataset/rawtrajectories'
    raw_files = [f for f in os.listdir(raw_traj_dir) if f.endswith('.parquet')]
    print(f"原始轨迹文件数量: {len(raw_files)}")
    print(f"时间跨度: {min(raw_files)} 到 {max(raw_files)}")
    
    # 统计插值轨迹文件数量
    interp_traj_dir = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories'
    if os.path.exists(interp_traj_dir):
        interp_files = [f for f in os.listdir(interp_traj_dir) if f.endswith('.parquet')]
        print(f"插值轨迹文件数量: {len(interp_files)}")

if __name__ == "__main__":
    # 切换到正确的目录
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    # 执行各项分析
    df_raw = analyze_raw_trajectories()
    df_interp = analyze_interpolated_trajectories()
    analyze_flight_metadata()
    analyze_weather_data()
    analyze_dataset_completeness()
    
    print("\n=== 总结 ===")
    print("该数据集包含:")
    print("1. 完整的ADS-B轨迹数据 (经纬度、高度、速度、航向、垂直速度)")
    print("2. 详细的气象数据 (风速、风向、温度、湿度等)")
    print("3. 航班元数据 (起降机场、航空公司、机型等)")
    print("4. 预处理后的插值轨迹数据")
    print("\n适合训练decoder-only模型进行轨迹预测!")
