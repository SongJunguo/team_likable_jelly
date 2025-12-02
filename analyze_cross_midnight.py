import pandas as pd
from datetime import datetime, date, timedelta
import pytz
from trajectory_stitching.processing.utils import calculate_distance

# 加载数据
df1 = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet')
df2 = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-02.parquet')

# 确保时间戳是datetime类型
df1['timestamp'] = pd.to_datetime(df1['timestamp'])
df2['timestamp'] = pd.to_datetime(df2['timestamp'])

print(f'第一天数据: {len(df1)} 条记录')
print(f'第二天数据: {len(df2)} 条记录')

# 分析边界时间的航班
utc = pytz.UTC
date1 = date(2022, 1, 1)
date2 = date(2022, 1, 2)

# 第一天的晚间时间窗口（22:00-24:00）
midnight1 = datetime.combine(date1, datetime.min.time()).replace(tzinfo=utc)
evening_start = midnight1 + timedelta(hours=22)
evening_end = midnight1 + timedelta(days=1)

# 第二天的凌晨时间窗口（00:00-02:00）
midnight2 = datetime.combine(date2, datetime.min.time()).replace(tzinfo=utc)
morning_start = midnight2
morning_end = midnight2 + timedelta(hours=2)

# 提取边界航班
evening_flights = df1[(df1['timestamp'] >= evening_start) & (df1['timestamp'] < evening_end)]
morning_flights = df2[(df2['timestamp'] >= morning_start) & (df2['timestamp'] <= morning_end)]

print(f'\n第一天晚间航班: {len(evening_flights)} 条记录, 唯一icao24: {evening_flights["icao24"].nunique()}')
print(f'第二天凌晨航班: {len(morning_flights)} 条记录, 唯一icao24: {morning_flights["icao24"].nunique()}')

# 获取晚间航班的最后位置
evening_last = evening_flights.groupby('icao24').last().reset_index()
print(f'\n第一天晚间航班最后记录: {len(evening_last)} 个')

# 获取凌晨航班的第一位置
morning_first = morning_flights.groupby('icao24').first().reset_index()
print(f'第二天凌晨航班第一记录: {len(morning_first)} 个')

# 基于位置和时间连续性查找潜在匹配
matches = []
max_distance = 100  # 公里
max_time_gap = 60   # 分钟

print(f'\n开始基于位置和时间连续性的匹配...')
print(f'距离阈值: {max_distance} 公里')
print(f'时间阈值: {max_time_gap} 分钟')

for _, evening_record in evening_last.iterrows():
    evening_time = evening_record['timestamp']
    evening_lat = evening_record['latitude']
    evening_lon = evening_record['longitude']
    evening_icao24 = evening_record['icao24']
    
    for _, morning_record in morning_first.iterrows():
        morning_time = morning_record['timestamp']
        morning_lat = morning_record['latitude']
        morning_lon = morning_record['longitude']
        morning_icao24 = morning_record['icao24']
        
        # 计算时间间隔
        time_gap = (morning_time - evening_time).total_seconds() / 60  # 分钟
        
        # 计算距离
        distance = calculate_distance(evening_lat, evening_lon, morning_lat, morning_lon)
        
        # 检查是否满足条件
        if time_gap >= 0 and time_gap <= max_time_gap and distance <= max_distance:
            matches.append({
                'evening_icao24': evening_icao24,
                'morning_icao24': morning_icao24,
                'time_gap_minutes': time_gap,
                'distance_km': distance,
                'evening_time': evening_time,
                'morning_time': morning_time,
                'evening_position': (evening_lat, evening_lon),
                'morning_position': (morning_lat, morning_lon)
            })

print(f'\n找到 {len(matches)} 个潜在跨日期航班匹配')

if len(matches) > 0:
    print('\n前10个匹配:')
    for i, match in enumerate(matches[:10]):
        print(f'{i+1}. 晚间icao24: {match["evening_icao24"]}, 凌晨icao24: {match["morning_icao24"]}')
        print(f'   时间间隔: {match["time_gap_minutes"]:.1f} 分钟')
        print(f'   距离: {match["distance_km"]:.1f} 公里')
        print(f'   晚间时间: {match["evening_time"]}')
        print(f'   凌晨时间: {match["morning_time"]}')
        print()
else:
    print('\n没有找到满足条件的跨日期航班匹配')
    
    # 分析最近的匹配
    print('\n分析最近的10个位置匹配:')
    closest_matches = []
    
    for _, evening_record in evening_last.iterrows():
        evening_time = evening_record['timestamp']
        evening_lat = evening_record['latitude']
        evening_lon = evening_record['longitude']
        evening_icao24 = evening_record['icao24']
        
        for _, morning_record in morning_first.iterrows():
            morning_time = morning_record['timestamp']
            morning_lat = morning_record['latitude']
            morning_lon = morning_record['longitude']
            morning_icao24 = morning_record['icao24']
            
            time_gap = (morning_time - evening_time).total_seconds() / 60
            distance = calculate_distance(evening_lat, evening_lon, morning_lat, morning_lon)
            
            closest_matches.append({
                'evening_icao24': evening_icao24,
                'morning_icao24': morning_icao24,
                'time_gap_minutes': time_gap,
                'distance_km': distance
            })
    
    # 按距离排序
    closest_matches.sort(key=lambda x: x['distance_km'])
    
    for i, match in enumerate(closest_matches[:10]):
        print(f'{i+1}. 距离: {match["distance_km"]:.1f} 公里, 时间间隔: {match["time_gap_minutes"]:.1f} 分钟')
        print(f'   晚间icao24: {match["evening_icao24"]}, 凌晨icao24: {match["morning_icao24"]}')