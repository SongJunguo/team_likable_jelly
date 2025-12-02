#!/usr/bin/env python3
"""
使用Polars高性能检查OpenSky数据集的数据质量
支持全量365天数据分析，充分利用多核CPU和大内存
"""

import polars as pl
import os
import glob
from datetime import datetime
import argparse
from pathlib import Path
import time

def setup_polars():
    """配置Polars以充分利用系统资源"""
    # 设置线程数为CPU核心数
    pl.Config.set_tbl_rows(20)  # 限制表格显示行数
    # Polars会自动使用所有可用CPU核心
    print(f"Polars配置完成，将使用所有可用CPU核心进行并行处理")

def get_file_list(data_dir, start_date=None, end_date=None, limit=None):
    """获取要处理的文件列表"""
    pattern = os.path.join(data_dir, "*.parquet")
    all_files = sorted(glob.glob(pattern))
    
    if not all_files:
        raise FileNotFoundError(f"在目录 {data_dir} 中未找到parquet文件")
    
    # 日期过滤
    if start_date or end_date:
        filtered_files = []
        for file in all_files:
            filename = os.path.basename(file)
            if filename.endswith('.parquet'):
                date_str = filename.replace('.parquet', '')
                try:
                    file_date = datetime.strptime(date_str, '%Y-%m-%d')
                    if start_date and file_date < start_date:
                        continue
                    if end_date and file_date > end_date:
                        continue
                    filtered_files.append(file)
                except ValueError:
                    # 不是日期格式的文件，跳过
                    continue
        all_files = filtered_files
    
    # 数量限制
    if limit and limit > 0:
        all_files = all_files[:limit]
    
    return all_files

def check_missing_values_batch(files, data_type=""):
    """批量检查缺失值 - 内存高效版本"""
    print(f"\n=== {data_type} 缺失值分析 (批量处理) ===")
    
    total_rows = 0
    column_missing = {}
    columns = None  # 初始化columns变量
    
    for i, file in enumerate(files):
        print(f"  处理文件 {i+1}/{len(files)}: {os.path.basename(file)}")
        
        try:
            # 使用lazy loading减少内存占用
            df = pl.scan_parquet(file)
            
            # 收集列信息（只在第一个文件时执行）
            if i == 0:
                columns = df.collect_schema().names()
                for col in columns:
                    column_missing[col] = 0
            
            # 如果columns还是None，跳过这个文件
            if columns is None:
                continue
            
            # 计算每列的缺失值
            missing_stats = df.select([
                pl.len().alias("total_rows"),
                *[pl.col(col).null_count().alias(f"{col}_missing") for col in columns]
            ]).collect()
            
            row_count = missing_stats["total_rows"][0]
            total_rows += row_count
            
            # 累加缺失值计数
            for col in columns:
                column_missing[col] += missing_stats[f"{col}_missing"][0]
                
        except Exception as e:
            print(f"    警告: 处理文件 {file} 时出错: {e}")
            continue
    
    # 输出结果
    print(f"\n总行数: {total_rows:,}")
    print("缺失值统计:")
    
    for col, missing_count in column_missing.items():
        if missing_count > 0:
            missing_pct = (missing_count / total_rows) * 100
            print(f"  {col}: {missing_count:,} ({missing_pct:.3f}%)")
    
    return column_missing, total_rows

def check_data_ranges_batch(files, data_type=""):
    """批量检查数据范围异常"""
    print(f"\n=== {data_type} 数据范围分析 (批量处理) ===")
    
    # 定义合理范围
    reasonable_ranges = {
        'latitude': (-90, 90),
        'longitude': (-180, 180),
        'altitude': (-2000, 50000),  # 米
        'groundspeed': (0, 1000),    # km/h
        'track': (0, 360),
        'vertical_rate': (-10000, 10000)  # ft/min
    }
    
    total_rows = 0
    global_stats = {}
    out_of_range_counts = {}
    
    for i, file in enumerate(files):
        print(f"  处理文件 {i+1}/{len(files)}: {os.path.basename(file)}")
        
        try:
            df = pl.scan_parquet(file)
            
            # 只检查存在的字段
            available_fields = [col for col in reasonable_ranges.keys() 
                              if col in df.collect_schema().names()]
            
            if not available_fields:
                continue
            
            # 计算统计信息
            stats_exprs = [pl.len().alias("total_rows")]
            
            for field in available_fields:
                min_val, max_val = reasonable_ranges[field]
                stats_exprs.extend([
                    pl.col(field).min().alias(f"{field}_min"),
                    pl.col(field).max().alias(f"{field}_max"),
                    ((pl.col(field) < min_val) | (pl.col(field) > max_val)).sum().alias(f"{field}_out_of_range")
                ])
            
            stats = df.select(stats_exprs).collect()
            
            row_count = stats["total_rows"][0]
            total_rows += row_count
            
            # 更新全局统计
            for field in available_fields:
                if field not in global_stats:
                    global_stats[field] = {'min': float('inf'), 'max': float('-inf')}
                    out_of_range_counts[field] = 0
                
                field_min = stats[f"{field}_min"][0]
                field_max = stats[f"{field}_max"][0]
                field_out_of_range = stats[f"{field}_out_of_range"][0]
                
                if field_min is not None:
                    global_stats[field]['min'] = min(global_stats[field]['min'], field_min)
                if field_max is not None:
                    global_stats[field]['max'] = max(global_stats[field]['max'], field_max)
                
                out_of_range_counts[field] += field_out_of_range
                
        except Exception as e:
            print(f"    警告: 处理文件 {file} 时出错: {e}")
            continue
    
    # 输出结果
    print(f"\n总行数: {total_rows:,}")
    for field, ranges in reasonable_ranges.items():
        if field in global_stats:
            min_val, max_val = ranges
            actual_min = global_stats[field]['min']
            actual_max = global_stats[field]['max']
            out_count = out_of_range_counts[field]
            
            if out_count > 0:
                pct = (out_count / total_rows) * 100
                print(f"  {field} 超出合理范围: {out_count:,} ({pct:.3f}%)")
            
            print(f"    实际范围: {actual_min:.2f} 到 {actual_max:.2f}")
            print(f"    合理范围: {min_val} 到 {max_val}")

def analyze_flight_stats_batch(files, data_type=""):
    """批量分析航班统计信息"""
    print(f"\n=== {data_type} 航班统计分析 (批量处理) ===")
    
    total_flights = set()
    total_points = 0
    
    # 使用流式处理来避免内存溢出
    flight_point_counts = {}
    
    for i, file in enumerate(files):
        print(f"  处理文件 {i+1}/{len(files)}: {os.path.basename(file)}")
        
        try:
            # 计算每个文件的航班统计
            df = pl.scan_parquet(file)
            
            file_stats = df.group_by("flight_id").agg([
                pl.len().alias("point_count")
            ]).collect()
            
            file_flight_count = len(file_stats)
            file_point_count = file_stats["point_count"].sum()
            
            print(f"    航班数: {file_flight_count:,}, 轨迹点数: {file_point_count:,}")
            
            # 更新全局统计
            for row in file_stats.iter_rows():
                flight_id, point_count = row
                total_flights.add(flight_id)
                if flight_id in flight_point_counts:
                    flight_point_counts[flight_id] += point_count
                else:
                    flight_point_counts[flight_id] = point_count
            
            total_points += file_point_count
            
        except Exception as e:
            print(f"    警告: 处理文件 {file} 时出错: {e}")
            continue
    
    # 输出总体统计
    print(f"\n总体统计:")
    print(f"  唯一航班数: {len(total_flights):,}")
    print(f"  总轨迹点数: {total_points:,}")
    print(f"  平均每航班轨迹点数: {total_points / len(total_flights):.1f}")
    
    # 分析轨迹点分布
    if flight_point_counts:
        point_counts = list(flight_point_counts.values())
        point_counts.sort()
        
        print(f"  轨迹点数分布:")
        print(f"    最少: {min(point_counts)}")
        print(f"    最多: {max(point_counts)}")
        print(f"    中位数: {point_counts[len(point_counts)//2]}")
        print(f"    25%分位数: {point_counts[len(point_counts)//4]}")
        print(f"    75%分位数: {point_counts[len(point_counts)*3//4]}")

def compare_datasets(raw_files, interp_files):
    """对比原始数据和插值数据"""
    print(f"\n=== 原始数据 vs 插值数据对比 ===")
    
    if not raw_files or not interp_files:
        print("缺少原始数据或插值数据文件，跳过对比分析")
        return
    
    # 确保文件对应关系
    raw_dates = set(os.path.basename(f).replace('.parquet', '') for f in raw_files)
    interp_dates = set(os.path.basename(f).replace('.parquet', '') for f in interp_files)
    common_dates = raw_dates & interp_dates
    
    print(f"找到 {len(common_dates)} 个共同日期的数据进行对比")
    
    if not common_dates:
        print("没有找到共同日期的数据文件")
        return
    
    # 选择前几个日期进行详细对比
    sample_dates = sorted(list(common_dates))[:5]
    
    for date in sample_dates:
        print(f"\n对比日期: {date}")
        
        raw_file = None
        interp_file = None
        
        for f in raw_files:
            if date in os.path.basename(f):
                raw_file = f
                break
        
        for f in interp_files:
            if date in os.path.basename(f):
                interp_file = f
                break
        
        if not raw_file or not interp_file:
            continue
        
        try:
            # 加载数据进行对比
            raw_df = pl.scan_parquet(raw_file)
            interp_df = pl.scan_parquet(interp_file)
            
            # 基本统计对比
            raw_stats = raw_df.select([
                pl.len().alias("total_points"),
                pl.col("flight_id").n_unique().alias("unique_flights")
            ]).collect()
            
            interp_stats = interp_df.select([
                pl.len().alias("total_points"),
                pl.col("flight_id").n_unique().alias("unique_flights")
            ]).collect()
            
            raw_points = raw_stats["total_points"][0]
            raw_flights = raw_stats["unique_flights"][0]
            interp_points = interp_stats["total_points"][0]
            interp_flights = interp_stats["unique_flights"][0]
            
            print(f"  原始数据: {raw_flights:,} 航班, {raw_points:,} 轨迹点")
            print(f"  插值数据: {interp_flights:,} 航班, {interp_points:,} 轨迹点")
            
            point_change = ((interp_points - raw_points) / raw_points) * 100
            flight_change = ((interp_flights - raw_flights) / raw_flights) * 100
            
            print(f"  变化: 航班数 {flight_change:+.1f}%, 轨迹点数 {point_change:+.1f}%")
            
        except Exception as e:
            print(f"  错误: 处理日期 {date} 时出错: {e}")

def main():
    parser = argparse.ArgumentParser(description='高性能数据质量检测工具')
    parser.add_argument('--raw-dir', default='../opensky_2024_PRC_dataset/rawtrajectories',
                       help='原始轨迹数据目录')
    parser.add_argument('--interp-dir', default='../opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories',
                       help='插值轨迹数据目录')
    parser.add_argument('--start-date', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, help='限制处理的文件数量 (用于测试)')
    parser.add_argument('--skip-interp', action='store_true', help='跳过插值数据分析')
    parser.add_argument('--skip-comparison', action='store_true', help='跳过数据对比')
    
    args = parser.parse_args()
    
    # 配置Polars
    setup_polars()
    
    # 解析日期
    start_date = None
    end_date = None
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    
    print("=== OpenSky数据集高性能质量检测 ===")
    print(f"CPU核心数: {os.cpu_count()}")
    print(f"处理日期范围: {args.start_date or '全部'} 到 {args.end_date or '全部'}")
    if args.limit:
        print(f"文件数量限制: {args.limit}")
    
    start_time = time.time()
    
    # 检查原始数据
    print(f"\n检查原始轨迹数据目录: {args.raw_dir}")
    if os.path.exists(args.raw_dir):
        raw_files = get_file_list(args.raw_dir, start_date, end_date, args.limit)
        print(f"找到 {len(raw_files)} 个原始数据文件")
        
        if raw_files:
            check_missing_values_batch(raw_files, "原始轨迹数据")
            check_data_ranges_batch(raw_files, "原始轨迹数据")
            analyze_flight_stats_batch(raw_files, "原始轨迹数据")
    else:
        print(f"原始数据目录不存在: {args.raw_dir}")
        raw_files = []
    
    # 检查插值数据
    interp_files = []
    if not args.skip_interp:
        print(f"\n检查插值轨迹数据目录: {args.interp_dir}")
        if os.path.exists(args.interp_dir):
            interp_files = get_file_list(args.interp_dir, start_date, end_date, args.limit)
            print(f"找到 {len(interp_files)} 个插值数据文件")
            
            if interp_files:
                check_missing_values_batch(interp_files, "插值轨迹数据")
                check_data_ranges_batch(interp_files, "插值轨迹数据")
                analyze_flight_stats_batch(interp_files, "插值轨迹数据")
        else:
            print(f"插值数据目录不存在: {args.interp_dir}")
    
    # 数据对比
    if not args.skip_comparison and raw_files and interp_files:
        compare_datasets(raw_files, interp_files)
    
    total_time = time.time() - start_time
    print(f"\n=== 分析完成 ===")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"建议: 基于以上分析结果选择合适的数据预处理策略")

if __name__ == "__main__":
    main()