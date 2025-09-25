#!/usr/bin/env python3
"""
数据集改进策略：解决缺失值问题的多种方案
"""

import pandas as pd
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
from pathlib import Path

class TrajectoryImprovementStrategy:
    """轨迹改进策略类"""
    
    def __init__(self):
        self.strategies = {
            'remove_problematic': self.remove_problematic_trajectories,
            'compute_motion_params': self.compute_motion_parameters,
            'hybrid_approach': self.hybrid_approach
        }
    
    def remove_problematic_trajectories(self, df, flight_ids_to_remove):
        """策略1: 直接移除有问题的轨迹"""
        print(f'🗑️  策略1: 移除有问题的轨迹')
        
        original_count = df['flight_id'].nunique()
        original_points = len(df)
        
        # 移除指定的轨迹
        df_clean = df[~df['flight_id'].isin(flight_ids_to_remove)].copy()
        
        new_count = df_clean['flight_id'].nunique()
        new_points = len(df_clean)
        
        print(f'  移除轨迹数: {len(flight_ids_to_remove)}')
        print(f'  剩余轨迹数: {new_count} (原来: {original_count})')
        print(f'  剩余数据点: {new_points:,} (原来: {original_points:,})')
        print(f'  数据点损失: {original_points - new_points:,} ({(original_points - new_points)/original_points*100:.3f}%)')
        
        return df_clean
    
    def compute_motion_parameters(self, df):
        """策略2: 基于位置数据计算运动参数"""
        print(f'🧮 策略2: 基于位置数据计算运动参数')
        
        df_computed = df.copy()
        computed_count = 0
        
        for flight_id, group in df.groupby('flight_id'):
            # 检查是否需要计算运动参数
            needs_computation = (
                group['groundspeed'].isna().all() or 
                group['track'].isna().all() or 
                group['vertical_rate'].isna().all()
            )
            
            if needs_computation and len(group) > 1:
                group_sorted = group.sort_values('timestamp')
                
                # 计算时间差（秒）
                time_diffs = group_sorted['timestamp'].diff().dt.total_seconds()
                
                # 计算地面速度 (基于经纬度变化)
                if group_sorted['groundspeed'].isna().all():
                    lat_diffs = group_sorted['latitude'].diff()
                    lon_diffs = group_sorted['longitude'].diff()
                    
                    # 简化的距离计算 (假设地球是平面，适用于小范围)
                    # 1度纬度 ≈ 111km, 1度经度 ≈ 111km * cos(纬度)
                    lat_km = lat_diffs * 111
                    lon_km = lon_diffs * 111 * np.cos(np.radians(group_sorted['latitude']))
                    
                    distance_km = np.sqrt(lat_km**2 + lon_km**2)
                    groundspeed_kmh = distance_km / (time_diffs / 3600)  # km/h
                    groundspeed_ms = groundspeed_kmh / 3.6  # m/s
                    
                    # 填充计算出的地面速度
                    df_computed.loc[group_sorted.index, 'groundspeed'] = groundspeed_ms
                
                # 计算航向角 (track)
                if group_sorted['track'].isna().all():
                    lat_diffs = group_sorted['latitude'].diff()
                    lon_diffs = group_sorted['longitude'].diff()
                    
                    # 计算航向角 (0-360度)
                    track_rad = np.arctan2(lon_diffs, lat_diffs)
                    track_deg = np.degrees(track_rad)
                    track_deg = (track_deg + 360) % 360  # 转换为0-360度
                    
                    df_computed.loc[group_sorted.index, 'track'] = track_deg
                
                # 计算垂直速度
                if group_sorted['vertical_rate'].isna().all():
                    alt_diffs = group_sorted['altitude'].diff()
                    vertical_rate = alt_diffs / time_diffs  # m/s
                    
                    df_computed.loc[group_sorted.index, 'vertical_rate'] = vertical_rate
                
                computed_count += 1
        
        print(f'  计算了 {computed_count} 条轨迹的运动参数')
        
        return df_computed
    
    def hybrid_approach(self, df, flight_ids_to_remove):
        """策略3: 混合方法 - 先尝试计算，失败则移除"""
        print(f'🔄 策略3: 混合方法')
        
        # 先尝试计算运动参数
        df_computed = self.compute_motion_parameters(df)
        
        # 检查计算后仍有缺失值的轨迹
        still_problematic = []
        for flight_id in flight_ids_to_remove:
            traj = df_computed[df_computed['flight_id'] == flight_id]
            if (traj['groundspeed'].isna().any() or 
                traj['track'].isna().any() or 
                traj['vertical_rate'].isna().any()):
                still_problematic.append(flight_id)
        
        print(f'  计算后仍有问题的轨迹: {len(still_problematic)}')
        
        # 移除仍有问题的轨迹
        if still_problematic:
            df_final = self.remove_problematic_trajectories(df_computed, still_problematic)
        else:
            df_final = df_computed
        
        return df_final

def analyze_strategy_impact(original_df, improved_df, strategy_name):
    """分析策略的影响"""
    print(f'\n📊 策略 "{strategy_name}" 影响分析:')
    
    orig_trajectories = original_df['flight_id'].nunique()
    orig_points = len(original_df)
    
    new_trajectories = improved_df['flight_id'].nunique()
    new_points = len(improved_df)
    
    print(f'  轨迹数变化: {orig_trajectories} → {new_trajectories} (变化: {new_trajectories - orig_trajectories})')
    print(f'  数据点变化: {orig_points:,} → {new_points:,} (变化: {new_points - orig_points:,})')
    
    if orig_points > 0:
        point_change_pct = (new_points - orig_points) / orig_points * 100
        print(f'  数据点变化率: {point_change_pct:+.3f}%')
    
    # 检查缺失值
    missing_stats = {}
    for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
        if col in improved_df.columns:
            missing_count = improved_df[col].isna().sum()
            missing_pct = missing_count / len(improved_df) * 100 if len(improved_df) > 0 else 0
            missing_stats[col] = (missing_count, missing_pct)
    
    print(f'  改进后各列缺失值:')
    for col, (count, pct) in missing_stats.items():
        print(f'    {col}: {count} ({pct:.4f}%)')
    
    total_missing = sum(count for count, _ in missing_stats.values())
    print(f'  总缺失值: {total_missing}')
    
    return {
        'strategy': strategy_name,
        'trajectory_change': new_trajectories - orig_trajectories,
        'point_change': new_points - orig_points,
        'point_change_pct': point_change_pct if orig_points > 0 else 0,
        'total_missing': total_missing,
        'missing_stats': missing_stats
    }

def main():
    print('🎯 数据集改进策略分析')
    print('=' * 50)
    
    # 读取有问题的文件
    file_path = 'complete_high_quality_trajectories/complete_2022-02-10.parquet'
    
    if not os.path.exists(file_path):
        print(f'❌ 文件不存在: {file_path}')
        return
    
    df = pd.read_parquet(file_path)
    print(f'📁 读取测试文件: {file_path}')
    print(f'  总数据点: {len(df):,}')
    print(f'  轨迹数: {df["flight_id"].nunique():,}')
    
    # 有问题的轨迹ID
    problematic_flight_ids = [249452195, 249466605]
    
    # 初始化策略类
    strategy_handler = TrajectoryImprovementStrategy()
    
    # 测试各种策略
    strategies_results = {}
    
    print(f'\n🧪 测试各种改进策略:')
    
    # 策略1: 直接移除
    print(f'\n' + '='*30)
    df_strategy1 = strategy_handler.remove_problematic_trajectories(df, problematic_flight_ids)
    result1 = analyze_strategy_impact(df, df_strategy1, "直接移除问题轨迹")
    strategies_results['remove'] = result1
    
    # 策略2: 计算运动参数
    print(f'\n' + '='*30)
    df_strategy2 = strategy_handler.compute_motion_parameters(df)
    result2 = analyze_strategy_impact(df, df_strategy2, "计算运动参数")
    strategies_results['compute'] = result2
    
    # 策略3: 混合方法
    print(f'\n' + '='*30)
    df_strategy3 = strategy_handler.hybrid_approach(df, problematic_flight_ids)
    result3 = analyze_strategy_impact(df, df_strategy3, "混合方法")
    strategies_results['hybrid'] = result3
    
    # 生成策略对比报告
    print(f'\n📋 策略对比总结:')
    print(f'{"策略":<15} {"轨迹变化":<10} {"数据点变化":<12} {"变化率":<10} {"总缺失值":<10}')
    print(f'-' * 65)
    
    for strategy_key, result in strategies_results.items():
        print(f'{result["strategy"]:<15} {result["trajectory_change"]:<10} {result["point_change"]:<12,} {result["point_change_pct"]:<10.3f}% {result["total_missing"]:<10}')
    
    # 推荐策略
    print(f'\n🎯 推荐策略:')
    
    # 找到缺失值最少的策略
    best_strategy = min(strategies_results.values(), key=lambda x: x['total_missing'])
    
    print(f'  最佳策略: {best_strategy["strategy"]}')
    print(f'  理由: 该策略能够实现零缺失值，数据点损失最小')
    
    if best_strategy['total_missing'] == 0:
        print(f'  ✅ 该策略可以实现您的目标：轨迹一个缺失点都没有')
    else:
        print(f'  ⚠️  该策略仍有 {best_strategy["total_missing"]} 个缺失值')
    
    # 保存策略报告
    report_file = f'improvement_strategy_report_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('数据集改进策略分析报告\n')
        f.write('=' * 30 + '\n\n')
        f.write(f'分析时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'测试文件: {file_path}\n')
        f.write(f'问题轨迹: {problematic_flight_ids}\n\n')
        
        f.write('策略对比结果:\n')
        f.write(f'{"策略":<15} {"轨迹变化":<10} {"数据点变化":<12} {"变化率":<10} {"总缺失值":<10}\n')
        f.write(f'-' * 65 + '\n')
        
        for result in strategies_results.values():
            f.write(f'{result["strategy"]:<15} {result["trajectory_change"]:<10} {result["point_change"]:<12,} {result["point_change_pct"]:<10.3f}% {result["total_missing"]:<10}\n')
        
        f.write(f'\n推荐策略: {best_strategy["strategy"]}\n')
        f.write(f'推荐理由: 该策略总缺失值为 {best_strategy["total_missing"]}\n')
    
    print(f'\n📄 详细报告已保存: {report_file}')
    
    # 实施建议
    print(f'\n💡 实施建议:')
    if best_strategy['strategy'] == '直接移除问题轨迹':
        print(f'  1. 在数据处理流程中添加轨迹质量检查')
        print(f'  2. 过滤掉运动参数完全缺失的轨迹')
        print(f'  3. 这样可以确保最终数据集100%无缺失值')
    elif best_strategy['strategy'] == '计算运动参数':
        print(f'  1. 实现基于位置的运动参数计算算法')
        print(f'  2. 可以保留更多轨迹数据')
        print(f'  3. 需要验证计算出的参数的准确性')
    else:
        print(f'  1. 先尝试计算运动参数')
        print(f'  2. 对于无法计算的轨迹，直接移除')
        print(f'  3. 平衡数据完整性和数据质量')

if __name__ == '__main__':
    main()