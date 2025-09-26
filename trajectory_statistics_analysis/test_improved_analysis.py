#!/usr/bin/env python3
"""
测试改进的机场完整性分析
"""

import pandas as pd
import numpy as np
from pathlib import Path

def haversine_distance(lat1, lon1, lat2, lon2):
    """计算两点间的距离（公里）"""
    R = 6371  # 地球半径（公里）
    
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    
    return R * c

def main():
    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly")
    
    # 加载机场数据
    print("加载机场数据...")
    airports_df = pd.read_csv(base_dir / "ourairports2024-10-21.csv")
    airports_df = airports_df[
        (airports_df['ident'].notna()) & 
        (airports_df['latitude_deg'].notna()) & 
        (airports_df['longitude_deg'].notna())
    ].copy()
    
    # 创建机场字典
    airport_dict = {}
    for _, row in airports_df.iterrows():
        icao = row['ident']
        airport_dict[icao] = {
            'name': row['name'],
            'latitude': row['latitude_deg'],
            'longitude': row['longitude_deg'],
            'country': row['iso_country']
        }
    
    print(f"加载了 {len(airport_dict)} 个机场")
    
    # 加载官方轨迹数据
    print("加载官方轨迹数据...")
    challenge_df = pd.read_csv(base_dir / "opensky_2024_PRC_dataset" / "challenge_set.csv")
    print(f"加载了 {len(challenge_df)} 条官方轨迹记录")
    
    # 测试一个轨迹文件
    trajectory_file = base_dir / "perfect_trajectories" / "complete_2022-10-23.parquet"
    print(f"分析轨迹文件: {trajectory_file}")
    
    df = pd.read_parquet(trajectory_file)
    print(f"轨迹文件包含 {len(df)} 个数据点，{df['flight_id'].nunique()} 条轨迹")
    
    # 分析前10条轨迹
    results = []
    flight_ids = df['flight_id'].unique()[:10]
    
    for flight_id in flight_ids:
        flight_data = df[df['flight_id'] == flight_id]
        if len(flight_data) < 2:
            continue
            
        start_point = flight_data.iloc[0]
        end_point = flight_data.iloc[-1]
        
        # 查找官方数据
        official_info = challenge_df[challenge_df['flight_id'] == flight_id]
        
        result = {
            'flight_id': flight_id,
            'start_lat': start_point['latitude'],
            'start_lon': start_point['longitude'],
            'end_lat': end_point['latitude'],
            'end_lon': end_point['longitude'],
            'points': len(flight_data)
        }
        
        if not official_info.empty:
            official_row = official_info.iloc[0]
            result['official_adep'] = official_row['adep']
            result['official_ades'] = official_row['ades']
            result['official_adep_name'] = official_row['name_adep']
            result['official_ades_name'] = official_row['name_ades']
            
            # 计算到官方机场的距离
            if official_row['adep'] in airport_dict:
                adep_info = airport_dict[official_row['adep']]
                result['distance_to_adep'] = haversine_distance(
                    start_point['latitude'], start_point['longitude'],
                    adep_info['latitude'], adep_info['longitude']
                )
            
            if official_row['ades'] in airport_dict:
                ades_info = airport_dict[official_row['ades']]
                result['distance_to_ades'] = haversine_distance(
                    end_point['latitude'], end_point['longitude'],
                    ades_info['latitude'], ades_info['longitude']
                )
        
        results.append(result)
    
    # 显示结果
    print("\n分析结果:")
    print("=" * 100)
    for result in results:
        print(f"Flight ID: {result['flight_id']}")
        print(f"  轨迹点数: {result['points']}")
        print(f"  起点: ({result['start_lat']:.4f}, {result['start_lon']:.4f})")
        print(f"  终点: ({result['end_lat']:.4f}, {result['end_lon']:.4f})")
        
        if 'official_adep' in result:
            print(f"  官方起飞机场: {result['official_adep']} ({result['official_adep_name']})")
            print(f"  官方降落机场: {result['official_ades']} ({result['official_ades_name']})")
            
            if 'distance_to_adep' in result:
                print(f"  起点到起飞机场距离: {result['distance_to_adep']:.1f} km")
            if 'distance_to_ades' in result:
                print(f"  终点到降落机场距离: {result['distance_to_ades']:.1f} km")
        else:
            print("  未找到官方起降机场信息")
        
        print("-" * 100)
    
    # 统计
    has_official = [r for r in results if 'official_adep' in r]
    print(f"\n统计信息:")
    print(f"有官方数据的轨迹: {len(has_official)}/{len(results)} ({len(has_official)/len(results)*100:.1f}%)")
    
    if has_official:
        adep_distances = [r['distance_to_adep'] for r in has_official if 'distance_to_adep' in r]
        ades_distances = [r['distance_to_ades'] for r in has_official if 'distance_to_ades' in r]
        
        if adep_distances:
            print(f"平均起点到起飞机场距离: {np.mean(adep_distances):.1f} km")
            within_50km_adep = sum(1 for d in adep_distances if d <= 50)
            print(f"起点在50km内的轨迹: {within_50km_adep}/{len(adep_distances)} ({within_50km_adep/len(adep_distances)*100:.1f}%)")
        
        if ades_distances:
            print(f"平均终点到降落机场距离: {np.mean(ades_distances):.1f} km")
            within_50km_ades = sum(1 for d in ades_distances if d <= 50)
            print(f"终点在50km内的轨迹: {within_50km_ades}/{len(ades_distances)} ({within_50km_ades/len(ades_distances)*100:.1f}%)")

if __name__ == "__main__":
    main()