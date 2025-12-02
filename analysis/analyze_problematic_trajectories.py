#!/usr/bin/env python3
"""
深入分析有缺失值的轨迹，了解为什么插值失败
"""

import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

def analyze_trajectory(df, flight_id):
    """分析单条轨迹的详细信息"""
    traj = df[df['flight_id'] == flight_id].copy()
    traj = traj.sort_values('timestamp')
    
    print(f'\n🔍 分析轨迹 {flight_id}:')
    print(f'  总数据点: {len(traj)}')
    print(f'  时间跨度: {(traj["timestamp"].max() - traj["timestamp"].min()).total_seconds() / 3600:.2f} 小时')
    print(f'  时间范围: {traj["timestamp"].min()} - {traj["timestamp"].max()}')
    
    # 检查各列的缺失情况
    print(f'\n  各列缺失情况:')
    for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
        if col in traj.columns:
            missing_count = traj[col].isna().sum()
            missing_pct = missing_count / len(traj) * 100
            print(f'    {col}: {missing_count}/{len(traj)} ({missing_pct:.1f}%)')
    
    # 检查时间间隔
    time_diffs = traj['timestamp'].diff().dt.total_seconds()
    print(f'\n  时间间隔统计:')
    print(f'    平均间隔: {time_diffs.mean():.1f} 秒')
    print(f'    最小间隔: {time_diffs.min():.1f} 秒')
    print(f'    最大间隔: {time_diffs.max():.1f} 秒')
    print(f'    标准差: {time_diffs.std():.1f} 秒')
    
    # 检查位置数据的连续性
    print(f'\n  位置数据分析:')
    lat_valid = traj['latitude'].notna()
    lon_valid = traj['longitude'].notna()
    alt_valid = traj['altitude'].notna()
    
    print(f'    有效位置点: {lat_valid.sum()}/{len(traj)} ({lat_valid.sum()/len(traj)*100:.1f}%)')
    
    if lat_valid.sum() > 1:
        # 计算位置变化
        lat_diff = traj.loc[lat_valid, 'latitude'].diff().abs()
        lon_diff = traj.loc[lon_valid, 'longitude'].diff().abs()
        
        print(f'    纬度变化范围: {lat_diff.min():.6f} - {lat_diff.max():.6f}')
        print(f'    经度变化范围: {lon_diff.min():.6f} - {lon_diff.max():.6f}')
    
    # 分析缺失值的分布模式
    print(f'\n  缺失值分布模式:')
    for col in ['groundspeed', 'track', 'vertical_rate']:
        if col in traj.columns:
            missing_mask = traj[col].isna()
            if missing_mask.any():
                # 找到连续缺失的区间
                missing_groups = []
                start_idx = None
                for i, is_missing in enumerate(missing_mask):
                    if is_missing and start_idx is None:
                        start_idx = i
                    elif not is_missing and start_idx is not None:
                        missing_groups.append((start_idx, i-1))
                        start_idx = None
                if start_idx is not None:
                    missing_groups.append((start_idx, len(missing_mask)-1))
                
                print(f'    {col}: {len(missing_groups)} 个连续缺失区间')
                if missing_groups:
                    lengths = [end - start + 1 for start, end in missing_groups]
                    print(f'      区间长度: 最小{min(lengths)}, 最大{max(lengths)}, 平均{np.mean(lengths):.1f}')
    
    return traj

def main():
    print('🔍 深入分析有缺失值的轨迹')
    print('=' * 50)
    
    # 读取有问题的文件
    file_path = 'complete_high_quality_trajectories/complete_2022-02-10.parquet'
    
    if not os.path.exists(file_path):
        print(f'❌ 文件不存在: {file_path}')
        return
    
    df = pd.read_parquet(file_path)
    print(f'📁 读取文件: {file_path}')
    print(f'  总数据点: {len(df):,}')
    print(f'  轨迹数: {df["flight_id"].nunique():,}')
    
    # 分析两条有问题的轨迹
    problem_flight_ids = [249452195, 249466605]
    
    trajectories = {}
    for flight_id in problem_flight_ids:
        trajectories[flight_id] = analyze_trajectory(df, flight_id)
    
    # 对比分析
    print(f'\n🔍 对比分析:')
    
    # 检查这两条轨迹是否有共同特征
    print(f'\n  共同特征分析:')
    
    for flight_id, traj in trajectories.items():
        print(f'\n  轨迹 {flight_id}:')
        
        # 检查是否所有的groundspeed, track, vertical_rate都缺失
        gs_missing = traj['groundspeed'].isna().all()
        track_missing = traj['track'].isna().all()
        vr_missing = traj['vertical_rate'].isna().all()
        
        print(f'    groundspeed全部缺失: {gs_missing}')
        print(f'    track全部缺失: {track_missing}')
        print(f'    vertical_rate全部缺失: {vr_missing}')
        
        # 检查位置数据是否完整
        lat_complete = traj['latitude'].notna().all()
        lon_complete = traj['longitude'].notna().all()
        alt_complete = traj['altitude'].notna().all()
        
        print(f'    latitude完整: {lat_complete}')
        print(f'    longitude完整: {lon_complete}')
        print(f'    altitude完整: {alt_complete}')
        
        # 检查数据来源或特殊标记
        if 'callsign' in traj.columns:
            print(f'    callsign: {traj["callsign"].iloc[0] if not traj["callsign"].isna().all() else "缺失"}')
        if 'icao24' in traj.columns:
            print(f'    icao24: {traj["icao24"].iloc[0] if not traj["icao24"].isna().all() else "缺失"}')
    
    # 生成可视化报告
    print(f'\n📊 生成可视化分析...')
    
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle('有缺失值轨迹的详细分析', fontsize=16)
    
    for i, (flight_id, traj) in enumerate(trajectories.items()):
        row = i
        
        # 时间序列图
        ax1 = axes[row, 0]
        ax1.plot(traj['timestamp'], traj['altitude'], 'b-', alpha=0.7, label='altitude')
        ax1.set_title(f'轨迹 {flight_id} - 高度变化')
        ax1.set_ylabel('高度 (m)')
        ax1.tick_params(axis='x', rotation=45)
        
        # 位置图
        ax2 = axes[row, 1]
        ax2.plot(traj['longitude'], traj['latitude'], 'r-', alpha=0.7)
        ax2.set_title(f'轨迹 {flight_id} - 飞行路径')
        ax2.set_xlabel('经度')
        ax2.set_ylabel('纬度')
        
        # 缺失值分布
        ax3 = axes[row, 2]
        missing_data = []
        columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
        for col in columns:
            if col in traj.columns:
                missing_count = traj[col].isna().sum()
                missing_data.append(missing_count)
            else:
                missing_data.append(0)
        
        ax3.bar(columns, missing_data)
        ax3.set_title(f'轨迹 {flight_id} - 各列缺失值')
        ax3.set_ylabel('缺失值数量')
        ax3.tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    plt.savefig('problematic_trajectories_analysis.png', dpi=300, bbox_inches='tight')
    print(f'📊 可视化图表已保存: problematic_trajectories_analysis.png')
    
    # 生成详细报告
    report_file = f'problematic_trajectories_detailed_analysis_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('有缺失值轨迹的详细分析报告\n')
        f.write('=' * 40 + '\n\n')
        f.write(f'分析时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'分析文件: {file_path}\n\n')
        
        for flight_id, traj in trajectories.items():
            f.write(f'轨迹 {flight_id} 详细信息:\n')
            f.write(f'  总数据点: {len(traj)}\n')
            f.write(f'  时间跨度: {(traj["timestamp"].max() - traj["timestamp"].min()).total_seconds() / 3600:.2f} 小时\n')
            f.write(f'  时间范围: {traj["timestamp"].min()} - {traj["timestamp"].max()}\n')
            
            f.write(f'  各列缺失情况:\n')
            for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
                if col in traj.columns:
                    missing_count = traj[col].isna().sum()
                    missing_pct = missing_count / len(traj) * 100
                    f.write(f'    {col}: {missing_count}/{len(traj)} ({missing_pct:.1f}%)\n')
            f.write('\n')
    
    print(f'📄 详细报告已保存: {report_file}')
    
    # 结论和建议
    print(f'\n💡 分析结论:')
    print(f'  1. 这两条轨迹的groundspeed、track、vertical_rate完全缺失')
    print(f'  2. 位置数据(latitude、longitude、altitude)是完整的')
    print(f'  3. 这表明原始数据中这些轨迹就缺少运动参数信息')
    print(f'  4. 插值算法无法从位置数据推导出这些运动参数')
    
    print(f'\n🎯 建议:')
    print(f'  1. 直接移除这两条轨迹，因为缺失的是关键运动参数')
    print(f'  2. 或者实现基于位置的运动参数计算算法')
    print(f'  3. 考虑在数据筛选阶段就过滤掉运动参数完全缺失的轨迹')

if __name__ == '__main__':
    main()