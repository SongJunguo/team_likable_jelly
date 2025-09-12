#!/usr/bin/env python3
"""
分析原始轨迹数据的时间分布和缺失情况，理解插值处理的必要性
"""

import pandas as pd
import numpy as np
import os
from datetime import timedelta

def analyze_time_gaps(df):
    """分析时间间隔分布"""
    print(f"\n=== 原始轨迹时间间隔分析 ===")
    
    all_gaps = []
    flight_gap_stats = []
    
    # 分析每个航班的时间间隔
    for flight_id in df.flight_id.unique()[:50]:  # 分析前50个航班
        flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
        
        if len(flight_data) < 2:
            continue
            
        # 计算时间间隔（秒）
        time_diffs = flight_data['timestamp'].diff().dt.total_seconds().dropna()
        all_gaps.extend(time_diffs.tolist())
        
        # 统计该航班的间隔情况
        gaps_1s = (time_diffs == 1).sum()
        gaps_2_5s = ((time_diffs > 1) & (time_diffs <= 5)).sum()
        gaps_6_30s = ((time_diffs > 5) & (time_diffs <= 30)).sum()
        gaps_31_60s = ((time_diffs > 30) & (time_diffs <= 60)).sum()
        gaps_large = (time_diffs > 60).sum()
        
        flight_gap_stats.append({
            'flight_id': flight_id,
            'total_points': len(flight_data),
            'gaps_1s': gaps_1s,
            'gaps_2_5s': gaps_2_5s,
            'gaps_6_30s': gaps_6_30s,
            'gaps_31_60s': gaps_31_60s,
            'gaps_large': gaps_large,
            'median_gap': time_diffs.median(),
            'max_gap': time_diffs.max(),
            'min_gap': time_diffs.min()
        })
    
    # 总体统计
    all_gaps = np.array(all_gaps)
    print(f"总时间间隔数: {len(all_gaps):,}")
    print(f"间隔统计:")
    print(f"  1秒间隔: {(all_gaps == 1).sum():,} ({(all_gaps == 1).mean()*100:.1f}%)")
    print(f"  2-5秒间隔: {((all_gaps > 1) & (all_gaps <= 5)).sum():,} ({((all_gaps > 1) & (all_gaps <= 5)).mean()*100:.1f}%)")
    print(f"  6-30秒间隔: {((all_gaps > 5) & (all_gaps <= 30)).sum():,} ({((all_gaps > 5) & (all_gaps <= 30)).mean()*100:.1f}%)")
    print(f"  31-60秒间隔: {((all_gaps > 30) & (all_gaps <= 60)).sum():,} ({((all_gaps > 30) & (all_gaps <= 60)).mean()*100:.1f}%)")
    print(f"  >60秒间隔: {(all_gaps > 60).sum():,} ({(all_gaps > 60).mean()*100:.1f}%)")
    print(f"  >300秒间隔: {(all_gaps > 300).sum():,} ({(all_gaps > 300).mean()*100:.1f}%)")
    
    print(f"\n间隔统计值:")
    print(f"  最小间隔: {all_gaps.min():.1f}秒")
    print(f"  最大间隔: {all_gaps.max():.1f}秒")
    print(f"  中位数间隔: {np.median(all_gaps):.1f}秒")
    print(f"  平均间隔: {all_gaps.mean():.1f}秒")
    
    return flight_gap_stats

def analyze_missing_periods(df):
    """分析缺失时间段"""
    print(f"\n=== 缺失时间段分析 ===")
    
    missing_periods = []
    
    for flight_id in df.flight_id.unique()[:20]:  # 分析前20个航班
        flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
        
        if len(flight_data) < 2:
            continue
        
        # 找到大的时间间隔（可能的缺失段）
        time_diffs = flight_data['timestamp'].diff().dt.total_seconds()
        large_gaps = time_diffs > 60  # 超过1分钟认为是缺失
        
        if large_gaps.any():
            gap_indices = flight_data[large_gaps].index
            
            for idx in gap_indices:
                gap_start = flight_data.loc[idx-1, 'timestamp'] if idx-1 in flight_data.index else None
                gap_end = flight_data.loc[idx, 'timestamp']
                gap_duration = time_diffs.loc[idx]
                
                if gap_start:
                    missing_periods.append({
                        'flight_id': flight_id,
                        'gap_start': gap_start,
                        'gap_end': gap_end,
                        'duration_sec': gap_duration,
                        'duration_min': gap_duration / 60
                    })
    
    if missing_periods:
        missing_df = pd.DataFrame(missing_periods)
        print(f"检测到的缺失时间段: {len(missing_df)}")
        print(f"平均缺失时长: {missing_df.duration_min.mean():.1f}分钟")
        print(f"最长缺失时长: {missing_df.duration_min.max():.1f}分钟")
        print(f"超过10分钟的缺失: {(missing_df.duration_min > 10).sum()}")
        print(f"超过1小时的缺失: {(missing_df.duration_min > 60).sum()}")
        
        print(f"\n前10个最长缺失段:")
        top_missing = missing_df.nlargest(10, 'duration_min')
        for _, row in top_missing.iterrows():
            print(f"  航班 {row.flight_id}: {row.duration_min:.1f}分钟 ({row.gap_start} - {row.gap_end})")
    
    return missing_periods

def compare_flight_coverage(df):
    """比较航班的时间覆盖情况"""
    print(f"\n=== 航班时间覆盖分析 ===")
    
    coverage_stats = []
    
    for flight_id in df.flight_id.unique()[:30]:  # 分析前30个航班
        flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
        
        if len(flight_data) < 2:
            continue
        
        # 计算理论应有的点数（假设1秒间隔）
        total_duration = (flight_data.timestamp.max() - flight_data.timestamp.min()).total_seconds()
        theoretical_points = int(total_duration) + 1
        actual_points = len(flight_data)
        coverage_rate = (actual_points / theoretical_points) * 100 if theoretical_points > 0 else 0
        
        # 计算连续段数量
        time_diffs = flight_data['timestamp'].diff().dt.total_seconds()
        large_gaps = time_diffs > 60
        num_segments = large_gaps.sum() + 1  # 间隔数 + 1 = 段数
        
        coverage_stats.append({
            'flight_id': flight_id,
            'actual_points': actual_points,
            'theoretical_points': theoretical_points,
            'coverage_rate': coverage_rate,
            'num_segments': num_segments,
            'duration_hours': total_duration / 3600
        })
    
    coverage_df = pd.DataFrame(coverage_stats)
    
    print(f"航班数量: {len(coverage_df)}")
    print(f"平均时间覆盖率: {coverage_df.coverage_rate.mean():.1f}%")
    print(f"覆盖率 < 50%的航班: {(coverage_df.coverage_rate < 50).sum()}")
    print(f"覆盖率 < 80%的航班: {(coverage_df.coverage_rate < 80).sum()}")
    print(f"平均连续段数: {coverage_df.num_segments.mean():.1f}")
    print(f"多段轨迹航班: {(coverage_df.num_segments > 1).sum()}")
    
    print(f"\n覆盖率最低的航班:")
    worst_coverage = coverage_df.nsmallest(5, 'coverage_rate')
    for _, row in worst_coverage.iterrows():
        print(f"  航班 {row.flight_id}: {row.coverage_rate:.1f}% ({row.actual_points}/{row.theoretical_points}点, {row.num_segments}段)")
    
    return coverage_df

def understand_interpolation_purpose():
    """理解插值处理的目的"""
    print(f"\n=== 插值处理目的分析 ===")
    
    # 读取原始数据和插值数据进行对比
    raw_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    interp_file = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/2022-01-01.parquet'
    
    df_raw = pd.read_parquet(raw_file)
    df_interp = pd.read_parquet(interp_file)
    
    # 选择一个有明显时间间隔的航班进行详细分析
    sample_flight_id = None
    for flight_id in df_raw.flight_id.unique()[:10]:
        flight_data = df_raw[df_raw.flight_id == flight_id].sort_values('timestamp')
        time_diffs = flight_data['timestamp'].diff().dt.total_seconds().dropna()
        if (time_diffs > 60).any():  # 找到有大间隔的航班
            sample_flight_id = flight_id
            break
    
    if sample_flight_id:
        print(f"详细分析航班 {sample_flight_id}:")
        
        # 原始数据
        raw_flight = df_raw[df_raw.flight_id == sample_flight_id].sort_values('timestamp')
        interp_flight = df_interp[df_interp.flight_id == sample_flight_id].sort_values('timestamp')
        
        print(f"  原始数据: {len(raw_flight)} 个点")
        print(f"  插值数据: {len(interp_flight)} 个点")
        
        # 分析时间间隔
        raw_gaps = raw_flight['timestamp'].diff().dt.total_seconds().dropna()
        interp_gaps = interp_flight['timestamp'].diff().dt.total_seconds().dropna()
        
        print(f"  原始数据间隔: 中位数 {raw_gaps.median():.1f}s, 最大 {raw_gaps.max():.1f}s")
        print(f"  插值数据间隔: 中位数 {interp_gaps.median():.1f}s, 最大 {interp_gaps.max():.1f}s")
        
        # 检查插值是否填补了间隔
        large_gaps_raw = (raw_gaps > 60).sum()
        large_gaps_interp = (interp_gaps > 60).sum()
        
        print(f"  原始数据大间隔(>60s): {large_gaps_raw}")
        print(f"  插值数据大间隔(>60s): {large_gaps_interp}")

if __name__ == "__main__":
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    print("分析原始轨迹数据的时间分布和缺失情况...")
    
    # 读取原始数据
    raw_file = 'opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet'
    df_raw = pd.read_parquet(raw_file)
    
    # 执行各项分析
    flight_gap_stats = analyze_time_gaps(df_raw)
    missing_periods = analyze_missing_periods(df_raw)
    coverage_stats = compare_flight_coverage(df_raw)
    understand_interpolation_purpose()
    
    print(f"\n=== 结论 ===")
    print("插值处理的主要原因:")
    print("1. 原始ADS-B数据采样不均匀")
    print("2. 存在大量时间间隔缺失")
    print("3. 需要统一的时间网格进行分析")
    print("4. 但插值过程可能引入了新的数据质量问题")
    print("\n对于轨迹预测模型，建议:")
    print("1. 使用原始数据，接受不均匀采样")
    print("2. 或者进行更保守的插值处理")
    print("3. 重点关注连续的轨迹段")
