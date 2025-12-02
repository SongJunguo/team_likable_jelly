#!/usr/bin/env python3
"""
全面的缺失率分析：准确统计所有列（包括速度、航向角等）的缺失率
"""

import pandas as pd
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
from pathlib import Path

def analyze_file_missing_rates(file_path):
    """分析单个文件中所有列的缺失率"""
    try:
        df = pd.read_parquet(file_path)
        
        # 获取所有数值列
        all_columns = df.columns.tolist()
        
        # 统计每列的缺失情况
        missing_stats = {}
        total_rows = len(df)
        
        for col in all_columns:
            if col in df.columns:
                missing_count = df[col].isna().sum()
                missing_rate = missing_count / total_rows * 100 if total_rows > 0 else 0
                missing_stats[col] = {
                    'missing_count': missing_count,
                    'total_count': total_rows,
                    'missing_rate': missing_rate
                }
        
        # 统计轨迹相关信息
        trajectory_count = df['flight_id'].nunique() if 'flight_id' in df.columns else 0
        
        result = {
            'file': os.path.basename(file_path),
            'total_rows': total_rows,
            'trajectory_count': trajectory_count,
            'missing_stats': missing_stats,
            'all_columns': all_columns
        }
        
        return result
        
    except Exception as e:
        print(f'处理文件 {file_path} 时出错: {e}')
        return None

def main():
    print('📊 全面缺失率分析：统计所有列的缺失情况')
    print('=' * 60)
    
    output_dir = 'complete_high_quality_trajectories'
    
    if not os.path.exists(output_dir):
        print(f'❌ 输出目录不存在: {output_dir}')
        return
    
    # 获取所有文件
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.parquet')]
    print(f'📁 分析 {len(files)} 个文件')
    
    # 先分析一个文件看看有哪些列
    sample_file = files[0]
    sample_df = pd.read_parquet(sample_file)
    all_columns = sample_df.columns.tolist()
    print(f'📋 数据集包含的列: {all_columns}')
    
    start_time = time.time()
    
    # 多进程分析
    print('⏳ 开始分析所有文件的缺失率...')
    with ProcessPoolExecutor(max_workers=min(mp.cpu_count()//2, 16)) as executor:
        results = list(executor.map(analyze_file_missing_rates, files))
    
    # 过滤掉失败的结果
    results = [r for r in results if r is not None]
    
    elapsed_time = time.time() - start_time
    
    # 汇总统计
    print(f'\n📊 汇总统计 (处理时间: {elapsed_time:.1f}秒):')
    
    # 计算总体统计
    total_rows = sum(r['total_rows'] for r in results)
    total_trajectories = sum(r['trajectory_count'] for r in results)
    
    print(f'总文件数: {len(results)}')
    print(f'总数据行数: {total_rows:,}')
    print(f'总轨迹数: {total_trajectories:,}')
    
    # 汇总每列的缺失统计
    column_summary = {}
    
    for result in results:
        for col, stats in result['missing_stats'].items():
            if col not in column_summary:
                column_summary[col] = {
                    'total_missing': 0,
                    'total_count': 0
                }
            column_summary[col]['total_missing'] += stats['missing_count']
            column_summary[col]['total_count'] += stats['total_count']
    
    # 计算每列的总体缺失率
    for col in column_summary:
        total_missing = column_summary[col]['total_missing']
        total_count = column_summary[col]['total_count']
        missing_rate = total_missing / total_count * 100 if total_count > 0 else 0
        column_summary[col]['missing_rate'] = missing_rate
    
    # 按缺失率排序显示
    print(f'\n📋 各列缺失率统计 (按缺失率降序):')
    print(f'{"列名":<20} {"缺失数量":<15} {"总数量":<15} {"缺失率":<10}')
    print('-' * 70)
    
    sorted_columns = sorted(column_summary.items(), key=lambda x: x[1]['missing_rate'], reverse=True)
    
    for col, stats in sorted_columns:
        missing_count = stats['total_missing']
        total_count = stats['total_count']
        missing_rate = stats['missing_rate']
        print(f'{col:<20} {missing_count:<15,} {total_count:<15,} {missing_rate:<10.4f}%')
    
    # 重点关注的列
    key_columns = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    print(f'\n🎯 重点列缺失率分析:')
    print(f'{"列名":<15} {"缺失数量":<15} {"缺失率":<10} {"状态":<10}')
    print('-' * 55)
    
    total_key_missing = 0
    for col in key_columns:
        if col in column_summary:
            missing_count = column_summary[col]['total_missing']
            missing_rate = column_summary[col]['missing_rate']
            total_key_missing += missing_count
            
            status = "✅ 完美" if missing_rate == 0 else "⚠️ 有缺失" if missing_rate < 1 else "❌ 严重缺失"
            print(f'{col:<15} {missing_count:<15,} {missing_rate:<10.4f}% {status:<10}')
        else:
            print(f'{col:<15} {"列不存在":<15} {"N/A":<10} {"❌ 缺失":<10}')
    
    print(f'\n📊 重点列总缺失数: {total_key_missing:,}')
    print(f'重点列总缺失率: {total_key_missing / (total_rows * len(key_columns)) * 100:.4f}%')
    
    # 分析缺失值分布
    print(f'\n🔍 缺失值分布分析:')
    
    # 找出缺失率最高的文件
    file_missing_rates = []
    for result in results:
        file_total_missing = 0
        file_total_possible = 0
        
        for col in key_columns:
            if col in result['missing_stats']:
                file_total_missing += result['missing_stats'][col]['missing_count']
                file_total_possible += result['missing_stats'][col]['total_count']
        
        file_missing_rate = file_total_missing / file_total_possible * 100 if file_total_possible > 0 else 0
        file_missing_rates.append({
            'file': result['file'],
            'missing_count': file_total_missing,
            'missing_rate': file_missing_rate,
            'trajectories': result['trajectory_count']
        })
    
    # 按缺失率排序
    file_missing_rates.sort(key=lambda x: x['missing_rate'], reverse=True)
    
    print(f'缺失率最高的文件 (前10个):')
    print(f'{"文件名":<25} {"缺失数量":<10} {"缺失率":<10} {"轨迹数":<8}')
    print('-' * 60)
    
    for i, file_info in enumerate(file_missing_rates[:10]):
        print(f'{file_info["file"]:<25} {file_info["missing_count"]:<10,} {file_info["missing_rate"]:<10.4f}% {file_info["trajectories"]:<8}')
    
    # 统计完全无缺失的文件
    perfect_files = [f for f in file_missing_rates if f['missing_rate'] == 0]
    print(f'\n✅ 完全无缺失的文件: {len(perfect_files)} 个 ({len(perfect_files)/len(file_missing_rates)*100:.1f}%)')
    
    # 生成详细报告
    report_file = f'comprehensive_missing_rate_report_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('全面缺失率分析报告\n')
        f.write('=' * 25 + '\n\n')
        f.write(f'分析时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'处理时间: {elapsed_time:.1f} 秒\n')
        f.write(f'数据目录: {output_dir}\n\n')
        
        f.write('总体统计:\n')
        f.write(f'  总文件数: {len(results)}\n')
        f.write(f'  总数据行数: {total_rows:,}\n')
        f.write(f'  总轨迹数: {total_trajectories:,}\n\n')
        
        f.write('各列缺失率统计 (按缺失率降序):\n')
        f.write(f'{"列名":<20} {"缺失数量":<15} {"总数量":<15} {"缺失率":<10}\n')
        f.write('-' * 70 + '\n')
        
        for col, stats in sorted_columns:
            missing_count = stats['total_missing']
            total_count = stats['total_count']
            missing_rate = stats['missing_rate']
            f.write(f'{col:<20} {missing_count:<15,} {total_count:<15,} {missing_rate:<10.4f}%\n')
        
        f.write(f'\n重点列缺失率分析:\n')
        f.write(f'{"列名":<15} {"缺失数量":<15} {"缺失率":<10}\n')
        f.write('-' * 45 + '\n')
        
        for col in key_columns:
            if col in column_summary:
                missing_count = column_summary[col]['total_missing']
                missing_rate = column_summary[col]['missing_rate']
                f.write(f'{col:<15} {missing_count:<15,} {missing_rate:<10.4f}%\n')
            else:
                f.write(f'{col:<15} {"列不存在":<15} {"N/A":<10}\n')
        
        f.write(f'\n重点列总缺失数: {total_key_missing:,}\n')
        f.write(f'重点列总缺失率: {total_key_missing / (total_rows * len(key_columns)) * 100:.4f}%\n')
        
        f.write(f'\n文件缺失率分布:\n')
        f.write(f'  完全无缺失文件: {len(perfect_files)} 个 ({len(perfect_files)/len(file_missing_rates)*100:.1f}%)\n')
        f.write(f'  有缺失值文件: {len(file_missing_rates) - len(perfect_files)} 个\n')
        
        f.write(f'\n缺失率最高的文件:\n')
        f.write(f'{"文件名":<25} {"缺失数量":<10} {"缺失率":<10} {"轨迹数":<8}\n')
        f.write('-' * 60 + '\n')
        
        for file_info in file_missing_rates[:20]:
            f.write(f'{file_info["file"]:<25} {file_info["missing_count"]:<10,} {file_info["missing_rate"]:<10.4f}% {file_info["trajectories"]:<8}\n')
    
    print(f'\n📄 详细报告已保存: {report_file}')
    
    # 结论
    print(f'\n💡 分析结论:')
    
    if total_key_missing == 0:
        print(f'  ✅ 所有重点列都没有缺失值！数据质量完美！')
    else:
        print(f'  ⚠️  重点列总共有 {total_key_missing:,} 个缺失值')
        print(f'  📊 总体缺失率: {total_key_missing / (total_rows * len(key_columns)) * 100:.4f}%')
        
        # 找出缺失最严重的列
        worst_col = max([(col, stats['missing_rate']) for col, stats in column_summary.items() 
                        if col in key_columns], key=lambda x: x[1])
        print(f'  🚨 缺失最严重的列: {worst_col[0]} ({worst_col[1]:.4f}%)')
    
    # 修正之前的统计错误
    print(f'\n🔧 修正说明:')
    print(f'  之前报告的0.10%缺失率可能统计有误')
    print(f'  本次分析包含了所有列的完整统计')
    print(f'  实际缺失率: {total_key_missing / (total_rows * len(key_columns)) * 100:.4f}%')

if __name__ == '__main__':
    main()