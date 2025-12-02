#!/usr/bin/env python3
"""
轨迹统计分析程序
统计轨迹点数和时长，支持多进程处理
"""

import pandas as pd
import numpy as np
import os
import glob
import time
from datetime import datetime, timedelta
from multiprocessing import Pool, cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
import argparse
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

def process_single_file(file_path):
    """
    处理单个parquet文件，统计轨迹信息
    
    Args:
        file_path: parquet文件路径
        
    Returns:
        dict: 包含轨迹统计信息的字典
    """
    try:
        # 读取parquet文件
        df = pd.read_parquet(file_path)
        
        if df.empty:
            return {
                'file_name': os.path.basename(file_path),
                'trajectory_count': 0,
                'total_points': 0,
                'trajectories': []
            }
        
        # 按flight_id分组统计每条轨迹
        trajectory_stats = []
        
        for flight_id, group in df.groupby('flight_id'):
            # 计算轨迹点数
            point_count = len(group)
            
            # 计算时长（假设时间列名为'timestamp'或'time'）
            time_col = None
            for col in ['timestamp', 'time', 'datetime']:
                if col in group.columns:
                    time_col = col
                    break
            
            if time_col is not None:
                # 确保时间列是datetime类型
                if not pd.api.types.is_datetime64_any_dtype(group[time_col]):
                    time_series = pd.to_datetime(group[time_col])
                else:
                    time_series = group[time_col]
                
                # 计算时长（小时）
                duration_hours = (time_series.max() - time_series.min()).total_seconds() / 3600
            else:
                # 如果没有时间列，尝试从索引或其他方式推断
                duration_hours = 0
            
            trajectory_stats.append({
                'flight_id': flight_id,
                'point_count': point_count,
                'duration_hours': duration_hours,
                'start_time': time_series.min() if time_col else None,
                'end_time': time_series.max() if time_col else None
            })
        
        return {
            'file_name': os.path.basename(file_path),
            'trajectory_count': len(trajectory_stats),
            'total_points': len(df),
            'trajectories': trajectory_stats
        }
        
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return {
            'file_name': os.path.basename(file_path),
            'trajectory_count': 0,
            'total_points': 0,
            'trajectories': [],
            'error': str(e)
        }

def find_trajectory_data_directories():
    """
    查找包含轨迹数据的目录
    
    Returns:
        list: 包含parquet文件的目录列表
    """
    base_dir = '/workspace/aircraft_trajectory/team_likable_jelly'
    
    # 可能包含轨迹数据的目录
    candidate_dirs = [
        'perfect_trajectories',
        'complete_high_quality_trajectories', 
        'interpolated_trajectories',
        'opensky_2024_PRC_dataset/rawtrajectories',
        'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories',
        'opensky_2024_PRC_dataset/high_quality_interpolated_trajectories',
        'opensky_2024_PRC_dataset/classic_filtered_trajectories'
    ]
    
    valid_dirs = []
    
    for dir_name in candidate_dirs:
        full_path = os.path.join(base_dir, dir_name)
        if os.path.exists(full_path):
            # 检查是否包含parquet文件
            parquet_files = glob.glob(os.path.join(full_path, '*.parquet'))
            if parquet_files:
                valid_dirs.append({
                    'path': full_path,
                    'name': dir_name,
                    'file_count': len(parquet_files),
                    'total_size_gb': sum(os.path.getsize(f) for f in parquet_files) / (1024**3)
                })
    
    return valid_dirs

def analyze_trajectories(data_dir, max_workers=None, output_dir=None):
    """
    分析轨迹数据
    
    Args:
        data_dir: 数据目录路径
        max_workers: 最大工作进程数
        output_dir: 输出目录
        
    Returns:
        dict: 分析结果
    """
    print(f"🔍 分析轨迹数据目录: {data_dir}")
    
    # 获取所有parquet文件
    parquet_files = glob.glob(os.path.join(data_dir, '*.parquet'))
    parquet_files.sort()
    
    if not parquet_files:
        print(f"❌ 在 {data_dir} 中没有找到parquet文件")
        return None
    
    print(f"📁 找到 {len(parquet_files)} 个parquet文件")
    
    # 计算总文件大小
    total_size_gb = sum(os.path.getsize(f) for f in parquet_files) / (1024**3)
    print(f"💾 总数据大小: {total_size_gb:.2f} GB")
    
    # 确定工作进程数
    if max_workers is None:
        max_workers = min(cpu_count(), len(parquet_files), 16)  # 限制最大进程数
    
    print(f"🚀 使用 {max_workers} 个工作进程")
    
    start_time = time.time()
    
    # 多进程处理
    all_results = []
    completed_files = 0
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_file = {
            executor.submit(process_single_file, file_path): file_path 
            for file_path in parquet_files
        }
        
        # 收集结果
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                result = future.result()
                all_results.append(result)
                completed_files += 1
                
                if completed_files % 10 == 0:
                    print(f"⏳ 已处理 {completed_files}/{len(parquet_files)} 个文件")
                    
            except Exception as e:
                print(f"❌ 处理文件 {file_path} 时出错: {e}")
    
    processing_time = time.time() - start_time
    print(f"✅ 处理完成，耗时 {processing_time:.2f} 秒")
    
    # 汇总统计
    total_trajectories = sum(r['trajectory_count'] for r in all_results)
    total_points = sum(r['total_points'] for r in all_results)
    
    # 收集所有轨迹详细信息
    all_trajectories = []
    for result in all_results:
        all_trajectories.extend(result['trajectories'])
    
    # 创建轨迹统计DataFrame
    if all_trajectories:
        trajectories_df = pd.DataFrame(all_trajectories)
        
        # 统计信息
        stats = {
            'total_files': len(parquet_files),
            'total_trajectories': total_trajectories,
            'total_points': total_points,
            'processing_time_seconds': processing_time,
            'data_size_gb': total_size_gb,
            'avg_points_per_trajectory': total_points / total_trajectories if total_trajectories > 0 else 0,
            'point_count_stats': {
                'min': trajectories_df['point_count'].min(),
                'max': trajectories_df['point_count'].max(),
                'mean': trajectories_df['point_count'].mean(),
                'median': trajectories_df['point_count'].median(),
                'std': trajectories_df['point_count'].std()
            },
            'duration_stats': {
                'min': trajectories_df['duration_hours'].min(),
                'max': trajectories_df['duration_hours'].max(),
                'mean': trajectories_df['duration_hours'].mean(),
                'median': trajectories_df['duration_hours'].median(),
                'std': trajectories_df['duration_hours'].std()
            } if 'duration_hours' in trajectories_df.columns else None
        }
        
        return {
            'stats': stats,
            'trajectories_df': trajectories_df,
            'file_results': all_results
        }
    else:
        return {
            'stats': {
                'total_files': len(parquet_files),
                'total_trajectories': 0,
                'total_points': 0,
                'processing_time_seconds': processing_time,
                'data_size_gb': total_size_gb
            },
            'trajectories_df': pd.DataFrame(),
            'file_results': all_results
        }

def main():
    parser = argparse.ArgumentParser(description='轨迹统计分析程序')
    parser.add_argument('--data-dir', type=str, help='数据目录路径')
    parser.add_argument('--output-dir', type=str, 
                       default='/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output',
                       help='输出目录路径')
    parser.add_argument('--max-workers', type=int, help='最大工作进程数')
    parser.add_argument('--list-dirs', action='store_true', help='列出可用的数据目录')
    
    args = parser.parse_args()
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.list_dirs:
        print("🔍 搜索可用的轨迹数据目录...")
        valid_dirs = find_trajectory_data_directories()
        
        if valid_dirs:
            print("\n📁 找到以下包含轨迹数据的目录:")
            for i, dir_info in enumerate(valid_dirs, 1):
                print(f"{i}. {dir_info['name']}")
                print(f"   路径: {dir_info['path']}")
                print(f"   文件数: {dir_info['file_count']}")
                print(f"   大小: {dir_info['total_size_gb']:.2f} GB")
                print()
        else:
            print("❌ 没有找到包含parquet文件的轨迹数据目录")
        return
    
    if not args.data_dir:
        print("❌ 请指定数据目录路径，或使用 --list-dirs 查看可用目录")
        return
    
    if not os.path.exists(args.data_dir):
        print(f"❌ 数据目录不存在: {args.data_dir}")
        return
    
    # 执行分析
    result = analyze_trajectories(args.data_dir, args.max_workers, args.output_dir)
    
    if result is None:
        return
    
    # 输出统计结果
    stats = result['stats']
    print(f"\n📊 统计结果:")
    print(f"  处理文件数: {stats['total_files']}")
    print(f"  总轨迹数: {stats['total_trajectories']:,}")
    print(f"  总数据点: {stats['total_points']:,}")
    print(f"  平均每轨迹点数: {stats['avg_points_per_trajectory']:.1f}")
    print(f"  处理时间: {stats['processing_time_seconds']:.2f} 秒")
    print(f"  数据大小: {stats['data_size_gb']:.2f} GB")
    
    if 'point_count_stats' in stats:
        pc_stats = stats['point_count_stats']
        print(f"\n📈 轨迹点数分布:")
        print(f"  最小值: {pc_stats['min']}")
        print(f"  最大值: {pc_stats['max']}")
        print(f"  平均值: {pc_stats['mean']:.1f}")
        print(f"  中位数: {pc_stats['median']:.1f}")
        print(f"  标准差: {pc_stats['std']:.1f}")
    
    if stats.get('duration_stats'):
        dur_stats = stats['duration_stats']
        print(f"\n⏱️ 轨迹时长分布 (小时):")
        print(f"  最小值: {dur_stats['min']:.2f}")
        print(f"  最大值: {dur_stats['max']:.2f}")
        print(f"  平均值: {dur_stats['mean']:.2f}")
        print(f"  中位数: {dur_stats['median']:.2f}")
        print(f"  标准差: {dur_stats['std']:.2f}")
    
    # 保存结果到parquet文件
    if not result['trajectories_df'].empty:
        output_file = os.path.join(args.output_dir, 'trajectory_statistics.parquet')
        result['trajectories_df'].to_parquet(output_file, index=False)
        print(f"\n💾 轨迹统计数据已保存到: {output_file}")
        
        # 保存汇总统计
        summary_file = os.path.join(args.output_dir, 'summary_statistics.txt')
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("轨迹统计分析报告\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"数据目录: {args.data_dir}\n\n")
            f.write(f"处理文件数: {stats['total_files']}\n")
            f.write(f"总轨迹数: {stats['total_trajectories']:,}\n")
            f.write(f"总数据点: {stats['total_points']:,}\n")
            f.write(f"平均每轨迹点数: {stats['avg_points_per_trajectory']:.1f}\n")
            f.write(f"处理时间: {stats['processing_time_seconds']:.2f} 秒\n")
            f.write(f"数据大小: {stats['data_size_gb']:.2f} GB\n")
        
        print(f"📄 汇总报告已保存到: {summary_file}")

if __name__ == "__main__":
    main()