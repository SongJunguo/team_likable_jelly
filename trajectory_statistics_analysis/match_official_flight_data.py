#!/usr/bin/env python3
"""
轨迹与官方航班数据匹配分析
匹配轨迹ID与challenge_set.csv等文件，获取官方起降时间信息
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
import argparse
import warnings
warnings.filterwarnings('ignore')

def load_official_flight_data(data_dir):
    """
    加载官方航班数据文件
    
    Args:
        data_dir: 数据目录路径
        
    Returns:
        dict: 包含各个数据集的字典
    """
    print("📊 Loading official flight data...")
    
    flight_data = {}
    
    # 定义要加载的文件
    files_to_load = {
        'challenge_set': 'challenge_set.csv',
        'submission_set': 'submission_set.csv', 
        'final_submission_set': 'final_submission_set.csv'
    }
    
    for dataset_name, filename in files_to_load.items():
        file_path = os.path.join(data_dir, filename)
        
        if os.path.exists(file_path):
            try:
                print(f"  📁 Loading {filename}...")
                df = pd.read_csv(file_path)
                
                # 转换时间列为datetime
                time_columns = ['actual_offblock_time', 'arrival_time']
                for col in time_columns:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                
                flight_data[dataset_name] = df
                print(f"    ✅ Loaded {len(df):,} flights from {filename}")
                
                # 显示基本信息
                if 'flight_id' in df.columns:
                    print(f"    📈 Flight ID range: {df['flight_id'].min()} - {df['flight_id'].max()}")
                
            except Exception as e:
                print(f"    ❌ Error loading {filename}: {str(e)}")
        else:
            print(f"    ⚠️  File not found: {filename}")
    
    return flight_data

def load_trajectory_statistics(stats_file):
    """
    加载轨迹统计数据
    
    Args:
        stats_file: 统计数据文件路径
        
    Returns:
        DataFrame: 轨迹统计数据
    """
    print(f"📊 Loading trajectory statistics from: {stats_file}")
    
    if not os.path.exists(stats_file):
        print(f"❌ Statistics file not found: {stats_file}")
        return pd.DataFrame()
    
    df = pd.read_parquet(stats_file)
    print(f"✅ Loaded {len(df):,} trajectory records")
    
    return df

def match_trajectories_with_official_data(trajectory_stats, flight_data):
    """
    匹配轨迹数据与官方航班数据
    
    Args:
        trajectory_stats: 轨迹统计数据
        flight_data: 官方航班数据字典
        
    Returns:
        dict: 匹配结果
    """
    print("🔍 Matching trajectories with official flight data...")
    
    matching_results = {}
    
    # 获取轨迹中的flight_id
    trajectory_flight_ids = set(trajectory_stats['flight_id'].unique())
    print(f"📊 Unique flight IDs in trajectories: {len(trajectory_flight_ids):,}")
    
    for dataset_name, official_df in flight_data.items():
        if official_df.empty or 'flight_id' not in official_df.columns:
            continue
            
        print(f"\n🔍 Matching with {dataset_name}...")
        
        # 获取官方数据中的flight_id
        official_flight_ids = set(official_df['flight_id'].unique())
        print(f"  📊 Flight IDs in {dataset_name}: {len(official_flight_ids):,}")
        
        # 找到匹配的flight_id
        matched_ids = trajectory_flight_ids.intersection(official_flight_ids)
        print(f"  ✅ Matched flight IDs: {len(matched_ids):,}")
        
        if len(matched_ids) > 0:
            # 计算匹配率
            match_rate_trajectory = len(matched_ids) / len(trajectory_flight_ids) * 100
            match_rate_official = len(matched_ids) / len(official_flight_ids) * 100
            
            print(f"  📈 Match rate (trajectory perspective): {match_rate_trajectory:.2f}%")
            print(f"  📈 Match rate (official data perspective): {match_rate_official:.2f}%")
            
            # 创建匹配的数据集
            matched_trajectories = trajectory_stats[trajectory_stats['flight_id'].isin(matched_ids)].copy()
            matched_official = official_df[official_df['flight_id'].isin(matched_ids)].copy()
            
            # 合并数据
            merged_data = matched_trajectories.merge(
                matched_official, 
                on='flight_id', 
                how='inner',
                suffixes=('_trajectory', '_official')
            )
            
            print(f"  📊 Merged records: {len(merged_data):,}")
            
            matching_results[dataset_name] = {
                'matched_ids': matched_ids,
                'match_rate_trajectory': match_rate_trajectory,
                'match_rate_official': match_rate_official,
                'matched_trajectories': matched_trajectories,
                'matched_official': matched_official,
                'merged_data': merged_data
            }
        else:
            print(f"  ❌ No matches found for {dataset_name}")
            matching_results[dataset_name] = {
                'matched_ids': set(),
                'match_rate_trajectory': 0.0,
                'match_rate_official': 0.0,
                'matched_trajectories': pd.DataFrame(),
                'matched_official': pd.DataFrame(),
                'merged_data': pd.DataFrame()
            }
    
    return matching_results

def analyze_flight_duration_consistency(matching_results):
    """
    分析轨迹时长与官方航班时长的一致性
    
    Args:
        matching_results: 匹配结果
        
    Returns:
        dict: 时长一致性分析结果
    """
    print("\n⏱️  Analyzing flight duration consistency...")
    
    duration_analysis = {}
    
    for dataset_name, match_data in matching_results.items():
        merged_data = match_data['merged_data']
        
        if merged_data.empty:
            continue
            
        print(f"\n📊 Duration analysis for {dataset_name}:")
        
        # 计算官方航班时长（如果有起降时间）
        if 'actual_offblock_time' in merged_data.columns and 'arrival_time' in merged_data.columns:
            # 过滤掉时间为空的记录
            valid_times = merged_data.dropna(subset=['actual_offblock_time', 'arrival_time'])
            
            if len(valid_times) > 0:
                # 计算官方时长（小时）
                official_duration = (valid_times['arrival_time'] - valid_times['actual_offblock_time']).dt.total_seconds() / 3600
                trajectory_duration = valid_times['duration_hours']
                
                # 计算时长差异
                duration_diff = trajectory_duration - official_duration
                duration_diff_percent = (duration_diff / official_duration) * 100
                
                analysis = {
                    'total_records': len(merged_data),
                    'valid_time_records': len(valid_times),
                    'official_duration_stats': {
                        'mean': official_duration.mean(),
                        'median': official_duration.median(),
                        'std': official_duration.std(),
                        'min': official_duration.min(),
                        'max': official_duration.max()
                    },
                    'trajectory_duration_stats': {
                        'mean': trajectory_duration.mean(),
                        'median': trajectory_duration.median(),
                        'std': trajectory_duration.std(),
                        'min': trajectory_duration.min(),
                        'max': trajectory_duration.max()
                    },
                    'duration_difference_stats': {
                        'mean_diff_hours': duration_diff.mean(),
                        'median_diff_hours': duration_diff.median(),
                        'std_diff_hours': duration_diff.std(),
                        'mean_diff_percent': duration_diff_percent.mean(),
                        'median_diff_percent': duration_diff_percent.median()
                    }
                }
                
                # 分类时长差异
                consistent_flights = len(valid_times[abs(duration_diff_percent) <= 10])  # 差异在10%以内
                moderate_diff = len(valid_times[(abs(duration_diff_percent) > 10) & (abs(duration_diff_percent) <= 50)])
                large_diff = len(valid_times[abs(duration_diff_percent) > 50])
                
                analysis['consistency_classification'] = {
                    'consistent_flights': consistent_flights,
                    'moderate_difference': moderate_diff,
                    'large_difference': large_diff,
                    'consistent_percentage': consistent_flights / len(valid_times) * 100,
                    'moderate_percentage': moderate_diff / len(valid_times) * 100,
                    'large_difference_percentage': large_diff / len(valid_times) * 100
                }
                
                print(f"  📊 Valid time records: {len(valid_times):,} / {len(merged_data):,}")
                print(f"  ⏱️  Official duration - Mean: {analysis['official_duration_stats']['mean']:.2f}h, Median: {analysis['official_duration_stats']['median']:.2f}h")
                print(f"  ⏱️  Trajectory duration - Mean: {analysis['trajectory_duration_stats']['mean']:.2f}h, Median: {analysis['trajectory_duration_stats']['median']:.2f}h")
                print(f"  📈 Duration difference - Mean: {analysis['duration_difference_stats']['mean_diff_percent']:.1f}%, Median: {analysis['duration_difference_stats']['median_diff_percent']:.1f}%")
                print(f"  ✅ Consistent flights (±10%): {consistent_flights:,} ({analysis['consistency_classification']['consistent_percentage']:.1f}%)")
                print(f"  ⚠️  Moderate difference (10-50%): {moderate_diff:,} ({analysis['consistency_classification']['moderate_percentage']:.1f}%)")
                print(f"  ❌ Large difference (>50%): {large_diff:,} ({analysis['consistency_classification']['large_difference_percentage']:.1f}%)")
                
                duration_analysis[dataset_name] = analysis
            else:
                print(f"  ❌ No valid time records found")
        else:
            print(f"  ❌ Missing time columns")
    
    return duration_analysis

def identify_incomplete_trajectories(matching_results, duration_analysis):
    """
    基于匹配结果识别可能不完整的轨迹
    
    Args:
        matching_results: 匹配结果
        duration_analysis: 时长分析结果
        
    Returns:
        dict: 不完整轨迹分析结果
    """
    print("\n🔍 Identifying potentially incomplete trajectories...")
    
    incomplete_analysis = {}
    
    for dataset_name, match_data in matching_results.items():
        merged_data = match_data['merged_data']
        
        if merged_data.empty:
            continue
            
        print(f"\n📊 Incomplete trajectory analysis for {dataset_name}:")
        
        # 定义不完整轨迹的标准
        incomplete_criteria = []
        
        # 标准1: 轨迹点数过少
        short_trajectories = merged_data[merged_data['point_count'] < 500]
        incomplete_criteria.append(('short_point_count', short_trajectories))
        
        # 标准2: 轨迹时长过短
        short_duration = merged_data[merged_data['duration_hours'] < 0.5]  # 少于30分钟
        incomplete_criteria.append(('short_duration', short_duration))
        
        # 标准3: 时长差异过大（如果有时长分析）
        if dataset_name in duration_analysis:
            duration_data = duration_analysis[dataset_name]
            if 'valid_time_records' in duration_data and duration_data['valid_time_records'] > 0:
                # 重新计算时长差异
                valid_times = merged_data.dropna(subset=['actual_offblock_time', 'arrival_time'])
                if len(valid_times) > 0:
                    official_duration = (valid_times['arrival_time'] - valid_times['actual_offblock_time']).dt.total_seconds() / 3600
                    trajectory_duration = valid_times['duration_hours']
                    duration_diff_percent = ((trajectory_duration - official_duration) / official_duration) * 100
                    
                    # 轨迹时长明显短于官方时长（差异超过-30%）
                    significantly_shorter = valid_times[duration_diff_percent < -30]
                    incomplete_criteria.append(('significantly_shorter_duration', significantly_shorter))
        
        # 统计各种不完整情况
        analysis = {
            'total_matched_trajectories': len(merged_data)
        }
        
        all_incomplete_ids = set()
        
        for criterion_name, criterion_data in incomplete_criteria:
            count = len(criterion_data)
            percentage = count / len(merged_data) * 100 if len(merged_data) > 0 else 0
            
            analysis[criterion_name] = {
                'count': count,
                'percentage': percentage,
                'flight_ids': set(criterion_data['flight_id'].tolist()) if not criterion_data.empty else set()
            }
            
            all_incomplete_ids.update(analysis[criterion_name]['flight_ids'])
            
            print(f"  📊 {criterion_name}: {count:,} trajectories ({percentage:.1f}%)")
        
        # 综合不完整轨迹
        analysis['combined_incomplete'] = {
            'count': len(all_incomplete_ids),
            'percentage': len(all_incomplete_ids) / len(merged_data) * 100 if len(merged_data) > 0 else 0,
            'flight_ids': all_incomplete_ids
        }
        
        print(f"  🎯 Total potentially incomplete: {len(all_incomplete_ids):,} ({analysis['combined_incomplete']['percentage']:.1f}%)")
        
        incomplete_analysis[dataset_name] = analysis
    
    return incomplete_analysis

def generate_matching_report(matching_results, duration_analysis, incomplete_analysis, output_dir):
    """
    生成匹配分析报告
    
    Args:
        matching_results: 匹配结果
        duration_analysis: 时长分析结果
        incomplete_analysis: 不完整轨迹分析结果
        output_dir: 输出目录
    """
    print("📄 Generating matching analysis report...")
    
    report_file = os.path.join(output_dir, 'trajectory_official_matching_report.txt')
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("Trajectory-Official Flight Data Matching Report\n")
        f.write("=" * 60 + "\n\n")
        
        # 匹配统计
        f.write("1. MATCHING STATISTICS\n")
        f.write("-" * 30 + "\n")
        
        for dataset_name, match_data in matching_results.items():
            f.write(f"\n{dataset_name.upper()}:\n")
            f.write(f"  Matched flight IDs: {len(match_data['matched_ids']):,}\n")
            f.write(f"  Match rate (trajectory perspective): {match_data['match_rate_trajectory']:.2f}%\n")
            f.write(f"  Match rate (official data perspective): {match_data['match_rate_official']:.2f}%\n")
            f.write(f"  Merged records: {len(match_data['merged_data']):,}\n")
        
        # 时长一致性分析
        f.write(f"\n\n2. DURATION CONSISTENCY ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        for dataset_name, duration_data in duration_analysis.items():
            f.write(f"\n{dataset_name.upper()}:\n")
            f.write(f"  Total records: {duration_data['total_records']:,}\n")
            f.write(f"  Valid time records: {duration_data['valid_time_records']:,}\n")
            
            if 'consistency_classification' in duration_data:
                cc = duration_data['consistency_classification']
                f.write(f"  Consistent flights (±10%): {cc['consistent_flights']:,} ({cc['consistent_percentage']:.1f}%)\n")
                f.write(f"  Moderate difference (10-50%): {cc['moderate_difference']:,} ({cc['moderate_percentage']:.1f}%)\n")
                f.write(f"  Large difference (>50%): {cc['large_difference']:,} ({cc['large_difference_percentage']:.1f}%)\n")
                
                dd = duration_data['duration_difference_stats']
                f.write(f"  Mean duration difference: {dd['mean_diff_percent']:.1f}%\n")
                f.write(f"  Median duration difference: {dd['median_diff_percent']:.1f}%\n")
        
        # 不完整轨迹分析
        f.write(f"\n\n3. INCOMPLETE TRAJECTORY ANALYSIS\n")
        f.write("-" * 40 + "\n")
        
        for dataset_name, incomplete_data in incomplete_analysis.items():
            f.write(f"\n{dataset_name.upper()}:\n")
            f.write(f"  Total matched trajectories: {incomplete_data['total_matched_trajectories']:,}\n")
            
            if 'short_point_count' in incomplete_data:
                spc = incomplete_data['short_point_count']
                f.write(f"  Short trajectories (<500 points): {spc['count']:,} ({spc['percentage']:.1f}%)\n")
            
            if 'short_duration' in incomplete_data:
                sd = incomplete_data['short_duration']
                f.write(f"  Short duration (<0.5h): {sd['count']:,} ({sd['percentage']:.1f}%)\n")
            
            if 'significantly_shorter_duration' in incomplete_data:
                ssd = incomplete_data['significantly_shorter_duration']
                f.write(f"  Significantly shorter than official: {ssd['count']:,} ({ssd['percentage']:.1f}%)\n")
            
            ci = incomplete_data['combined_incomplete']
            f.write(f"  Total potentially incomplete: {ci['count']:,} ({ci['percentage']:.1f}%)\n")
        
        # 结论和建议
        f.write(f"\n\n4. CONCLUSIONS AND RECOMMENDATIONS\n")
        f.write("-" * 45 + "\n")
        
        f.write("\nKey Findings:\n")
        
        # 计算总体匹配率
        total_matches = sum(len(match_data['matched_ids']) for match_data in matching_results.values())
        if total_matches > 0:
            f.write(f"- Successfully matched trajectory data with official flight records\n")
        else:
            f.write(f"- WARNING: No matches found between trajectory and official data\n")
        
        # 时长一致性总结
        consistent_datasets = []
        for dataset_name, duration_data in duration_analysis.items():
            if 'consistency_classification' in duration_data:
                consistent_pct = duration_data['consistency_classification']['consistent_percentage']
                if consistent_pct > 70:
                    consistent_datasets.append(dataset_name)
        
        if consistent_datasets:
            f.write(f"- Good duration consistency found in: {', '.join(consistent_datasets)}\n")
        
        # 不完整轨迹总结
        high_incomplete_datasets = []
        for dataset_name, incomplete_data in incomplete_analysis.items():
            incomplete_pct = incomplete_data['combined_incomplete']['percentage']
            if incomplete_pct > 20:
                high_incomplete_datasets.append(f"{dataset_name} ({incomplete_pct:.1f}%)")
        
        if high_incomplete_datasets:
            f.write(f"- High incomplete trajectory rates in: {', '.join(high_incomplete_datasets)}\n")
        
        f.write("\nRecommendations:\n")
        f.write("1. Filter out trajectories with <500 points for analysis\n")
        f.write("2. Cross-validate trajectory duration with official flight times\n")
        f.write("3. Investigate trajectories with >50% duration difference\n")
        f.write("4. Consider using only trajectories that match official records\n")
        f.write("5. Implement quality scoring based on multiple criteria\n")
    
    print(f"📄 Matching report saved: {report_file}")
    return report_file

def save_matched_data(matching_results, output_dir):
    """
    保存匹配的数据到文件
    
    Args:
        matching_results: 匹配结果
        output_dir: 输出目录
    """
    print("💾 Saving matched data...")
    
    for dataset_name, match_data in matching_results.items():
        if not match_data['merged_data'].empty:
            # 保存合并后的数据
            merged_file = os.path.join(output_dir, f'matched_{dataset_name}_data.parquet')
            match_data['merged_data'].to_parquet(merged_file, index=False)
            print(f"  💾 Saved {len(match_data['merged_data']):,} records to: {merged_file}")
            
            # 保存匹配的flight_id列表
            ids_file = os.path.join(output_dir, f'matched_{dataset_name}_flight_ids.txt')
            with open(ids_file, 'w') as f:
                for flight_id in sorted(match_data['matched_ids']):
                    f.write(f"{flight_id}\n")
            print(f"  📝 Saved {len(match_data['matched_ids']):,} flight IDs to: {ids_file}")

def main():
    parser = argparse.ArgumentParser(description='Match trajectory data with official flight records')
    parser.add_argument('--stats-file', type=str,
                       default='/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output/trajectory_statistics.parquet',
                       help='Path to trajectory statistics file')
    parser.add_argument('--data-dir', type=str,
                       default='/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset',
                       help='Path to official flight data directory')
    parser.add_argument('--output-dir', type=str,
                       default='/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/matching_analysis',
                       help='Output directory for matching results')
    
    args = parser.parse_args()
    
    try:
        print("🚀 Trajectory-Official Flight Data Matching Analysis")
        print("=" * 60)
        
        # 创建输出目录
        os.makedirs(args.output_dir, exist_ok=True)
        
        # 1. 加载轨迹统计数据
        trajectory_stats = load_trajectory_statistics(args.stats_file)
        
        if trajectory_stats.empty:
            print("❌ No trajectory statistics data found. Exiting.")
            return
        
        # 2. 加载官方航班数据
        flight_data = load_official_flight_data(args.data_dir)
        
        if not flight_data:
            print("❌ No official flight data found. Exiting.")
            return
        
        # 3. 匹配轨迹与官方数据
        matching_results = match_trajectories_with_official_data(trajectory_stats, flight_data)
        
        # 4. 分析时长一致性
        duration_analysis = analyze_flight_duration_consistency(matching_results)
        
        # 5. 识别不完整轨迹
        incomplete_analysis = identify_incomplete_trajectories(matching_results, duration_analysis)
        
        # 6. 生成报告
        generate_matching_report(matching_results, duration_analysis, incomplete_analysis, args.output_dir)
        
        # 7. 保存匹配数据
        save_matched_data(matching_results, args.output_dir)
        
        print("\n" + "=" * 60)
        print("🎉 Trajectory-official data matching analysis completed!")
        print(f"📁 Results saved to: {args.output_dir}")
        
    except Exception as e:
        print(f"❌ Error in matching analysis: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()