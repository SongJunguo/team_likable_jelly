#!/usr/bin/env python3
"""
检查trajectory_analysis.parquet中缺失率数据的实际值
"""

import pandas as pd
import numpy as np

def check_missing_rate_data():
    # 读取最新的数据
    file_path = './junguo_analysis_for_opensky2022/analysis_for_interpolation/full_365_analysis_output_v2/trajectory_analysis.parquet'
    print(f"读取文件: {file_path}")
    
    df = pd.read_parquet(file_path)
    print(f"数据形状: {df.shape}")
    
    # 检查缺失率列的实际值
    missing_rate_cols = [col for col in df.columns if col.endswith('_missing_rate')]
    print(f'\n缺失率列: {missing_rate_cols}')
    
    # 查看前几行的实际值
    print('\n前5行缺失率数据:')
    for col in missing_rate_cols[:3]:  # 只看前3个列
        values = df[col].head().tolist()
        print(f'{col}: {values}')
    
    # 查看统计信息
    print('\n缺失率原始统计（不乘100）:')
    for col in missing_rate_cols[:3]:
        print(f'{col}:')
        print(f'  平均: {df[col].mean():.4f}')
        print(f'  最大: {df[col].max():.4f}')
        print(f'  最小: {df[col].min():.4f}')
    
    # 检查是否已经是百分比形式
    print('\n检查数据范围:')
    for col in missing_rate_cols[:3]:
        min_val = df[col].min()
        max_val = df[col].max()
        print(f'{col}: 范围 [{min_val:.4f}, {max_val:.4f}]')
        
        # 判断是否可能已经是百分比
        if max_val > 1.0:
            print(f'  -> 可能已经是百分比形式（最大值 > 1.0）')
        else:
            print(f'  -> 可能是小数形式（最大值 <= 1.0）')
    
    # 特别检查一些异常高的值
    print('\n检查异常高的缺失率:')
    for col in missing_rate_cols[:3]:
        high_values = df[df[col] > 10][col]  # 大于10的值
        if len(high_values) > 0:
            print(f'{col}: 有 {len(high_values)} 个值 > 10')
            print(f'  最高的5个值: {high_values.nlargest(5).tolist()}')

if __name__ == "__main__":
    check_missing_rate_data()