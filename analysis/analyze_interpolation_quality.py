#!/usr/bin/env python3
"""
分析插值质量和缺失值分布
"""

import pandas as pd
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
from pathlib import Path

def analyze_single_file(file_path):
    """分析单个文件的插值质量"""
    try:
        df = pd.read_parquet(file_path)
        
        # 基本统计
        total_points = len(df)
        total_trajectories = df['flight_id'].nunique()
        
        # 检查各列的缺失值
        missing_stats = {}
        for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
            if col in df.columns:
                missing_count = df[col].isna().sum()
                missing_stats[col] = {
                    'count': missing_count,
                    'rate': missing_count / total_points * 100 if total_points > 0 else 0
                }
        
        # 分析有缺失值的轨迹
        trajectories_with_missing = []
        for flight_id, group in df.groupby('flight_id'):
            traj_missing = {}
            has_missing = False
            
            for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
                if col in group.columns:
                    missing_count = group[col].isna().sum()
                    if missing_count > 0:
                        has_missing = True
                        traj_missing[col] = missing_count
            
            if has_missing:
                trajectories_with_missing.append({
                    'flight_id': flight_id,
                    'total_points': len(group),
                    'missing_by_column': traj_missing,
                    'total_missing': sum(traj_missing.values())
                })
        
        return {
            'file': os.path.basename(file_path),
            'total_points': total_points,
            'total_trajectories': total_trajectories,
            'missing_stats': missing_stats,
            'trajectories_with_missing': len(trajectories_with_missing),
            'trajectories_with_missing_details': trajectories_with_missing[:10]  # 只保留前10个作为样本
        }
        
    except Exception as e:
        return {
            'file': os.path.basename(file_path),
            'error': str(e)
        }

def main():
    print('🔍 分析插值质量和缺失值分布')
    print('=' * 60)
    
    output_dir = 'complete_high_quality_trajectories'
    
    if not os.path.exists(output_dir):
        print(f'❌ 输出目录不存在: {output_dir}')
        return
    
    # 获取所有文件
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.parquet')]
    print(f'📁 找到 {len(files)} 个文件')
    
    # 抽样分析（分析前50个文件）
    sample_files = files[:50]
    print(f'📊 抽样分析前 {len(sample_files)} 个文件')
    
    start_time = time.time()
    
    # 多进程分析
    with ProcessPoolExecutor(max_workers=min(mp.cpu_count()//2, 8)) as executor:
        results = list(executor.map(analyze_single_file, sample_files))
    
    elapsed_time = time.time() - start_time
    
    # 汇总统计
    total_points = 0
    total_trajectories = 0
    total_missing_by_column = {}
    total_trajectories_with_missing = 0
    error_files = []
    
    print(f'\n📈 分析结果 (处理时间: {elapsed_time:.1f}秒):')
    print('-' * 60)
    
    for result in results:
        if 'error' in result:
            error_files.append(result)
            continue
        
        total_points += result['total_points']
        total_trajectories += result['total_trajectories']
        total_trajectories_with_missing += result['trajectories_with_missing']
        
        # 累计各列缺失值
        for col, stats in result['missing_stats'].items():
            if col not in total_missing_by_column:
                total_missing_by_column[col] = {'count': 0, 'rate': 0}
            total_missing_by_column[col]['count'] += stats['count']
    
    # 计算总体缺失率
    for col in total_missing_by_column:
        total_missing_by_column[col]['rate'] = total_missing_by_column[col]['count'] / total_points * 100 if total_points > 0 else 0
    
    print(f'总数据点: {total_points:,}')
    print(f'总轨迹数: {total_trajectories:,}')
    print(f'有缺失值的轨迹数: {total_trajectories_with_missing:,}')
    print(f'有缺失值的轨迹比例: {total_trajectories_with_missing/total_trajectories*100:.2f}%')
    
    print(f'\n📋 各列缺失值统计:')
    for col, stats in total_missing_by_column.items():
        print(f'  {col}: {stats["count"]:,} 个缺失值 ({stats["rate"]:.4f}%)')
    
    total_missing = sum(stats['count'] for stats in total_missing_by_column.values())
    print(f'\n总缺失值: {total_missing:,} ({total_missing/total_points*100:.4f}%)')
    
    # 分析缺失值模式
    print(f'\n🔍 缺失值轨迹样本分析:')
    sample_count = 0
    for result in results:
        if 'error' in result or not result['trajectories_with_missing_details']:
            continue
        
        for traj in result['trajectories_with_missing_details'][:3]:  # 每个文件最多显示3个样本
            if sample_count >= 10:  # 总共最多显示10个样本
                break
            
            print(f'  轨迹 {traj["flight_id"]}: {traj["total_points"]}个点, 缺失{traj["total_missing"]}个值')
            for col, missing_count in traj['missing_by_column'].items():
                print(f'    - {col}: {missing_count}个缺失值')
            sample_count += 1
        
        if sample_count >= 10:
            break
    
    # 估算全部文件
    estimated_total_points = total_points * len(files) // len(sample_files)
    estimated_total_missing = total_missing * len(files) // len(sample_files)
    estimated_trajectories_with_missing = total_trajectories_with_missing * len(files) // len(sample_files)
    
    print(f'\n🎯 全部文件估算:')
    print(f'预计总数据点: {estimated_total_points:,}')
    print(f'预计总缺失值: {estimated_total_missing:,} ({estimated_total_missing/estimated_total_points*100:.4f}%)')
    print(f'预计有缺失值的轨迹: {estimated_trajectories_with_missing:,}')
    
    # 保存详细报告
    report_file = f'interpolation_quality_analysis_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('插值质量分析报告\n')
        f.write('=' * 30 + '\n\n')
        f.write(f'分析时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'分析文件数: {len(sample_files)} / {len(files)}\n')
        f.write(f'总数据点: {total_points:,}\n')
        f.write(f'总轨迹数: {total_trajectories:,}\n')
        f.write(f'有缺失值的轨迹数: {total_trajectories_with_missing:,}\n')
        f.write(f'有缺失值的轨迹比例: {total_trajectories_with_missing/total_trajectories*100:.2f}%\n\n')
        
        f.write('各列缺失值统计:\n')
        for col, stats in total_missing_by_column.items():
            f.write(f'  {col}: {stats["count"]:,} 个缺失值 ({stats["rate"]:.4f}%)\n')
        
        f.write(f'\n总缺失值: {total_missing:,} ({total_missing/total_points*100:.4f}%)\n')
        
        f.write(f'\n全部文件估算:\n')
        f.write(f'预计总数据点: {estimated_total_points:,}\n')
        f.write(f'预计总缺失值: {estimated_total_missing:,} ({estimated_total_missing/estimated_total_points*100:.4f}%)\n')
        f.write(f'预计有缺失值的轨迹: {estimated_trajectories_with_missing:,}\n')
    
    print(f'\n📄 详细报告已保存至: {report_file}')
    
    # 错误文件报告
    if error_files:
        print(f'\n⚠️  处理失败的文件: {len(error_files)}个')
        for error_file in error_files[:5]:
            print(f'  {error_file["file"]}: {error_file["error"]}')

if __name__ == '__main__':
    main()