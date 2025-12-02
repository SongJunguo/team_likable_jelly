#!/usr/bin/env python3
"""
测试不同检测模式的跨日期航班检测效果
"""

import sys
import os
sys.path.append('..')

from processing.utils import load_config
from analysis.detect_cross_date_flights import detect_cross_date_flights_for_date_pair
import yaml
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_detection_modes():
    """测试不同检测模式的效果"""
    
    # 加载基础配置
    config = load_config('config/stitching_config.yaml')
    
    # 测试数据路径
    data_dir = config['data_paths']['raw_trajectories']
    
    # 测试日期对
    test_dates = [
        ('2022-01-05', '2022-01-06'),
        ('2022-01-06', '2022-01-07'),
        ('2022-01-07', '2022-01-08')
    ]
    
    # 测试不同的检测模式
    detection_modes = ['flight_id_only', 'icao24_only', 'both']
    
    results = {}
    
    for mode in detection_modes:
        print(f"\n{'='*60}")
        print(f"测试检测模式: {mode}")
        print(f"{'='*60}")
        
        # 修改配置中的检测模式
        test_config = config.copy()
        test_config['cross_date_detection']['detection_mode'] = mode
        
        mode_results = []
        total_flights = 0
        
        for date1, date2 in test_dates:
            print(f"\n--- 检测日期对: {date1} -> {date2} ---")
            
            file1 = os.path.join(data_dir, f"{date1}.parquet")
            file2 = os.path.join(data_dir, f"{date2}.parquet")
            
            if not os.path.exists(file1) or not os.path.exists(file2):
                print(f"跳过: 文件不存在")
                continue
            
            try:
                result = detect_cross_date_flights_for_date_pair(
                    file1, file2, test_config
                )
                
                # 从结果中获取跨日期航班列表
                if result.get('success', False):
                    cross_date_flights = result.get('matches', [])
                    flight_count = len(cross_date_flights)
                else:
                    cross_date_flights = []
                    flight_count = 0
                
                total_flights += flight_count
                mode_results.append((date1, date2, flight_count))
                
                print(f"发现跨日期航班: {flight_count} 个")
                
                # 显示前几个匹配的详细信息
                if flight_count > 0:
                    print("匹配详情:")
                    for i, flight in enumerate(cross_date_flights[:3]):  # 只显示前3个
                        identifier_type = flight.get('identifier_type', 'unknown')
                        identifier_value = flight.get('identifier_value', 'unknown')
                        time_gap = flight.get('time_gap_minutes', 0)
                        
                        print(f"  {i+1}. {identifier_type}: {identifier_value}")
                        print(f"     时间间隔: {time_gap:.1f}分钟")
                        
                        # 如果有位置信息，计算距离
                        if 'position_info' in flight:
                            pos_info = flight['position_info']
                            evening_pos = pos_info.get('evening_last_position', {})
                            morning_pos = pos_info.get('morning_first_position', {})
                            
                            if all(k in evening_pos for k in ['lat', 'lon']) and all(k in morning_pos for k in ['lat', 'lon']):
                                # 简单距离计算（这里可以用更精确的方法）
                                import math
                                lat1, lon1 = evening_pos['lat'], evening_pos['lon']
                                lat2, lon2 = morning_pos['lat'], morning_pos['lon']
                                
                                # 简化的距离计算
                                distance = math.sqrt((lat2-lat1)**2 + (lon2-lon1)**2) * 111  # 大约转换为公里
                                print(f"     距离: {distance:.1f}公里")
                            else:
                                print(f"     距离: 位置信息不完整")
                
            except Exception as e:
                print(f"检测失败: {e}")
                mode_results.append((date1, date2, 0))
        
        results[mode] = {
            'details': mode_results,
            'total': total_flights
        }
        
        print(f"\n{mode} 模式总计: {total_flights} 个跨日期航班")
    
    # 汇总比较结果
    print(f"\n{'='*60}")
    print("检测模式比较汇总")
    print(f"{'='*60}")
    
    for mode in detection_modes:
        total = results[mode]['total']
        print(f"{mode:15}: {total:4d} 个跨日期航班")
    
    # 详细对比
    print(f"\n详细对比:")
    print(f"{'日期对':<20} {'flight_id_only':<15} {'icao24_only':<15} {'both':<15}")
    print("-" * 70)
    
    for i, (date1, date2) in enumerate(test_dates):
        if i < len(results['flight_id_only']['details']):
            flight_id_count = results['flight_id_only']['details'][i][2]
            icao24_count = results['icao24_only']['details'][i][2]
            both_count = results['both']['details'][i][2]
            
            date_pair = f"{date1}->{date2}"
            print(f"{date_pair:<20} {flight_id_count:<15} {icao24_count:<15} {both_count:<15}")
    
    # 分析结论
    print(f"\n{'='*60}")
    print("分析结论")
    print(f"{'='*60}")
    
    flight_id_total = results['flight_id_only']['total']
    icao24_total = results['icao24_only']['total']
    both_total = results['both']['total']
    
    if flight_id_total == 0:
        print("✗ flight_id_only模式: 无法找到跨日期航班")
        print("  原因: 每个日期文件的flight_id都是独立的，没有重叠")
    else:
        print(f"✓ flight_id_only模式: 找到 {flight_id_total} 个跨日期航班")
    
    if icao24_total > 0:
        print(f"✓ icao24_only模式: 找到 {icao24_total} 个跨日期航班")
        print("  优势: 基于飞机标识符，能够跨文件匹配同一架飞机")
    else:
        print("✗ icao24_only模式: 无法找到跨日期航班")
    
    if both_total >= max(flight_id_total, icao24_total):
        print(f"✓ both模式: 找到 {both_total} 个跨日期航班")
        print("  优势: 结合两种方法，覆盖面最广")
    
    # 推荐配置
    print(f"\n推荐配置:")
    if icao24_total > flight_id_total:
        print("建议使用 'icao24_only' 模式")
        print("原因: 数据中flight_id在不同日期文件间不重叠，icao24更适合跨日期检测")
    elif flight_id_total > 0:
        print("建议使用 'both' 模式")
        print("原因: 两种方法都有效，结合使用效果更好")
    else:
        print("建议使用 'icao24_only' 模式")
        print("原因: flight_id无法跨日期匹配，只能依赖icao24")

if __name__ == "__main__":
    test_detection_modes()