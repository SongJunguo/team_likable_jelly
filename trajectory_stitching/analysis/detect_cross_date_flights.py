#!/usr/bin/env python3
"""
检测跨日期航班
Detect Cross-Date Flights
"""

import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple, Set
import os
import sys

# 添加处理模块路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'processing'))
from trajectory_stitching.processing.utils import load_config, setup_logging, get_consecutive_date_pairs, load_trajectory_data

class CrossDateFlightDetector:
    """跨日期航班检测器"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.data_dir = config['data_paths']['raw_trajectories']
        self.reports_dir = config['data_paths']['reports_dir']
        
    def run_detection(self, start_date: str = None, end_date: str = None) -> Dict:
        """运行跨日期航班检测"""
        logging.info("开始检测跨日期航班")
        
        # 获取连续日期文件对
        date_pairs = get_consecutive_date_pairs(self.data_dir, start_date, end_date)
        logging.info(f"找到 {len(date_pairs)} 对连续日期文件")
        
        # 检测每对日期的跨日期航班
        all_results = []
        for i, (date1_file, date2_file) in enumerate(date_pairs, 1):
            logging.info(f"处理第 {i}/{len(date_pairs)} 对文件")
            result = detect_cross_date_flights_for_date_pair(date1_file, date2_file, self.config)
            all_results.append(result)
            
            # 移除测试限制，处理所有文件
            # if i >= 5:  # 只处理前5对文件进行测试
            #     logging.info("测试模式：只处理前5对文件")
            #     break
        
        # 生成检测报告
        from utils import create_stitching_report
        os.makedirs(self.reports_dir, exist_ok=True)
        report_path = os.path.join(self.reports_dir, "cross_date_detection_report.yaml")
        create_stitching_report(all_results, report_path)
        
        # 统计总结
        successful_detections = [r for r in all_results if r.get('success', False)]
        total_cross_date_flights = sum(r.get('likely_cross_date_flights', 0) for r in successful_detections)
        
        logging.info("=" * 60)
        logging.info("跨日期航班检测完成")
        logging.info(f"处理文件对数: {len(date_pairs)}")
        logging.info(f"成功检测数: {len(successful_detections)}")
        logging.info(f"发现跨日期航班总数: {total_cross_date_flights}")
        logging.info(f"详细报告: {report_path}")
        
        return all_results

def extract_boundary_flights(df: pd.DataFrame, date: date, config: Dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """提取边界时间的航班数据"""
    detection_config = config.get('cross_date_detection', {})
    
    # 获取边界时间窗口
    hours_before = detection_config.get('boundary_hours_before_midnight', 2)
    hours_after = detection_config.get('boundary_hours_after_midnight', 2)
    
    # 计算边界时间 - 确保使用UTC时区
    import pytz
    utc = pytz.UTC
    
    # 为指定日期创建UTC午夜时间
    midnight = datetime.combine(date, datetime.min.time()).replace(tzinfo=utc)
    next_midnight = midnight + timedelta(days=1)
    
    # 晚间时间窗口：当天22:00-24:00
    evening_start = midnight + timedelta(hours=24-hours_before)  # 22:00 UTC 当天
    evening_end = next_midnight  # 24:00 UTC 当天（即次日00:00）
    
    # 凌晨时间窗口：当天00:00-02:00
    morning_start = midnight  # 00:00 UTC 当天
    morning_end = midnight + timedelta(hours=hours_after)  # 02:00 UTC 当天
    
    logging.info(f"边界时间窗口: 晚间 {evening_start} - {evening_end}, 凌晨 {morning_start} - {morning_end}")
    
    # 提取晚间航班（当天22:00-24:00 UTC）
    evening_flights = df[
        (df['timestamp'] >= evening_start) & 
        (df['timestamp'] < evening_end)
    ].copy()
    
    # 提取凌晨航班（当天00:00-02:00 UTC）
    morning_flights = df[
        (df['timestamp'] >= morning_start) & 
        (df['timestamp'] <= morning_end)
    ].copy()
    
    logging.info(f"日期 {date.strftime('%Y-%m-%d')}: 晚间航班 {len(evening_flights)} 条记录, 凌晨航班 {len(morning_flights)} 条记录")
    
    return evening_flights, morning_flights

def find_matching_flights(evening_df: pd.DataFrame, morning_df: pd.DataFrame, config: Dict) -> List[Dict]:
    """查找匹配的跨日期航班 - 基于位置和时间连续性"""
    from trajectory_stitching.processing.utils import calculate_distance
    
    detection_config = config.get('cross_date_detection', {})
    max_distance_km = detection_config.get('max_distance_km', 50)  # 最大距离阈值
    max_time_gap_minutes = detection_config.get('max_time_gap_minutes', 30)  # 最大时间间隔
    detection_mode = detection_config.get('detection_mode', 'both')  # 检测模式
    
    matches = []
    
    # 根据检测模式选择匹配策略
    if detection_mode == 'flight_id_only':
        # 仅使用flight_id匹配
        matching_identifiers = ['flight_id']
    elif detection_mode == 'icao24_only':
        # 仅使用icao24匹配
        matching_identifiers = ['icao24']
    else:  # detection_mode == 'both'
        # 使用配置中的匹配标识符优先级
        matching_identifiers = detection_config.get('matching_identifiers', ['flight_id', 'icao24'])
    
    # 基于标识符的匹配
    for identifier in matching_identifiers:
        if identifier not in evening_df.columns or identifier not in morning_df.columns:
            continue
        
        evening_ids = set(evening_df[identifier].dropna().unique())
        morning_ids = set(morning_df[identifier].dropna().unique())
        common_ids = evening_ids.intersection(morning_ids)
        
        if common_ids:
            logging.info(f"使用 {identifier} 找到 {len(common_ids)} 个直接匹配的跨日期航班")
            
            for flight_id in common_ids:
                evening_flight = evening_df[evening_df[identifier] == flight_id]
                morning_flight = morning_df[morning_df[identifier] == flight_id]
                
                match_info = create_match_info(evening_flight, morning_flight, identifier, flight_id)
                matches.append(match_info)
    
    # 如果没有直接匹配且检测模式允许，尝试基于位置和时间的匹配
    if not matches and detection_mode in ['icao24_only', 'both']:
        logging.info("未找到直接标识符匹配，尝试基于位置和时间连续性的匹配")
        
        # 获取每个晚间航班的最后位置和时间
        evening_endpoints = []
        for flight_id in evening_df['flight_id'].unique():
            flight_data = evening_df[evening_df['flight_id'] == flight_id]
            if len(flight_data) > 0:
                last_point = flight_data.iloc[-1]
                if not pd.isna(last_point['latitude']) and not pd.isna(last_point['longitude']):
                    evening_endpoints.append({
                        'flight_id': flight_id,
                        'icao24': last_point.get('icao24'),
                        'timestamp': last_point['timestamp'],
                        'latitude': last_point['latitude'],
                        'longitude': last_point['longitude'],
                        'altitude': last_point.get('altitude'),
                        'data': flight_data
                    })
        
        # 获取每个凌晨航班的第一位置和时间
        morning_startpoints = []
        for flight_id in morning_df['flight_id'].unique():
            flight_data = morning_df[morning_df['flight_id'] == flight_id]
            if len(flight_data) > 0:
                first_point = flight_data.iloc[0]
                if not pd.isna(first_point['latitude']) and not pd.isna(first_point['longitude']):
                    morning_startpoints.append({
                        'flight_id': flight_id,
                        'icao24': first_point.get('icao24'),
                        'timestamp': first_point['timestamp'],
                        'latitude': first_point['latitude'],
                        'longitude': first_point['longitude'],
                        'altitude': first_point.get('altitude'),
                        'data': flight_data
                    })
        
        logging.info(f"分析 {len(evening_endpoints)} 个晚间航班终点和 {len(morning_startpoints)} 个凌晨航班起点")
        
        # 寻找位置和时间连续的航班对
        for evening_end in evening_endpoints:
            for morning_start in morning_startpoints:
                # 计算时间间隔
                time_gap = (morning_start['timestamp'] - evening_end['timestamp']).total_seconds() / 60
                
                # 时间间隔检查
                if time_gap < 0 or time_gap > max_time_gap_minutes:
                    continue
                
                # 计算距离
                distance = calculate_distance(
                    evening_end['latitude'], evening_end['longitude'],
                    morning_start['latitude'], morning_start['longitude']
                )
                
                # 距离检查
                if distance > max_distance_km:
                    continue
                
                # 如果有icao24信息，优先匹配相同的icao24
                icao24_match = (evening_end.get('icao24') == morning_start.get('icao24') 
                               and evening_end.get('icao24') is not None)
                
                match_info = {
                    'identifier_type': 'position_time_based',
                    'identifier_value': f"{evening_end['flight_id']}->{morning_start['flight_id']}",
                    'evening_flight_id': evening_end['flight_id'],
                    'morning_flight_id': morning_start['flight_id'],
                    'evening_icao24': evening_end.get('icao24'),
                    'morning_icao24': morning_start.get('icao24'),
                    'icao24_match': icao24_match,
                    'evening_records': len(evening_end['data']),
                    'morning_records': len(morning_start['data']),
                    'time_gap_minutes': time_gap,
                    'distance_km': distance,
                    'evening_time_range': {
                        'start': evening_end['data']['timestamp'].min(),
                        'end': evening_end['data']['timestamp'].max()
                    },
                    'morning_time_range': {
                        'start': morning_start['data']['timestamp'].min(),
                        'end': morning_start['data']['timestamp'].max()
                    },
                    'position_info': {
                        'evening_last_position': {
                            'lat': evening_end['latitude'],
                            'lon': evening_end['longitude'],
                            'alt': evening_end.get('altitude')
                        },
                        'morning_first_position': {
                            'lat': morning_start['latitude'],
                            'lon': morning_start['longitude'],
                            'alt': morning_start.get('altitude')
                        }
                    }
                }
                
                matches.append(match_info)
        
        logging.info(f"基于位置和时间连续性找到 {len(matches)} 个潜在跨日期航班")
    
    return matches

def create_match_info(evening_flight: pd.DataFrame, morning_flight: pd.DataFrame, 
                     identifier: str, flight_id) -> Dict:
    """创建匹配信息"""
    match_info = {
        'identifier_type': identifier,
        'identifier_value': flight_id,
        'evening_records': len(evening_flight),
        'morning_records': len(morning_flight),
        'evening_time_range': {
            'start': evening_flight['timestamp'].min(),
            'end': evening_flight['timestamp'].max()
        },
        'morning_time_range': {
            'start': morning_flight['timestamp'].min(),
            'end': morning_flight['timestamp'].max()
        }
    }
    
    # 计算时间间隔
    time_gap = (morning_flight['timestamp'].min() - evening_flight['timestamp'].max()).total_seconds() / 60
    match_info['time_gap_minutes'] = time_gap
    
    # 添加位置信息（如果可用）
    if all(col in evening_flight.columns for col in ['latitude', 'longitude']):
        evening_last = evening_flight.iloc[-1]
        morning_first = morning_flight.iloc[0]
        
        match_info['position_info'] = {
            'evening_last_position': {
                'lat': evening_last['latitude'],
                'lon': evening_last['longitude'],
                'alt': evening_last.get('altitude', None)
            },
            'morning_first_position': {
                'lat': morning_first['latitude'],
                'lon': morning_first['longitude'],
                'alt': morning_first.get('altitude', None)
            }
        }
    
    return match_info

def analyze_cross_date_candidates(matches: List[Dict], config: Dict) -> List[Dict]:
    """分析跨日期候选航班的可信度"""
    from trajectory_stitching.processing.utils import calculate_distance, validate_trajectory_continuity
    
    validation_config = config.get('continuity_validation', {})
    analyzed_matches = []
    
    for match in matches:
        analysis = match.copy()
        
        # 时间连续性评分
        time_gap = match['time_gap_minutes']
        max_time_gap = validation_config.get('max_time_gap_minutes', 30)
        time_score = max(0, 1 - time_gap / max_time_gap) if time_gap >= 0 else 0
        
        # 位置连续性评分
        position_score = 0
        if 'position_info' in match:
            pos_info = match['position_info']
            distance = calculate_distance(
                pos_info['evening_last_position']['lat'],
                pos_info['evening_last_position']['lon'],
                pos_info['morning_first_position']['lat'],
                pos_info['morning_first_position']['lon']
            )
            
            max_distance = validation_config.get('max_distance_km', 100)
            position_score = max(0, 1 - distance / max_distance)
            analysis['distance_km'] = distance
        
        # 综合可信度评分
        confidence_score = (time_score + position_score) / 2
        
        analysis.update({
            'time_score': time_score,
            'position_score': position_score,
            'confidence_score': confidence_score,
            'is_likely_cross_date': confidence_score > 0.7  # 阈值可配置
        })
        
        analyzed_matches.append(analysis)
    
    return analyzed_matches

def detect_cross_date_flights_for_date_pair(date1_file: str, date2_file: str, config: Dict) -> Dict:
    """检测一对连续日期文件中的跨日期航班"""
    try:
        # 获取日期信息
        from trajectory_stitching.processing.utils import get_date_from_filename
        date1 = get_date_from_filename(os.path.basename(date1_file))
        date2 = get_date_from_filename(os.path.basename(date2_file))
        
        logging.info(f"检测跨日期航班: {date1.strftime('%Y-%m-%d')} -> {date2.strftime('%Y-%m-%d')}")
        
        # 加载数据
        df1 = load_trajectory_data(date1_file)
        df2 = load_trajectory_data(date2_file)
        
        # 提取边界航班
        # 从第一天数据中提取晚间航班（第一天22:00-24:00）
        evening_flights, _ = extract_boundary_flights(df1, date1, config)
        # 从第一天数据中提取跨越到第二天的凌晨航班（第二天00:00-02:00）
        _, morning_flights_from_day1 = extract_boundary_flights(df1, date2, config)
        # 从第二天数据中提取凌晨航班（第二天00:00-02:00）
        _, morning_flights_from_day2 = extract_boundary_flights(df2, date2, config)
        
        # 合并两个数据源的凌晨航班
        morning_flights = pd.concat([morning_flights_from_day1, morning_flights_from_day2], ignore_index=True)
        
        # 查找匹配航班
        matches = find_matching_flights(evening_flights, morning_flights, config)
        
        # 分析候选航班
        analyzed_matches = analyze_cross_date_candidates(matches, config)
        
        # 筛选高可信度的跨日期航班
        likely_cross_date = [m for m in analyzed_matches if m['is_likely_cross_date']]
        
        result = {
            'date_pair': f"{date1.strftime('%Y-%m-%d')} -> {date2.strftime('%Y-%m-%d')}",
            'date1_file': date1_file,
            'date2_file': date2_file,
            'total_candidates': len(matches),
            'likely_cross_date_flights': len(likely_cross_date),
            'matches': analyzed_matches,
            'success': True
        }
        
        logging.info(f"检测完成: 发现 {len(likely_cross_date)} 个可能的跨日期航班")
        return result
        
    except Exception as e:
        logging.error(f"检测跨日期航班失败 {date1_file} -> {date2_file}: {e}")
        return {
            'date_pair': f"{os.path.basename(date1_file)} -> {os.path.basename(date2_file)}",
            'error': str(e),
            'success': False
        }

def main():
    """主函数"""
    # 加载配置
    config = load_config()
    setup_logging(config)
    
    logging.info("开始检测跨日期航班")
    
    # 获取数据路径
    data_dir = config['data_paths']['raw_trajectories']
    reports_dir = config['data_paths']['reports_dir']
    
    # 获取连续日期文件对
    date_pairs = get_consecutive_date_pairs(data_dir)
    logging.info(f"找到 {len(date_pairs)} 对连续日期文件")
    
    # 检测每对日期的跨日期航班
    all_results = []
    for i, (date1_file, date2_file) in enumerate(date_pairs, 1):
        logging.info(f"处理第 {i}/{len(date_pairs)} 对文件")
        result = detect_cross_date_flights_for_date_pair(date1_file, date2_file, config)
        all_results.append(result)
        
        # 移除测试限制，处理所有文件
        # if i >= 5:  # 只处理前5对文件进行测试
        #     logging.info("测试模式：只处理前5对文件")
        #     break
    
    # 生成检测报告
    from utils import create_stitching_report
    report_path = os.path.join(reports_dir, "cross_date_detection_report.yaml")
    create_stitching_report(all_results, report_path)
    
    # 统计总结
    successful_detections = [r for r in all_results if r.get('success', False)]
    total_cross_date_flights = sum(r.get('likely_cross_date_flights', 0) for r in successful_detections)
    
    logging.info("=" * 60)
    logging.info("跨日期航班检测完成")
    logging.info(f"处理文件对数: {len(date_pairs)}")
    logging.info(f"成功检测数: {len(successful_detections)}")
    logging.info(f"发现跨日期航班总数: {total_cross_date_flights}")
    logging.info(f"详细报告: {report_path}")

if __name__ == "__main__":
    main()