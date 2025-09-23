#!/usr/bin/env python3
"""
增强版轨迹数据缺失率统计程序
专门针对opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories路径
支持80核心CPU多进程处理，512GB内存优化

新增功能：
1. 头尾缺失检测（影响插值的边界问题）
2. 所有字段的详细统计
3. 更精确的缺失窗口分析
4. 内存优化的大数据处理
"""

import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import psutil
import argparse
from pathlib import Path
import json
import warnings
warnings.filterwarnings('ignore')

def analyze_missing_windows_enhanced(series, flight_id=None):
    """
    增强版缺失窗口分析
    返回详细的缺失窗口统计，包括位置信息
    """
    if series.empty:
        return {
            'windows': [],
            'num_windows': 0,
            'total_missing': 0,
            'max_window': 0,
            'min_window': 0,
            'avg_window': 0,
            'head_missing': False,
            'tail_missing': False,
            'head_missing_count': 0,
            'tail_missing_count': 0
        }
    
    # 找到NaN值的位置
    is_nan = series.isna()
    
    if not is_nan.any():
        return {
            'windows': [],
            'num_windows': 0,
            'total_missing': 0,
            'max_window': 0,
            'min_window': 0,
            'avg_window': 0,
            'head_missing': False,
            'tail_missing': False,
            'head_missing_count': 0,
            'tail_missing_count': 0
        }
    
    # 检测头尾缺失情况
    head_missing = is_nan.iloc[0] if len(is_nan) > 0 else False
    tail_missing = is_nan.iloc[-1] if len(is_nan) > 0 else False
    
    # 计算头部连续缺失数量
    head_missing_count = 0
    if head_missing:
        for i in range(len(is_nan)):
            if is_nan.iloc[i]:
                head_missing_count += 1
            else:
                break
    
    # 计算尾部连续缺失数量
    tail_missing_count = 0
    if tail_missing:
        for i in range(len(is_nan)-1, -1, -1):
            if is_nan.iloc[i]:
                tail_missing_count += 1
            else:
                break
    
    # 找到连续的NaN窗口
    windows = []
    window_positions = []  # 记录窗口位置
    in_window = False
    window_start = 0
    
    for i, nan_val in enumerate(is_nan):
        if nan_val and not in_window:
            # 开始一个新的缺失窗口
            in_window = True
            window_start = i
        elif not nan_val and in_window:
            # 结束当前缺失窗口
            in_window = False
            window_length = i - window_start
            windows.append(window_length)
            window_positions.append((window_start, i-1))
    
    # 如果序列以NaN结尾
    if in_window:
        window_length = len(series) - window_start
        windows.append(window_length)
        window_positions.append((window_start, len(series)-1))
    
    return {
        'windows': windows,
        'window_positions': window_positions,
        'num_windows': len(windows),
        'total_missing': sum(windows) if windows else 0,
        'max_window': max(windows) if windows else 0,
        'min_window': min(windows) if windows else 0,
        'avg_window': np.mean(windows) if windows else 0,
        'head_missing': head_missing,
        'tail_missing': tail_missing,
        'head_missing_count': head_missing_count,
        'tail_missing_count': tail_missing_count
    }

def analyze_trajectory_comprehensive(df, flight_id):
    """
    全面分析单个轨迹的缺失数据情况
    包含所有字段的详细统计
    """
    flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
    
    if flight_data.empty:
        return None
    
    # 所有需要分析的字段
    all_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    # 基础信息
    total_points = len(flight_data)
    duration_seconds = 0
    if len(flight_data) > 1:
        duration_seconds = (flight_data.timestamp.max() - flight_data.timestamp.min()).total_seconds()
    
    trajectory_stats = {
        'flight_id': flight_id,
        'total_points': total_points,
        'duration_seconds': duration_seconds,
        'duration_minutes': duration_seconds / 60,
        'avg_interval_seconds': duration_seconds / (total_points - 1) if total_points > 1 else 0,
        'field_analysis': {}
    }
    
    # 分析每个字段
    for field in all_fields:
        if field in flight_data.columns:
            series = flight_data[field]
            missing_count = series.isna().sum()
            missing_rate = (missing_count / total_points) * 100 if total_points > 0 else 0
            
            # 增强版缺失窗口分析
            window_analysis = analyze_missing_windows_enhanced(series, flight_id)
            
            # 数据范围统计（非NaN值）
            valid_data = series.dropna()
            data_range = {}
            if len(valid_data) > 0:
                data_range = {
                    'min_value': float(valid_data.min()),
                    'max_value': float(valid_data.max()),
                    'mean_value': float(valid_data.mean()),
                    'std_value': float(valid_data.std()) if len(valid_data) > 1 else 0
                }
            
            trajectory_stats['field_analysis'][field] = {
                'missing_count': int(missing_count),
                'missing_rate': float(missing_rate),
                'valid_count': int(total_points - missing_count),
                'data_range': data_range,
                **window_analysis
            }
        else:
            # 字段不存在
            trajectory_stats['field_analysis'][field] = {
                'missing_count': total_points,
                'missing_rate': 100.0,
                'valid_count': 0,
                'data_range': {},
                'windows': [],
                'num_windows': 0,
                'total_missing': total_points,
                'max_window': total_points,
                'min_window': total_points if total_points > 0 else 0,
                'avg_window': total_points,
                'head_missing': True,
                'tail_missing': True,
                'head_missing_count': total_points,
                'tail_missing_count': total_points
            }
    
    # 计算综合质量评分
    trajectory_stats['quality_score'] = calculate_trajectory_quality_score(trajectory_stats)
    
    return trajectory_stats

def calculate_trajectory_quality_score(trajectory_stats):
    """
    计算轨迹质量评分 (0-100)
    基于缺失率、头尾完整性、窗口大小等因素
    """
    if not trajectory_stats['field_analysis']:
        return 0
    
    # 核心字段权重
    core_fields = ['latitude', 'longitude', 'altitude']
    secondary_fields = ['groundspeed', 'track', 'vertical_rate']
    
    score = 100
    
    # 核心字段缺失惩罚 (权重70%)
    core_penalty = 0
    for field in core_fields:
        if field in trajectory_stats['field_analysis']:
            field_data = trajectory_stats['field_analysis'][field]
            missing_rate = field_data['missing_rate']
            
            # 缺失率惩罚
            core_penalty += missing_rate * 0.7 / len(core_fields)
            
            # 头尾缺失额外惩罚
            if field_data['head_missing']:
                core_penalty += min(field_data['head_missing_count'] / trajectory_stats['total_points'] * 20, 10)
            if field_data['tail_missing']:
                core_penalty += min(field_data['tail_missing_count'] / trajectory_stats['total_points'] * 20, 10)
            
            # 大缺失窗口惩罚
            if field_data['max_window'] > 50:
                core_penalty += min(field_data['max_window'] / trajectory_stats['total_points'] * 30, 15)
    
    # 次要字段缺失惩罚 (权重30%)
    secondary_penalty = 0
    for field in secondary_fields:
        if field in trajectory_stats['field_analysis']:
            field_data = trajectory_stats['field_analysis'][field]
            missing_rate = field_data['missing_rate']
            secondary_penalty += missing_rate * 0.3 / len(secondary_fields)
    
    # 轨迹长度奖励
    if trajectory_stats['total_points'] > 100:
        length_bonus = min((trajectory_stats['total_points'] - 100) / 1000 * 5, 5)
        score += length_bonus
    
    final_score = max(0, score - core_penalty - secondary_penalty)
    return round(final_score, 2)

def process_file_enhanced(args):
    """
    增强版文件处理函数
    支持完整分析或抽样分析
    """
    file_path, sample_percentage, max_trajectories_per_file = args
    
    try:
        filename = os.path.basename(file_path)
        print(f"正在处理文件: {filename}")
        
        # 读取文件
        df = pd.read_parquet(file_path)
        total_trajectories = df.flight_id.nunique()
        
        # 确定分析数量
        if sample_percentage and sample_percentage < 100:
            sample_size = max(1, int(total_trajectories * sample_percentage / 100))
        else:
            sample_size = min(max_trajectories_per_file, total_trajectories) if max_trajectories_per_file else total_trajectories
        
        # 选择轨迹
        unique_flights = df.flight_id.unique()
        if len(unique_flights) > sample_size:
            selected_flights = np.random.choice(unique_flights, sample_size, replace=False)
            df = df[df.flight_id.isin(selected_flights)]
        
        # 分析每个轨迹
        trajectory_stats = []
        for flight_id in df.flight_id.unique():
            stats = analyze_trajectory_comprehensive(df, flight_id)
            if stats:
                trajectory_stats.append(stats)
        
        file_result = {
            'filename': filename,
            'total_trajectories_in_file': total_trajectories,
            'analyzed_trajectories': len(trajectory_stats),
            'trajectory_stats': trajectory_stats,
            'file_size_mb': os.path.getsize(file_path) / (1024*1024),
            'processing_time': time.time()
        }
        
        print(f"完成文件 {filename}: {len(trajectory_stats)}/{total_trajectories} 轨迹")
        return file_result
        
    except Exception as e:
        filename = os.path.basename(file_path)
        print(f"处理文件 {filename} 时出错: {e}")
        return {
            'filename': filename,
            'total_trajectories_in_file': 0,
            'analyzed_trajectories': 0,
            'trajectory_stats': [],
            'file_size_mb': 0,
            'error': str(e)
        }

def generate_enhanced_report(all_file_results, output_dir, sample_percentage=None):
    """
    生成增强版分析报告
    包含详细的统计信息和质量评估
    """
    # 收集所有轨迹统计
    all_trajectory_stats = []
    total_files = len(all_file_results)
    successful_files = 0
    total_trajectories_in_dataset = 0
    total_analyzed_trajectories = 0
    
    for file_result in all_file_results:
        if 'error' not in file_result:
            successful_files += 1
            total_trajectories_in_dataset += file_result['total_trajectories_in_file']
            total_analyzed_trajectories += file_result['analyzed_trajectories']
            all_trajectory_stats.extend(file_result['trajectory_stats'])
    
    if not all_trajectory_stats:
        print("没有数据可分析")
        return
    
    # 生成主报告
    report_file = os.path.join(output_dir, "enhanced_trajectory_analysis_report.txt")
    generate_main_report(all_trajectory_stats, report_file, sample_percentage, 
                        successful_files, total_files, total_trajectories_in_dataset, total_analyzed_trajectories)
    
    # 生成详细统计JSON
    stats_file = os.path.join(output_dir, "trajectory_statistics.json")
    generate_statistics_json(all_trajectory_stats, stats_file)
    
    # 生成质量分析报告
    quality_file = os.path.join(output_dir, "trajectory_quality_analysis.txt")
    generate_quality_report(all_trajectory_stats, quality_file)
    
    # 生成CSV和Parquet格式的数据文件
    generate_data_files(all_trajectory_stats, output_dir)
    
    print(f"报告已生成:")
    print(f"  主报告: {report_file}")
    print(f"  统计数据: {stats_file}")
    print(f"  质量分析: {quality_file}")
    print(f"  数据文件: {output_dir}/trajectory_summary.csv")
    print(f"  数据文件: {output_dir}/trajectory_summary.parquet")
    print(f"  字段统计: {output_dir}/field_statistics.csv")

def generate_main_report(all_trajectory_stats, report_file, sample_percentage, 
                        successful_files, total_files, total_trajectories_in_dataset, total_analyzed_trajectories):
    """生成主要分析报告"""
    
    all_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 100 + "\n")
        f.write("增强版轨迹数据缺失率和质量分析报告\n")
        f.write("=" * 100 + "\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"抽样比例: {sample_percentage}%" if sample_percentage else "完整分析\n")
        f.write(f"处理文件数: {successful_files}/{total_files}\n")
        f.write(f"数据集总轨迹数: {total_trajectories_in_dataset:,}\n")
        f.write(f"分析轨迹数: {total_analyzed_trajectories:,}\n")
        if sample_percentage:
            f.write(f"实际抽样比例: {total_analyzed_trajectories/total_trajectories_in_dataset*100:.2f}%\n")
        f.write("\n")
        
        # 整体统计
        total_points = sum([stat['total_points'] for stat in all_trajectory_stats])
        avg_duration = np.mean([stat['duration_minutes'] for stat in all_trajectory_stats if stat['duration_minutes'] > 0])
        avg_points = total_points / len(all_trajectory_stats)
        
        f.write("=== 整体统计 ===\n")
        f.write(f"分析的总轨迹点数: {total_points:,}\n")
        f.write(f"平均轨迹时长: {avg_duration:.1f} 分钟\n")
        f.write(f"平均每轨迹点数: {avg_points:.0f}\n")
        
        # 轨迹长度分布
        durations = [stat['duration_minutes'] for stat in all_trajectory_stats if stat['duration_minutes'] > 0]
        point_counts = [stat['total_points'] for stat in all_trajectory_stats]
        
        if durations:
            f.write(f"轨迹时长分布:\n")
            f.write(f"  最短: {min(durations):.1f} 分钟\n")
            f.write(f"  最长: {max(durations):.1f} 分钟\n")
            f.write(f"  中位数: {np.median(durations):.1f} 分钟\n")
            
            # 时长分类统计
            short_count = sum(1 for d in durations if d < 60)
            medium_count = sum(1 for d in durations if 60 <= d <= 180)
            long_count = sum(1 for d in durations if d > 180)
            
            f.write(f"  短途轨迹 (<1小时): {short_count} ({short_count/len(durations)*100:.1f}%)\n")
            f.write(f"  中途轨迹 (1-3小时): {medium_count} ({medium_count/len(durations)*100:.1f}%)\n")
            f.write(f"  长途轨迹 (>3小时): {long_count} ({long_count/len(durations)*100:.1f}%)\n")
        
        f.write(f"轨迹点数分布:\n")
        f.write(f"  最少: {min(point_counts)} 点\n")
        f.write(f"  最多: {max(point_counts)} 点\n")
        f.write(f"  中位数: {np.median(point_counts):.0f} 点\n")
        f.write("\n")
        
        # 各字段详细分析
        for field in all_fields:
            f.write(f"=== {field.upper()} 字段分析 ===\n")
            
            # 收集该字段的统计数据
            field_stats = []
            for traj_stat in all_trajectory_stats:
                if field in traj_stat['field_analysis']:
                    field_stats.append(traj_stat['field_analysis'][field])
            
            if not field_stats:
                f.write(f"  该字段无数据\n\n")
                continue
            
            # 基础统计
            missing_rates = [stat['missing_rate'] for stat in field_stats]
            total_missing = sum([stat['missing_count'] for stat in field_stats])
            total_valid = sum([stat['valid_count'] for stat in field_stats])
            
            f.write(f"  有该字段数据的轨迹: {len(field_stats)}\n")
            f.write(f"  总缺失点数: {total_missing:,}\n")
            f.write(f"  总有效点数: {total_valid:,}\n")
            f.write(f"  整体缺失率: {total_missing/(total_missing+total_valid)*100:.2f}%\n")
            
            # 缺失率分布
            f.write(f"  缺失率统计:\n")
            f.write(f"    平均值: {np.mean(missing_rates):.2f}%\n")
            f.write(f"    中位数: {np.median(missing_rates):.2f}%\n")
            f.write(f"    标准差: {np.std(missing_rates):.2f}%\n")
            f.write(f"    最小值: {min(missing_rates):.2f}%\n")
            f.write(f"    最大值: {max(missing_rates):.2f}%\n")
            
            # 缺失率分级统计
            no_missing = sum(1 for rate in missing_rates if rate == 0)
            very_low = sum(1 for rate in missing_rates if 0 < rate <= 5)
            low = sum(1 for rate in missing_rates if 5 < rate <= 20)
            high = sum(1 for rate in missing_rates if 20 < rate <= 50)
            very_high = sum(1 for rate in missing_rates if rate > 50)
            
            f.write(f"  缺失率分布:\n")
            f.write(f"    无缺失 (0%): {no_missing} 轨迹 ({no_missing/len(field_stats)*100:.1f}%)\n")
            f.write(f"    极低缺失 (0-5%): {very_low} 轨迹 ({very_low/len(field_stats)*100:.1f}%)\n")
            f.write(f"    低缺失 (5-20%): {low} 轨迹 ({low/len(field_stats)*100:.1f}%)\n")
            f.write(f"    高缺失 (20-50%): {high} 轨迹 ({high/len(field_stats)*100:.1f}%)\n")
            f.write(f"    极高缺失 (>50%): {very_high} 轨迹 ({very_high/len(field_stats)*100:.1f}%)\n")
            
            # 缺失窗口统计
            all_windows = []
            for stat in field_stats:
                all_windows.extend(stat['windows'])
            
            if all_windows:
                f.write(f"  缺失窗口统计:\n")
                f.write(f"    总缺失窗口数: {len(all_windows):,}\n")
                f.write(f"    窗口长度统计:\n")
                f.write(f"      平均值: {np.mean(all_windows):.1f} 个点\n")
                f.write(f"      中位数: {np.median(all_windows):.1f} 个点\n")
                f.write(f"      标准差: {np.std(all_windows):.1f} 个点\n")
                f.write(f"      最小值: {min(all_windows)} 个点\n")
                f.write(f"      最大值: {max(all_windows)} 个点\n")
                
                # 窗口长度分布
                very_short = sum(1 for w in all_windows if w <= 2)
                short = sum(1 for w in all_windows if 3 <= w <= 10)
                medium = sum(1 for w in all_windows if 11 <= w <= 50)
                long_w = sum(1 for w in all_windows if 51 <= w <= 200)
                very_long = sum(1 for w in all_windows if w > 200)
                
                f.write(f"    窗口长度分布:\n")
                f.write(f"      极短窗口 (≤2点): {very_short:,} ({very_short/len(all_windows)*100:.1f}%)\n")
                f.write(f"      短窗口 (3-10点): {short:,} ({short/len(all_windows)*100:.1f}%)\n")
                f.write(f"      中等窗口 (11-50点): {medium:,} ({medium/len(all_windows)*100:.1f}%)\n")
                f.write(f"      长窗口 (51-200点): {long_w:,} ({long_w/len(all_windows)*100:.1f}%)\n")
                f.write(f"      超长窗口 (>200点): {very_long:,} ({very_long/len(all_windows)*100:.1f}%)\n")
            
            # 头尾缺失统计
            head_missing_count = sum(1 for stat in field_stats if stat['head_missing'])
            tail_missing_count = sum(1 for stat in field_stats if stat['tail_missing'])
            both_missing_count = sum(1 for stat in field_stats if stat['head_missing'] and stat['tail_missing'])
            
            f.write(f"  头尾缺失统计:\n")
            f.write(f"    头部缺失轨迹: {head_missing_count} ({head_missing_count/len(field_stats)*100:.1f}%)\n")
            f.write(f"    尾部缺失轨迹: {tail_missing_count} ({tail_missing_count/len(field_stats)*100:.1f}%)\n")
            f.write(f"    头尾都缺失轨迹: {both_missing_count} ({both_missing_count/len(field_stats)*100:.1f}%)\n")
            
            # 数据范围统计（如果有有效数据）
            valid_ranges = [stat['data_range'] for stat in field_stats if stat['data_range']]
            if valid_ranges:
                all_mins = [r['min_value'] for r in valid_ranges]
                all_maxs = [r['max_value'] for r in valid_ranges]
                all_means = [r['mean_value'] for r in valid_ranges]
                
                f.write(f"  数据范围统计:\n")
                f.write(f"    全局最小值: {min(all_mins):.2f}\n")
                f.write(f"    全局最大值: {max(all_maxs):.2f}\n")
                f.write(f"    平均值范围: {min(all_means):.2f} 到 {max(all_means):.2f}\n")
            
            f.write("\n")

def generate_statistics_json(all_trajectory_stats, stats_file):
    """生成详细的统计数据JSON文件"""
    
    # 准备统计数据
    statistics = {
        'summary': {
            'total_trajectories': len(all_trajectory_stats),
            'total_points': sum([stat['total_points'] for stat in all_trajectory_stats]),
            'avg_duration_minutes': np.mean([stat['duration_minutes'] for stat in all_trajectory_stats if stat['duration_minutes'] > 0]),
            'avg_points_per_trajectory': np.mean([stat['total_points'] for stat in all_trajectory_stats])
        },
        'quality_distribution': {},
        'field_statistics': {},
        'trajectory_details': []
    }
    
    # 质量分数分布
    quality_scores = [stat['quality_score'] for stat in all_trajectory_stats]
    statistics['quality_distribution'] = {
        'excellent': sum(1 for score in quality_scores if score >= 90),
        'good': sum(1 for score in quality_scores if 70 <= score < 90),
        'fair': sum(1 for score in quality_scores if 50 <= score < 70),
        'poor': sum(1 for score in quality_scores if score < 50),
        'avg_score': np.mean(quality_scores),
        'median_score': np.median(quality_scores)
    }
    
    # 各字段统计
    all_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    for field in all_fields:
        field_data = []
        for traj_stat in all_trajectory_stats:
            if field in traj_stat['field_analysis']:
                field_data.append(traj_stat['field_analysis'][field])
        
        if field_data:
            missing_rates = [data['missing_rate'] for data in field_data]
            statistics['field_statistics'][field] = {
                'trajectories_with_field': len(field_data),
                'avg_missing_rate': np.mean(missing_rates),
                'median_missing_rate': np.median(missing_rates),
                'std_missing_rate': np.std(missing_rates),
                'min_missing_rate': min(missing_rates),
                'max_missing_rate': max(missing_rates),
                'head_missing_count': sum(1 for data in field_data if data['head_missing']),
                'tail_missing_count': sum(1 for data in field_data if data['tail_missing']),
                'avg_max_window': np.mean([data['max_window'] for data in field_data]),
                'total_windows': sum([data['num_windows'] for data in field_data])
            }
    
    # 保存前1000个轨迹的详细信息（避免文件过大）
    for i, traj_stat in enumerate(all_trajectory_stats[:1000]):
        trajectory_detail = {
            'flight_id': traj_stat['flight_id'],
            'total_points': traj_stat['total_points'],
            'duration_minutes': traj_stat['duration_minutes'],
            'quality_score': traj_stat['quality_score'],
            'field_summary': {}
        }
        
        for field in all_fields:
            if field in traj_stat['field_analysis']:
                field_analysis = traj_stat['field_analysis'][field]
                trajectory_detail['field_summary'][field] = {
                    'missing_rate': field_analysis['missing_rate'],
                    'max_window': field_analysis['max_window'],
                    'head_missing': field_analysis['head_missing'],
                    'tail_missing': field_analysis['tail_missing']
                }
        
        statistics['trajectory_details'].append(trajectory_detail)
    
    # 保存JSON文件
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(statistics, f, indent=2, ensure_ascii=False)

def generate_quality_report(all_trajectory_stats, quality_file):
    """生成轨迹质量分析报告"""
    
    quality_scores = [stat['quality_score'] for stat in all_trajectory_stats]
    
    with open(quality_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("轨迹质量分析报告\n")
        f.write("=" * 80 + "\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"总轨迹数: {len(all_trajectory_stats):,}\n\n")
        
        # 质量分数统计
        f.write("=== 质量分数分布 ===\n")
        f.write(f"平均质量分数: {np.mean(quality_scores):.2f}\n")
        f.write(f"中位数质量分数: {np.median(quality_scores):.2f}\n")
        f.write(f"标准差: {np.std(quality_scores):.2f}\n")
        f.write(f"最高分数: {max(quality_scores):.2f}\n")
        f.write(f"最低分数: {min(quality_scores):.2f}\n\n")
        
        # 质量等级分布
        excellent = sum(1 for score in quality_scores if score >= 90)
        good = sum(1 for score in quality_scores if 70 <= score < 90)
        fair = sum(1 for score in quality_scores if 50 <= score < 70)
        poor = sum(1 for score in quality_scores if score < 50)
        
        f.write("=== 质量等级分布 ===\n")
        f.write(f"优秀 (≥90分): {excellent:,} 轨迹 ({excellent/len(quality_scores)*100:.1f}%)\n")
        f.write(f"良好 (70-89分): {good:,} 轨迹 ({good/len(quality_scores)*100:.1f}%)\n")
        f.write(f"一般 (50-69分): {fair:,} 轨迹 ({fair/len(quality_scores)*100:.1f}%)\n")
        f.write(f"较差 (<50分): {poor:,} 轨迹 ({poor/len(quality_scores)*100:.1f}%)\n\n")
        
        # 推荐的数据清洗策略
        f.write("=== 数据清洗建议 ===\n")
        f.write("基于质量分析的建议:\n\n")
        
        if excellent > 0:
            f.write(f"1. 高质量数据集 (≥90分): {excellent:,} 轨迹\n")
            f.write("   - 可直接用于深度学习模型训练\n")
            f.write("   - 缺失率低，头尾完整\n\n")
        
        if good > 0:
            f.write(f"2. 中高质量数据集 (70-89分): {good:,} 轨迹\n")
            f.write("   - 经过轻度清洗后可用于训练\n")
            f.write("   - 建议修剪头尾缺失部分\n\n")
        
        if fair > 0:
            f.write(f"3. 中等质量数据集 (50-69分): {fair:,} 轨迹\n")
            f.write("   - 需要强化插值处理\n")
            f.write("   - 可作为扩充数据集使用\n\n")
        
        if poor > 0:
            f.write(f"4. 低质量数据集 (<50分): {poor:,} 轨迹\n")
            f.write("   - 建议暂时排除\n")
            f.write("   - 缺失率过高，不适合直接使用\n\n")
        
        # 具体建议
        high_quality_count = excellent + good
        f.write("=== 具体实施建议 ===\n")
        f.write(f"1. 立即可用数据: {high_quality_count:,} 轨迹 ({high_quality_count/len(quality_scores)*100:.1f}%)\n")
        f.write("2. 建议的训练策略:\n")
        f.write("   - 阶段1: 使用优秀质量数据训练基础模型\n")
        f.write("   - 阶段2: 加入良好质量数据扩充训练集\n")
        f.write("   - 阶段3: 处理中等质量数据进一步扩充\n\n")
        
        # 头尾缺失统计
        core_fields = ['latitude', 'longitude', 'altitude']
        for field in core_fields:
            head_missing = sum(1 for stat in all_trajectory_stats 
                             if field in stat['field_analysis'] and stat['field_analysis'][field]['head_missing'])
            tail_missing = sum(1 for stat in all_trajectory_stats 
                             if field in stat['field_analysis'] and stat['field_analysis'][field]['tail_missing'])
            
            f.write(f"{field} 头尾缺失情况:\n")
            f.write(f"  头部缺失: {head_missing:,} 轨迹 ({head_missing/len(all_trajectory_stats)*100:.1f}%)\n")
            f.write(f"  尾部缺失: {tail_missing:,} 轨迹 ({tail_missing/len(all_trajectory_stats)*100:.1f}%)\n")

def generate_data_files(all_trajectory_stats, output_dir):
    """
    生成CSV和Parquet格式的数据文件，便于后续分析
    """
    print("正在生成数据文件...")
    
    # 1. 生成轨迹汇总数据
    trajectory_summary = []
    all_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    for stat in all_trajectory_stats:
        row = {
            'flight_id': stat['flight_id'],
            'total_points': stat['total_points'],
            'duration_minutes': stat['duration_minutes'],
            'duration_hours': stat['duration_minutes'] / 60,
            'quality_score': stat['quality_score'],
            'avg_interval_seconds': stat['avg_interval_seconds']
        }
        
        # 添加各字段的统计信息
        for field in all_fields:
            if field in stat['field_analysis']:
                field_data = stat['field_analysis'][field]
                row[f'{field}_missing_rate'] = field_data['missing_rate']
                row[f'{field}_missing_count'] = field_data['missing_count']
                row[f'{field}_valid_count'] = field_data['valid_count']
                row[f'{field}_max_window'] = field_data['max_window']
                row[f'{field}_num_windows'] = field_data['num_windows']
                row[f'{field}_head_missing'] = field_data['head_missing']
                row[f'{field}_tail_missing'] = field_data['tail_missing']
                row[f'{field}_head_missing_count'] = field_data['head_missing_count']
                row[f'{field}_tail_missing_count'] = field_data['tail_missing_count']
                
                # 数据范围信息
                if field_data['data_range']:
                    row[f'{field}_min_value'] = field_data['data_range']['min_value']
                    row[f'{field}_max_value'] = field_data['data_range']['max_value']
                    row[f'{field}_mean_value'] = field_data['data_range']['mean_value']
                    row[f'{field}_std_value'] = field_data['data_range']['std_value']
                else:
                    row[f'{field}_min_value'] = None
                    row[f'{field}_max_value'] = None
                    row[f'{field}_mean_value'] = None
                    row[f'{field}_std_value'] = None
            else:
                # 字段不存在的情况
                row[f'{field}_missing_rate'] = 100.0
                row[f'{field}_missing_count'] = stat['total_points']
                row[f'{field}_valid_count'] = 0
                row[f'{field}_max_window'] = stat['total_points']
                row[f'{field}_num_windows'] = 1 if stat['total_points'] > 0 else 0
                row[f'{field}_head_missing'] = True
                row[f'{field}_tail_missing'] = True
                row[f'{field}_head_missing_count'] = stat['total_points']
                row[f'{field}_tail_missing_count'] = stat['total_points']
                row[f'{field}_min_value'] = None
                row[f'{field}_max_value'] = None
                row[f'{field}_mean_value'] = None
                row[f'{field}_std_value'] = None
        
        # 添加质量等级
        if row['quality_score'] >= 90:
            row['quality_level'] = 'Excellent'
        elif row['quality_score'] >= 70:
            row['quality_level'] = 'Good'
        elif row['quality_score'] >= 50:
            row['quality_level'] = 'Fair'
        else:
            row['quality_level'] = 'Poor'
        
        trajectory_summary.append(row)
    
    # 转换为DataFrame并保存
    df_summary = pd.DataFrame(trajectory_summary)
    
    # 保存CSV文件
    csv_file = os.path.join(output_dir, "trajectory_summary.csv")
    df_summary.to_csv(csv_file, index=False, encoding='utf-8')
    
    # 保存Parquet文件
    parquet_file = os.path.join(output_dir, "trajectory_summary.parquet")
    df_summary.to_parquet(parquet_file, index=False)
    
    # 2. 生成字段统计汇总
    field_statistics = []
    
    for field in all_fields:
        field_data = []
        for traj_stat in all_trajectory_stats:
            if field in traj_stat['field_analysis']:
                field_data.append(traj_stat['field_analysis'][field])
        
        if field_data:
            missing_rates = [data['missing_rate'] for data in field_data]
            max_windows = [data['max_window'] for data in field_data]
            num_windows = [data['num_windows'] for data in field_data]
            
            field_stat = {
                'field_name': field,
                'trajectories_with_field': len(field_data),
                'trajectories_total': len(all_trajectory_stats),
                'field_coverage_rate': len(field_data) / len(all_trajectory_stats) * 100,
                'avg_missing_rate': np.mean(missing_rates),
                'median_missing_rate': np.median(missing_rates),
                'std_missing_rate': np.std(missing_rates),
                'min_missing_rate': min(missing_rates),
                'max_missing_rate': max(missing_rates),
                'trajectories_no_missing': sum(1 for rate in missing_rates if rate == 0),
                'trajectories_low_missing': sum(1 for rate in missing_rates if 0 < rate <= 20),
                'trajectories_high_missing': sum(1 for rate in missing_rates if rate > 20),
                'head_missing_count': sum(1 for data in field_data if data['head_missing']),
                'tail_missing_count': sum(1 for data in field_data if data['tail_missing']),
                'both_missing_count': sum(1 for data in field_data if data['head_missing'] and data['tail_missing']),
                'avg_max_window': np.mean(max_windows),
                'median_max_window': np.median(max_windows),
                'total_windows': sum(num_windows),
                'avg_windows_per_trajectory': np.mean(num_windows)
            }
            
            field_statistics.append(field_stat)
    
    # 保存字段统计
    df_field_stats = pd.DataFrame(field_statistics)
    field_stats_file = os.path.join(output_dir, "field_statistics.csv")
    df_field_stats.to_csv(field_stats_file, index=False, encoding='utf-8')
    
    print(f"数据文件已生成:")
    print(f"  轨迹汇总: {csv_file} ({len(df_summary):,} 行)")
    print(f"  轨迹汇总: {parquet_file}")
    print(f"  字段统计: {field_stats_file} ({len(df_field_stats)} 行)")

def get_optimal_workers():
    """
    根据系统资源确定最优工作进程数
    考虑80核CPU和512GB内存
    """
    cpu_count = mp.cpu_count()
    memory_gb = psutil.virtual_memory().total / (1024**3)
    
    # 保守估计，使用70%的CPU核心
    optimal_workers = min(int(cpu_count * 0.7), 60)  # 最多60个进程
    
    # 根据内存限制调整（每个进程预估需要4GB内存）
    memory_limited_workers = int(memory_gb * 0.8 / 4)  # 使用80%内存
    
    final_workers = min(optimal_workers, memory_limited_workers)
    
    print(f"系统信息: {cpu_count} CPU核心, {memory_gb:.1f}GB 内存")
    print(f"建议使用 {final_workers} 个工作进程")
    
    return max(1, final_workers)

def main():
    parser = argparse.ArgumentParser(description='增强版轨迹数据缺失率统计程序')
    parser.add_argument('--data_dir', 
                       default='../../opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories',
                       help='数据目录路径')
    parser.add_argument('--output_dir', 
                       default='enhanced_analysis_output',
                       help='输出目录路径')
    parser.add_argument('--sample_percentage', type=float, default=None,
                       help='抽样百分比 (1-100)，不指定则全量分析')
    parser.add_argument('--max_trajectories_per_file', type=int, default=None,
                       help='每个文件最大分析轨迹数')
    parser.add_argument('--workers', type=int, default=None,
                       help='工作进程数，不指定则自动确定')
    
    args = parser.parse_args()
    
    # 检查数据目录
    if not os.path.exists(args.data_dir):
        print(f"错误: 数据目录不存在: {args.data_dir}")
        print(f"当前工作目录: {os.getcwd()}")
        print("请检查数据目录路径是否正确")
        return
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 获取所有parquet文件
    parquet_files = glob.glob(os.path.join(args.data_dir, "*.parquet"))
    if not parquet_files:
        print(f"错误: 在 {args.data_dir} 中未找到parquet文件")
        return
    
    print(f"找到 {len(parquet_files)} 个parquet文件")
    
    # 确定工作进程数
    workers = args.workers if args.workers else get_optimal_workers()
    
    # 准备参数
    process_args = [(file_path, args.sample_percentage, args.max_trajectories_per_file) 
                   for file_path in parquet_files]
    
    print(f"开始处理，使用 {workers} 个进程...")
    start_time = time.time()
    
    # 多进程处理
    all_file_results = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_file = {executor.submit(process_file_enhanced, args): args[0] 
                         for args in process_args}
        
        for future in as_completed(future_to_file):
            result = future.result()
            all_file_results.append(result)
            
            # 显示进度
            completed = len(all_file_results)
            print(f"进度: {completed}/{len(parquet_files)} 文件已完成 ({completed/len(parquet_files)*100:.1f}%)")
    
    processing_time = time.time() - start_time
    print(f"处理完成，耗时: {processing_time:.1f} 秒")
    
    # 生成报告
    print("正在生成分析报告...")
    generate_enhanced_report(all_file_results, args.output_dir, args.sample_percentage)
    
    print(f"\n分析完成！结果保存在: {args.output_dir}")
    print(f"\n文件说明:")
    print(f"  - enhanced_trajectory_analysis_report.txt: 详细的文本分析报告")
    print(f"  - trajectory_quality_analysis.txt: 质量分析和建议")
    print(f"  - trajectory_statistics.json: 完整的统计数据(JSON格式)")
    print(f"  - trajectory_summary.csv: 轨迹汇总数据(便于Excel打开)")
    print(f"  - trajectory_summary.parquet: 轨迹汇总数据(高效存储格式)")
    print(f"  - field_statistics.csv: 各字段统计汇总")
    print(f"\n建议使用Excel或pandas读取CSV文件进行进一步分析")

if __name__ == "__main__":
    # 设置多进程启动方法
    mp.set_start_method('spawn', force=True)
    
    # 设置随机种子以确保可重现性
    np.random.seed(42)
    
    main()