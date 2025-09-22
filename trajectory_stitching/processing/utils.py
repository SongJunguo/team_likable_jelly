#!/usr/bin/env python3
"""
轨迹拼接工具函数模块
Trajectory Stitching Utility Functions
"""

import pandas as pd
import numpy as np
import yaml
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
import os

def load_config(config_path: str = "trajectory_stitching/config/stitching_config.yaml") -> Dict:
    """加载配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        logging.error(f"加载配置文件失败: {e}")
        raise

def setup_logging(config: Dict) -> None:
    """设置日志配置"""
    log_config = config.get('logging', {})
    
    # 创建日志目录
    log_file = log_config.get('log_file', 'trajectory_stitching.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # 配置日志
    logging.basicConfig(
        level=getattr(logging, log_config.get('level', 'INFO')),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler() if log_config.get('console_output', True) else logging.NullHandler()
        ]
    )

def get_date_from_filename(filename: str) -> date:
    """从文件名提取日期"""
    try:
        # 假设文件名格式为 YYYY-MM-DD.parquet
        date_str = Path(filename).stem
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError as e:
        logging.error(f"无法从文件名 {filename} 提取日期: {e}")
        raise

def get_consecutive_date_pairs(data_dir: str, start_date: str = None, end_date: str = None) -> List[Tuple[str, str]]:
    """获取连续日期的文件对"""
    files = sorted([f for f in os.listdir(data_dir) if f.endswith('.parquet')])
    
    # 如果指定了日期范围，进行过滤
    if start_date or end_date:
        filtered_files = []
        for f in files:
            try:
                file_date = get_date_from_filename(f)
                if start_date and file_date < datetime.strptime(start_date, '%Y-%m-%d').date():
                    continue
                if end_date and file_date > datetime.strptime(end_date, '%Y-%m-%d').date():
                    continue
                filtered_files.append(f)
            except:
                continue
        files = filtered_files
    
    date_pairs = []
    
    for i in range(len(files) - 1):
        current_file = files[i]
        next_file = files[i + 1]
        
        current_date = get_date_from_filename(current_file)
        next_date = get_date_from_filename(next_file)
        
        # 检查是否为连续日期
        if (next_date - current_date).days == 1:
            current_path = os.path.join(data_dir, current_file)
            next_path = os.path.join(data_dir, next_file)
            date_pairs.append((current_path, next_path))
    
    return date_pairs

def load_trajectory_data(file_path: str, time_filter: Optional[Dict] = None) -> pd.DataFrame:
    """加载轨迹数据，可选时间过滤"""
    try:
        df = pd.read_parquet(file_path)
        
        # 确保timestamp列为datetime类型
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 应用时间过滤
        if time_filter:
            start_time = time_filter.get('start_time')
            end_time = time_filter.get('end_time')
            
            if start_time:
                df = df[df['timestamp'] >= start_time]
            if end_time:
                df = df[df['timestamp'] <= end_time]
        
        logging.info(f"加载数据文件 {file_path}: {len(df)} 条记录")
        return df
        
    except Exception as e:
        logging.error(f"加载数据文件 {file_path} 失败: {e}")
        raise

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """计算两点间的大圆距离（公里）"""
    from math import radians, sin, cos, sqrt, atan2
    
    # 转换为弧度
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    
    # Haversine公式
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    # 地球半径（公里）
    R = 6371.0
    distance = R * c
    
    return distance

def create_stitching_report(results: List[Dict], report_path: str) -> None:
    """创建拼接报告"""
    try:
        # 确保报告目录存在
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        
        # 生成报告数据
        report_data = {
            'timestamp': datetime.now().isoformat(),
            'summary': {
                'total_processed': len(results),
                'successful': len([r for r in results if r.get('success', False)]),
                'failed': len([r for r in results if not r.get('success', False)]),
                'total_cross_date_flights': sum(r.get('likely_cross_date_flights', 0) for r in results if r.get('success', False))
            },
            'details': results
        }
        
        # 写入YAML文件
        with open(report_path, 'w', encoding='utf-8') as f:
            yaml.dump(report_data, f, default_flow_style=False, allow_unicode=True)
        
        logging.info(f"报告已生成: {report_path}")
        
    except Exception as e:
        logging.error(f"生成报告失败: {e}")
        raise

def validate_trajectory_continuity(df1: pd.DataFrame, df2: pd.DataFrame, 
                                 flight_id: Union[str, int], config: Dict) -> Dict:
    """验证两个轨迹段的连续性"""
    validation_config = config.get('continuity_validation', {})
    
    # 获取第一段的最后一个点和第二段的第一个点
    last_point = df1[df1['flight_id'] == flight_id].iloc[-1]
    first_point = df2[df2['flight_id'] == flight_id].iloc[0]
    
    result = {
        'flight_id': flight_id,
        'time_continuous': False,
        'position_continuous': False,
        'parameters_continuous': False,
        'overall_continuous': False
    }
    
    # 时间连续性检查
    time_gap = (first_point['timestamp'] - last_point['timestamp']).total_seconds() / 60
    max_time_gap = validation_config.get('max_time_gap_minutes', 30)
    result['time_gap_minutes'] = time_gap
    result['time_continuous'] = time_gap <= max_time_gap
    
    # 位置连续性检查
    if all(col in last_point.index for col in ['latitude', 'longitude']):
        distance = calculate_distance(
            last_point['latitude'], last_point['longitude'],
            first_point['latitude'], first_point['longitude']
        )
        max_distance = validation_config.get('max_distance_km', 100)
        result['distance_km'] = distance
        result['position_continuous'] = distance <= max_distance
    
    # 飞行参数连续性检查
    param_checks = []
    
    # 高度检查
    if 'altitude' in last_point.index:
        alt_change = abs(first_point['altitude'] - last_point['altitude'])
        max_alt_change = validation_config.get('max_altitude_change_ft', 5000)
        param_checks.append(alt_change <= max_alt_change)
        result['altitude_change_ft'] = alt_change
    
    # 速度检查
    if 'groundspeed' in last_point.index:
        speed_change = abs(first_point['groundspeed'] - last_point['groundspeed'])
        max_speed_change = validation_config.get('max_speed_change_kts', 100)
        param_checks.append(speed_change <= max_speed_change)
        result['speed_change_kts'] = speed_change
    
    result['parameters_continuous'] = all(param_checks) if param_checks else True
    
    # 总体连续性判断
    result['overall_continuous'] = (
        result['time_continuous'] and 
        result['position_continuous'] and 
        result['parameters_continuous']
    )
    
    return result

def generate_new_flight_id(existing_ids: List[Union[str, int]], strategy: str = "max_plus_increment") -> Union[str, int]:
    """生成新的flight_id"""
    if strategy == "max_plus_increment":
        if not existing_ids:
            return 1
        
        # 尝试转换为数字
        numeric_ids = []
        for fid in existing_ids:
            try:
                numeric_ids.append(int(fid))
            except (ValueError, TypeError):
                continue
        
        if numeric_ids:
            return max(numeric_ids) + 1
        else:
            # 如果都不是数字，使用字符串策略
            return f"stitched_{len(existing_ids) + 1}"
    
    return f"stitched_{len(existing_ids) + 1}"

def save_stitched_trajectory(df: pd.DataFrame, output_path: str) -> None:
    """保存拼接后的轨迹数据"""
    try:
        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        # 保存为parquet格式
        df.to_parquet(output_path, index=False)
        logging.info(f"保存拼接轨迹到 {output_path}: {len(df)} 条记录")
        
    except Exception as e:
        logging.error(f"保存拼接轨迹失败 {output_path}: {e}")
        raise

def create_stitching_report(results: List[Dict], output_path: str) -> None:
    """创建拼接处理报告"""
    try:
        report = {
            'processing_time': datetime.now().isoformat(),
            'total_date_pairs_processed': len(results),
            'successful_stitches': sum(1 for r in results if r.get('success', False)),
            'failed_stitches': sum(1 for r in results if not r.get('success', False)),
            'total_flights_stitched': sum(r.get('flights_stitched', 0) for r in results),
            'details': results
        }
        
        # 保存为YAML格式
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(report, f, default_flow_style=False, allow_unicode=True)
        
        logging.info(f"生成拼接报告: {output_path}")
        
    except Exception as e:
        logging.error(f"生成拼接报告失败: {e}")
        raise

def validate_data_quality(df: pd.DataFrame, config: Dict) -> Dict:
    """验证数据质量"""
    quality_config = config.get('quality_control', {})
    outlier_config = quality_config.get('outlier_detection', {})
    
    quality_report = {
        'total_records': len(df),
        'unique_flights': df['flight_id'].nunique() if 'flight_id' in df.columns else 0,
        'time_range': {
            'start': df['timestamp'].min().isoformat() if 'timestamp' in df.columns else None,
            'end': df['timestamp'].max().isoformat() if 'timestamp' in df.columns else None
        },
        'outliers': {}
    }
    
    # 检查异常值
    for column, (min_val, max_val) in outlier_config.items():
        if column in df.columns:
            outliers = df[(df[column] < min_val) | (df[column] > max_val)]
            quality_report['outliers'][column] = {
                'count': len(outliers),
                'percentage': len(outliers) / len(df) * 100 if len(df) > 0 else 0
            }
    
    return quality_report