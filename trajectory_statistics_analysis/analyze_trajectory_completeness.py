#!/usr/bin/env python3
"""
轨迹完整性分析程序
分析轨迹数据的完整性，识别可能不完整的轨迹
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import argparse
from pathlib import Path
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# 设置matplotlib字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")

def load_trajectory_statistics(stats_file):
    """
    加载轨迹统计数据
    
    Args:
        stats_file: 统计数据文件路径
        
    Returns:
        DataFrame: 轨迹统计数据
    """
    print(f"📊 Loading trajectory statistics from: {stats_file}")
    df = pd.read_parquet(stats_file)
    print(f"✅ Loaded {len(df):,} trajectories")
    return df

def analyze_short_trajectories(df, threshold=1000):
    """
    分析超短轨迹的特征
    
    Args:
        df: 轨迹统计数据
        threshold: 短轨迹阈值（点数）
        
    Returns:
        dict: 分析结果
    """
    print(f"🔍 Analyzing trajectories with < {threshold} points...")
    
    # 识别短轨迹
    short_trajectories = df[df['point_count'] < threshold].copy()
    normal_trajectories = df[df['point_count'] >= threshold].copy()
    
    analysis = {
        'total_trajectories': len(df),
        'short_trajectories_count': len(short_trajectories),
        'short_trajectories_percentage': len(short_trajectories) / len(df) * 100,
        'normal_trajectories_count': len(normal_trajectories),
        'threshold': threshold
    }
    
    # 短轨迹统计
    if len(short_trajectories) > 0:
        analysis['short_stats'] = {
            'min_points': short_trajectories['point_count'].min(),
            'max_points': short_trajectories['point_count'].max(),
            'mean_points': short_trajectories['point_count'].mean(),
            'median_points': short_trajectories['point_count'].median(),
            'std_points': short_trajectories['point_count'].std(),
            'min_duration': short_trajectories['duration_hours'].min(),
            'max_duration': short_trajectories['duration_hours'].max(),
            'mean_duration': short_trajectories['duration_hours'].mean(),
            'median_duration': short_trajectories['duration_hours'].median()
        }
    
    # 正常轨迹统计
    if len(normal_trajectories) > 0:
        analysis['normal_stats'] = {
            'min_points': normal_trajectories['point_count'].min(),
            'max_points': normal_trajectories['point_count'].max(),
            'mean_points': normal_trajectories['point_count'].mean(),
            'median_points': normal_trajectories['point_count'].median(),
            'std_points': normal_trajectories['point_count'].std(),
            'min_duration': normal_trajectories['duration_hours'].min(),
            'max_duration': normal_trajectories['duration_hours'].max(),
            'mean_duration': normal_trajectories['duration_hours'].mean(),
            'median_duration': normal_trajectories['duration_hours'].median()
        }
    
    print(f"📈 Found {len(short_trajectories):,} short trajectories ({analysis['short_trajectories_percentage']:.2f}%)")
    
    return analysis, short_trajectories, normal_trajectories

def load_single_trajectory_file(file_path):
    """
    加载单个轨迹文件并分析高度信息
    
    Args:
        file_path: 轨迹文件路径
        
    Returns:
        list: 轨迹高度分析结果
    """
    try:
        df = pd.read_parquet(file_path)
        
        if df.empty:
            return []
        
        results = []
        
        # 按flight_id分组分析每条轨迹
        for flight_id, group in df.groupby('flight_id'):
            if len(group) < 10:  # 跳过太短的轨迹
                continue
                
            # 按时间排序
            group = group.sort_values('timestamp')
            
            # 计算高度信息
            altitudes = group['altitude'].dropna()
            if len(altitudes) < 5:
                continue
                
            start_altitude = altitudes.iloc[0]
            end_altitude = altitudes.iloc[-1]
            max_altitude = altitudes.max()
            min_altitude = altitudes.min()
            altitude_range = max_altitude - min_altitude
            
            # 计算地理范围
            lats = group['latitude'].dropna()
            lons = group['longitude'].dropna()
            
            if len(lats) > 0 and len(lons) > 0:
                lat_range = lats.max() - lats.min()
                lon_range = lons.max() - lons.min()
                geo_distance = np.sqrt(lat_range**2 + lon_range**2)
            else:
                lat_range = lon_range = geo_distance = 0
            
            results.append({
                'flight_id': flight_id,
                'point_count': len(group),
                'duration_minutes': (group['timestamp'].max() - group['timestamp'].min()).total_seconds() / 60,
                'start_altitude': start_altitude,
                'end_altitude': end_altitude,
                'max_altitude': max_altitude,
                'min_altitude': min_altitude,
                'altitude_range': altitude_range,
                'altitude_change': abs(end_altitude - start_altitude),
                'lat_range': lat_range,
                'lon_range': lon_range,
                'geo_distance': geo_distance,
                'file_path': file_path
            })
            
        return results
        
    except Exception as e:
        print(f"❌ Error processing {file_path}: {str(e)}")
        return []

def analyze_trajectory_altitude_patterns(trajectory_dir, max_workers=None):
    """
    分析轨迹的高度模式，判断完整性
    
    Args:
        trajectory_dir: 轨迹数据目录
        max_workers: 最大工作进程数
        
    Returns:
        DataFrame: 轨迹高度分析结果
    """
    print(f"🔍 Analyzing altitude patterns in: {trajectory_dir}")
    
    # 获取所有parquet文件
    parquet_files = list(Path(trajectory_dir).glob("*.parquet"))
    print(f"📁 Found {len(parquet_files)} parquet files")
    
    if not parquet_files:
        print("❌ No parquet files found")
        return pd.DataFrame()
    
    # 限制文件数量进行快速分析
    sample_files = parquet_files[:50]  # 只分析前50个文件
    print(f"📊 Analyzing sample of {len(sample_files)} files for altitude patterns...")
    
    if max_workers is None:
        max_workers = min(mp.cpu_count(), len(sample_files))
    
    all_results = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(load_single_trajectory_file, file_path) for file_path in sample_files]
        
        for i, future in enumerate(futures):
            try:
                results = future.result()
                all_results.extend(results)
                if (i + 1) % 10 == 0:
                    print(f"⏳ Processed {i + 1}/{len(sample_files)} files")
            except Exception as e:
                print(f"❌ Error in file processing: {str(e)}")
    
    if not all_results:
        print("❌ No trajectory data found")
        return pd.DataFrame()
    
    df = pd.DataFrame(all_results)
    print(f"✅ Analyzed {len(df):,} trajectories from {len(sample_files)} files")
    
    return df

def classify_trajectory_completeness(df):
    """
    根据高度和地理信息分类轨迹完整性
    
    Args:
        df: 轨迹分析数据
        
    Returns:
        DataFrame: 带有完整性分类的数据
    """
    print("🏷️ Classifying trajectory completeness...")
    
    df = df.copy()
    
    # 定义完整性分类规则
    def classify_completeness(row):
        # 规则1: 高度变化判断
        altitude_change = row['altitude_change']
        max_altitude = row['max_altitude']
        start_altitude = row['start_altitude']
        end_altitude = row['end_altitude']
        
        # 规则2: 地理距离判断
        geo_distance = row['geo_distance']
        
        # 规则3: 时长判断
        duration = row['duration_minutes']
        
        # 规则4: 点数判断
        point_count = row['point_count']
        
        # 完整轨迹特征：
        # - 高度变化大（起降过程）
        # - 地理距离合理
        # - 时长合理
        # - 点数充足
        
        if (altitude_change > 5000 and  # 高度变化超过5000英尺
            geo_distance > 0.5 and      # 地理距离超过0.5度
            duration > 30 and           # 时长超过30分钟
            point_count > 500):         # 点数超过500
            return 'Complete'
        elif (altitude_change > 2000 and
              geo_distance > 0.2 and
              duration > 15 and
              point_count > 200):
            return 'Likely_Complete'
        elif (altitude_change < 1000 and
              geo_distance < 0.1 and
              duration < 10):
            return 'Fragment'
        else:
            return 'Partial'
    
    df['completeness'] = df.apply(classify_completeness, axis=1)
    
    # 统计各类别
    completeness_counts = df['completeness'].value_counts()
    print("📊 Completeness classification:")
    for category, count in completeness_counts.items():
        percentage = count / len(df) * 100
        print(f"  {category}: {count:,} ({percentage:.1f}%)")
    
    return df

def create_completeness_visualizations(df, short_trajectories, analysis, output_dir):
    """
    创建轨迹完整性可视化图表
    
    Args:
        df: 轨迹分析数据
        short_trajectories: 短轨迹数据
        analysis: 分析结果
        output_dir: 输出目录
    """
    print("📊 Creating completeness visualization charts...")
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 图1: 轨迹长度分布对比
    plt.figure(figsize=(15, 10))
    
    # 子图1: 点数分布
    plt.subplot(2, 3, 1)
    plt.hist(short_trajectories['point_count'], bins=50, alpha=0.7, color='red', label='Short Trajectories')
    plt.xlabel('Point Count')
    plt.ylabel('Frequency')
    plt.title('Short Trajectories Point Count Distribution')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 子图2: 时长分布
    plt.subplot(2, 3, 2)
    plt.hist(short_trajectories['duration_hours'], bins=50, alpha=0.7, color='orange', label='Short Trajectories')
    plt.xlabel('Duration (hours)')
    plt.ylabel('Frequency')
    plt.title('Short Trajectories Duration Distribution')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    # 子图3: 完整性分类（如果有高度数据）
    if 'completeness' in df.columns:
        plt.subplot(2, 3, 3)
        completeness_counts = df['completeness'].value_counts()
        colors = ['green', 'lightgreen', 'orange', 'red']
        plt.pie(completeness_counts.values, labels=completeness_counts.index, 
                autopct='%1.1f%%', colors=colors[:len(completeness_counts)])
        plt.title('Trajectory Completeness Classification')
    
    # 子图4: 高度变化分析（如果有数据）
    if 'altitude_change' in df.columns:
        plt.subplot(2, 3, 4)
        plt.scatter(df['point_count'], df['altitude_change'], alpha=0.6, s=10)
        plt.xlabel('Point Count')
        plt.ylabel('Altitude Change (ft)')
        plt.title('Point Count vs Altitude Change')
        plt.grid(True, alpha=0.3)
    
    # 子图5: 地理距离分析（如果有数据）
    if 'geo_distance' in df.columns:
        plt.subplot(2, 3, 5)
        plt.scatter(df['duration_minutes'], df['geo_distance'], alpha=0.6, s=10)
        plt.xlabel('Duration (minutes)')
        plt.ylabel('Geographic Distance (degrees)')
        plt.title('Duration vs Geographic Distance')
        plt.grid(True, alpha=0.3)
    
    # 子图6: 轨迹完整性得分分布
    plt.subplot(2, 3, 6)
    # 创建简单的完整性得分
    if len(short_trajectories) > 0:
        completeness_score = (short_trajectories['point_count'] / 1000 + 
                            short_trajectories['duration_hours'] / 2) / 2
        plt.hist(completeness_score, bins=30, alpha=0.7, color='purple')
        plt.xlabel('Completeness Score')
        plt.ylabel('Frequency')
        plt.title('Trajectory Completeness Score Distribution')
        plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图表
    plot_file = os.path.join(output_dir, 'trajectory_completeness_analysis.png')
    plt.savefig(plot_file, dpi=300, bbox_inches='tight')
    print(f"💾 Completeness analysis chart saved: {plot_file}")
    plt.show()
    plt.close()
    
    return plot_file

def generate_completeness_report(analysis, df, output_dir):
    """
    生成轨迹完整性分析报告
    
    Args:
        analysis: 分析结果
        df: 轨迹分析数据
        output_dir: 输出目录
    """
    print("📄 Generating completeness analysis report...")
    
    report_file = os.path.join(output_dir, 'trajectory_completeness_report.txt')
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("Trajectory Completeness Analysis Report\n")
        f.write("=" * 50 + "\n\n")
        
        # 基本统计
        f.write("Basic Statistics:\n")
        f.write(f"  Total trajectories: {analysis['total_trajectories']:,}\n")
        f.write(f"  Short trajectories (< {analysis['threshold']} points): {analysis['short_trajectories_count']:,} ({analysis['short_trajectories_percentage']:.2f}%)\n")
        f.write(f"  Normal trajectories: {analysis['normal_trajectories_count']:,}\n\n")
        
        # 短轨迹统计
        if 'short_stats' in analysis:
            f.write("Short Trajectories Statistics:\n")
            stats = analysis['short_stats']
            f.write(f"  Point count - Min: {stats['min_points']}, Max: {stats['max_points']}, Mean: {stats['mean_points']:.1f}, Median: {stats['median_points']:.1f}\n")
            f.write(f"  Duration (hours) - Min: {stats['min_duration']:.2f}, Max: {stats['max_duration']:.2f}, Mean: {stats['mean_duration']:.2f}, Median: {stats['median_duration']:.2f}\n\n")
        
        # 正常轨迹统计
        if 'normal_stats' in analysis:
            f.write("Normal Trajectories Statistics:\n")
            stats = analysis['normal_stats']
            f.write(f"  Point count - Min: {stats['min_points']}, Max: {stats['max_points']}, Mean: {stats['mean_points']:.1f}, Median: {stats['median_points']:.1f}\n")
            f.write(f"  Duration (hours) - Min: {stats['min_duration']:.2f}, Max: {stats['max_duration']:.2f}, Mean: {stats['mean_duration']:.2f}, Median: {stats['median_duration']:.2f}\n\n")
        
        # 完整性分类统计（如果有）
        if 'completeness' in df.columns:
            f.write("Completeness Classification:\n")
            completeness_counts = df['completeness'].value_counts()
            for category, count in completeness_counts.items():
                percentage = count / len(df) * 100
                f.write(f"  {category}: {count:,} ({percentage:.1f}%)\n")
            f.write("\n")
        
        # 分析结论
        f.write("Analysis Conclusions:\n")
        f.write("1. Trajectory Length Analysis:\n")
        if analysis['short_trajectories_percentage'] > 20:
            f.write("   - HIGH CONCERN: More than 20% of trajectories are very short\n")
        elif analysis['short_trajectories_percentage'] > 10:
            f.write("   - MODERATE CONCERN: 10-20% of trajectories are short\n")
        else:
            f.write("   - LOW CONCERN: Less than 10% of trajectories are short\n")
        
        f.write("\n2. Potential Issues:\n")
        f.write("   - Short trajectories may indicate incomplete flight data\n")
        f.write("   - Could be flight segments rather than complete flights\n")
        f.write("   - May need validation against official flight records\n")
        
        f.write("\n3. Recommendations:\n")
        f.write("   - Cross-reference with official flight schedules\n")
        f.write("   - Analyze altitude patterns for takeoff/landing detection\n")
        f.write("   - Check geographic coverage against airport locations\n")
        f.write("   - Consider filtering out trajectories below minimum thresholds\n")
    
    print(f"📄 Completeness report saved: {report_file}")
    return report_file

def main():
    parser = argparse.ArgumentParser(description='Analyze trajectory completeness')
    parser.add_argument('--stats-file', type=str, 
                       default='/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output/trajectory_statistics.parquet',
                       help='Path to trajectory statistics file')
    parser.add_argument('--trajectory-dir', type=str,
                       default='/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories',
                       help='Path to trajectory data directory')
    parser.add_argument('--output-dir', type=str,
                       default='/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/completeness_analysis',
                       help='Output directory for analysis results')
    parser.add_argument('--threshold', type=int, default=1000,
                       help='Threshold for short trajectories (default: 1000 points)')
    parser.add_argument('--max-workers', type=int, default=None,
                       help='Maximum number of worker processes')
    parser.add_argument('--analyze-altitude', action='store_true',
                       help='Perform detailed altitude pattern analysis')
    
    args = parser.parse_args()
    
    try:
        print("🚀 Trajectory Completeness Analysis")
        print("=" * 50)
        
        # 创建输出目录
        os.makedirs(args.output_dir, exist_ok=True)
        
        # 1. 加载轨迹统计数据
        stats_df = load_trajectory_statistics(args.stats_file)
        
        # 2. 分析短轨迹
        analysis, short_trajectories, normal_trajectories = analyze_short_trajectories(
            stats_df, args.threshold)
        
        # 3. 详细高度分析（可选）
        altitude_df = pd.DataFrame()
        if args.analyze_altitude:
            altitude_df = analyze_trajectory_altitude_patterns(
                args.trajectory_dir, args.max_workers)
            
            if not altitude_df.empty:
                altitude_df = classify_trajectory_completeness(altitude_df)
        
        # 4. 创建可视化图表
        create_completeness_visualizations(
            altitude_df if not altitude_df.empty else stats_df, 
            short_trajectories, analysis, args.output_dir)
        
        # 5. 生成分析报告
        generate_completeness_report(
            analysis, 
            altitude_df if not altitude_df.empty else stats_df, 
            args.output_dir)
        
        print("\n" + "=" * 50)
        print("🎉 Trajectory completeness analysis completed!")
        print(f"📁 Results saved to: {args.output_dir}")
        
    except Exception as e:
        print(f"❌ Error in completeness analysis: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()