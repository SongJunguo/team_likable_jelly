#!/usr/bin/env python3
"""
统计perfect_trajectories目录下的轨迹数量和数据点数量
基于现有的count_total_trajectories_multiprocess.py和validate_trajectory_count.py改进
"""

import pandas as pd
import numpy as np
import os
import time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
from pathlib import Path

def count_trajectories_and_points_in_file(file_path):
    """统计单个文件中的轨迹数量和数据点数量"""
    try:
        # 读取文件
        df = pd.read_parquet(file_path)
        
        # 统计基本信息
        unique_flights = df['flight_id'].nunique()
        total_points = len(df)
        file_size_mb = os.path.getsize(file_path) / (1024*1024)
        
        # 统计各列的缺失值情况
        missing_stats = {}
        key_columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
        total_missing = 0
        
        for col in key_columns:
            if col in df.columns:
                missing_count = df[col].isna().sum()
                missing_stats[col] = missing_count
                total_missing += missing_count
            else:
                missing_stats[col] = 'N/A'
        
        # 统计轨迹长度分布
        trajectory_lengths = df.groupby('flight_id').size()
        length_stats = {
            'min_length': trajectory_lengths.min(),
            'max_length': trajectory_lengths.max(),
            'mean_length': trajectory_lengths.mean(),
            'median_length': trajectory_lengths.median()
        }
        
        filename = os.path.basename(file_path)
        return {
            'filename': filename,
            'flights': unique_flights,
            'points': total_points,
            'file_size_mb': file_size_mb,
            'total_missing': total_missing,
            'missing_by_column': missing_stats,
            'trajectory_length_stats': length_stats,
            'success': True
        }
        
    except Exception as e:
        filename = os.path.basename(file_path)
        print(f"❌ 处理文件 {filename} 时出错: {e}")
        return {
            'filename': filename,
            'flights': 0,
            'points': 0,
            'file_size_mb': 0,
            'total_missing': 0,
            'missing_by_column': {},
            'trajectory_length_stats': {},
            'error': str(e),
            'success': False
        }

def main():
    print('📊 统计perfect_trajectories目录下的轨迹数量和数据点')
    print('=' * 60)
    
    # 检查目录 - perfect_trajectories在项目根目录下
    # 使用绝对路径，确保无论在哪个目录运行都能找到正确路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.join(script_dir, '..', '..')
    perfect_dir = os.path.join(project_root, 'perfect_trajectories')
    perfect_dir = os.path.abspath(perfect_dir)
    
    print(f'🔍 查找目录: {perfect_dir}')
    
    if not os.path.exists(perfect_dir):
        print(f'❌ 目录不存在: {perfect_dir}')
        print('💡 提示: 请先运行implement_final_solution.py创建perfect_trajectories目录')
        return
    
    # 获取所有parquet文件
    files = [os.path.join(perfect_dir, f) for f in os.listdir(perfect_dir) if f.endswith('.parquet')]
    
    if not files:
        print(f'❌ 在 {perfect_dir} 目录中没有找到parquet文件')
        return
    
    print(f'📁 找到 {len(files)} 个parquet文件')
    print('⏳ 开始统计...')
    
    start_time = time.time()
    
    # 使用多进程加速统计
    max_workers = min(mp.cpu_count()//2, 16)
    print(f'🚀 使用 {max_workers} 个进程并行处理')
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(count_trajectories_and_points_in_file, files))
    
    # 过滤成功的结果
    successful_results = [r for r in results if r['success']]
    failed_results = [r for r in results if not r['success']]
    
    elapsed_time = time.time() - start_time
    
    # 统计总体结果
    total_files = len(files)
    successful_files = len(successful_results)
    total_trajectories = sum(r['flights'] for r in successful_results)
    total_points = sum(r['points'] for r in successful_results)
    total_size_mb = sum(r['file_size_mb'] for r in successful_results)
    total_missing = sum(r['total_missing'] for r in successful_results)
    
    print(f'\n📊 统计结果 (处理时间: {elapsed_time:.1f}秒):')
    print(f'=' * 50)
    print(f'📁 文件统计:')
    print(f'  总文件数: {total_files}')
    print(f'  成功处理: {successful_files}')
    print(f'  处理失败: {len(failed_results)}')
    print(f'  总文件大小: {total_size_mb:.1f} MB ({total_size_mb/1024:.1f} GB)')
    
    print(f'\n🛩️  轨迹统计:')
    print(f'  总轨迹数: {total_trajectories:,}')
    print(f'  总数据点: {total_points:,}')
    print(f'  平均每条轨迹: {total_points/total_trajectories:.1f} 个点' if total_trajectories > 0 else '  平均每条轨迹: N/A')
    
    print(f'\n🎯 数据质量:')
    print(f'  总缺失值: {total_missing:,}')
    print(f'  缺失值率: {total_missing/total_points*100:.6f}%' if total_points > 0 else '  缺失值率: N/A')
    
    if total_missing == 0:
        print('  ✅ 完美！数据集100%无缺失值')
    elif total_missing < 1000:
        print('  ✅ 优秀！缺失值极少')
    else:
        print('  ⚠️  存在缺失值，需要进一步处理')
    
    # 统计各列缺失值情况
    if successful_results:
        print(f'\n📋 各列缺失值统计:')
        column_missing = {}
        key_columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
        
        for col in key_columns:
            column_missing[col] = sum(
                r['missing_by_column'].get(col, 0) 
                for r in successful_results 
                if isinstance(r['missing_by_column'].get(col), int)
            )
        
        for col, missing_count in column_missing.items():
            if missing_count > 0:
                print(f'  {col}: {missing_count:,} 个缺失值')
            else:
                print(f'  {col}: ✅ 无缺失值')
    
    # 轨迹长度统计
    if successful_results:
        print(f'\n📏 轨迹长度分布:')
        all_min_lengths = [r['trajectory_length_stats'].get('min_length', 0) for r in successful_results if r['trajectory_length_stats']]
        all_max_lengths = [r['trajectory_length_stats'].get('max_length', 0) for r in successful_results if r['trajectory_length_stats']]
        all_mean_lengths = [r['trajectory_length_stats'].get('mean_length', 0) for r in successful_results if r['trajectory_length_stats']]
        
        if all_min_lengths and all_max_lengths and all_mean_lengths:
            print(f'  最短轨迹: {min(all_min_lengths)} 个点')
            print(f'  最长轨迹: {max(all_max_lengths)} 个点')
            print(f'  平均长度: {np.mean(all_mean_lengths):.1f} 个点')
    
    # 显示处理失败的文件
    if failed_results:
        print(f'\n❌ 处理失败的文件:')
        for r in failed_results:
            print(f'  {r["filename"]}: {r["error"]}')
    
    # 与预期结果对比
    print(f'\n🎯 与预期结果对比:')
    expected_trajectories = 238215  # 从报告文件中获得的预期值
    expected_points = 1497169274    # 从报告文件中获得的预期值
    
    print(f'  预期轨迹数: {expected_trajectories:,}')
    print(f'  实际轨迹数: {total_trajectories:,}')
    if total_trajectories == expected_trajectories:
        print('  ✅ 轨迹数量完全匹配！')
    else:
        diff = total_trajectories - expected_trajectories
        print(f'  ⚠️  轨迹数量差异: {diff:+,}')
    
    print(f'  预期数据点: {expected_points:,}')
    print(f'  实际数据点: {total_points:,}')
    if total_points == expected_points:
        print('  ✅ 数据点数量完全匹配！')
    else:
        diff = total_points - expected_points
        print(f'  ⚠️  数据点差异: {diff:+,}')
    
    # 保存详细报告
    report_file = f'perfect_trajectories_statistics_report_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('Perfect Trajectories统计报告\n')
        f.write('=' * 40 + '\n\n')
        f.write(f'统计时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'处理时间: {elapsed_time:.1f}秒\n')
        f.write(f'目标目录: {perfect_dir}\n\n')
        
        f.write('文件统计:\n')
        f.write(f'  总文件数: {total_files}\n')
        f.write(f'  成功处理: {successful_files}\n')
        f.write(f'  处理失败: {len(failed_results)}\n')
        f.write(f'  总文件大小: {total_size_mb:.1f} MB\n\n')
        
        f.write('轨迹统计:\n')
        f.write(f'  总轨迹数: {total_trajectories:,}\n')
        f.write(f'  总数据点: {total_points:,}\n')
        f.write(f'  平均每条轨迹: {total_points/total_trajectories:.1f} 个点\n\n' if total_trajectories > 0 else '  平均每条轨迹: N/A\n\n')
        
        f.write('数据质量:\n')
        f.write(f'  总缺失值: {total_missing:,}\n')
        f.write(f'  缺失值率: {total_missing/total_points*100:.6f}%\n\n' if total_points > 0 else '  缺失值率: N/A\n\n')
        
        f.write('各列缺失值统计:\n')
        for col, missing_count in column_missing.items():
            f.write(f'  {col}: {missing_count:,}\n')
        
        f.write('\n与预期结果对比:\n')
        f.write(f'  预期轨迹数: {expected_trajectories:,}\n')
        f.write(f'  实际轨迹数: {total_trajectories:,}\n')
        f.write(f'  轨迹数差异: {total_trajectories - expected_trajectories:+,}\n')
        f.write(f'  预期数据点: {expected_points:,}\n')
        f.write(f'  实际数据点: {total_points:,}\n')
        f.write(f'  数据点差异: {total_points - expected_points:+,}\n')
        
        if failed_results:
            f.write('\n处理失败的文件:\n')
            for r in failed_results:
                f.write(f'  {r["filename"]}: {r["error"]}\n')
    
    print(f'\n📄 详细报告已保存至: {report_file}')
    
    # 总结
    print(f'\n🎉 统计完成！')
    if total_missing == 0 and total_trajectories > 0:
        print('✅ Perfect Trajectories数据集质量完美，可以用于后续分析！')
    elif total_trajectories == 0:
        print('❌ 没有找到任何轨迹数据，请检查数据源！')
    else:
        print('⚠️  数据集存在一些问题，请查看详细报告！')

if __name__ == '__main__':
    main()