import pandas as pd
from datetime import datetime, date, timedelta
import pytz

# 加载数据
df1 = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet')
df2 = pd.read_parquet('opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-02.parquet')

print('=== 原始数据flight_id分析 ===')
print(f'第一天数据: {len(df1)} 条记录')
print(f'第二天数据: {len(df2)} 条记录')

# 确保时间戳是datetime类型
df1['timestamp'] = pd.to_datetime(df1['timestamp'])
df2['timestamp'] = pd.to_datetime(df2['timestamp'])

print(f'\n第一天时间范围: {df1["timestamp"].min()} - {df1["timestamp"].max()}')
print(f'第二天时间范围: {df2["timestamp"].min()} - {df2["timestamp"].max()}')

# 分析flight_id的特点
print(f'\n第一天唯一flight_id数量: {df1["flight_id"].nunique()}')
print(f'第二天唯一flight_id数量: {df2["flight_id"].nunique()}')

# 检查flight_id重叠
flight_ids_1 = set(df1['flight_id'].unique())
flight_ids_2 = set(df2['flight_id'].unique())
common_flight_ids = flight_ids_1.intersection(flight_ids_2)
print(f'\n重叠的flight_id数量: {len(common_flight_ids)}')

# 分析第一天数据中跨越到第二天的轨迹
utc = pytz.UTC
date1 = date(2022, 1, 1)
date2 = date(2022, 1, 2)

# 第二天的开始时间
midnight2 = datetime.combine(date2, datetime.min.time()).replace(tzinfo=utc)

# 第一天数据中跨越到第二天的记录
cross_day_records = df1[df1['timestamp'] >= midnight2]
print(f'\n第一天数据中跨越到第二天的记录: {len(cross_day_records)} 条')

if len(cross_day_records) > 0:
    print(f'跨越记录的时间范围: {cross_day_records["timestamp"].min()} - {cross_day_records["timestamp"].max()}')
    print(f'跨越记录的唯一flight_id数量: {cross_day_records["flight_id"].nunique()}')
    
    # 检查这些flight_id是否在第二天数据中也存在
    cross_day_flight_ids = set(cross_day_records['flight_id'].unique())
    overlap_with_day2 = cross_day_flight_ids.intersection(flight_ids_2)
    print(f'跨越flight_id与第二天数据的重叠: {len(overlap_with_day2)} 个')
    
    if len(overlap_with_day2) > 0:
        print(f'重叠的flight_id示例: {list(overlap_with_day2)[:5]}')
        
        # 详细分析一个重叠的flight_id
        sample_id = list(overlap_with_day2)[0]
        print(f'\n详细分析flight_id {sample_id}:')
        
        # 第一天数据中的记录
        day1_records = df1[df1['flight_id'] == sample_id]
        print(f'第一天记录数: {len(day1_records)}')
        print(f'第一天时间范围: {day1_records["timestamp"].min()} - {day1_records["timestamp"].max()}')
        
        # 第二天数据中的记录
        day2_records = df2[df2['flight_id'] == sample_id]
        print(f'第二天记录数: {len(day2_records)}')
        print(f'第二天时间范围: {day2_records["timestamp"].min()} - {day2_records["timestamp"].max()}')
        
        # 检查icao24是否相同
        day1_icao24 = day1_records['icao24'].unique()
        day2_icao24 = day2_records['icao24'].unique()
        print(f'第一天icao24: {day1_icao24}')
        print(f'第二天icao24: {day2_icao24}')
        print(f'icao24是否相同: {set(day1_icao24) == set(day2_icao24)}')

print('\n=== 结论 ===')
if len(common_flight_ids) > 0:
    print('✓ 发现跨日期的flight_id，原始数据已经处理了跨日期轨迹')
    print('✓ 同一个flight_id可能跨越多个日期文件')
    print('✓ 我们的检测逻辑是正确的，能够找到这些跨日期航班')
else:
    print('✗ 没有发现跨日期的flight_id')
    print('✗ 每个日期文件的flight_id都是独立的')
    print('✗ 需要基于icao24和位置连续性来检测跨日期航班')