#!/usr/bin/env python3
"""
插值质量验证脚本
验证插值后的数据是否真的没有任何缺失值
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
import multiprocessing as mp
from functools import partial
import traceback
from datetime import datetime

def validate_single_file(file_path):
    """验证单个插值文件的质量"""
    try:
        # 读取数据
        df = pd.read_parquet(file_path)
        
        if df.empty:
            return {
                'file': os.path.basename(file_path),
                'total_points': 0,
                'trajectories': 0,
                'missing_values': {},
                'has_missing': False,
                'error': None
            }
        
        # 检查必需列
        required_columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
        missing_values = {}
        total_missing = 0
        
        for col in required_columns:
            if col in df.columns:
                missing_count = df[col].isna().sum()
                missing_values[col] = missing_count
                total_missing += missing_count
            else:
                missing_values[col] = f"列不存在"
        
        # 统计轨迹数量
        trajectories = df['flight_id'].nunique() if 'flight_id' in df.columns else 0
        
        return {
            'file': os.path.basename(file_path),
            'total_points': len(df),
            'trajectories': trajectories,
            'missing_values': missing_values,
            'has_missing': total_missing > 0,
            'total_missing': total_missing,
            'error': None
        }
        
    except Exception as e:
        return {
            'file': os.path.basename(file_path),
            'total_points': 0,
            'trajectories': 0,
            'missing_values': {},
            'has_missing': False,
            'error': str(e)
        }

def main():
    """主函数"""
    print("🔍 开始验证插值质量")
    print("=" * 60)
    
    # 插值数据目录
    interpolated_dir = "interpolated_trajectories"
    
    if not os.path.exists(interpolated_dir):
        print(f"❌ 插值数据目录不存在: {interpolated_dir}")
        return
    
    # 获取所有插值文件
    interpolated_files = [f for f in os.listdir(interpolated_dir) if f.endswith('.parquet')]
    interpolated_files.sort()
    
    print(f"找到 {len(interpolated_files)} 个插值文件")
    
    if not interpolated_files:
        print("❌ 没有找到插值文件")
        return
    
    # 多进程验证
    print("🔄 开始多进程验证...")
    num_processes = min(mp.cpu_count(), 16)
    print(f"使用 {num_processes} 个进程")
    
    # 准备文件路径
    file_paths = [os.path.join(interpolated_dir, f) for f in interpolated_files]
    
    # 执行多进程验证
    with mp.Pool(processes=num_processes) as pool:
        results = pool.map(validate_single_file, file_paths)
    
    # 分析结果
    print("\n📊 验证结果统计:")
    print("=" * 60)
    
    total_stats = {
        'total_files': len(results),
        'valid_files': 0,
        'error_files': 0,
        'files_with_missing': 0,
        'total_points': 0,
        'total_trajectories': 0,
        'total_missing_values': 0,
        'missing_by_column': {}
    }
    
    files_with_missing = []
    error_files = []
    
    # 初始化列统计
    required_columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    for col in required_columns:
        total_stats['missing_by_column'][col] = 0
    
    for result in results:
        if result['error']:
            total_stats['error_files'] += 1
            error_files.append((result['file'], result['error']))
        else:
            total_stats['valid_files'] += 1
            total_stats['total_points'] += result['total_points']
            total_stats['total_trajectories'] += result['trajectories']
            
            if result['has_missing']:
                total_stats['files_with_missing'] += 1
                files_with_missing.append(result)
                total_stats['total_missing_values'] += result.get('total_missing', 0)
                
                # 按列统计缺失值
                for col, missing_count in result['missing_values'].items():
                    if isinstance(missing_count, int):
                        total_stats['missing_by_column'][col] += missing_count
    
    # 输出统计结果
    print(f"总文件数: {total_stats['total_files']}")
    print(f"有效文件数: {total_stats['valid_files']}")
    print(f"错误文件数: {total_stats['error_files']}")
    print(f"有缺失值的文件数: {total_stats['files_with_missing']}")
    print(f"总数据点数: {total_stats['total_points']:,}")
    print(f"总轨迹数: {total_stats['total_trajectories']:,}")
    print(f"总缺失值数: {total_stats['total_missing_values']:,}")
    
    # 按列显示缺失值统计
    print("\n📋 各列缺失值统计:")
    for col in required_columns:
        missing_count = total_stats['missing_by_column'][col]
        if total_stats['total_points'] > 0:
            missing_rate = missing_count / total_stats['total_points'] * 100
            print(f"  {col.upper()}: {missing_count:,} ({missing_rate:.4f}%)")
        else:
            print(f"  {col.upper()}: {missing_count:,}")
    
    # 显示有缺失值的文件详情
    if files_with_missing:
        print(f"\n⚠️  有缺失值的文件详情 (共{len(files_with_missing)}个):")
        for result in files_with_missing[:10]:  # 只显示前10个
            print(f"  📁 {result['file']}:")
            print(f"     数据点: {result['total_points']:,}, 轨迹数: {result['trajectories']}")
            for col, missing_count in result['missing_values'].items():
                if isinstance(missing_count, int) and missing_count > 0:
                    missing_rate = missing_count / result['total_points'] * 100
                    print(f"     {col}: {missing_count:,} ({missing_rate:.2f}%)")
        
        if len(files_with_missing) > 10:
            print(f"     ... 还有 {len(files_with_missing) - 10} 个文件有缺失值")
    
    # 显示错误文件
    if error_files:
        print(f"\n❌ 错误文件详情 (共{len(error_files)}个):")
        for file_name, error in error_files[:5]:  # 只显示前5个
            print(f"  📁 {file_name}: {error}")
        
        if len(error_files) > 5:
            print(f"     ... 还有 {len(error_files) - 5} 个错误文件")
    
    # 生成验证报告
    report_file = f"interpolation_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("插值质量验证报告\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"验证文件数: {len(interpolated_files)}\n\n")
        
        f.write("验证结果:\n")
        f.write(f"  总文件数: {total_stats['total_files']}\n")
        f.write(f"  有效文件数: {total_stats['valid_files']}\n")
        f.write(f"  错误文件数: {total_stats['error_files']}\n")
        f.write(f"  有缺失值的文件数: {total_stats['files_with_missing']}\n")
        f.write(f"  总数据点数: {total_stats['total_points']:,}\n")
        f.write(f"  总轨迹数: {total_stats['total_trajectories']:,}\n")
        f.write(f"  总缺失值数: {total_stats['total_missing_values']:,}\n\n")
        
        f.write("各列缺失值统计:\n")
        for col in required_columns:
            missing_count = total_stats['missing_by_column'][col]
            if total_stats['total_points'] > 0:
                missing_rate = missing_count / total_stats['total_points'] * 100
                f.write(f"  {col.upper()}: {missing_count:,} ({missing_rate:.4f}%)\n")
            else:
                f.write(f"  {col.upper()}: {missing_count:,}\n")
        
        if files_with_missing:
            f.write(f"\n有缺失值的文件列表:\n")
            for result in files_with_missing:
                f.write(f"  {result['file']}: {result.get('total_missing', 0)} 个缺失值\n")
        
        if error_files:
            f.write(f"\n错误文件列表:\n")
            for file_name, error in error_files:
                f.write(f"  {file_name}: {error}\n")
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    
    # 最终结论
    if total_stats['total_missing_values'] == 0 and total_stats['error_files'] == 0:
        print("✅ 插值质量验证通过！所有数据都没有缺失值。")
    elif total_stats['total_missing_values'] == 0:
        print(f"⚠️  插值数据没有缺失值，但有 {total_stats['error_files']} 个文件处理出错。")
    else:
        print(f"❌ 插值质量验证失败！仍有 {total_stats['total_missing_values']:,} 个缺失值。")

if __name__ == "__main__":
    main()