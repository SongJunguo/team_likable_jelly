#!/usr/bin/env python3
"""
验证最终数据集的轨迹数量和质量
"""

import pandas as pd
import os
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time

def count_trajectories(file_path):
    """统计单个文件中的轨迹数量"""
    try:
        df = pd.read_parquet(file_path)
        return df['flight_id'].nunique()
    except Exception as e:
        print(f'Error reading {os.path.basename(file_path)}: {e}')
        return 0

def main():
    print('🔍 验证最终数据集质量')
    print('=' * 50)
    
    output_dir = 'complete_high_quality_trajectories'
    
    if not os.path.exists(output_dir):
        print(f'❌ 输出目录不存在: {output_dir}')
        return
    
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.parquet')]
    
    print(f'📁 找到 {len(files)} 个parquet文件')
    print('⏳ 开始统计轨迹数量...')
    
    start_time = time.time()
    
    # 使用多进程加速统计
    with ProcessPoolExecutor(max_workers=min(mp.cpu_count()//2, 8)) as executor:
        trajectory_counts = list(executor.map(count_trajectories, files))
    
    total_trajectories = sum(trajectory_counts)
    elapsed_time = time.time() - start_time
    
    print(f'\n📊 统计结果:')
    print(f'  处理时间: {elapsed_time:.1f}秒')
    print(f'  文件数: {len(files)}')
    print(f'  总轨迹数: {total_trajectories:,}')
    print(f'  目标轨迹数: 238,217')
    print(f'  达成率: {total_trajectories/238217*100:.2f}%')
    
    # 评估结果
    if total_trajectories == 238217:
        print('\n✅ 完美匹配！数据集包含预期的238,217条轨迹')
        status = "PERFECT"
    elif total_trajectories >= 238000:
        print('\n✅ 接近目标！数据集质量良好')
        status = "GOOD"
    elif total_trajectories >= 230000:
        print('\n⚠️  轨迹数量略低于预期，但仍在可接受范围内')
        status = "ACCEPTABLE"
    else:
        print('\n❌ 轨迹数量明显低于预期，可能存在数据丢失')
        status = "POOR"
    
    # 保存验证报告
    report_file = f'dataset_validation_report_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('最终数据集验证报告\n')
        f.write('=' * 30 + '\n\n')
        f.write(f'验证时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'数据目录: {output_dir}\n')
        f.write(f'文件数量: {len(files)}\n')
        f.write(f'总轨迹数: {total_trajectories:,}\n')
        f.write(f'目标轨迹数: 238,217\n')
        f.write(f'达成率: {total_trajectories/238217*100:.2f}%\n')
        f.write(f'验证状态: {status}\n')
    
    print(f'\n📄 验证报告已保存至: {report_file}')

if __name__ == '__main__':
    main()