#!/usr/bin/env python3
"""
分析OpenSky数据集中航班标识和区分方式
"""

import pandas as pd
import numpy as np
import os

def analyze_flight_identifiers():
    """分析航班标识符"""
    print("=== 航班标识符分析 ===")
    
    # 读取轨迹数据
    traj_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df_traj = pd.read_parquet(traj_file)
    
    print(f"轨迹数据中的标识字段:")
    identifier_fields = ['flight_id', 'icao24']
    for field in identifier_fields:
        if field in df_traj.columns:
            unique_count = df_traj[field].nunique()
            print(f"  {field}: {unique_count:,} 个唯一值")
    
    # 分析flight_id的特征
    print(f"\nflight_id 详细分析:")
    print(f"  数据类型: {df_traj['flight_id'].dtype}")
    print(f"  最小值: {df_traj['flight_id'].min()}")
    print(f"  最大值: {df_traj['flight_id'].max()}")
    print(f"  示例值: {df_traj['flight_id'].head(10).tolist()}")
    
    # 分析icao24的特征
    print(f"\nicao24 详细分析:")
    print(f"  数据类型: {df_traj['icao24'].dtype}")
    print(f"  最小值: {df_traj['icao24'].min()}")
    print(f"  最大值: {df_traj['icao24'].max()}")
    print(f"  示例值: {df_traj['icao24'].head(10).tolist()}")
    
    return df_traj

def analyze_flight_metadata():
    """分析航班元数据中的标识符"""
    print(f"\n=== 航班元数据标识符分析 ===")
    
    # 使用命令行工具查看CSV结构（因为文件太大）
    import subprocess
    
    # 获取CSV文件的前几行
    result = subprocess.run(['head', '-10', 'opensky_2024_PRC_dataset/challenge_set.csv'], 
                          capture_output=True, text=True)
    lines = result.stdout.strip().split('\n')
    
    if len(lines) >= 2:
        headers = lines[0].split(',')
        print(f"元数据字段: {headers}")
        
        # 显示前几行数据
        print(f"\n前几行数据:")
        for i, line in enumerate(lines[1:6]):  # 显示前5行数据
            values = line.split(',')
            print(f"  行 {i+1}: flight_id={values[0]}, callsign={values[2] if len(values) > 2 else 'N/A'}")

def check_flight_id_uniqueness(df_traj):
    """检查flight_id的唯一性"""
    print(f"\n=== flight_id 唯一性检查 ===")
    
    # 按flight_id分组，查看每个航班的基本信息
    flight_groups = df_traj.groupby('flight_id').agg({
        'timestamp': ['min', 'max', 'count'],
        'icao24': 'nunique',
        'latitude': ['min', 'max'],
        'longitude': ['min', 'max'],
        'altitude': ['min', 'max']
    }).round(2)
    
    # 扁平化列名
    flight_groups.columns = ['_'.join(col).strip() for col in flight_groups.columns]
    
    print(f"总航班数: {len(flight_groups)}")
    print(f"前10个航班的详细信息:")
    print(flight_groups.head(10))
    
    # 检查是否有flight_id对应多个icao24（飞机）
    multi_aircraft = flight_groups[flight_groups['icao24_nunique'] > 1]
    if len(multi_aircraft) > 0:
        print(f"\n⚠️  发现 {len(multi_aircraft)} 个flight_id对应多个飞机:")
        print(multi_aircraft)
    else:
        print(f"\n✅ 所有flight_id都对应唯一的飞机")
    
    return flight_groups

def analyze_icao24_aircraft():
    """分析icao24飞机标识"""
    print(f"\n=== icao24 飞机标识分析 ===")
    
    traj_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df_traj = pd.read_parquet(traj_file)
    
    # 按icao24分组，查看每架飞机的航班数
    aircraft_flights = df_traj.groupby('icao24')['flight_id'].nunique().sort_values(ascending=False)
    
    print(f"总飞机数: {len(aircraft_flights)}")
    print(f"平均每架飞机的航班数: {aircraft_flights.mean():.1f}")
    print(f"最多航班数的飞机: {aircraft_flights.max()} 个航班")
    print(f"只有1个航班的飞机: {(aircraft_flights == 1).sum()} 架")
    print(f"超过5个航班的飞机: {(aircraft_flights > 5).sum()} 架")
    
    print(f"\n航班数最多的前10架飞机:")
    for icao24, flight_count in aircraft_flights.head(10).items():
        print(f"  飞机 {icao24}: {flight_count} 个航班")
        
        # 显示该飞机的航班时间分布
        aircraft_data = df_traj[df_traj.icao24 == icao24]
        flight_times = aircraft_data.groupby('flight_id')['timestamp'].agg(['min', 'max'])
        print(f"    航班时间分布: {flight_times.iloc[0]['min']} 到 {flight_times.iloc[-1]['max']}")

def check_cross_day_flights():
    """检查跨天航班"""
    print(f"\n=== 跨天航班检查 ===")
    
    traj_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df_traj = pd.read_parquet(traj_file)
    
    # 检查是否有航班跨越了1月1日和1月2日
    flight_dates = df_traj.groupby('flight_id')['timestamp'].agg(['min', 'max'])
    flight_dates['start_date'] = flight_dates['min'].dt.date
    flight_dates['end_date'] = flight_dates['max'].dt.date
    flight_dates['cross_day'] = flight_dates['start_date'] != flight_dates['end_date']
    
    cross_day_count = flight_dates['cross_day'].sum()
    print(f"跨天航班数: {cross_day_count}")
    
    if cross_day_count > 0:
        print(f"跨天航班示例:")
        cross_day_flights = flight_dates[flight_dates['cross_day']]
        for flight_id, row in cross_day_flights.head(5).iterrows():
            print(f"  航班 {flight_id}: {row['min']} 到 {row['max']}")

def analyze_callsign_relationship():
    """分析callsign与flight_id的关系"""
    print(f"\n=== callsign 与 flight_id 关系分析 ===")
    
    # 读取元数据（使用pandas，限制行数避免内存问题）
    try:
        # 只读取前1000行来分析
        df_meta = pd.read_csv('opensky_2024_PRC_dataset/challenge_set.csv', nrows=1000)
        
        print(f"元数据字段: {df_meta.columns.tolist()}")
        
        if 'callsign' in df_meta.columns and 'flight_id' in df_meta.columns:
            print(f"\ncallsign 分析:")
            print(f"  总记录数: {len(df_meta)}")
            print(f"  唯一 flight_id: {df_meta['flight_id'].nunique()}")
            print(f"  唯一 callsign: {df_meta['callsign'].nunique()}")
            
            # 检查callsign与flight_id的对应关系
            callsign_flights = df_meta.groupby('callsign')['flight_id'].nunique()
            multi_flight_callsigns = callsign_flights[callsign_flights > 1]
            
            if len(multi_flight_callsigns) > 0:
                print(f"  一个callsign对应多个flight_id的情况: {len(multi_flight_callsigns)}")
                print(f"  示例: {multi_flight_callsigns.head()}")
            
            print(f"\n前10个航班的标识信息:")
            display_cols = ['flight_id', 'callsign', 'adep', 'ades', 'aircraft_type']
            available_cols = [col for col in display_cols if col in df_meta.columns]
            print(df_meta[available_cols].head(10))
            
    except Exception as e:
        print(f"读取元数据文件时出错: {e}")

if __name__ == "__main__":
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    print("分析OpenSky数据集中的航班标识方式...")
    
    # 执行各项分析
    df_traj = analyze_flight_identifiers()
    analyze_flight_metadata()
    flight_groups = check_flight_id_uniqueness(df_traj)
    analyze_icao24_aircraft()
    check_cross_day_flights()
    analyze_callsign_relationship()
    
    print(f"\n=== 总结 ===")
    print("航班标识方式:")
    print("1. flight_id: 主要标识符，每个航班唯一")
    print("2. icao24: 飞机标识符，同一架飞机可能有多个航班")
    print("3. callsign: 航班呼号，可能在不同时间重复使用")
    print("4. 组合标识: flight_id + timestamp 确保唯一性")
    print("\n建议使用 flight_id 作为航班的主要标识符进行轨迹预测模型训练!")
