#!/usr/bin/env python3
"""
拼接结果验证脚本
Stitching Results Validation Script
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import os
import sys
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# 添加处理模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'processing'))
from utils import (
    load_config, setup_logging, load_trajectory_data,
    validate_data_quality, calculate_distance
)

class StitchingValidator:
    """拼接结果验证器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.data_paths = config['data_paths']
        self.validation_config = config.get('validation', {})
        
    def load_stitched_trajectories(self) -> List[Tuple[str, pd.DataFrame]]:
        """加载所有拼接后的轨迹文件"""
        stitched_dir = self.data_paths['output_dir']
        
        if not os.path.exists(stitched_dir):
            logging.error(f"拼接输出目录不存在: {stitched_dir}")
            return []
        
        stitched_files = []
        for filename in os.listdir(stitched_dir):
            if filename.endswith('_stitched.parquet'):
                file_path = os.path.join(stitched_dir, filename)
                try:
                    df = pd.read_parquet(file_path)
                    stitched_files.append((filename, df))
                    logging.info(f"加载拼接文件: {filename} ({len(df)} 条记录)")
                except Exception as e:
                    logging.error(f"加载拼接文件 {filename} 失败: {e}")
        
        return stitched_files
    
    def validate_time_continuity(self, df: pd.DataFrame) -> Dict:
        """验证时间连续性"""
        validation_results = {
            'total_flights': df['flight_id'].nunique(),
            'time_gaps': [],
            'large_gaps_count': 0,
            'average_gap_seconds': 0,
            'max_gap_seconds': 0
        }
        
        max_gap_minutes = self.config.get('continuity_validation', {}).get('max_time_gap_minutes', 30)
        
        for flight_id in df['flight_id'].unique():
            flight_data = df[df['flight_id'] == flight_id].sort_values('timestamp')
            
            if len(flight_data) < 2:
                continue
            
            # 计算时间间隔
            time_diffs = flight_data['timestamp'].diff().dt.total_seconds().dropna()
            
            for gap in time_diffs:
                validation_results['time_gaps'].append(gap)
                if gap > max_gap_minutes * 60:
                    validation_results['large_gaps_count'] += 1
        
        if validation_results['time_gaps']:
            validation_results['average_gap_seconds'] = np.mean(validation_results['time_gaps'])
            validation_results['max_gap_seconds'] = np.max(validation_results['time_gaps'])
        
        return validation_results
    
    def validate_spatial_continuity(self, df: pd.DataFrame) -> Dict:
        """验证空间连续性"""
        validation_results = {
            'total_flights': df['flight_id'].nunique(),
            'position_jumps': [],
            'large_jumps_count': 0,
            'average_jump_km': 0,
            'max_jump_km': 0
        }
        
        max_distance_km = self.config.get('continuity_validation', {}).get('max_distance_km', 100)
        
        for flight_id in df['flight_id'].unique():
            flight_data = df[df['flight_id'] == flight_id].sort_values('timestamp')
            
            if len(flight_data) < 2:
                continue
            
            # 计算相邻点间距离
            for i in range(1, len(flight_data)):
                prev_point = flight_data.iloc[i-1]
                curr_point = flight_data.iloc[i]
                
                if pd.isna(prev_point['latitude']) or pd.isna(curr_point['latitude']):
                    continue
                
                distance = calculate_distance(
                    prev_point['latitude'], prev_point['longitude'],
                    curr_point['latitude'], curr_point['longitude']
                )
                
                validation_results['position_jumps'].append(distance)
                
                if distance > max_distance_km:
                    validation_results['large_jumps_count'] += 1
        
        if validation_results['position_jumps']:
            validation_results['average_jump_km'] = np.mean(validation_results['position_jumps'])
            validation_results['max_jump_km'] = np.max(validation_results['position_jumps'])
        
        return validation_results
    
    def validate_flight_parameters(self, df: pd.DataFrame) -> Dict:
        """验证飞行参数的合理性"""
        validation_results = {
            'altitude_stats': {},
            'speed_stats': {},
            'parameter_outliers': {}
        }
        
        # 高度统计
        if 'altitude' in df.columns:
            altitude_data = df['altitude'].dropna()
            validation_results['altitude_stats'] = {
                'min': altitude_data.min(),
                'max': altitude_data.max(),
                'mean': altitude_data.mean(),
                'std': altitude_data.std(),
                'outliers_count': len(altitude_data[(altitude_data < -2000) | (altitude_data > 50000)])
            }
        
        # 速度统计
        if 'groundspeed' in df.columns:
            speed_data = df['groundspeed'].dropna()
            validation_results['speed_stats'] = {
                'min': speed_data.min(),
                'max': speed_data.max(),
                'mean': speed_data.mean(),
                'std': speed_data.std(),
                'outliers_count': len(speed_data[(speed_data < 0) | (speed_data > 1000)])
            }
        
        return validation_results
    
    def compare_with_original_data(self, stitched_files: List[Tuple[str, pd.DataFrame]]) -> Dict:
        """与原始数据进行对比"""
        comparison_results = {
            'original_vs_stitched': {},
            'data_integrity': {}
        }
        
        raw_dir = self.data_paths['raw_trajectories']
        
        for filename, stitched_df in stitched_files:
            # 提取日期
            date_str = filename.replace('_stitched.parquet', '')
            original_file = os.path.join(raw_dir, f"{date_str}.parquet")
            
            if not os.path.exists(original_file):
                logging.warning(f"原始文件不存在: {original_file}")
                continue
            
            try:
                original_df = pd.read_parquet(original_file)
                
                # 统计对比
                comparison = {
                    'original_flights': original_df['flight_id'].nunique(),
                    'original_records': len(original_df),
                    'stitched_flights': stitched_df['flight_id'].nunique(),
                    'stitched_records': len(stitched_df),
                    'flight_reduction': original_df['flight_id'].nunique() - stitched_df['flight_id'].nunique(),
                    'records_change': len(stitched_df) - len(original_df)
                }
                
                comparison_results['original_vs_stitched'][date_str] = comparison
                
            except Exception as e:
                logging.error(f"对比原始数据失败 {original_file}: {e}")
        
        return comparison_results
    
    def generate_validation_plots(self, stitched_files: List[Tuple[str, pd.DataFrame]]) -> None:
        """生成验证图表"""
        if not stitched_files:
            logging.warning("没有拼接文件可用于生成图表")
            return
        
        # 创建图表输出目录
        plots_dir = os.path.join(self.data_paths['reports_dir'], 'validation_plots')
        os.makedirs(plots_dir, exist_ok=True)
        
        # 合并所有数据用于统计
        all_data = pd.concat([df for _, df in stitched_files], ignore_index=True)
        
        # 1. 时间间隔分布图
        plt.figure(figsize=(12, 6))
        
        time_gaps = []
        for flight_id in all_data['flight_id'].unique():
            flight_data = all_data[all_data['flight_id'] == flight_id].sort_values('timestamp')
            if len(flight_data) > 1:
                gaps = flight_data['timestamp'].diff().dt.total_seconds().dropna()
                time_gaps.extend(gaps[gaps < 3600])  # 只显示小于1小时的间隔
        
        plt.subplot(1, 2, 1)
        plt.hist(time_gaps, bins=50, alpha=0.7, edgecolor='black')
        plt.xlabel('时间间隔 (秒)')
        plt.ylabel('频次')
        plt.title('轨迹点时间间隔分布')
        plt.yscale('log')
        
        # 2. 飞行参数分布图
        plt.subplot(1, 2, 2)
        if 'altitude' in all_data.columns:
            altitude_data = all_data['altitude'].dropna()
            altitude_data = altitude_data[(altitude_data >= -2000) & (altitude_data <= 50000)]
            plt.hist(altitude_data, bins=50, alpha=0.7, edgecolor='black')
            plt.xlabel('高度 (英尺)')
            plt.ylabel('频次')
            plt.title('高度分布')
        
        plt.tight_layout()
        plt.savefig(os.path.join(plots_dir, 'time_altitude_distribution.png'), dpi=300, bbox_inches='tight')
        plt.close()
        
        logging.info(f"验证图表已保存到: {plots_dir}")
    
    def run_validation(self) -> Dict:
        """运行完整的验证流程"""
        logging.info("开始拼接结果验证")
        
        # 加载拼接后的轨迹
        stitched_files = self.load_stitched_trajectories()
        
        if not stitched_files:
            logging.error("没有找到拼接后的轨迹文件")
            return {'error': 'No stitched files found'}
        
        validation_report = {
            'validation_timestamp': datetime.now().isoformat(),
            'total_stitched_files': len(stitched_files),
            'file_validations': {},
            'overall_statistics': {}
        }
        
        # 验证每个文件
        all_time_results = []
        all_spatial_results = []
        all_parameter_results = []
        
        for filename, df in stitched_files:
            logging.info(f"验证文件: {filename}")
            
            # 时间连续性验证
            time_validation = self.validate_time_continuity(df)
            
            # 空间连续性验证
            spatial_validation = self.validate_spatial_continuity(df)
            
            # 飞行参数验证
            parameter_validation = self.validate_flight_parameters(df)
            
            # 数据质量验证
            quality_validation = validate_data_quality(df, self.config)
            
            file_validation = {
                'time_continuity': time_validation,
                'spatial_continuity': spatial_validation,
                'flight_parameters': parameter_validation,
                'data_quality': quality_validation
            }
            
            validation_report['file_validations'][filename] = file_validation
            
            # 收集统计数据
            all_time_results.append(time_validation)
            all_spatial_results.append(spatial_validation)
            all_parameter_results.append(parameter_validation)
        
        # 与原始数据对比
        comparison_results = self.compare_with_original_data(stitched_files)
        validation_report['original_comparison'] = comparison_results
        
        # 生成验证图表
        if self.validation_config.get('generate_reports', True):
            self.generate_validation_plots(stitched_files)
        
        # 总体统计
        validation_report['overall_statistics'] = {
            'total_flights_processed': sum(r['total_flights'] for r in all_time_results),
            'average_time_gap_seconds': np.mean([r['average_gap_seconds'] for r in all_time_results if r['average_gap_seconds'] > 0]),
            'average_spatial_jump_km': np.mean([r['average_jump_km'] for r in all_spatial_results if r['average_jump_km'] > 0]),
            'total_large_time_gaps': sum(r['large_gaps_count'] for r in all_time_results),
            'total_large_spatial_jumps': sum(r['large_jumps_count'] for r in all_spatial_results)
        }
        
        return validation_report

def main():
    """主函数"""
    # 加载配置
    config = load_config()
    setup_logging(config)
    
    logging.info("=" * 60)
    logging.info("开始拼接结果验证")
    logging.info("=" * 60)
    
    # 创建验证器
    validator = StitchingValidator(config)
    
    # 执行验证
    validation_report = validator.run_validation()
    
    # 保存验证报告
    import yaml
    report_path = os.path.join(
        config['data_paths']['reports_dir'],
        'stitching_validation_report.yaml'
    )
    
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        yaml.dump(validation_report, f, default_flow_style=False, allow_unicode=True)
    
    # 输出验证总结
    if 'overall_statistics' in validation_report:
        stats = validation_report['overall_statistics']
        logging.info("=" * 60)
        logging.info("验证结果总结")
        logging.info(f"处理航班总数: {stats.get('total_flights_processed', 0)}")
        logging.info(f"平均时间间隔: {stats.get('average_time_gap_seconds', 0):.2f} 秒")
        logging.info(f"平均空间跳跃: {stats.get('average_spatial_jump_km', 0):.2f} 公里")
        logging.info(f"大时间间隔数: {stats.get('total_large_time_gaps', 0)}")
        logging.info(f"大空间跳跃数: {stats.get('total_large_spatial_jumps', 0)}")
        logging.info(f"详细报告: {report_path}")
        logging.info("=" * 60)

if __name__ == "__main__":
    main()