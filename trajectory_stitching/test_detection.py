#!/usr/bin/env python3
"""
测试跨日期航班检测逻辑
"""

import sys
import os
sys.path.append('..')  # 添加父目录到路径

from analysis.detect_cross_date_flights import detect_cross_date_flights_for_date_pair
from processing.utils import load_config, setup_logging, get_consecutive_date_pairs
import yaml

def test_detection():
    """测试跨日期检测"""
    config = load_config()
    setup_logging(config)
    
    # 只测试前5对文件
    data_dir = config['data_paths']['raw_trajectories']
    date_pairs = get_consecutive_date_pairs(data_dir)[:5]
    print(f'测试处理 {len(date_pairs)} 对文件')
    
    total_cross_date = 0
    for i, (date1_file, date2_file) in enumerate(date_pairs, 1):
        print(f'\n处理第 {i} 对文件:')
        print(f'  文件1: {os.path.basename(date1_file)}')
        print(f'  文件2: {os.path.basename(date2_file)}')
        
        result = detect_cross_date_flights_for_date_pair(date1_file, date2_file, config)
        
        if result.get('success', False):
            cross_date_count = result.get('likely_cross_date_flights', 0)
            total_candidates = result.get('total_candidates', 0)
            print(f'  候选航班: {total_candidates}')
            print(f'  跨日期航班: {cross_date_count}')
            total_cross_date += cross_date_count
        else:
            print(f'  处理失败: {result.get("error", "未知错误")}')
    
    print(f'\n总计发现跨日期航班: {total_cross_date}')

if __name__ == "__main__":
    test_detection()