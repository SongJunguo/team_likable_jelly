#!/usr/bin/env python3
"""
插值质量验证脚本
验证插值后的数据是否真的没有任何缺失值
"""

import pandas as pd
from pathlib import Path
import multiprocessing as mp
from functools import partial
from datetime import datetime
import argparse

DEFAULT_COLUMNS = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']


def load_dataframe(file_path):
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == '.parquet':
        return pd.read_parquet(path)
    if suffix == '.csv':
        return pd.read_csv(path)
    raise ValueError(f"不支持的文件格式: {suffix} ({path})")


def validate_single_file(task, required_columns=None, total_files=None):
    """验证单个插值文件的质量"""
    try:
        if isinstance(task, tuple):
            index, file_path = task
        else:
            index, file_path = None, task

        file_path = Path(file_path)

        if total_files and index is not None:
            print(f"▶️ [{index}/{total_files}] 正在处理: {file_path.name}")

        # 读取数据
        df = load_dataframe(file_path)
        
        if df.empty:
            return {
                'file': file_path.name,
                'total_points': 0,
                'trajectories': 0,
                'missing_values': {},
                'has_missing': False,
                'error': None
            }
        
        # 检查必需列
        if required_columns is None:
            required_columns = DEFAULT_COLUMNS
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
            'file': file_path.name,
            'total_points': len(df),
            'trajectories': trajectories,
            'missing_values': missing_values,
            'has_missing': total_missing > 0,
            'total_missing': total_missing,
            'error': None
        }
        
    except Exception as e:
        return {
            'file': file_path.name,
            'total_points': 0,
            'trajectories': 0,
            'missing_values': {},
            'has_missing': False,
            'error': str(e)
        }

def parse_args():
    parser = argparse.ArgumentParser(description="验证插值后的Parquet文件是否存在缺失值")
    parser.add_argument(
        "--input-dir",
        default="interpolated_trajectories",
        help="需要检查的Parquet目录，默认interpolated_trajectories"
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=min(mp.cpu_count(), 16),
        help="并行进程数，默认min(16, CPU核心数)"
    )
    parser.add_argument(
        "--output",
        help="验证报告输出文件，默认生成带时间戳的txt"
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        default=DEFAULT_COLUMNS,
        help="需要检查缺失值的列名列表"
    )
    parser.add_argument(
        "--suffixes",
        nargs="+",
        default=['.parquet'],
        help="需要检查的文件后缀，默认只检查.parquet"
    )
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        print(f"❌ 插值数据目录不存在: {input_dir}")
        return

    print("🔍 开始验证插值质量")
    print("=" * 60)

    suffixes = []
    for suffix in args.suffixes:
        suffix = suffix.lower()
        if not suffix.startswith('.'):
            suffix = f".{suffix}"
        suffixes.append(suffix)

    # 获取所有插值文件
    interpolated_files = sorted(
        [f for f in input_dir.iterdir() if f.is_file() and f.suffix.lower() in suffixes]
    )
    total_files = len(interpolated_files)
    print(f"找到 {total_files} 个插值文件")

    if not interpolated_files:
        print("❌ 没有找到插值文件")
        return

    # 多进程验证
    print("🔄 开始多进程验证...")
    num_processes = max(1, min(args.processes, mp.cpu_count()))
    print(f"使用 {num_processes} 个进程")

    # 准备任务列表
    tasks = list(enumerate(interpolated_files, start=1))

    validate_func = partial(
        validate_single_file,
        required_columns=args.columns,
        total_files=total_files
    )

    # 执行多进程验证并打印进度
    results = []
    with mp.Pool(processes=num_processes) as pool:
        for completed, result in enumerate(pool.imap_unordered(validate_func, tasks), start=1):
            results.append(result)
            print(f"✅ 已完成 {completed}/{total_files}: {result['file']}")
    
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
    required_columns = args.columns
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
    if args.output:
        report_file = args.output
    else:
        report_file = f"interpolation_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("插值质量验证报告\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"验证时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"验证文件数: {total_files}\n\n")
        
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
