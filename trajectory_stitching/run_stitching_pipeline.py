#!/usr/bin/env python3
"""
跨日期轨迹拼接完整流水线
Cross-Date Trajectory Stitching Pipeline
"""

import os
import sys
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# 添加模块路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(current_dir, 'processing'))
sys.path.append(os.path.join(current_dir, 'analysis'))

from utils import load_config, setup_logging
from detect_cross_date_flights import CrossDateFlightDetector
from stitch_trajectories import TrajectoryStitcher
from validate_stitching import StitchingValidator

class StitchingPipeline:
    """轨迹拼接流水线"""
    
    def __init__(self, config_path: str = None):
        """初始化流水线"""
        if config_path is None:
            config_path = os.path.join(current_dir, 'config', 'stitching_config.yaml')
        
        self.config = load_config(config_path)
        setup_logging(self.config)
        
        # 初始化各个组件
        self.detector = CrossDateFlightDetector(self.config)
        self.stitcher = TrajectoryStitcher(self.config)
        self.validator = StitchingValidator(self.config)
        
        logging.info("轨迹拼接流水线初始化完成")
    
    def check_prerequisites(self) -> bool:
        """检查运行前提条件"""
        logging.info("检查运行前提条件...")
        
        # 检查原始数据目录
        raw_dir = self.config['data_paths']['raw_trajectories']
        if not os.path.exists(raw_dir):
            logging.error(f"原始轨迹数据目录不存在: {raw_dir}")
            return False
        
        # 检查数据文件
        parquet_files = [f for f in os.listdir(raw_dir) if f.endswith('.parquet')]
        if len(parquet_files) < 2:
            logging.error(f"原始数据文件不足，需要至少2个文件进行拼接，当前只有 {len(parquet_files)} 个")
            return False
        
        logging.info(f"找到 {len(parquet_files)} 个原始轨迹文件")
        
        # 创建输出目录
        for dir_key in ['output_dir', 'reports_dir']:
            dir_path = self.config['data_paths'][dir_key]
            os.makedirs(dir_path, exist_ok=True)
            logging.info(f"输出目录已准备: {dir_path}")
        
        return True
    
    def run_detection_phase(self, start_date: str = None, end_date: str = None) -> bool:
        """运行跨日期航班检测阶段"""
        logging.info("=" * 60)
        logging.info("阶段 1: 跨日期航班检测")
        logging.info("=" * 60)
        
        try:
            detection_results = self.detector.run_detection(start_date, end_date)
            
            if not detection_results:
                logging.warning("未检测到跨日期航班")
                return False
            
            # detection_results现在是一个列表，不是字典
            total_candidates = sum(r.get('total_candidates', 0) for r in detection_results if r.get('success', False))
            logging.info(f"检测完成，共发现 {total_candidates} 个跨日期航班候选")
            
            return True
            
        except Exception as e:
            logging.error(f"跨日期航班检测失败: {e}")
            return False
    
    def run_stitching_phase(self, start_date: str = None, end_date: str = None) -> bool:
        """运行轨迹拼接阶段"""
        logging.info("=" * 60)
        logging.info("阶段 2: 轨迹拼接处理")
        logging.info("=" * 60)
        
        try:
            stitching_results = self.stitcher.run_stitching(start_date, end_date)
            
            if not stitching_results:
                logging.warning("轨迹拼接未产生结果")
                return False
            
            # 生成拼接报告
            from processing.utils import create_stitching_report
            report_path = os.path.join(
                self.config['data_paths']['reports_dir'], 
                "trajectory_stitching_report.yaml"
            )
            create_stitching_report(stitching_results, report_path)
            
            # stitching_results现在是列表类型，不是字典
            total_stitched = sum(result.get('flights_stitched', 0) for result in stitching_results)
            logging.info(f"拼接完成，共处理 {total_stitched} 个航班对")
            logging.info(f"详细报告: {report_path}")
            
            return True
            
        except Exception as e:
            logging.error(f"轨迹拼接失败: {e}")
            return False
    
    def run_validation_phase(self) -> bool:
        """运行结果验证阶段"""
        logging.info("=" * 60)
        logging.info("阶段 3: 结果验证")
        logging.info("=" * 60)
        
        try:
            validation_results = self.validator.run_validation()
            
            if 'error' in validation_results:
                logging.error(f"验证失败: {validation_results['error']}")
                return False
            
            # 输出验证摘要
            if 'overall_statistics' in validation_results:
                stats = validation_results['overall_statistics']
                logging.info("验证结果摘要:")
                logging.info(f"  - 处理航班总数: {stats.get('total_flights_processed', 0)}")
                logging.info(f"  - 平均时间间隔: {stats.get('average_time_gap_seconds', 0):.2f} 秒")
                logging.info(f"  - 平均空间跳跃: {stats.get('average_spatial_jump_km', 0):.2f} 公里")
                logging.info(f"  - 异常时间间隔: {stats.get('total_large_time_gaps', 0)}")
                logging.info(f"  - 异常空间跳跃: {stats.get('total_large_spatial_jumps', 0)}")
            
            return True
            
        except Exception as e:
            logging.error(f"结果验证失败: {e}")
            return False
    
    def run_pipeline(self, start_date: str = None, end_date: str = None, 
                    skip_detection: bool = False, skip_validation: bool = False) -> bool:
        """运行完整流水线"""
        pipeline_start_time = datetime.now()
        
        logging.info("=" * 80)
        logging.info("跨日期轨迹拼接流水线开始运行")
        logging.info(f"开始时间: {pipeline_start_time}")
        logging.info("=" * 80)
        
        # 检查前提条件
        if not self.check_prerequisites():
            logging.error("前提条件检查失败，流水线终止")
            return False
        
        success = True
        
        # 阶段1: 跨日期航班检测
        if not skip_detection:
            if not self.run_detection_phase(start_date, end_date):
                logging.error("跨日期航班检测阶段失败")
                success = False
        else:
            logging.info("跳过跨日期航班检测阶段")
        
        # 阶段2: 轨迹拼接
        if success:
            if not self.run_stitching_phase(start_date, end_date):
                logging.error("轨迹拼接阶段失败")
                success = False
        
        # 阶段3: 结果验证
        if success and not skip_validation:
            if not self.run_validation_phase():
                logging.error("结果验证阶段失败")
                success = False
        elif skip_validation:
            logging.info("跳过结果验证阶段")
        
        # 流水线完成
        pipeline_end_time = datetime.now()
        duration = pipeline_end_time - pipeline_start_time
        
        logging.info("=" * 80)
        if success:
            logging.info("跨日期轨迹拼接流水线成功完成")
        else:
            logging.error("跨日期轨迹拼接流水线执行失败")
        
        logging.info(f"结束时间: {pipeline_end_time}")
        logging.info(f"总耗时: {duration}")
        logging.info("=" * 80)
        
        return success

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='跨日期轨迹拼接流水线')
    
    parser.add_argument('--config', type=str, 
                       help='配置文件路径')
    parser.add_argument('--start-date', type=str,
                       help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str,
                       help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--skip-detection', action='store_true',
                       help='跳过跨日期航班检测阶段')
    parser.add_argument('--skip-validation', action='store_true',
                       help='跳过结果验证阶段')
    parser.add_argument('--detection-only', action='store_true',
                       help='仅运行跨日期航班检测')
    parser.add_argument('--stitching-only', action='store_true',
                       help='仅运行轨迹拼接')
    parser.add_argument('--validation-only', action='store_true',
                       help='仅运行结果验证')
    
    args = parser.parse_args()
    
    # 创建流水线
    try:
        pipeline = StitchingPipeline(args.config)
    except Exception as e:
        print(f"流水线初始化失败: {e}")
        return 1
    
    # 根据参数运行不同阶段
    success = False
    
    if args.detection_only:
        success = pipeline.run_detection_phase(args.start_date, args.end_date)
    elif args.stitching_only:
        success = pipeline.run_stitching_phase(args.start_date, args.end_date)
    elif args.validation_only:
        success = pipeline.run_validation_phase()
    else:
        success = pipeline.run_pipeline(
            start_date=args.start_date,
            end_date=args.end_date,
            skip_detection=args.skip_detection,
            skip_validation=args.skip_validation
        )
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())