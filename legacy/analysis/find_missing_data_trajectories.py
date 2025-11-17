#!/usr/bin/env python3
"""
找到插值后仍有缺失值的轨迹并分析其特征
"""

import pandas as pd
import numpy as np
import os
from concurrent.futures import ProcessPoolExecutor
import multiprocessing as mp
import time
from pathlib import Path

def find_missing_trajectories_in_file(file_path):
    """在单个文件中找到有缺失值的轨迹"""
    try:
        df = pd.read_parquet(file_path)
        
        missing_trajectories = []
        
        for flight_id, group in df.groupby('flight_id'):
            # 检查各列的缺失值
            missing_info = {}
            has_missing = False
            
            for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
                if col in group.columns:
                    missing_count = group[col].isna().sum()
                    if missing_count > 0:
                        has_missing = True
                        missing_info[col] = missing_count
            
            if has_missing:
                # 分析轨迹特征
                traj_info = {
                    'file': os.path.basename(file_path),
                    'flight_id': flight_id,
                    'total_points': len(group),
                    'missing_by_column': missing_info,
                    'total_missing': sum(missing_info.values()),
                    'time_span': (group['timestamp'].max() - group['timestamp'].min()).total_seconds() / 3600,  # 小时
                    'first_timestamp': group['timestamp'].min(),
                    'last_timestamp': group['timestamp'].max(),
                }
                
                # 分析缺失值分布
                missing_positions = []
                for col in missing_info.keys():
                    missing_mask = group[col].isna()
                    if missing_mask.any():
                        missing_indices = group.index[missing_mask].tolist()
                        missing_positions.extend([(col, idx) for idx in missing_indices])
                
                traj_info['missing_positions'] = missing_positions[:20]  # 只保留前20个位置
                missing_trajectories.append(traj_info)
        
        return missing_trajectories
        
    except Exception as e:
        print(f'处理文件 {file_path} 时出错: {e}')
        return []

def main():
    print('🔍 查找插值后仍有缺失值的轨迹')
    print('=' * 50)
    
    output_dir = 'complete_high_quality_trajectories'
    
    if not os.path.exists(output_dir):
        print(f'❌ 输出目录不存在: {output_dir}')
        return
    
    # 获取所有文件
    files = [os.path.join(output_dir, f) for f in os.listdir(output_dir) if f.endswith('.parquet')]
    print(f'📁 检查 {len(files)} 个文件')
    
    start_time = time.time()
    
    # 多进程查找
    print('⏳ 开始查找有缺失值的轨迹...')
    with ProcessPoolExecutor(max_workers=min(mp.cpu_count()//2, 8)) as executor:
        results = list(executor.map(find_missing_trajectories_in_file, files))
    
    # 合并结果
    all_missing_trajectories = []
    for file_results in results:
        all_missing_trajectories.extend(file_results)
    
    elapsed_time = time.time() - start_time
    
    print(f'\n📊 查找结果 (处理时间: {elapsed_time:.1f}秒):')
    print(f'找到 {len(all_missing_trajectories)} 条有缺失值的轨迹')
    
    if len(all_missing_trajectories) == 0:
        print('✅ 太好了！所有轨迹都已完全插值，没有缺失值！')
        return
    
    # 分析缺失值特征
    print(f'\n🔍 缺失值轨迹特征分析:')
    
    # 按缺失值数量排序
    all_missing_trajectories.sort(key=lambda x: x['total_missing'], reverse=True)
    
    # 统计信息
    total_missing_points = sum(traj['total_missing'] for traj in all_missing_trajectories)
    avg_missing_per_traj = total_missing_points / len(all_missing_trajectories)
    
    print(f'总缺失数据点: {total_missing_points:,}')
    print(f'平均每条轨迹缺失: {avg_missing_per_traj:.1f} 个点')
    
    # 缺失值分布
    missing_by_column = {}
    for traj in all_missing_trajectories:
        for col, count in traj['missing_by_column'].items():
            if col not in missing_by_column:
                missing_by_column[col] = 0
            missing_by_column[col] += count
    
    print(f'\n各列缺失值分布:')
    for col, count in sorted(missing_by_column.items(), key=lambda x: x[1], reverse=True):
        print(f'  {col}: {count:,} 个缺失值')
    
    # 显示最严重的轨迹
    print(f'\n🚨 缺失值最多的轨迹 (前10条):')
    for i, traj in enumerate(all_missing_trajectories[:10]):
        print(f'  {i+1}. 轨迹 {traj["flight_id"]} ({traj["file"]}):')
        print(f'     总点数: {traj["total_points"]}, 缺失: {traj["total_missing"]} 个点')
        print(f'     时间跨度: {traj["time_span"]:.1f} 小时')
        print(f'     缺失列: {", ".join(traj["missing_by_column"].keys())}')
    
    # 分析轨迹长度分布
    traj_lengths = [traj['total_points'] for traj in all_missing_trajectories]
    missing_counts = [traj['total_missing'] for traj in all_missing_trajectories]
    
    print(f'\n📈 轨迹长度统计:')
    print(f'  最短轨迹: {min(traj_lengths)} 个点')
    print(f'  最长轨迹: {max(traj_lengths)} 个点')
    print(f'  平均长度: {np.mean(traj_lengths):.1f} 个点')
    print(f'  中位数长度: {np.median(traj_lengths):.1f} 个点')
    
    print(f'\n📈 缺失值统计:')
    print(f'  最少缺失: {min(missing_counts)} 个点')
    print(f'  最多缺失: {max(missing_counts)} 个点')
    print(f'  平均缺失: {np.mean(missing_counts):.1f} 个点')
    print(f'  中位数缺失: {np.median(missing_counts):.1f} 个点')
    
    # 保存详细报告
    report_file = f'missing_data_trajectories_report_{time.strftime("%Y%m%d_%H%M%S")}.txt'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write('插值后缺失值轨迹报告\n')
        f.write('=' * 30 + '\n\n')
        f.write(f'分析时间: {time.strftime("%Y-%m-%d %H:%M:%S")}\n')
        f.write(f'检查文件数: {len(files)}\n')
        f.write(f'有缺失值的轨迹数: {len(all_missing_trajectories)}\n')
        f.write(f'总缺失数据点: {total_missing_points:,}\n')
        f.write(f'平均每条轨迹缺失: {avg_missing_per_traj:.1f} 个点\n\n')
        
        f.write('各列缺失值分布:\n')
        for col, count in sorted(missing_by_column.items(), key=lambda x: x[1], reverse=True):
            f.write(f'  {col}: {count:,} 个缺失值\n')
        
        f.write(f'\n缺失值最多的轨迹详情:\n')
        for i, traj in enumerate(all_missing_trajectories[:20]):
            f.write(f'  {i+1}. 轨迹 {traj["flight_id"]} ({traj["file"]}):\n')
            f.write(f'     总点数: {traj["total_points"]}, 缺失: {traj["total_missing"]} 个点\n')
            f.write(f'     时间跨度: {traj["time_span"]:.1f} 小时\n')
            f.write(f'     缺失列: {traj["missing_by_column"]}\n')
            f.write(f'     时间范围: {traj["first_timestamp"]} - {traj["last_timestamp"]}\n\n')
    
    print(f'\n📄 详细报告已保存至: {report_file}')
    
    # 建议
    print(f'\n💡 建议:')
    if len(all_missing_trajectories) < 100:
        print(f'  缺失值轨迹数量很少({len(all_missing_trajectories)}条)，可以考虑直接移除这些轨迹')
    elif total_missing_points < 50000:
        print(f'  总缺失值较少({total_missing_points:,}个)，可以考虑加强插值或移除问题轨迹')
    else:
        print(f'  缺失值较多，建议分析具体原因并改进插值算法')

if __name__ == '__main__':
    main()