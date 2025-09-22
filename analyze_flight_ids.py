#!/usr/bin/env python3
"""
分析flight_id的命名规律和重叠情况
"""

import pandas as pd
from datetime import datetime, timedelta, date
import pytz

def analyze_flight_ids():
    # 加载数据
    df1 = pd.read_parquet('/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet')
    df2 = pd.read_parquet('/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-02.parquet')

    print('=== Flight ID 命名规律分析 ===')
    print('第一天flight_id样本:')
    sample_ids_1 = df1['flight_id'].dropna().unique()[:10]
    for fid in sample_ids_1:
        print(f'  {fid}')

    print('\n第二天flight_id样本:')
    sample_ids_2 = df2['flight_id'].dropna().unique()[:10]
    for fid in sample_ids_2:
        print(f'  {fid}')

    print('\n=== 检查是否有相同的航班号但不同的flight_id ===')
    # 提取航班号（假设flight_id包含航班号信息）
    def extract_callsign(flight_id):
        if pd.isna(flight_id):
            return None
        # flight_id格式可能是 'callsign_timestamp' 或类似格式
        parts = str(flight_id).split('_')
        return parts[0] if parts else flight_id

    df1['callsign'] = df1['flight_id'].apply(extract_callsign)
    df2['callsign'] = df2['flight_id'].apply(extract_callsign)

    callsigns_1 = set(df1['callsign'].dropna())
    callsigns_2 = set(df2['callsign'].dropna())
    callsign_overlap = callsigns_1 & callsigns_2

    print(f'第一天唯一航班号数量: {len(callsigns_1)}')
    print(f'第二天唯一航班号数量: {len(callsigns_2)}')
    print(f'航班号重叠数量: {len(callsign_overlap)}')

    if callsign_overlap:
        print(f'重叠的航班号样本: {list(callsign_overlap)[:10]}')
        
        # 分析重叠航班号的详细情况
        for callsign in list(callsign_overlap)[:3]:
            flights_1 = df1[df1['callsign'] == callsign]
            flights_2 = df2[df2['callsign'] == callsign]
            
            print(f'\n=== 航班号: {callsign} ===')
            print(f'第一天该航班号的flight_id: {list(flights_1["flight_id"].unique())}')
            print(f'第二天该航班号的flight_id: {list(flights_2["flight_id"].unique())}')
            print(f'第一天时间范围: {flights_1["timestamp"].min()} - {flights_1["timestamp"].max()}')
            print(f'第二天时间范围: {flights_2["timestamp"].min()} - {flights_2["timestamp"].max()}')
    
    # 分析数据的组织方式
    print('\n=== 数据组织方式分析 ===')
    print('检查flight_id是否包含日期信息...')
    
    # 检查flight_id中是否包含日期
    sample_flight_ids = list(df1['flight_id'].dropna().unique()[:5]) + list(df2['flight_id'].dropna().unique()[:5])
    for fid in sample_flight_ids:
        print(f'Flight ID: {fid}')
        # 检查是否包含日期模式
        if '2022' in str(fid) or '20220101' in str(fid) or '20220102' in str(fid):
            print(f'  -> 包含日期信息')
        else:
            print(f'  -> 不包含明显的日期信息')

if __name__ == "__main__":
    analyze_flight_ids()