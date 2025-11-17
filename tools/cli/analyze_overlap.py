#!/usr/bin/env python3
"""
分析晚间和凌晨航班的重叠情况
"""

import pandas as pd
from datetime import datetime, timedelta, date
import pytz

def analyze_overlap():
    # 加载数据
    df1 = pd.read_parquet('/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet')
    df2 = pd.read_parquet('/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-02.parquet')

    # 提取边界航班
    utc = pytz.UTC
    date1 = date(2022, 1, 1)
    date2 = date(2022, 1, 2)

    # 第一天晚间航班（22:00-24:00）
    midnight1 = datetime.combine(date1, datetime.min.time()).replace(tzinfo=utc)
    evening_start = midnight1 + timedelta(hours=22)
    evening_end = midnight1 + timedelta(days=1)
    evening_flights = df1[(df1['timestamp'] >= evening_start) & (df1['timestamp'] < evening_end)]

    # 第二天凌晨航班（00:00-02:00）
    midnight2 = datetime.combine(date2, datetime.min.time()).replace(tzinfo=utc)
    morning_start = midnight2
    morning_end = midnight2 + timedelta(hours=2)
    morning_flights = df2[(df2['timestamp'] >= morning_start) & (df2['timestamp'] <= morning_end)]

    print(f'晚间航班数量: {len(evening_flights)}')
    print(f'凌晨航班数量: {len(morning_flights)}')

    # 检查flight_id重叠
    evening_flight_ids = set(evening_flights['flight_id'].dropna())
    morning_flight_ids = set(morning_flights['flight_id'].dropna())
    flight_id_overlap = evening_flight_ids & morning_flight_ids

    print(f'晚间航班唯一flight_id数量: {len(evening_flight_ids)}')
    print(f'凌晨航班唯一flight_id数量: {len(morning_flight_ids)}')
    print(f'flight_id重叠数量: {len(flight_id_overlap)}')

    # 检查icao24重叠
    evening_icao24 = set(evening_flights['icao24'].dropna())
    morning_icao24 = set(morning_flights['icao24'].dropna())
    icao24_overlap = evening_icao24 & morning_icao24

    print(f'晚间航班唯一icao24数量: {len(evening_icao24)}')
    print(f'凌晨航班唯一icao24数量: {len(morning_icao24)}')
    print(f'icao24重叠数量: {len(icao24_overlap)}')

    # 如果有重叠，查看详细信息
    if flight_id_overlap:
        print(f'\n重叠的flight_id: {list(flight_id_overlap)[:10]}')  # 显示前10个
        
    if icao24_overlap:
        print(f'\n重叠的icao24: {list(icao24_overlap)[:10]}')  # 显示前10个
        
        # 分析重叠icao24的详细轨迹
        for icao in list(icao24_overlap)[:3]:  # 分析前3个
            evening_traj = evening_flights[evening_flights['icao24'] == icao]
            morning_traj = morning_flights[morning_flights['icao24'] == icao]
            
            print(f'\n=== ICAO24: {icao} ===')
            print(f'晚间轨迹点数: {len(evening_traj)}')
            print(f'凌晨轨迹点数: {len(morning_traj)}')
            
            if len(evening_traj) > 0 and len(morning_traj) > 0:
                evening_last = evening_traj.iloc[-1]
                morning_first = morning_traj.iloc[0]
                
                print(f'晚间最后点时间: {evening_last["timestamp"]}')
                print(f'凌晨第一点时间: {morning_first["timestamp"]}')
                
                time_gap = (morning_first['timestamp'] - evening_last['timestamp']).total_seconds() / 60
                print(f'时间间隔: {time_gap:.1f} 分钟')
                
                # 计算距离
                from math import radians, sin, cos, sqrt, atan2
                
                def calculate_distance(lat1, lon1, lat2, lon2):
                    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
                    dlat = lat2 - lat1
                    dlon = lon2 - lon1
                    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                    c = 2 * atan2(sqrt(a), sqrt(1-a))
                    return 6371.0 * c
                
                if not pd.isna(evening_last['latitude']) and not pd.isna(morning_first['latitude']):
                    distance = calculate_distance(
                        evening_last['latitude'], evening_last['longitude'],
                        morning_first['latitude'], morning_first['longitude']
                    )
                    print(f'位置距离: {distance:.1f} 公里')

if __name__ == "__main__":
    analyze_overlap()