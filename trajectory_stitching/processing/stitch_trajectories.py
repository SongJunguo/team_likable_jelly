#!/usr/bin/env python3
"""
主轨迹拼接处理脚本
Main Trajectory Stitching Processing Script
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import os
import sys
from pathlib import Path

# 添加工具模块路径
sys.path.append(os.path.dirname(__file__))
from utils import (
    load_config, setup_logging, get_consecutive_date_pairs, 
    load_trajectory_data, validate_trajectory_continuity,
    generate_new_flight_id, save_stitched_trajectory,
    create_stitching_report, validate_data_quality
)

class TrajectoryStitcher:
    """轨迹拼接处理器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.data_paths = config['data_paths']
        self.stitching_config = config['stitching_processing']
        self.quality_config = config['quality_control']
        
    def load_cross_date_detection_results(self) -> List[Dict]:
        """加载跨日期检测结果"""
        import yaml
        
        report_path = os.path.join(
            self.data_paths['reports_dir'], 
            "cross_date_detection_report.yaml"
        )
        
        if not os.path.exists(report_path):
            logging.error(f"跨日期检测报告不存在: {report_path}")
            logging.info("请先运行 detect_cross_date_flights.py")
            return []
        
        try:
            with open(report_path, 'r', encoding='utf-8') as f:
                report = yaml.safe_load(f)
            
            # 提取所有成功的检测结果（包括没有跨日期航班的情况）
            successful_results = [
                r for r in report.get('details', []) 
                if r.get('success', False)
            ]
            
            logging.info(f"加载跨日期检测结果: {len(successful_results)} 个有效结果")
            return successful_results
            
        except Exception as e:
            logging.error(f"加载跨日期检测结果失败: {e}")
            return []
    
    def stitch_flight_pair(self, evening_df: pd.DataFrame, morning_df: pd.DataFrame, 
                          flight_match: Dict) -> Optional[pd.DataFrame]:
        """拼接一对跨日期航班"""
        identifier_type = flight_match['identifier_type']
        identifier_value = flight_match['identifier_value']
        
        try:
            # 提取对应的航班数据
            evening_flight = evening_df[evening_df[identifier_type] == identifier_value].copy()
            morning_flight = morning_df[morning_df[identifier_type] == identifier_value].copy()
            
            if len(evening_flight) == 0 or len(morning_flight) == 0:
                logging.warning(f"航班 {identifier_value} 数据为空，跳过拼接")
                return None
            
            # 验证连续性
            continuity_result = validate_trajectory_continuity(
                evening_flight, morning_flight, identifier_value, self.config
            )
            
            if not continuity_result['overall_continuous']:
                logging.warning(f"航班 {identifier_value} 连续性验证失败，跳过拼接")
                logging.debug(f"连续性检查结果: {continuity_result}")
                return None
            
            # 执行拼接
            stitched_flight = pd.concat([evening_flight, morning_flight], ignore_index=True)
            
            # 按时间排序
            stitched_flight = stitched_flight.sort_values('timestamp').reset_index(drop=True)
            
            # 处理flight_id
            if self.stitching_config.get('preserve_original_flight_id', True):
                # 保持原始flight_id
                pass
            else:
                # 生成新的flight_id
                existing_ids = list(stitched_flight['flight_id'].unique())
                new_id = generate_new_flight_id(existing_ids, 
                    self.stitching_config.get('new_flight_id_strategy', 'max_plus_increment'))
                stitched_flight['flight_id'] = new_id
            
            # 添加拼接标记
            stitched_flight['is_stitched'] = True
            stitched_flight['stitching_timestamp'] = datetime.now()
            
            logging.info(f"成功拼接航班 {identifier_value}: {len(stitched_flight)} 个轨迹点")
            return stitched_flight
            
        except Exception as e:
            logging.error(f"拼接航班 {identifier_value} 失败: {e}")
            return None
    
    def process_date_pair(self, date_pair_result: Dict) -> Dict:
        """处理一对日期的轨迹拼接"""
        date1_file = date_pair_result['date1_file']
        date2_file = date_pair_result['date2_file']
        date_pair = date_pair_result['date_pair']
        
        logging.info(f"开始处理日期对: {date_pair}")
        
        try:
            # 获取需要拼接的航班匹配信息
            matches = [m for m in date_pair_result.get('matches', []) if m.get('is_likely_cross_date', False)]
            
            if not matches:
                logging.info(f"日期对 {date_pair} 没有需要拼接的航班")
                return {
                    'date_pair': date_pair,
                    'flights_stitched': 0,
                    'total_trajectory_points': 0,
                    'success': True,
                    'message': 'No flights to stitch'
                }
            
            # 加载数据
            df1 = load_trajectory_data(date1_file)
            df2 = load_trajectory_data(date2_file)
            
            # 执行拼接
            stitched_flights = []
            successful_stitches = 0
            
            for match in matches:
                stitched_flight = self.stitch_flight_pair(df1, df2, match)
                if stitched_flight is not None:
                    stitched_flights.append(stitched_flight)
                    successful_stitches += 1
            
            if not stitched_flights:
                logging.warning(f"日期对 {date_pair} 没有成功拼接的航班")
                return {
                    'date_pair': date_pair,
                    'flights_stitched': 0,
                    'total_trajectory_points': 0,
                    'success': True,
                    'message': 'No successful stitches'
                }
            
            # 合并所有拼接的航班
            all_stitched = pd.concat(stitched_flights, ignore_index=True)
            
            # 数据质量验证
            quality_report = validate_data_quality(all_stitched, self.config)
            
            # 保存拼接结果
            output_filename = self.stitching_config.get('output_filename_pattern', '{date}_stitched.parquet')
            date_str = date_pair.split(' -> ')[0]  # 使用第一个日期
            output_filename = output_filename.format(date=date_str)
            output_path = os.path.join(self.data_paths['output_dir'], output_filename)
            
            save_stitched_trajectory(all_stitched, output_path)
            
            result = {
                'date_pair': date_pair,
                'flights_stitched': successful_stitches,
                'total_trajectory_points': len(all_stitched),
                'output_file': output_path,
                'quality_report': quality_report,
                'success': True
            }
            
            logging.info(f"日期对 {date_pair} 处理完成: 拼接 {successful_stitches} 个航班")
            return result
            
        except Exception as e:
            logging.error(f"处理日期对 {date_pair} 失败: {e}")
            return {
                'date_pair': date_pair,
                'flights_stitched': 0,
                'total_trajectory_points': 0,
                'error': str(e),
                'success': False
            }
    
    def run_stitching(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """运行轨迹拼接处理"""
        logging.info("开始轨迹拼接处理")
        
        # 加载跨日期检测结果
        detection_results = self.load_cross_date_detection_results()
        
        if not detection_results:
            logging.error("没有可用的跨日期检测结果")
            return []
        
        # 处理每个日期对
        processing_results = []
        
        for i, date_pair_result in enumerate(detection_results, 1):
            logging.info(f"处理第 {i}/{len(detection_results)} 个日期对")
            result = self.process_date_pair(date_pair_result)
            processing_results.append(result)
        
        return processing_results

def main():
    """主函数"""
    # 加载配置
    config = load_config()
    setup_logging(config)
    
    logging.info("=" * 60)
    logging.info("开始轨迹拼接处理")
    logging.info("=" * 60)
    
    # 创建拼接处理器
    stitcher = TrajectoryStitcher(config)
    
    # 执行拼接处理
    results = stitcher.run_stitching()
    
    # 生成处理报告
    report_path = os.path.join(
        config['data_paths']['reports_dir'], 
        "trajectory_stitching_report.yaml"
    )
    create_stitching_report(results, report_path)
    
    # 统计总结
    successful_results = [r for r in results if r.get('success', False)]
    total_flights_stitched = sum(r.get('flights_stitched', 0) for r in successful_results)
    total_trajectory_points = sum(r.get('total_trajectory_points', 0) for r in successful_results)
    
    logging.info("=" * 60)
    logging.info("轨迹拼接处理完成")
    logging.info(f"处理日期对数: {len(results)}")
    logging.info(f"成功处理数: {len(successful_results)}")
    logging.info(f"拼接航班总数: {total_flights_stitched}")
    logging.info(f"总轨迹点数: {total_trajectory_points}")
    logging.info(f"详细报告: {report_path}")
    logging.info("=" * 60)

if __name__ == "__main__":
    main()