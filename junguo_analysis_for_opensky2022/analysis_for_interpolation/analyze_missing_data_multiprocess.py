#!/usr/bin/env python3
"""
多进程分析航迹数据的缺失率和缺失窗口长度
针对280GB数据和80核心CPU优化，支持10-30%抽样
"""

import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import psutil
import random

def analyze_missing_windows(series, flight_id=None):
    """
    分析单个时间序列中的缺失窗口
    返回缺失窗口的长度统计
    """
    if series.empty:
        return []
    
    # 找到NaN值的位置
    is_nan = series.isna()
    
    if not is_nan.any():
        return []  # 没有缺失值
    
    # 找到连续的NaN窗口
    windows = []
    in_window = False
    window_start = 0
    
    for i, nan_val in enumerate(is_nan):
        if nan_val and not in_window:
            # 开始一个新的缺失窗口
            in_window = True
            window_start = i
        elif not nan_val and in_window:
            # 结束当前缺失窗口
            in_window = False
            window_length = i - window_start
            windows.append(window_length)
    
    # 如果序列以NaN结尾
    if in_window:
        window_length = len(series) - window_start
        windows.append(window_length)
    
    return windows

def analyze_flight_missing_data(df, flight_id):
    """分析单个航班的缺失数据情况"""
    flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
    
    if flight_data.empty:
        return None
    
    # 关键字段
    key_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    flight_stats = {
        'flight_id': flight_id,
        'total_points': len(flight_data),
        'duration_minutes': 0,
        'missing_stats': {}
    }
    
    # 计算飞行时长
    if len(flight_data) > 1:
        duration = (flight_data.timestamp.max() - flight_data.timestamp.min()).total_seconds() / 60
        flight_stats['duration_minutes'] = duration
    
    # 分析每个字段的缺失情况
    for field in key_fields:
        if field in flight_data.columns:
            series = flight_data[field]
            total_points = len(series)
            missing_count = series.isna().sum()
            missing_rate = (missing_count / total_points) * 100 if total_points > 0 else 0
            
            # 分析缺失窗口
            missing_windows = analyze_missing_windows(series, flight_id)
            
            flight_stats['missing_stats'][field] = {
                'missing_count': missing_count,
                'missing_rate': missing_rate,
                'missing_windows': missing_windows,
                'num_windows': len(missing_windows),
                'avg_window_length': np.mean(missing_windows) if missing_windows else 0,
                'max_window_length': max(missing_windows) if missing_windows else 0,
                'total_missing_points': sum(missing_windows) if missing_windows else 0
            }
    
    return flight_stats

def process_file_with_sampling(args):
    """处理单个文件并进行抽样分析"""
    file_path, sample_percentage, max_flights_per_file = args
    
    try:
        filename = os.path.basename(file_path)
        
        # 读取文件
        df = pd.read_parquet(file_path)
        total_flights = df.flight_id.nunique()
        
        # 确定抽样数量
        if sample_percentage:
            sample_size = max(1, int(total_flights * sample_percentage / 100))
        else:
            sample_size = min(max_flights_per_file, total_flights)
        
        # 随机选择航班
        unique_flights = df.flight_id.unique()
        if len(unique_flights) > sample_size:
            selected_flights = np.random.choice(unique_flights, sample_size, replace=False)
            df = df[df.flight_id.isin(selected_flights)]
        
        # 分析每个航班
        flight_stats = []
        for flight_id in df.flight_id.unique():
            stats = analyze_flight_missing_data(df, flight_id)
            if stats:
                flight_stats.append(stats)
        
        return {
            'filename': filename,
            'total_flights_in_file': total_flights,
            'analyzed_flights': len(flight_stats),
            'flight_stats': flight_stats,
            'file_size_mb': os.path.getsize(file_path) / (1024*1024)
        }
        
    except Exception as e:
        filename = os.path.basename(file_path)
        print(f"处理文件 {filename} 时出错: {e}")
        return {
            'filename': filename,
            'total_flights_in_file': 0,
            'analyzed_flights': 0,
            'flight_stats': [],
            'file_size_mb': 0,
            'error': str(e)
        }

def generate_comprehensive_report(all_file_results, sample_percentage, output_file="comprehensive_missing_data_report.txt"):
    """生成综合的缺失数据分析报告"""
    
    # 收集所有航班统计
    all_flight_stats = []
    total_files = len(all_file_results)
    successful_files = 0
    total_flights_in_dataset = 0
    total_analyzed_flights = 0
    
    for file_result in all_file_results:
        if 'error' not in file_result:
            successful_files += 1
            total_flights_in_dataset += file_result['total_flights_in_file']
            total_analyzed_flights += file_result['analyzed_flights']
            all_flight_stats.extend(file_result['flight_stats'])
    
    if not all_flight_stats:
        print("没有数据可分析")
        return
    
    # 关键字段
    key_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    report_lines = []
    report_lines.append("=" * 80)
    report_lines.append("航迹数据缺失率和缺失窗口综合分析报告 (多进程版本)")
    report_lines.append("=" * 80)
    report_lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"抽样比例: {sample_percentage}%")
    report_lines.append(f"处理文件数: {successful_files}/{total_files}")
    report_lines.append(f"数据集总航班数: {total_flights_in_dataset:,}")
    report_lines.append(f"分析航班数: {total_analyzed_flights:,}")
    report_lines.append(f"实际抽样比例: {total_analyzed_flights/total_flights_in_dataset*100:.2f}%")
    report_lines.append("")
    
    # 整体统计
    total_points = sum([stat['total_points'] for stat in all_flight_stats])
    avg_duration = np.mean([stat['duration_minutes'] for stat in all_flight_stats if stat['duration_minutes'] > 0])
    
    report_lines.append("=== 整体统计 ===")
    report_lines.append(f"分析的总轨迹点数: {total_points:,}")
    report_lines.append(f"平均航班时长: {avg_duration:.1f} 分钟")
    report_lines.append(f"平均每航班轨迹点数: {total_points/len(all_flight_stats):.0f}")
    
    # 航班时长分布
    durations = [stat['duration_minutes'] for stat in all_flight_stats if stat['duration_minutes'] > 0]
    if durations:
        report_lines.append(f"航班时长分布:")
        report_lines.append(f"  最短: {min(durations):.1f} 分钟")
        report_lines.append(f"  最长: {max(durations):.1f} 分钟")
        report_lines.append(f"  中位数: {np.median(durations):.1f} 分钟")
        
        short_flights = sum(1 for d in durations if d < 60)
        medium_flights = sum(1 for d in durations if 60 <= d < 180)
        long_flights = sum(1 for d in durations if d >= 180)
        
        report_lines.append(f"  短途航班 (<1小时): {short_flights} ({short_flights/len(durations)*100:.1f}%)")
        report_lines.append(f"  中途航班 (1-3小时): {medium_flights} ({medium_flights/len(durations)*100:.1f}%)")
        report_lines.append(f"  长途航班 (>3小时): {long_flights} ({long_flights/len(durations)*100:.1f}%)")
    
    report_lines.append("")
    
    # 按字段分析缺失情况
    for field in key_fields:
        report_lines.append(f"=== {field.upper()} 字段缺失分析 ===")
        
        # 收集该字段的所有统计数据
        field_stats = []
        all_windows = []
        flights_with_missing = 0
        flights_with_data = 0
        
        for stat in all_flight_stats:
            if field in stat['missing_stats']:
                field_stat = stat['missing_stats'][field]
                field_stats.append(field_stat)
                flights_with_data += 1
                all_windows.extend(field_stat['missing_windows'])
                if field_stat['missing_count'] > 0:
                    flights_with_missing += 1
        
        if not field_stats:
            report_lines.append(f"  该字段无数据")
            continue
        
        # 缺失率统计
        missing_rates = [stat['missing_rate'] for stat in field_stats]
        avg_missing_rate = np.mean(missing_rates)
        median_missing_rate = np.median(missing_rates)
        std_missing_rate = np.std(missing_rates)
        
        report_lines.append(f"  有该字段数据的航班: {flights_with_data:,}")
        report_lines.append(f"  有缺失数据的航班数: {flights_with_missing}/{flights_with_data} ({flights_with_missing/flights_with_data*100:.1f}%)")
        report_lines.append(f"  缺失率统计:")
        report_lines.append(f"    平均值: {avg_missing_rate:.2f}%")
        report_lines.append(f"    中位数: {median_missing_rate:.2f}%")
        report_lines.append(f"    标准差: {std_missing_rate:.2f}%")
        report_lines.append(f"    最小值: {min(missing_rates):.2f}%")
        report_lines.append(f"    最大值: {max(missing_rates):.2f}%")
        
        # 缺失率分布
        no_missing = sum([1 for rate in missing_rates if rate == 0])
        low_missing = sum([1 for rate in missing_rates if 0 < rate <= 5])
        medium_missing = sum([1 for rate in missing_rates if 5 < rate <= 20])
        high_missing = sum([1 for rate in missing_rates if 20 < rate <= 50])
        very_high_missing = sum([1 for rate in missing_rates if rate > 50])
        
        report_lines.append(f"  缺失率分布:")
        report_lines.append(f"    无缺失 (0%): {no_missing} 航班 ({no_missing/len(missing_rates)*100:.1f}%)")
        report_lines.append(f"    极低缺失 (0-5%): {low_missing} 航班 ({low_missing/len(missing_rates)*100:.1f}%)")
        report_lines.append(f"    低缺失 (5-20%): {medium_missing} 航班 ({medium_missing/len(missing_rates)*100:.1f}%)")
        report_lines.append(f"    高缺失 (20-50%): {high_missing} 航班 ({high_missing/len(missing_rates)*100:.1f}%)")
        report_lines.append(f"    极高缺失 (>50%): {very_high_missing} 航班 ({very_high_missing/len(missing_rates)*100:.1f}%)")
        
        # 缺失窗口分析
        if all_windows:
            report_lines.append(f"  缺失窗口统计:")
            report_lines.append(f"    总缺失窗口数: {len(all_windows):,}")
            report_lines.append(f"    窗口长度统计:")
            report_lines.append(f"      平均值: {np.mean(all_windows):.1f} 个点")
            report_lines.append(f"      中位数: {np.median(all_windows):.1f} 个点")
            report_lines.append(f"      标准差: {np.std(all_windows):.1f} 个点")
            report_lines.append(f"      最小值: {min(all_windows)} 个点")
            report_lines.append(f"      最大值: {max(all_windows)} 个点")
            
            # 窗口长度分布
            very_short = sum([1 for w in all_windows if w <= 2])
            short_windows = sum([1 for w in all_windows if 2 < w <= 10])
            medium_windows = sum([1 for w in all_windows if 10 < w <= 50])
            long_windows = sum([1 for w in all_windows if 50 < w <= 200])
            very_long_windows = sum([1 for w in all_windows if w > 200])
            
            report_lines.append(f"    窗口长度分布:")
            report_lines.append(f"      极短窗口 (≤2点): {very_short:,} ({very_short/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      短窗口 (3-10点): {short_windows:,} ({short_windows/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      中等窗口 (11-50点): {medium_windows:,} ({medium_windows/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      长窗口 (51-200点): {long_windows:,} ({long_windows/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      超长窗口 (>200点): {very_long_windows:,} ({very_long_windows/len(all_windows)*100:.1f}%)")
        
        report_lines.append("")
    
    # 写入报告文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    # 同时打印到控制台
    print('\n'.join(report_lines))
    print(f"\n综合报告已保存到: {output_file}")

def get_optimal_workers():
    """根据系统资源确定最优工作进程数"""
    cpu_count = psutil.cpu_count(logical=True)
    memory_gb = psutil.virtual_memory().total / (1024**3)
    
    # 考虑到每个进程可能需要处理大文件，限制并发数
    # 假设每个进程最多使用6GB内存
    max_workers_by_memory = int(memory_gb / 6)
    
    # 使用CPU核心数的70%，留更多资源给系统
    max_workers_by_cpu = int(cpu_count * 0.7)
    
    # 取较小值，但至少4个进程，最多50个进程
    optimal_workers = max(4, min(max_workers_by_memory, max_workers_by_cpu, 50))
    
    print(f"系统信息:")
    print(f"  CPU核心数: {cpu_count}")
    print(f"  内存: {memory_gb:.1f} GB")
    print(f"  建议工作进程数: {optimal_workers}")
    
    return optimal_workers

def main():
    """主函数"""
    start_time = time.time()
    
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    # 分析参数
    SAMPLE_PERCENTAGE = 20  # 抽样20%
    MAX_FLIGHTS_PER_FILE = 500  # 每个文件最多分析500个航班
    
    # 插值后数据目录
    interp_dir = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/'
    
    if not os.path.exists(interp_dir):
        print(f"目录不存在: {interp_dir}")
        return
    
    # 获取所有parquet文件
    parquet_files = glob.glob(os.path.join(interp_dir, '*.parquet'))
    parquet_files.sort()
    
    if not parquet_files:
        print(f"在 {interp_dir} 中没有找到parquet文件")
        return
    
    print(f"找到 {len(parquet_files)} 个parquet文件")
    
    # 计算总文件大小
    total_size_gb = sum(os.path.getsize(f) for f in parquet_files) / (1024**3)
    print(f"总数据大小: {total_size_gb:.1f} GB")
    
    # 确定最优工作进程数
    num_workers = get_optimal_workers()
    
    print(f"\n开始多进程缺失数据分析...")
    print(f"抽样比例: {SAMPLE_PERCENTAGE}%")
    print(f"每文件最大分析航班数: {MAX_FLIGHTS_PER_FILE}")
    print(f"使用 {num_workers} 个工作进程")
    
    # 准备任务参数
    task_args = [(file_path, SAMPLE_PERCENTAGE, MAX_FLIGHTS_PER_FILE) for file_path in parquet_files]
    
    # 使用ProcessPoolExecutor进行多进程处理
    all_results = []
    completed_files = 0
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # 提交所有文件处理任务
        future_to_file = {
            executor.submit(process_file_with_sampling, args): args[0] 
            for args in task_args
        }
        
        # 收集结果
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                result = future.result()
                all_results.append(result)
                completed_files += 1
                
                if completed_files % 5 == 0 or completed_files == len(parquet_files):
                    elapsed = time.time() - start_time
                    progress = completed_files / len(parquet_files) * 100
                    eta = elapsed / completed_files * (len(parquet_files) - completed_files)
                    print(f"进度: {completed_files}/{len(parquet_files)} ({progress:.1f}%) "
                          f"已用时: {elapsed/60:.1f}分钟, 预计剩余: {eta/60:.1f}分钟")
                
            except Exception as e:
                print(f"处理文件 {os.path.basename(file_path)} 时出错: {e}")
    
    elapsed_time = time.time() - start_time
    
    print(f"\n多进程分析完成，总用时: {elapsed_time/60:.1f} 分钟")
    
    # 生成综合报告
    generate_comprehensive_report(all_results, SAMPLE_PERCENTAGE, "comprehensive_missing_data_report.txt")
    
    # 保存原始结果
    summary_stats = []
    for result in all_results:
        if 'error' not in result:
            summary_stats.append({
                'filename': result['filename'],
                'total_flights_in_file': result['total_flights_in_file'],
                'analyzed_flights': result['analyzed_flights'],
                'file_size_mb': result['file_size_mb']
            })
    
    if summary_stats:
        summary_df = pd.DataFrame(summary_stats)
        summary_df.to_csv('file_analysis_summary.csv', index=False)
        print(f"文件分析摘要已保存到: file_analysis_summary.csv")

if __name__ == "__main__":
    # 设置多进程启动方法
    mp.set_start_method('spawn', force=True)
    # 设置随机种子以确保可重现性
    np.random.seed(42)
    random.seed(42)
    main()