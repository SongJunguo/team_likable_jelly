#!/usr/bin/env python3
"""
高质量轨迹定制插值脚本
基于4,469条高质量轨迹，实施优化的插值策略
"""

import pandas as pd
import numpy as np
import os
import sys
from pathlib import Path
import argparse
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')

# 导入现有的插值模块
sys.path.append('/workspace/aircraft_trajectory/team_likable_jelly')
import interpolate

class HighQualityInterpolator:
    def __init__(self, max_hole_size=10, smooth_factor=1e-2):
        """
        高质量轨迹插值器
        
        Args:
            max_hole_size: 最大插值间隔（秒），从20秒优化为10秒
            smooth_factor: 平滑因子
        """
        self.max_hole_size = max_hole_size
        self.smooth_factor = smooth_factor
        
        # 临时修改全局插值参数
        interpolate.MAX_HOLE_SIZE = max_hole_size
        
    def remove_boundary_nans(self, df):
        """
        移除头尾的NaN值
        
        Args:
            df: 轨迹数据DataFrame
            
        Returns:
            处理后的DataFrame
        """
        # 检查关键字段
        key_columns = ['latitude', 'longitude', 'altitude']
        
        # 找到第一个所有关键字段都有效的索引
        valid_mask = df[key_columns].notna().all(axis=1)
        if not valid_mask.any():
            return df  # 如果没有有效数据，返回原始数据
            
        first_valid = valid_mask.idxmax()
        last_valid = valid_mask[::-1].idxmax()
        
        # 截取有效数据段
        df_trimmed = df.loc[first_valid:last_valid].copy()
        
        return df_trimmed
    
    def validate_interpolation_quality(self, df):
        """
        验证插值质量
        
        Args:
            df: 插值后的DataFrame
            
        Returns:
            dict: 质量指标
        """
        key_columns = ['latitude', 'longitude', 'altitude']
        
        quality_metrics = {}
        for col in key_columns:
            if col in df.columns:
                missing_count = df[col].isna().sum()
                total_count = len(df)
                missing_rate = missing_count / total_count if total_count > 0 else 1.0
                quality_metrics[f'{col}_missing_rate'] = missing_rate
        
        # 总体缺失率
        overall_missing = df[key_columns].isna().any(axis=1).sum()
        quality_metrics['overall_missing_rate'] = overall_missing / len(df) if len(df) > 0 else 1.0
        
        return quality_metrics
    
    def interpolate_trajectory(self, df):
        """
        对单条轨迹进行插值处理
        
        Args:
            df: 轨迹数据DataFrame
            
        Returns:
            tuple: (插值后的DataFrame, 质量指标)
        """
        try:
            # 1. 移除头尾NaN
            df_trimmed = self.remove_boundary_nans(df)
            
            if len(df_trimmed) < 10:  # 轨迹太短，跳过
                return None, {'error': 'trajectory_too_short'}
            
            # 2. 应用插值
            df_interpolated = interpolate.interpolate(df_trimmed, self.smooth_factor)
            
            # 3. 验证质量
            quality_metrics = self.validate_interpolation_quality(df_interpolated)
            
            return df_interpolated, quality_metrics
            
        except Exception as e:
            return None, {'error': str(e)}

def load_high_quality_flight_ids():
    """加载高质量轨迹的flight_id列表"""
    flight_ids_file = '/workspace/aircraft_trajectory/team_likable_jelly/high_quality_flight_ids.txt'
    
    if not os.path.exists(flight_ids_file):
        print(f"❌ 高质量轨迹ID文件不存在: {flight_ids_file}")
        return []
    
    with open(flight_ids_file, 'r') as f:
        flight_ids = [line.strip() for line in f if line.strip()]
    
    print(f"✅ 加载了 {len(flight_ids)} 个高质量轨迹ID")
    return flight_ids

def process_high_quality_trajectories():
    """处理高质量轨迹"""
    
    print("=" * 80)
    print("🚀 开始高质量轨迹插值处理")
    print("=" * 80)
    
    # 1. 加载高质量轨迹ID
    flight_ids = load_high_quality_flight_ids()
    if not flight_ids:
        print("❌ 没有找到高质量轨迹ID，退出处理")
        return
    
    # 转换为整数集合以便快速查找
    target_flight_ids = set(int(fid) for fid in flight_ids)
    
    # 2. 设置路径
    filtered_dir = Path('/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories')
    output_dir = Path('/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/high_quality_interpolated_trajectories')
    
    # 创建输出目录
    output_dir.mkdir(exist_ok=True)
    
    print(f"📂 输入目录: {filtered_dir}")
    print(f"📂 输出目录: {output_dir}")
    print(f"🎯 目标flight_id数量: {len(target_flight_ids)}")
    
    # 3. 初始化插值器
    interpolator = HighQualityInterpolator(max_hole_size=10, smooth_factor=1e-2)
    
    # 4. 处理统计
    stats = {
        'total_requested': len(flight_ids),
        'found_trajectories': 0,
        'processed_successfully': 0,
        'failed_processing': 0,
        'quality_metrics': []
    }
    
    print("\n开始处理...")
    
    # 5. 遍历所有日期文件
    date_files = sorted(filtered_dir.glob("2022-*.parquet"))
    print(f"📅 找到 {len(date_files)} 个日期文件")
    
    for date_file in tqdm(date_files, desc="处理日期文件"):
        try:
            # 读取日期文件
            df_day = pd.read_parquet(date_file)
            
            # 筛选出目标flight_id的轨迹
            target_trajectories = df_day[df_day['flight_id'].isin(target_flight_ids)]
            
            if len(target_trajectories) == 0:
                continue
                
            # 按flight_id分组处理
            for flight_id, df_trajectory in target_trajectories.groupby('flight_id'):
                try:
                    stats['found_trajectories'] += 1
                    
                    # 按时间排序
                    df_trajectory = df_trajectory.sort_values('timestamp').reset_index(drop=True)
                    
                    # 插值处理
                    df_interpolated, quality_metrics = interpolator.interpolate_trajectory(df_trajectory)
                    
                    if df_interpolated is not None and 'error' not in quality_metrics:
                        # 保存插值结果
                        output_file = output_dir / f"{flight_id}.parquet"
                        df_interpolated.to_parquet(output_file)
                        stats['processed_successfully'] += 1
                        stats['quality_metrics'].append(quality_metrics)
                    else:
                        stats['failed_processing'] += 1
                        
                except Exception as e:
                    stats['failed_processing'] += 1
                    if stats['failed_processing'] <= 10:  # 只打印前10个错误
                        print(f"❌ 处理flight_id {flight_id} 时出错: {e}")
                        
        except Exception as e:
            print(f"❌ 处理日期文件 {date_file} 时出错: {e}")
    
    # 6. 生成处理报告
    print("\n" + "=" * 80)
    print("📊 处理结果统计")
    print("=" * 80)
    
    print(f"🎯 目标轨迹数: {stats['total_requested']}")
    print(f"📁 找到轨迹数: {stats['found_trajectories']}")
    print(f"✅ 成功处理数: {stats['processed_successfully']}")
    print(f"❌ 处理失败数: {stats['failed_processing']}")
    
    if stats['found_trajectories'] > 0:
        success_rate = stats['processed_successfully']/stats['found_trajectories']*100
        print(f"📈 成功率: {success_rate:.1f}%")
    else:
        print("📈 成功率: 0% (未找到目标轨迹)")
    
    # 7. 质量分析
    if stats['quality_metrics']:
        print(f"\n📊 插值质量分析 (基于 {len(stats['quality_metrics'])} 条轨迹):")
        
        # 计算平均缺失率
        avg_metrics = {}
        for key in ['latitude_missing_rate', 'longitude_missing_rate', 'altitude_missing_rate', 'overall_missing_rate']:
            values = [m.get(key, 0) for m in stats['quality_metrics'] if key in m]
            if values:
                avg_metrics[key] = np.mean(values)
        
        for key, value in avg_metrics.items():
            print(f"   {key}: {value:.4f} ({value*100:.2f}%)")
        
        # 检查是否达到质量目标
        overall_missing = avg_metrics.get('overall_missing_rate', 1.0)
        if overall_missing < 0.01:
            print(f"🎉 质量目标达成！平均缺失率 {overall_missing*100:.2f}% < 1%")
        else:
            print(f"⚠️ 质量目标未达成，平均缺失率 {overall_missing*100:.2f}% >= 1%")
    
    # 8. 保存处理报告
    report_file = output_dir / 'interpolation_report.txt'
    with open(report_file, 'w') as f:
        f.write("高质量轨迹插值处理报告\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"处理时间: {pd.Timestamp.now()}\n")
        f.write(f"插值参数: MAX_HOLE_SIZE={interpolator.max_hole_size}s, SMOOTH_FACTOR={interpolator.smooth_factor}\n\n")
        f.write(f"目标轨迹数: {stats['total_requested']}\n")
        f.write(f"找到轨迹数: {stats['found_trajectories']}\n")
        f.write(f"成功处理数: {stats['processed_successfully']}\n")
        f.write(f"处理失败数: {stats['failed_processing']}\n")
        f.write(f"成功率: {stats['processed_successfully']/max(1,stats['found_trajectories'])*100:.1f}%\n\n")
        
        if avg_metrics:
            f.write("质量指标:\n")
            for key, value in avg_metrics.items():
                f.write(f"  {key}: {value:.4f} ({value*100:.2f}%)\n")
        
        # 记录找到的轨迹数量
        f.write(f"找到轨迹数: {stats['found_trajectories']}\n")
        f.write(f"成功率: {stats['processed_successfully']/max(1,stats['found_trajectories'])*100:.1f}%\n")
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    print("\n✅ 高质量轨迹插值处理完成！")

def main():
    parser = argparse.ArgumentParser(description='高质量轨迹定制插值处理')
    parser.add_argument('--max_hole_size', type=int, default=10, 
                       help='最大插值间隔（秒），默认10秒')
    parser.add_argument('--smooth_factor', type=float, default=1e-2,
                       help='平滑因子，默认1e-2')
    
    args = parser.parse_args()
    
    # 更新插值参数
    interpolate.MAX_HOLE_SIZE = args.max_hole_size
    
    # 开始处理
    process_high_quality_trajectories()

if __name__ == "__main__":
    main()