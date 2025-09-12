#!/usr/bin/env python3
"""
深入检查OpenSky数据集的数据质量，包括缺失值、异常值等
"""

import pandas as pd
import numpy as np
import os

def check_missing_values(df, data_type=""):
    """检查缺失值情况"""
    print(f"\n=== {data_type} 缺失值分析 ===")
    total_rows = len(df)
    
    for col in df.columns:
        missing_count = df[col].isnull().sum()
        missing_pct = (missing_count / total_rows) * 100
        
        if missing_count > 0:
            print(f"  {col}: {missing_count:,} ({missing_pct:.2f}%)")
    
    # 检查完全空的行
    empty_rows = df.isnull().all(axis=1).sum()
    if empty_rows > 0:
        print(f"  完全空的行: {empty_rows:,}")
    
    # 检查大部分字段为空的行
    mostly_empty = df.isnull().sum(axis=1) >= len(df.columns) * 0.5
    mostly_empty_count = mostly_empty.sum()
    if mostly_empty_count > 0:
        print(f"  大部分字段为空的行: {mostly_empty_count:,}")

def check_trajectory_continuity(df):
    """检查轨迹连续性"""
    print(f"\n=== 轨迹连续性分析 ===")
    
    flight_gaps = []
    trajectory_issues = []
    
    for flight_id in df.flight_id.unique()[:10]:  # 检查前10个航班
        flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
        
        # 检查时间间隔
        time_diffs = flight_data['timestamp'].diff().dt.total_seconds()
        
        # 找到大于正常间隔的gaps (假设正常间隔是1-5秒)
        large_gaps = time_diffs > 60  # 超过1分钟的gap
        gap_count = large_gaps.sum()
        
        if gap_count > 0:
            flight_gaps.append((flight_id, gap_count, time_diffs.max()))
        
        # 检查关键字段的连续性
        key_fields = ['latitude', 'longitude', 'altitude']
        for field in key_fields:
            null_count = flight_data[field].isnull().sum()
            if null_count > 0:
                trajectory_issues.append((flight_id, field, null_count))
    
    if flight_gaps:
        print(f"  发现时间间隔异常的航班: {len(flight_gaps)}")
        for flight_id, gap_count, max_gap in flight_gaps[:5]:
            print(f"    航班 {flight_id}: {gap_count} 个大间隔, 最大间隔 {max_gap:.0f}秒")
    
    if trajectory_issues:
        print(f"  发现关键字段缺失的航班: {len(trajectory_issues)}")
        for flight_id, field, null_count in trajectory_issues[:5]:
            print(f"    航班 {flight_id} 的 {field}: {null_count} 个缺失值")

def check_data_ranges(df):
    """检查数据范围异常"""
    print(f"\n=== 数据范围异常分析 ===")
    
    # 定义合理范围
    reasonable_ranges = {
        'latitude': (-90, 90),
        'longitude': (-180, 180),
        'altitude': (-2000, 50000),  # 米
        'groundspeed': (0, 1000),    # km/h
        'track': (0, 360),
        'vertical_rate': (-10000, 10000)  # ft/min
    }
    
    for field, (min_val, max_val) in reasonable_ranges.items():
        if field in df.columns:
            out_of_range = (df[field] < min_val) | (df[field] > max_val)
            out_of_range_count = out_of_range.sum()
            
            if out_of_range_count > 0:
                pct = (out_of_range_count / len(df)) * 100
                print(f"  {field} 超出合理范围: {out_of_range_count:,} ({pct:.3f}%)")
                print(f"    实际范围: {df[field].min():.2f} 到 {df[field].max():.2f}")
                print(f"    合理范围: {min_val} 到 {max_val}")

def analyze_flight_completeness(df):
    """分析航班轨迹完整性"""
    print(f"\n=== 航班轨迹完整性分析 ===")
    
    flight_stats = []
    
    for flight_id in df.flight_id.unique()[:20]:  # 分析前20个航班
        flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
        
        total_points = len(flight_data)
        duration = (flight_data.timestamp.max() - flight_data.timestamp.min()).total_seconds()
        expected_points = duration if duration > 0 else 1
        
        # 检查关键字段的完整性
        key_fields = ['latitude', 'longitude', 'altitude', 'groundspeed']
        complete_points = flight_data[key_fields].dropna().shape[0]
        completeness = (complete_points / total_points) * 100 if total_points > 0 else 0
        
        flight_stats.append({
            'flight_id': flight_id,
            'total_points': total_points,
            'complete_points': complete_points,
            'completeness_pct': completeness,
            'duration_min': duration / 60
        })
    
    flight_df = pd.DataFrame(flight_stats)
    print(f"  平均轨迹点数: {flight_df.total_points.mean():.0f}")
    print(f"  平均完整性: {flight_df.completeness_pct.mean():.1f}%")
    print(f"  完整性 < 90% 的航班: {(flight_df.completeness_pct < 90).sum()}")
    print(f"  完整性 < 50% 的航班: {(flight_df.completeness_pct < 50).sum()}")
    
    return flight_df

def check_processed_vs_raw():
    """比较处理前后的数据质量"""
    print(f"\n=== 处理前后数据质量对比 ===")
    
    # 原始数据
    raw_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df_raw = pd.read_parquet(raw_file)
    
    # 插值处理后数据
    interp_file = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/2022-01-01.parquet'
    df_interp = pd.read_parquet(interp_file)
    
    print(f"原始数据:")
    print(f"  总点数: {len(df_raw):,}")
    print(f"  航班数: {df_raw.flight_id.nunique():,}")
    
    print(f"处理后数据:")
    print(f"  总点数: {len(df_interp):,}")
    print(f"  航班数: {df_interp.flight_id.nunique():,}")
    
    # 检查每个航班的点数变化
    raw_counts = df_raw.groupby('flight_id').size()
    interp_counts = df_interp.groupby('flight_id').size()
    
    common_flights = set(raw_counts.index) & set(interp_counts.index)
    print(f"  共同航班数: {len(common_flights)}")
    
    if common_flights:
        point_changes = []
        for flight_id in list(common_flights)[:10]:
            raw_count = raw_counts[flight_id]
            interp_count = interp_counts[flight_id]
            change = ((interp_count - raw_count) / raw_count) * 100
            point_changes.append(change)
            print(f"    航班 {flight_id}: {raw_count} -> {interp_count} ({change:+.1f}%)")
    
    return df_raw, df_interp

if __name__ == "__main__":
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    print("开始深入数据质量检查...")
    
    # 检查原始数据
    raw_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df_raw = pd.read_parquet(raw_file)
    
    check_missing_values(df_raw, "原始轨迹数据")
    check_trajectory_continuity(df_raw)
    check_data_ranges(df_raw)
    flight_stats = analyze_flight_completeness(df_raw)
    
    # 检查处理后数据
    interp_file = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/2022-01-01.parquet'
    if os.path.exists(interp_file):
        df_interp = pd.read_parquet(interp_file)
        check_missing_values(df_interp, "插值处理后数据")
        
    # 对比分析
    check_processed_vs_raw()
    
    print(f"\n=== 总结 ===")
    print("数据质量问题可能包括:")
    print("1. 轨迹点时间间隔不均匀")
    print("2. 关键字段存在缺失值")
    print("3. 某些航班轨迹不完整")
    print("4. 数值范围可能存在异常")
    print("\n建议在训练模型前进行额外的数据清洗和预处理!")
