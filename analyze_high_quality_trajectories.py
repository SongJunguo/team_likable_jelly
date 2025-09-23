#!/usr/bin/env python3
"""
分析高质量轨迹（5%缺失率以内）的特征和分布
"""

import pandas as pd
import numpy as np
import os

def analyze_high_quality_trajectories():
    """分析高质量轨迹的缺失率分布和特征"""
    
    # 读取分析结果
    parquet_path = '/workspace/aircraft_trajectory/team_likable_jelly/junguo_analysis_for_opensky2022/analysis_for_interpolation/full_365_analysis_output_v2/trajectory_analysis.parquet'
    
    if not os.path.exists(parquet_path):
        print(f"错误：文件不存在 {parquet_path}")
        return
    
    print("正在读取轨迹分析数据...")
    df = pd.read_parquet(parquet_path)
    
    print('=== 数据概览 ===')
    print(f'总轨迹数: {len(df):,}')
    print(f'数据列: {list(df.columns)}')
    
    # 分析缺失率分布
    print('\n=== 缺失率分布 ===')
    missing_rates = df['missing_rate'] * 100  # 转换为百分比
    print(f'缺失率统计:')
    print(f'  平均: {missing_rates.mean():.2f}%')
    print(f'  中位数: {missing_rates.median():.2f}%')
    print(f'  最小: {missing_rates.min():.2f}%')
    print(f'  最大: {missing_rates.max():.2f}%')
    
    # 分析不同缺失率阈值下的轨迹数量
    thresholds = [1, 2, 3, 5, 10, 15, 20]
    print('\n=== 不同缺失率阈值下的轨迹数量 ===')
    for threshold in thresholds:
        count = (missing_rates <= threshold).sum()
        percentage = count / len(df) * 100
        print(f'  ≤{threshold}%: {count:,} 条轨迹 ({percentage:.1f}%)')
    
    # 重点分析5%以内的高质量轨迹
    high_quality = df[missing_rates <= 5.0].copy()
    print(f'\n=== 5%缺失率以内的高质量轨迹分析 ===')
    print(f'数量: {len(high_quality):,} 条')
    print(f'占比: {len(high_quality)/len(df)*100:.1f}%')
    
    if len(high_quality) > 0:
        # 分析高质量轨迹的缺失窗口特征
        print('\n=== 高质量轨迹的缺失窗口分析 ===')
        print(f'最大缺失窗口统计:')
        print(f'  平均: {high_quality["max_window"].mean():.1f} 个点')
        print(f'  中位数: {high_quality["max_window"].median():.1f} 个点')
        print(f'  最大: {high_quality["max_window"].max():.0f} 个点')
        print(f'  最小: {high_quality["max_window"].min():.0f} 个点')
        
        # 分析头尾缺失情况
        print('\n=== 头尾缺失情况 ===')
        head_missing = high_quality['head_missing'].sum()
        tail_missing = high_quality['tail_missing'].sum()
        print(f'有头部缺失的轨迹: {head_missing:,} 条 ({head_missing/len(high_quality)*100:.1f}%)')
        print(f'有尾部缺失的轨迹: {tail_missing:,} 条 ({tail_missing/len(high_quality)*100:.1f}%)')
        
        # 分析轨迹长度分布
        print('\n=== 轨迹长度分布 ===')
        print(f'总点数统计:')
        print(f'  平均: {high_quality["total_points"].mean():.1f} 个点')
        print(f'  中位数: {high_quality["total_points"].median():.1f} 个点')
        print(f'  最大: {high_quality["total_points"].max():.0f} 个点')
        print(f'  最小: {high_quality["total_points"].min():.0f} 个点')
        
        # 输出高质量轨迹的flight_id列表
        print('\n=== 输出高质量轨迹flight_id ===')
        output_file = 'high_quality_flight_ids.txt'
        flight_ids = high_quality['flight_id'].tolist()
        
        with open(output_file, 'w') as f:
            for flight_id in flight_ids:
                f.write(f"{flight_id}\n")
        
        print(f'已将 {len(flight_ids):,} 个高质量轨迹的flight_id保存到: {output_file}')
        print(f'前10个flight_id示例:')
        for i, fid in enumerate(flight_ids[:10]):
            print(f'  {i+1}. {fid}')
        
        # 分析最长缺失窗口的分布
        print('\n=== 最长缺失窗口分布详情 ===')
        max_windows = high_quality['max_window']
        window_ranges = [(0, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, float('inf'))]
        
        for min_val, max_val in window_ranges:
            if max_val == float('inf'):
                count = (max_windows > min_val).sum()
                print(f'  >{min_val}个点: {count:,} 条轨迹')
            else:
                count = ((max_windows >= min_val) & (max_windows <= max_val)).sum()
                print(f'  {min_val}-{max_val}个点: {count:,} 条轨迹')
    
    else:
        print("没有找到5%缺失率以内的轨迹")

if __name__ == "__main__":
    analyze_high_quality_trajectories()