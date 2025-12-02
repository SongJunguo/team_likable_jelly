#!/usr/bin/env python3
"""
轨迹统计可视化程序
生成轨迹时长和点数分布的图表
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
import argparse
from pathlib import Path

# 设置字体和样式 - 使用英文字体避免中文显示问题
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Liberation Sans']
plt.rcParams['axes.unicode_minus'] = False
sns.set_style("whitegrid")
plt.style.use('seaborn-v0_8')

def load_trajectory_data(data_file):
    """
    加载轨迹统计数据
    
    Args:
        data_file: parquet文件路径
        
    Returns:
        pd.DataFrame: 轨迹数据
    """
    if not os.path.exists(data_file):
        raise FileNotFoundError(f"数据文件不存在: {data_file}")
    
    df = pd.read_parquet(data_file)
    print(f"📊 加载轨迹数据: {len(df):,} 条轨迹")
    
    return df

def create_duration_distribution_plots(df, output_dir):
    """
    创建轨迹时长分布图表
    
    Args:
        df: 轨迹数据DataFrame
        output_dir: 输出目录
    """
    if 'duration_hours' not in df.columns:
        print("⚠️ 数据中没有时长信息，跳过时长分布图")
        return
    
    # 过滤有效时长数据
    valid_duration = df[df['duration_hours'] > 0]['duration_hours']
    
    if len(valid_duration) == 0:
        print("⚠️ 没有有效的时长数据")
        return
    
    print(f"📈 创建时长分布图，有效数据: {len(valid_duration):,} 条")
    
    # 创建子图
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Flight Trajectory Duration Distribution Analysis', fontsize=16, fontweight='bold')
    
    # 1. 直方图
    axes[0, 0].hist(valid_duration, bins=50, alpha=0.7, color='skyblue', edgecolor='black')
    axes[0, 0].set_title('Trajectory Duration Distribution Histogram')
    axes[0, 0].set_xlabel('Duration (hours)')
    axes[0, 0].set_ylabel('Number of Trajectories')
    axes[0, 0].grid(True, alpha=0.3)
    
    # 添加统计信息
    mean_duration = valid_duration.mean()
    median_duration = valid_duration.median()
    axes[0, 0].axvline(mean_duration, color='red', linestyle='--', label=f'Mean: {mean_duration:.2f}h')
    axes[0, 0].axvline(median_duration, color='green', linestyle='--', label=f'Median: {median_duration:.2f}h')
    axes[0, 0].legend()
    
    # 2. 累积分布图
    sorted_duration = np.sort(valid_duration)
    cumulative_prob = np.arange(1, len(sorted_duration) + 1) / len(sorted_duration)
    axes[0, 1].plot(sorted_duration, cumulative_prob, linewidth=2, color='orange')
    axes[0, 1].set_title('Trajectory Duration Cumulative Distribution')
    axes[0, 1].set_xlabel('Duration (hours)')
    axes[0, 1].set_ylabel('Cumulative Probability')
    axes[0, 1].grid(True, alpha=0.3)
    
    # 3. 箱线图
    axes[1, 0].boxplot(valid_duration, vert=True, patch_artist=True,
                       boxprops=dict(facecolor='lightblue', alpha=0.7))
    axes[1, 0].set_title('Trajectory Duration Box Plot')
    axes[1, 0].set_ylabel('Duration (hours)')
    axes[1, 0].grid(True, alpha=0.3)
    
    # 4. 时长区间分布柱状图
    # 定义时长区间
    duration_bins = [0, 0.5, 1, 2, 4, 8, 12, 24, float('inf')]
    duration_labels = ['<0.5h', '0.5-1h', '1-2h', '2-4h', '4-8h', '8-12h', '12-24h', '>24h']
    
    duration_counts = pd.cut(valid_duration, bins=duration_bins, labels=duration_labels, right=False).value_counts()
    
    bars = axes[1, 1].bar(range(len(duration_counts)), duration_counts.values, 
                         color='lightcoral', alpha=0.7, edgecolor='black')
    axes[1, 1].set_title('Trajectory Duration Interval Distribution')
    axes[1, 1].set_xlabel('Duration Interval')
    axes[1, 1].set_ylabel('Number of Trajectories')
    axes[1, 1].set_xticks(range(len(duration_counts)))
    axes[1, 1].set_xticklabels(duration_counts.index, rotation=45)
    axes[1, 1].grid(True, alpha=0.3)
    
    # 在柱状图上添加数值标签
    for bar, count in zip(bars, duration_counts.values):
        height = bar.get_height()
        axes[1, 1].text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                        f'{count:,}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    # 保存图表
    duration_plot_file = os.path.join(output_dir, 'trajectory_duration_distribution.png')
    plt.savefig(duration_plot_file, dpi=300, bbox_inches='tight')
    print(f"💾 Duration distribution chart saved: {duration_plot_file}")
    
    plt.show()

def create_point_count_distribution_plots(df, output_dir):
    """
    创建轨迹点数分布图表
    
    Args:
        df: 轨迹数据DataFrame
        output_dir: 输出目录
    """
    if 'point_count' not in df.columns:
        print("⚠️ 数据中没有点数信息，跳过点数分布图")
        return
    
    point_counts = df['point_count']
    print(f"📈 创建点数分布图，数据: {len(point_counts):,} 条")
    
    # 创建子图
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    fig.suptitle('Flight Trajectory Point Count Distribution Analysis', fontsize=16, fontweight='bold')
    
    # 1. 直方图
    axes[0, 0].hist(point_counts, bins=50, alpha=0.7, color='lightgreen', edgecolor='black')
    axes[0, 0].set_title('Trajectory Point Count Distribution Histogram')
    axes[0, 0].set_xlabel('Number of Points')
    axes[0, 0].set_ylabel('Number of Trajectories')
    axes[0, 0].grid(True, alpha=0.3)
    
    # 添加统计信息
    mean_points = point_counts.mean()
    median_points = point_counts.median()
    axes[0, 0].axvline(mean_points, color='red', linestyle='--', label=f'Mean: {mean_points:.0f}')
    axes[0, 0].axvline(median_points, color='green', linestyle='--', label=f'Median: {median_points:.0f}')
    axes[0, 0].legend()
    
    # 2. 对数尺度直方图
    axes[0, 1].hist(point_counts, bins=50, alpha=0.7, color='lightcoral', edgecolor='black')
    axes[0, 1].set_title('Trajectory Point Count Distribution (Log Scale)')
    axes[0, 1].set_xlabel('Number of Points')
    axes[0, 1].set_ylabel('Number of Trajectories')
    axes[0, 1].set_yscale('log')
    axes[0, 1].grid(True, alpha=0.3)
    
    # 3. 箱线图
    axes[1, 0].boxplot(point_counts, vert=True, patch_artist=True,
                       boxprops=dict(facecolor='lightyellow', alpha=0.7))
    axes[1, 0].set_title('Trajectory Point Count Box Plot')
    axes[1, 0].set_ylabel('Number of Points')
    axes[1, 0].grid(True, alpha=0.3)
    
    # 4. 点数区间分布柱状图
    # 定义点数区间
    point_bins = [0, 100, 500, 1000, 2000, 5000, 10000, 20000, float('inf')]
    point_labels = ['<100', '100-500', '500-1K', '1K-2K', '2K-5K', '5K-10K', '10K-20K', '>20K']
    
    point_counts_binned = pd.cut(point_counts, bins=point_bins, labels=point_labels, right=False).value_counts()
    
    bars = axes[1, 1].bar(range(len(point_counts_binned)), point_counts_binned.values,
                         color='plum', alpha=0.7, edgecolor='black')
    axes[1, 1].set_title('Trajectory Point Count Interval Distribution')
    axes[1, 1].set_xlabel('Point Count Interval')
    axes[1, 1].set_ylabel('Number of Trajectories')
    axes[1, 1].set_xticks(range(len(point_counts_binned)))
    axes[1, 1].set_xticklabels(point_counts_binned.index, rotation=45)
    axes[1, 1].grid(True, alpha=0.3)
    
    # 在柱状图上添加数值标签
    for bar, count in zip(bars, point_counts_binned.values):
        height = bar.get_height()
        axes[1, 1].text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                        f'{count:,}', ha='center', va='bottom', fontsize=9)
    
    plt.tight_layout()
    
    # 保存图表
    points_plot_file = os.path.join(output_dir, 'trajectory_points_distribution.png')
    plt.savefig(points_plot_file, dpi=300, bbox_inches='tight')
    print(f"💾 Point count distribution chart saved: {points_plot_file}")
    
    plt.show()

def create_correlation_plot(df, output_dir):
    """
    创建时长与点数的相关性图表
    
    Args:
        df: 轨迹数据DataFrame
        output_dir: 输出目录
    """
    if 'duration_hours' not in df.columns or 'point_count' not in df.columns:
        print("⚠️ 缺少时长或点数信息，跳过相关性分析")
        return
    
    # 过滤有效数据
    valid_data = df[(df['duration_hours'] > 0) & (df['point_count'] > 0)]
    
    if len(valid_data) == 0:
        print("⚠️ 没有有效的相关性数据")
        return
    
    print(f"📈 创建相关性图表，有效数据: {len(valid_data):,} 条")
    
    # 创建散点图
    plt.figure(figsize=(12, 8))
    
    # 使用hexbin来处理大量数据点
    plt.hexbin(valid_data['duration_hours'], valid_data['point_count'], 
               gridsize=50, cmap='Blues', alpha=0.7)
    plt.colorbar(label='Number of Trajectories')
    
    plt.title('Trajectory Duration vs Point Count Correlation Analysis', fontsize=14, fontweight='bold')
    plt.xlabel('Duration (hours)')
    plt.ylabel('Number of Points')
    plt.grid(True, alpha=0.3)
    
    # 计算相关系数
    correlation = valid_data['duration_hours'].corr(valid_data['point_count'])
    plt.text(0.05, 0.95, f'Correlation: {correlation:.3f}', 
             transform=plt.gca().transAxes, fontsize=12,
             bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    # 保存图表
    correlation_plot_file = os.path.join(output_dir, 'duration_points_correlation.png')
    plt.savefig(correlation_plot_file, dpi=300, bbox_inches='tight')
    print(f"💾 Correlation chart saved: {correlation_plot_file}")
    
    plt.show()
    plt.close()
    
    return correlation_plot_file

def generate_summary_report(df, output_dir):
    """
    生成汇总报告
    
    Args:
        df: 轨迹数据DataFrame
        output_dir: 输出目录
    """
    report_file = os.path.join(output_dir, 'visualization_report.txt')
    
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("轨迹统计可视化报告\n")
        f.write("=" * 50 + "\n\n")
        
        f.write(f"总轨迹数: {len(df):,}\n\n")
        
        if 'point_count' in df.columns:
            f.write("轨迹点数统计:\n")
            f.write(f"  最小值: {df['point_count'].min():,}\n")
            f.write(f"  最大值: {df['point_count'].max():,}\n")
            f.write(f"  平均值: {df['point_count'].mean():.1f}\n")
            f.write(f"  中位数: {df['point_count'].median():.1f}\n")
            f.write(f"  标准差: {df['point_count'].std():.1f}\n\n")
        
        if 'duration_hours' in df.columns:
            valid_duration = df[df['duration_hours'] > 0]['duration_hours']
            if len(valid_duration) > 0:
                f.write("轨迹时长统计 (小时):\n")
                f.write(f"  有效数据: {len(valid_duration):,} 条\n")
                f.write(f"  最小值: {valid_duration.min():.2f}\n")
                f.write(f"  最大值: {valid_duration.max():.2f}\n")
                f.write(f"  平均值: {valid_duration.mean():.2f}\n")
                f.write(f"  中位数: {valid_duration.median():.2f}\n")
                f.write(f"  标准差: {valid_duration.std():.2f}\n\n")
        
        f.write("生成的图表文件:\n")
        f.write("  - trajectory_duration_distribution.png: Duration distribution analysis\n")
        f.write("  - trajectory_points_distribution.png: Point count distribution analysis\n")
        f.write("  - duration_points_correlation.png: Duration vs point count correlation\n")
    
    print(f"📄 Visualization report saved: {report_file}")

def main():
    print("🚀 Trajectory Statistics Visualization Program")
    print("=" * 50)
    
    parser = argparse.ArgumentParser(description='Generate visualization charts for trajectory statistics')
    parser.add_argument('stats_file', help='Path to trajectory statistics data file')
    parser.add_argument('--output-dir', default='./visualization_output', 
                       help='Output directory path (default: ./visualization_output)')
    
    args = parser.parse_args()
    
    try:
        print(f"📊 Starting to generate visualization charts...")
        print(f"📁 Statistics file: {args.stats_file}")
        print(f"📁 Output directory: {args.output_dir}")
        
        # 创建输出目录
        os.makedirs(args.output_dir, exist_ok=True)
        
        # 加载数据
        df = load_trajectory_data(args.stats_file)
        
        print("🎨 Starting to generate visualization charts...")
        
        # 生成时长分布图
        create_duration_distribution_plots(df, args.output_dir)
        
        # 生成点数分布图
        create_point_count_distribution_plots(df, args.output_dir)
        
        # 生成相关性图表
        create_correlation_plot(df, args.output_dir)
        
        # 生成汇总报告
        generate_summary_report(df, args.output_dir)
        
        print("🎉 All charts generated successfully!")
        
    except Exception as e:
        print(f"❌ Error occurred while generating charts: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()