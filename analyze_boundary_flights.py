import pandas as pd
from datetime import datetime, date, timedelta
import pytz

# 加载数据
df1 = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet')
df2 = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-02.parquet')

print(f'第一天数据: {len(df1)} 条记录')
print(f'第二天数据: {len(df2)} 条记录')

# 确保时间戳是datetime类型
df1['timestamp'] = pd.to_datetime(df1['timestamp'])
df2['timestamp'] = pd.to_datetime(df2['timestamp'])

# 检查时间范围
print(f'第一天时间范围: {df1["timestamp"].min()} - {df1["timestamp"].max()}')
print(f'第二天时间范围: {df2["timestamp"].min()} - {df2["timestamp"].max()}')

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

print(f'\n第一天晚间窗口: {evening_start} - {evening_end}')
print(f'第二天凌晨窗口: {morning_start} - {morning_end}')

# 提取边界航班
evening_flights = df1[(df1['timestamp'] >= evening_start) & (df1['timestamp'] < evening_end)]
morning_flights = df2[(df2['timestamp'] >= morning_start) & (df2['timestamp'] <= morning_end)]

print(f'\n第一天晚间航班: {len(evening_flights)} 条记录')
print(f'第二天凌晨航班: {len(morning_flights)} 条记录')

if len(evening_flights) > 0:
    print(f'\n第一天晚间航班时间范围: {evening_flights["timestamp"].min()} - {evening_flights["timestamp"].max()}')
    print(f'第一天晚间航班唯一icao24数量: {evening_flights["icao24"].nunique()}')
    
    # 分析晚间航班的最后记录
    evening_last = evening_flights.groupby('icao24').last().reset_index()
    print(f'第一天晚间航班最后记录数: {len(evening_last)}')
    print(f'第一天晚间航班最后记录时间范围: {evening_last["timestamp"].min()} - {evening_last["timestamp"].max()}')
    
if len(morning_flights) > 0:
    print(f'第二天凌晨航班时间范围: {morning_flights["timestamp"].min()} - {morning_flights["timestamp"].max()}')
    print(f'第二天凌晨航班唯一icao24数量: {morning_flights["icao24"].nunique()}')
    
    # 分析凌晨航班的第一记录
    morning_first = morning_flights.groupby('icao24').first().reset_index()
    print(f'第二天凌晨航班第一记录数: {len(morning_first)}')
    print(f'第二天凌晨航班第一记录时间范围: {morning_first["timestamp"].min()} - {morning_first["timestamp"].max()}')

# 检查是否有相同的icao24
if len(evening_flights) > 0 and len(morning_flights) > 0:
    evening_icao24 = set(evening_flights['icao24'].unique())
    morning_icao24 = set(morning_flights['icao24'].unique())
    common_icao24 = evening_icao24.intersection(morning_icao24)
    print(f'\n相同的icao24数量: {len(common_icao24)}')
    if len(common_icao24) > 0:
        print(f'相同的icao24: {list(common_icao24)[:10]}')  # 只显示前10个