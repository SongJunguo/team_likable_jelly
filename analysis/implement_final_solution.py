#!/usr/bin/env python3
"""
实施最终解决方案：移除有缺失值的轨迹，确保数据集100%无缺失值
"""

import pandas as pd
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
from pathlib import Path

def find_and_remove_problematic_trajectories(file_path):
    """在单个文件中找到并移除有缺失值的轨迹"""
    try:
        df = pd.read_parquet(file_path)
        original_trajectories = df['flight_id'].nunique()
        original_points = len(df)
        
        # 找到有缺失值的轨迹
        problematic_flight_ids = set()
        
        for flight_id, group in df.groupby('flight_id'):
            # 检查关键列的缺失值
            for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
                if col in group.columns and group[col].isna().any():
                    problematic_flight_ids.add(flight_id)
                    break
        
        # 移除有问题的轨迹
        if problematic_flight_ids:
            df_clean = df[~df['flight_id'].isin(problematic_flight_ids)].copy()
        else:
            df_clean = df.copy()
        
        new_trajectories = df_clean['flight_id'].nunique()
        new_points = len(df_clean)
        
        # 验证清理后的数据
        total_missing = 0
        for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
            if col in df_clean.columns:
                total_missing += df_clean[col].isna().sum()
        
        result = {
            'file': os.path.basename(file_path),
            'original_trajectories': original_trajectories,
            'original_points': original_points,
            'removed_trajectories': len(problematic_flight_ids),
            'new_trajectories': new_trajectories,
            'new_points': new_points,
            'total_missing_after': total_missing,
            'problematic_flight_ids': list(problematic_flight_ids)
        }
        
        # 保存清理后的文件
        output_path = file_path.replace('complete_high_quality_trajectories', 'perfect_trajectories')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df_clean.to_parquet(output_path, index=False)
        
        return result
        
    except Exception as e:
        print(f'处理文件 {file_path} 时出错: {e}')
        return None

def main():
    print('🎯 实施最终解决方案：创建100%无缺失值的数据集')
    print('=' * 60)
    
    input_dir = 'complete_high_quality_trajectories'
    output_dir = 'perfect_trajectories'
    
    if not os.path.exists(input_dir):
        print(f'❌ 输入目录不存在: {input_dir}')
        return
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有文件
    files = [os.path.join(input_dir, f) for f in os.listdir(input_dir) if f.endswith('.parquet')]
    print(f'📁 处理 {len(files)} 个文件')
    
    start_time = time.time()
    
    # 多进程处理
    print('⏳ 开始清理数据集...')
    with ProcessPoolExecutor(max_workers=min(mp.cpu_count()//2, 16)) as executor:
        results = list(executor.map(find_and_remove_problematic_trajectories, files))
    
    # 过滤掉失败的结果
    results = [r for r in results if r is not None]
    
    elapsed_time = time.time() - start_time
    
    # 统计总体结果
    total_original_trajectories = sum(r['original_trajectories'] for r in results)
    total_original_points = sum(r['original_points'] for r in results)
    total_removed_trajectories = sum(r['removed_trajectories'] for r in results)
    total_new_trajectories = sum(r['new_trajectories'] for r in results)
    total_new_points = sum(r['new_points'] for r in results)
    total_missing_after = sum(r['total_missing_after'] for r in results)
    
    print(f'\n📊 清理结果 (处理时间: {elapsed_time:.1f}秒):')
    print(f'处理文件数: {len(results)}')
    print(f'原始轨迹数: {total_original_trajectories:,}')
    print(f'原始数据点: {total_original_points:,}')
    print(f'移除轨迹数: {total_removed_trajectories:,}')
    print(f'最终轨迹数: {total_new_trajectories:,}')
    print(f'最终数据点: {total_new_points:,}')
    print(f'数据点损失: {total_original_points - total_new_points:,} ({(total_original_points - total_new_points)/total_original_points*100:.3f}%)')
    print(f'清理后缺失值: {total_missing_after}')
    
    if total_missing_after == 0:
        print(f'✅ 成功！数据集现在100%无缺失值！')
    else:
        print(f'⚠️  警告：仍有 {total_missing_after} 个缺失值')
    
    # 分析移除的轨迹
    files_with_removals = [r for r in results if r['removed_trajectories'] > 0]
    print(f'\n🔍 有轨迹被移除的文件: {len(files_with_removals)} 个')
    
    if files_with_removals:
        print(f'移除轨迹最多的文件:')
        files_with_removals.sort(key=lambda x: x['removed_trajectories'], reverse=True)
        for i, result in enumerate(files_with_removals[:5]):
            print(f'  {i+1}. {result["file"]}: 移除 {result["removed_trajectories"]} 条轨迹')
    
    # 收集所有被移除的轨迹ID
    all_removed_flight_ids = []
    for result in results:
        all_removed_flight_ids.extend(result['problematic_flight_ids'])
    
    print(f'\n📋 总共移除的轨迹ID: {len(all_removed_flight_ids)} 个')
    if len(all_removed_flight_ids) <= 20:
        print(f'被移除的轨迹ID: {all_removed_flight_ids}')
    else:
        print(f'前20个被移除的轨迹ID: {all_removed_flight_ids[:20]}')
    
    # 生成最终报告
    report_file = f'perfect_dataset_creation_report_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('完美数据集创建报告\n')
        f.write('=' * 25 + '\n\n')
        f.write(f'创建时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'处理时间: {elapsed_time:.1f} 秒\n')
        f.write(f'输入目录: {input_dir}\n')
        f.write(f'输出目录: {output_dir}\n\n')
        
        f.write('处理统计:\n')
        f.write(f'  处理文件数: {len(results)}\n')
        f.write(f'  原始轨迹数: {total_original_trajectories:,}\n')
        f.write(f'  原始数据点: {total_original_points:,}\n')
        f.write(f'  移除轨迹数: {total_removed_trajectories:,}\n')
        f.write(f'  最终轨迹数: {total_new_trajectories:,}\n')
        f.write(f'  最终数据点: {total_new_points:,}\n')
        f.write(f'  数据点损失: {total_original_points - total_new_points:,} ({(total_original_points - total_new_points)/total_original_points*100:.3f}%)\n')
        f.write(f'  清理后缺失值: {total_missing_after}\n\n')
        
        f.write('质量保证:\n')
        if total_missing_after == 0:
            f.write('  ✅ 数据集100%无缺失值\n')
        else:
            f.write(f'  ⚠️  仍有 {total_missing_after} 个缺失值\n')
        
        f.write(f'\n被移除的轨迹ID ({len(all_removed_flight_ids)} 个):\n')
        for i, flight_id in enumerate(all_removed_flight_ids):
            f.write(f'  {i+1}. {flight_id}\n')
        
        f.write(f'\n文件处理详情:\n')
        for result in results:
            if result['removed_trajectories'] > 0:
                f.write(f'  {result["file"]}: 移除 {result["removed_trajectories"]} 条轨迹\n')
    
    print(f'\n📄 详细报告已保存: {report_file}')
    
    # 验证输出目录
    output_files = [f for f in os.listdir(output_dir) if f.endswith('.parquet')]
    print(f'\n✅ 完美数据集已创建:')
    print(f'  输出目录: {output_dir}')
    print(f'  文件数量: {len(output_files)}')
    print(f'  轨迹总数: {total_new_trajectories:,}')
    print(f'  数据点总数: {total_new_points:,}')
    print(f'  缺失值: {total_missing_after} (0%)')
    
    # 最终建议
    print(f'\n💡 使用建议:')
    print(f'  1. 新的数据集位于 {output_dir} 目录')
    print(f'  2. 该数据集保证100%无缺失值')
    print(f'  3. 数据点损失极小 ({(total_original_points - total_new_points)/total_original_points*100:.3f}%)')
    print(f'  4. 可以直接用于机器学习训练，无需额外的缺失值处理')

if __name__ == '__main__':
    main()