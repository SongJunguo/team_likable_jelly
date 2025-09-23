#!/usr/bin/env python3
"""
快速轨迹数据缺失率统计程序
专门生成CSV和Parquet格式的结果文件，便于后续分析
优化内存使用，适合大规模数据处理
"""

import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import argparse
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

def analyze_trajectory_quick(df, flight_id):
    """
    快速分析单个轨迹的缺失情况
    """
    total_points = len(df)
    if total_points == 0:
        return None
    
    # 关键字段
    key_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    result = {
        'flight_id': flight_id,
        'total_points': total_points,
        'duration_minutes': 0,  # 简化版本不计算时间
    }
    
    # 分析每个字段
    for field in key_fields:
        if field in df.columns:
            series = df[field]
            missing_mask = series.isna()
            missing_count = missing_mask.sum()
            valid_count = total_points - missing_count
            missing_rate = (missing_count / total_points) * 100
            
            # 头尾缺失检测
            head_missing = missing_mask.iloc[0] if total_points > 0 else False
            tail_missing = missing_mask.iloc[-1] if total_points > 0 else False
            
            # 计算最大缺失窗口
            max_window = 0
            current_window = 0
            num_windows = 0
            in_window = False
            
            for is_missing in missing_mask:
                if is_missing:
                    if not in_window:
                        num_windows += 1
                        in_window = True
                    current_window += 1
                    max_window = max(max_window, current_window)
                else:
                    current_window = 0
                    in_window = False
            
            # 数据范围（仅对有效数据）
            if valid_count > 0:
                valid_data = series.dropna()
                min_val = float(valid_data.min())
                max_val = float(valid_data.max())
                mean_val = float(valid_data.mean())
                std_val = float(valid_data.std()) if valid_count > 1 else 0.0
            else:
                min_val = max_val = mean_val = std_val = None
            
            # 保存字段统计
            result.update({
                f'{field}_missing_rate': missing_rate,
                f'{field}_missing_count': missing_count,
                f'{field}_valid_count': valid_count,
                f'{field}_max_window': max_window,
                f'{field}_num_windows': num_windows,
                f'{field}_head_missing': head_missing,
                f'{field}_tail_missing': tail_missing,
                f'{field}_min_value': min_val,
                f'{field}_max_value': max_val,
                f'{field}_mean_value': mean_val,
                f'{field}_std_value': std_val
            })
        else:
            # 字段不存在
            result.update({
                f'{field}_missing_rate': 100.0,
                f'{field}_missing_count': total_points,
                f'{field}_valid_count': 0,
                f'{field}_max_window': total_points,
                f'{field}_num_windows': 1 if total_points > 0 else 0,
                f'{field}_head_missing': True,
                f'{field}_tail_missing': True,
                f'{field}_min_value': None,
                f'{field}_max_value': None,
                f'{field}_mean_value': None,
                f'{field}_std_value': None
            })
    
    # 计算质量分数（基于关键字段的平均缺失率）
    key_missing_rates = [result[f'{field}_missing_rate'] for field in ['latitude', 'longitude', 'altitude']]
    avg_missing_rate = np.mean(key_missing_rates)
    quality_score = max(0, 100 - avg_missing_rate)
    result['quality_score'] = quality_score
    
    # 质量等级
    if quality_score >= 90:
        result['quality_level'] = 'Excellent'
    elif quality_score >= 70:
        result['quality_level'] = 'Good'
    elif quality_score >= 50:
        result['quality_level'] = 'Fair'
    else:
        result['quality_level'] = 'Poor'
    
    return result

def process_file_quick(file_path, sample_percentage=1.0):
    """
    快速处理单个文件
    """
    try:
        print(f"正在处理文件: {os.path.basename(file_path)}")
        
        # 读取文件
        df = pd.read_parquet(file_path)
        
        if df.empty:
            return []
        
        # 按flight_id分组
        flight_groups = df.groupby('flight_id')
        total_flights = len(flight_groups)
        
        # 抽样
        if sample_percentage < 1.0:
            sample_size = max(1, int(total_flights * sample_percentage))
            flight_ids = np.random.choice(list(flight_groups.groups.keys()), 
                                        size=sample_size, replace=False)
            flight_groups = {fid: flight_groups.get_group(fid) for fid in flight_ids}
        else:
            flight_groups = {fid: group for fid, group in flight_groups}
        
        results = []
        processed = 0
        
        for flight_id, flight_df in flight_groups.items():
            result = analyze_trajectory_quick(flight_df, flight_id)
            if result:
                results.append(result)
            processed += 1
            
            if processed % 100 == 0:
                print(f"  已处理 {processed}/{len(flight_groups)} 轨迹")
        
        print(f"完成文件 {os.path.basename(file_path)}: {len(results)}/{total_flights} 轨迹")
        return results
        
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {str(e)}")
        return []

def main():
    parser = argparse.ArgumentParser(description='快速轨迹数据缺失率统计')
    parser.add_argument('--data_dir', type=str, 
                       default='../../opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories',
                       help='数据目录路径')
    parser.add_argument('--output_dir', type=str, 
                       default='./quick_analysis_output',
                       help='输出目录路径')
    parser.add_argument('--sample_percentage', type=float, default=0.05,
                       help='抽样百分比 (0.01-1.0)')
    parser.add_argument('--max_workers', type=int, default=None,
                       help='最大进程数')
    parser.add_argument('--max_files', type=int, default=50,
                       help='最大处理文件数（用于测试）')
    
    args = parser.parse_args()
    
    # 检查数据目录
    if not os.path.exists(args.data_dir):
        print(f"错误: 数据目录不存在: {args.data_dir}")
        print(f"当前工作目录: {os.getcwd()}")
        return
    
    # 创建输出目录
    os.makedirs(args.output_dir, exist_ok=True)
    
    # 获取所有parquet文件
    parquet_files = glob.glob(os.path.join(args.data_dir, "*.parquet"))
    if not parquet_files:
        print(f"错误: 在 {args.data_dir} 中未找到parquet文件")
        return
    
    # 限制文件数量（用于测试）
    if args.max_files and len(parquet_files) > args.max_files:
        parquet_files = parquet_files[:args.max_files]
        print(f"限制处理文件数量为: {len(parquet_files)}")
    
    print(f"找到 {len(parquet_files)} 个parquet文件")
    print(f"抽样比例: {args.sample_percentage*100:.1f}%")
    
    # 确定进程数
    if args.max_workers is None:
        max_workers = min(mp.cpu_count(), len(parquet_files), 40)  # 限制最大进程数
    else:
        max_workers = min(args.max_workers, len(parquet_files))
    
    print(f"使用 {max_workers} 个进程")
    
    # 多进程处理
    start_time = time.time()
    all_results = []
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # 提交任务
        future_to_file = {
            executor.submit(process_file_quick, file_path, args.sample_percentage): file_path
            for file_path in parquet_files
        }
        
        completed = 0
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                results = future.result()
                all_results.extend(results)
                completed += 1
                print(f"进度: {completed}/{len(parquet_files)} 文件已完成 ({completed/len(parquet_files)*100:.1f}%)")
            except Exception as e:
                print(f"处理文件 {file_path} 时出错: {str(e)}")
    
    processing_time = time.time() - start_time
    
    if not all_results:
        print("错误: 没有成功处理任何轨迹数据")
        return
    
    print(f"\n处理完成!")
    print(f"总处理时间: {processing_time:.1f} 秒")
    print(f"总轨迹数: {len(all_results):,}")
    
    # 转换为DataFrame
    print("正在生成数据文件...")
    df_results = pd.DataFrame(all_results)
    
    # 保存CSV文件
    csv_file = os.path.join(args.output_dir, "trajectory_analysis.csv")
    df_results.to_csv(csv_file, index=False, encoding='utf-8')
    print(f"CSV文件已保存: {csv_file}")
    
    # 保存Parquet文件
    parquet_file = os.path.join(args.output_dir, "trajectory_analysis.parquet")
    df_results.to_parquet(parquet_file, index=False)
    print(f"Parquet文件已保存: {parquet_file}")
    
    # 生成简单统计报告
    report_file = os.path.join(args.output_dir, "analysis_summary.txt")
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"轨迹数据缺失率分析报告\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"=" * 50 + "\n\n")
        
        f.write(f"数据概览:\n")
        f.write(f"  总轨迹数: {len(all_results):,}\n")
        f.write(f"  处理文件数: {len(parquet_files)}\n")
        f.write(f"  抽样比例: {args.sample_percentage*100:.1f}%\n")
        f.write(f"  处理时间: {processing_time:.1f} 秒\n\n")
        
        # 质量分布
        quality_counts = df_results['quality_level'].value_counts()
        f.write(f"质量分布:\n")
        for level, count in quality_counts.items():
            f.write(f"  {level}: {count:,} ({count/len(df_results)*100:.1f}%)\n")
        f.write("\n")
        
        # 关键字段统计
        key_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
        f.write(f"关键字段缺失率统计:\n")
        for field in key_fields:
            missing_col = f'{field}_missing_rate'
            if missing_col in df_results.columns:
                avg_missing = df_results[missing_col].mean()
                median_missing = df_results[missing_col].median()
                f.write(f"  {field}: 平均 {avg_missing:.1f}%, 中位数 {median_missing:.1f}%\n")
    
    print(f"分析报告已保存: {report_file}")
    
    print(f"\n文件说明:")
    print(f"  - trajectory_analysis.csv: 轨迹汇总数据(便于Excel打开)")
    print(f"  - trajectory_analysis.parquet: 轨迹汇总数据(高效存储格式)")
    print(f"  - analysis_summary.txt: 简要分析报告")
    print(f"\n建议使用Excel或pandas读取CSV文件进行进一步分析")

if __name__ == "__main__":
    main()