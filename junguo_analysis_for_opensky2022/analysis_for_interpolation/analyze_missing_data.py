#!/usr/bin/env python3
"""
分析航迹数据的缺失率和缺失窗口长度
专门针对插值后的parquet文件进行NaN值统计分析
"""

import pandas as pd
import numpy as np
import os
import glob
from datetime import datetime

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

def analyze_dataset_missing_data(file_path, sample_size=None):
    """分析整个数据集的缺失情况"""
    print(f"正在分析文件: {file_path}")
    
    try:
        df = pd.read_parquet(file_path)
        print(f"数据形状: {df.shape}")
        print(f"航班数量: {df.flight_id.nunique()}")
        
        # 如果指定了样本大小，随机选择航班
        unique_flights = df.flight_id.unique()
        if sample_size and len(unique_flights) > sample_size:
            selected_flights = np.random.choice(unique_flights, sample_size, replace=False)
            df = df[df.flight_id.isin(selected_flights)]
            print(f"随机选择 {sample_size} 个航班进行分析")
        
        # 分析每个航班
        all_flight_stats = []
        total_flights = df.flight_id.nunique()
        
        for i, flight_id in enumerate(df.flight_id.unique()):
            if i % 100 == 0:
                print(f"处理进度: {i}/{total_flights} ({i/total_flights*100:.1f}%)")
            
            flight_stats = analyze_flight_missing_data(df, flight_id)
            if flight_stats:
                all_flight_stats.append(flight_stats)
        
        return all_flight_stats, df
        
    except Exception as e:
        print(f"处理文件 {file_path} 时出错: {e}")
        return [], None

def generate_missing_data_report(all_stats, output_file="missing_data_report.txt"):
    """生成缺失数据分析报告"""
    
    if not all_stats:
        print("没有数据可分析")
        return
    
    # 关键字段
    key_fields = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']
    
    report_lines = []
    report_lines.append("=" * 60)
    report_lines.append("航迹数据缺失率和缺失窗口分析报告")
    report_lines.append("=" * 60)
    report_lines.append(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append(f"总航班数: {len(all_stats)}")
    report_lines.append("")
    
    # 整体统计
    total_points = sum([stat['total_points'] for stat in all_stats])
    avg_duration = np.mean([stat['duration_minutes'] for stat in all_stats if stat['duration_minutes'] > 0])
    
    report_lines.append("=== 整体统计 ===")
    report_lines.append(f"总轨迹点数: {total_points:,}")
    report_lines.append(f"平均航班时长: {avg_duration:.1f} 分钟")
    report_lines.append(f"平均每航班轨迹点数: {total_points/len(all_stats):.0f}")
    report_lines.append("")
    
    # 按字段分析缺失情况
    for field in key_fields:
        report_lines.append(f"=== {field.upper()} 字段缺失分析 ===")
        
        # 收集该字段的所有统计数据
        field_stats = []
        all_windows = []
        flights_with_missing = 0
        
        for stat in all_stats:
            if field in stat['missing_stats']:
                field_stat = stat['missing_stats'][field]
                field_stats.append(field_stat)
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
        
        report_lines.append(f"  有缺失数据的航班数: {flights_with_missing}/{len(all_stats)} ({flights_with_missing/len(all_stats)*100:.1f}%)")
        report_lines.append(f"  平均缺失率: {avg_missing_rate:.2f}%")
        report_lines.append(f"  中位数缺失率: {median_missing_rate:.2f}%")
        
        # 缺失率分布
        high_missing = sum([1 for rate in missing_rates if rate > 50])
        medium_missing = sum([1 for rate in missing_rates if 10 < rate <= 50])
        low_missing = sum([1 for rate in missing_rates if 0 < rate <= 10])
        no_missing = sum([1 for rate in missing_rates if rate == 0])
        
        report_lines.append(f"  缺失率分布:")
        report_lines.append(f"    无缺失 (0%): {no_missing} 航班")
        report_lines.append(f"    低缺失 (0-10%): {low_missing} 航班")
        report_lines.append(f"    中等缺失 (10-50%): {medium_missing} 航班")
        report_lines.append(f"    高缺失 (>50%): {high_missing} 航班")
        
        # 缺失窗口分析
        if all_windows:
            report_lines.append(f"  缺失窗口统计:")
            report_lines.append(f"    总缺失窗口数: {len(all_windows)}")
            report_lines.append(f"    平均窗口长度: {np.mean(all_windows):.1f} 个点")
            report_lines.append(f"    中位数窗口长度: {np.median(all_windows):.1f} 个点")
            report_lines.append(f"    最大窗口长度: {max(all_windows)} 个点")
            report_lines.append(f"    窗口长度分布:")
            
            # 窗口长度分布
            short_windows = sum([1 for w in all_windows if w <= 5])
            medium_windows = sum([1 for w in all_windows if 5 < w <= 20])
            long_windows = sum([1 for w in all_windows if 20 < w <= 100])
            very_long_windows = sum([1 for w in all_windows if w > 100])
            
            report_lines.append(f"      短窗口 (≤5点): {short_windows} ({short_windows/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      中等窗口 (6-20点): {medium_windows} ({medium_windows/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      长窗口 (21-100点): {long_windows} ({long_windows/len(all_windows)*100:.1f}%)")
            report_lines.append(f"      超长窗口 (>100点): {very_long_windows} ({very_long_windows/len(all_windows)*100:.1f}%)")
        
        report_lines.append("")
    
    # 写入报告文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))
    
    # 同时打印到控制台
    print('\n'.join(report_lines))
    print(f"\n报告已保存到: {output_file}")

def main():
    """主函数"""
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    # 分析插值后的数据
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
    
    # 选择几个文件进行分析（避免处理时间过长）
    selected_files = parquet_files[:3]  # 分析前3个文件
    print(f"将分析以下文件: {[os.path.basename(f) for f in selected_files]}")
    
    all_stats = []
    
    for file_path in selected_files:
        print(f"\n处理文件: {os.path.basename(file_path)}")
        file_stats, df = analyze_dataset_missing_data(file_path, sample_size=200)  # 每个文件随机选择200个航班
        all_stats.extend(file_stats)
        print(f"完成文件 {os.path.basename(file_path)}, 累计分析 {len(all_stats)} 个航班")
    
    if all_stats:
        print(f"\n开始生成报告...")
        generate_missing_data_report(all_stats, "missing_data_analysis_report.txt")
    else:
        print("没有收集到任何统计数据")

if __name__ == "__main__":
    main()