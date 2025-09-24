#!/usr/bin/env python3
"""
完整插值处理脚本
- 确保插值后无任何缺失值
- 实施头尾NaN截断逻辑
- 处理高质量轨迹数据
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
import multiprocessing as mp
from functools import partial
import traceback
from datetime import datetime

class CompleteInterpolator:
    """完整插值处理器"""
    
    def __init__(self, time_interval=10):
        """
        初始化插值器
        
        Args:
            time_interval: 时间间隔（秒）
        """
        self.time_interval = time_interval
        self.required_columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    def remove_head_tail_nan(self, df):
        """
        移除头尾的NaN值
        
        Args:
            df: 轨迹数据DataFrame
            
        Returns:
            处理后的DataFrame
        """
        if df.empty:
            return df
        
        # 基于经纬度来判断有效数据范围（经纬度是最重要的）
        lat_valid = df['latitude'].notna()
        lon_valid = df['longitude'].notna()
        position_valid = lat_valid & lon_valid
        
        if not position_valid.any():
            return pd.DataFrame()  # 如果没有有效位置数据，返回空DataFrame
        
        # 找到第一个和最后一个有效位置数据的索引
        valid_indices = position_valid[position_valid].index
        first_valid = valid_indices[0]
        last_valid = valid_indices[-1]
        
        # 截取有效范围的数据
        truncated_df = df.loc[first_valid:last_valid].copy()
        
        return truncated_df
    
    def interpolate_column(self, series, method='linear'):
        """
        对单列进行插值
        
        Args:
            series: 数据序列
            method: 插值方法
            
        Returns:
            插值后的序列
        """
        if series.isna().all():
            return series
        
        # 线性插值
        interpolated = series.interpolate(method=method, limit_direction='both')
        
        # 如果还有缺失值，用前向填充和后向填充
        if interpolated.isna().any():
            interpolated = interpolated.fillna(method='ffill').fillna(method='bfill')
        
        # 如果还有缺失值，用均值填充
        if interpolated.isna().any():
            mean_value = interpolated.mean()
            if not np.isnan(mean_value):
                interpolated = interpolated.fillna(mean_value)
            else:
                # 如果均值也是NaN，用0填充（最后的保险）
                interpolated = interpolated.fillna(0)
        
        return interpolated
    
    def process_trajectory(self, df):
        """
        处理单条轨迹
        
        Args:
            df: 轨迹数据DataFrame
            
        Returns:
            处理后的DataFrame和统计信息
        """
        stats = {
            'original_points': len(df),
            'original_missing': {},
            'after_truncation_points': 0,
            'after_truncation_missing': {},
            'final_points': 0,
            'final_missing': {},
            'success': False
        }
        
        try:
            # 记录原始缺失情况
            for col in self.required_columns:
                if col in df.columns:
                    stats['original_missing'][col] = df[col].isna().sum()
            
            # 1. 移除头尾NaN
            truncated_df = self.remove_head_tail_nan(df)
            
            if truncated_df.empty:
                return pd.DataFrame(), stats
            
            stats['after_truncation_points'] = len(truncated_df)
            
            # 记录截断后缺失情况
            for col in self.required_columns:
                if col in truncated_df.columns:
                    stats['after_truncation_missing'][col] = truncated_df[col].isna().sum()
            
            # 2. 对每列进行完整插值
            interpolated_df = truncated_df.copy()
            
            for col in self.required_columns:
                if col in interpolated_df.columns:
                    # 特殊处理track角度数据
                    if col == 'track':
                        # 对于track，先处理角度连续性
                        track_series = interpolated_df[col].copy()
                        if not track_series.isna().all():
                            # 角度展开处理
                            track_unwrapped = np.unwrap(np.radians(track_series.fillna(0))) * 180 / np.pi
                            track_series_temp = pd.Series(track_unwrapped, index=track_series.index)
                            interpolated_track = self.interpolate_column(track_series_temp)
                            # 将角度规范化到[0, 360)
                            interpolated_df[col] = interpolated_track % 360
                        else:
                            interpolated_df[col] = self.interpolate_column(track_series)
                    else:
                        interpolated_df[col] = self.interpolate_column(interpolated_df[col])
            
            stats['final_points'] = len(interpolated_df)
            
            # 验证最终结果无缺失值
            for col in self.required_columns:
                if col in interpolated_df.columns:
                    missing_count = interpolated_df[col].isna().sum()
                    stats['final_missing'][col] = missing_count
                    if missing_count > 0:
                        print(f"警告: {col} 列仍有 {missing_count} 个缺失值")
            
            # 检查是否成功（无任何缺失值）
            total_missing = sum(stats['final_missing'].values())
            stats['success'] = (total_missing == 0 and len(interpolated_df) > 0)
            
            return interpolated_df, stats
            
        except Exception as e:
            print(f"处理轨迹时出错: {e}")
            traceback.print_exc()
            return pd.DataFrame(), stats

def load_high_quality_flight_ids(file_path='high_quality_flight_ids.txt'):
    """加载高质量轨迹ID列表"""
    try:
        with open(file_path, 'r') as f:
            flight_ids = [int(line.strip()) for line in f if line.strip()]
        return set(flight_ids)
    except Exception as e:
        print(f"加载高质量轨迹ID失败: {e}")
        return set()

def process_single_file(args):
    """处理单个日期文件"""
    date_file, target_flight_ids, input_dir, output_dir = args
    
    try:
        # 读取数据
        file_path = os.path.join(input_dir, date_file)
        df = pd.read_parquet(file_path)
        
        # 筛选目标flight_id
        target_df = df[df['flight_id'].isin(target_flight_ids)]
        
        if target_df.empty:
            return {
                'date': date_file,
                'found_trajectories': 0,
                'processed_trajectories': 0,
                'success_trajectories': 0,
                'total_points_before': 0,
                'total_points_after': 0
            }
        
        # 按flight_id分组处理
        interpolator = CompleteInterpolator(time_interval=10)
        processed_data = []
        stats = {
            'date': date_file,
            'found_trajectories': 0,
            'processed_trajectories': 0,
            'success_trajectories': 0,
            'total_points_before': 0,
            'total_points_after': 0
        }
        
        for flight_id, group in target_df.groupby('flight_id'):
            stats['found_trajectories'] += 1
            stats['total_points_before'] += len(group)
            
            # 按时间排序
            group_sorted = group.sort_values('timestamp').reset_index(drop=True)
            
            # 处理轨迹
            processed_traj, traj_stats = interpolator.process_trajectory(group_sorted)
            
            if not processed_traj.empty and traj_stats['success']:
                processed_data.append(processed_traj)
                stats['success_trajectories'] += 1
                stats['total_points_after'] += len(processed_traj)
            
            stats['processed_trajectories'] += 1
        
        # 保存处理后的数据
        if processed_data:
            combined_df = pd.concat(processed_data, ignore_index=True)
            output_file = os.path.join(output_dir, f"interpolated_{date_file}")
            combined_df.to_parquet(output_file, index=False)
        
        return stats
        
    except Exception as e:
        print(f"处理文件 {date_file} 时出错: {e}")
        return {
            'date': date_file,
            'found_trajectories': 0,
            'processed_trajectories': 0,
            'success_trajectories': 0,
            'total_points_before': 0,
            'total_points_after': 0,
            'error': str(e)
        }

def main():
    """主函数"""
    print("🚀 开始完整插值处理")
    print("=" * 60)
    
    # 路径设置
    input_dir = "opensky_2024_PRC_dataset/classic_filtered_trajectories"
    output_dir = "interpolated_trajectories"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载高质量轨迹ID
    print("📋 加载高质量轨迹ID...")
    target_flight_ids = load_high_quality_flight_ids()
    print(f"目标轨迹数量: {len(target_flight_ids):,}")
    
    if not target_flight_ids:
        print("❌ 未找到高质量轨迹ID，退出")
        return
    
    # 获取所有日期文件
    date_files = [f for f in os.listdir(input_dir) if f.endswith('.parquet')]
    date_files.sort()
    print(f"找到 {len(date_files)} 个日期文件")
    
    # 多进程处理
    print("🔄 开始多进程处理...")
    num_processes = min(mp.cpu_count(), 16)  # 限制进程数
    print(f"使用 {num_processes} 个进程")
    
    # 准备参数
    process_args = [(date_file, target_flight_ids, input_dir, output_dir) 
                   for date_file in date_files]
    
    # 执行多进程处理
    with mp.Pool(processes=num_processes) as pool:
        results = pool.map(process_single_file, process_args)
    
    # 统计结果
    print("\n📊 处理结果统计:")
    print("=" * 60)
    
    total_stats = {
        'found_trajectories': 0,
        'processed_trajectories': 0,
        'success_trajectories': 0,
        'total_points_before': 0,
        'total_points_after': 0,
        'files_with_data': 0
    }
    
    for result in results:
        if 'error' not in result:
            total_stats['found_trajectories'] += result['found_trajectories']
            total_stats['processed_trajectories'] += result['processed_trajectories']
            total_stats['success_trajectories'] += result['success_trajectories']
            total_stats['total_points_before'] += result['total_points_before']
            total_stats['total_points_after'] += result['total_points_after']
            if result['found_trajectories'] > 0:
                total_stats['files_with_data'] += 1
    
    print(f"找到轨迹数: {total_stats['found_trajectories']:,}")
    print(f"处理轨迹数: {total_stats['processed_trajectories']:,}")
    print(f"成功轨迹数: {total_stats['success_trajectories']:,}")
    print(f"处理前总点数: {total_stats['total_points_before']:,}")
    print(f"处理后总点数: {total_stats['total_points_after']:,}")
    print(f"有数据的文件数: {total_stats['files_with_data']}")
    
    if total_stats['processed_trajectories'] > 0:
        success_rate = total_stats['success_trajectories'] / total_stats['processed_trajectories'] * 100
        print(f"成功率: {success_rate:.1f}%")
    
    if total_stats['total_points_before'] > 0:
        point_retention = total_stats['total_points_after'] / total_stats['total_points_before'] * 100
        print(f"数据点保留率: {point_retention:.1f}%")
    
    # 生成处理报告
    report_file = f"complete_interpolation_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("完整插值处理报告\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"处理时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"目标轨迹数量: {len(target_flight_ids):,}\n")
        f.write(f"处理文件数: {len(date_files)}\n\n")
        
        f.write("处理结果:\n")
        f.write(f"  找到轨迹数: {total_stats['found_trajectories']:,}\n")
        f.write(f"  处理轨迹数: {total_stats['processed_trajectories']:,}\n")
        f.write(f"  成功轨迹数: {total_stats['success_trajectories']:,}\n")
        f.write(f"  处理前总点数: {total_stats['total_points_before']:,}\n")
        f.write(f"  处理后总点数: {total_stats['total_points_after']:,}\n")
        f.write(f"  有数据的文件数: {total_stats['files_with_data']}\n")
        
        if total_stats['processed_trajectories'] > 0:
            success_rate = total_stats['success_trajectories'] / total_stats['processed_trajectories'] * 100
            f.write(f"  成功率: {success_rate:.1f}%\n")
        
        if total_stats['total_points_before'] > 0:
            point_retention = total_stats['total_points_after'] / total_stats['total_points_before'] * 100
            f.write(f"  数据点保留率: {point_retention:.1f}%\n")
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    print("✅ 完整插值处理完成!")

if __name__ == "__main__":
    main()