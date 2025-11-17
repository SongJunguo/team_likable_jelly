#!/usr/bin/env python3
"""
NaN检测脚本 - 确保最终轨迹0个NaN

功能：
- 检查指定目录下所有parquet文件的NaN
- 统计每列的NaN数量
- 生成详细报告
- 如果发现NaN，返回非0退出码

用法：
    python check_nan_in_final.py \
        --data-dir /path/to/interpolated_clean_v1 \
        --out-file /path/to/nan_check_report.txt
"""

import pandas as pd
import argparse
from pathlib import Path
import sys
from datetime import datetime


def check_nan_in_file(file_path):
    """检查单个文件的NaN（仅检查核心6列）"""
    try:
        df = pd.read_parquet(file_path)

        if df.empty:
            return None

        # 只检查核心6列的NaN
        core_cols = ['latitude', 'longitude', 'altitude', 'groundspeed', 'vertical_rate']

        # track可能是track或track_unwrapped
        if 'track' in df.columns:
            core_cols.append('track')
        elif 'track_unwrapped' in df.columns:
            core_cols.append('track_unwrapped')

        # 只检查存在的列
        existing_cols = [col for col in core_cols if col in df.columns]

        nan_counts = df[existing_cols].isna().sum()
        total_nans = nan_counts.sum()

        if total_nans > 0:
            return {
                'file': file_path.name,
                'total_nans': int(total_nans),
                'nan_by_column': nan_counts[nan_counts > 0].to_dict(),
                'total_rows': len(df),
                'checked_columns': existing_cols
            }
        return None
    except Exception as e:
        return {
            'file': file_path.name,
            'error': str(e)
        }


def main():
    parser = argparse.ArgumentParser(
        description='检查最终轨迹中的NaN，确保0个NaN'
    )
    parser.add_argument('--data-dir', required=True, help='数据目录')
    parser.add_argument('--out-file', required=True, help='输出报告文件')
    parser.add_argument('--pattern', default='*.parquet', help='文件匹配模式')
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"❌ 数据目录不存在: {data_dir}")
        sys.exit(1)

    files = sorted(data_dir.glob(args.pattern))
    if not files:
        print(f"❌ 未找到文件: {data_dir}/{args.pattern}")
        sys.exit(1)

    print(f"🔍 检查 {len(files)} 个文件...")

    # 逐文件检查
    issues = []
    error_files = []

    for f in files:
        result = check_nan_in_file(f)
        if result:
            if 'error' in result:
                error_files.append(result)
            else:
                issues.append(result)

    # 生成报告
    with open(args.out_file, 'w', encoding='utf-8') as out:
        out.write("=" * 60 + "\n")
        out.write("  NaN检测报告 - Clean-Segment-Interp 流程\n")
        out.write("=" * 60 + "\n\n")
        out.write(f"检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write(f"数据目录: {data_dir}\n")
        out.write(f"检查文件数: {len(files)}\n\n")

        if not issues and not error_files:
            out.write("✅ 检查完成：0个NaN！\n\n")
            out.write("所有轨迹数据质量合格。\n")
            print(f"✅ 质量检查通过：最终轨迹无NaN")
            print(f"   报告: {args.out_file}")
            sys.exit(0)

        # 有问题
        if issues:
            out.write(f"❌ 发现NaN！共{len(issues)}个文件有问题\n\n")
            out.write("=" * 60 + "\n")
            out.write("详细信息：\n")
            out.write("=" * 60 + "\n\n")

            total_nans = sum(issue['total_nans'] for issue in issues)

            for issue in issues:
                out.write(f"📁 文件: {issue['file']}\n")
                out.write(f"   总NaN数: {issue['total_nans']:,}\n")
                out.write(f"   总行数: {issue['total_rows']:,}\n")
                out.write(f"   NaN占比: {issue['total_nans']/issue['total_rows']*100:.2f}%\n")
                out.write(f"   各列NaN:\n")
                for col, count in issue['nan_by_column'].items():
                    out.write(f"     - {col}: {count:,}\n")
                out.write("\n")

            out.write("=" * 60 + "\n")
            out.write(f"汇总：总共 {total_nans:,} 个NaN\n")
            out.write("=" * 60 + "\n")

        if error_files:
            out.write(f"\n⚠️  错误文件（共{len(error_files)}个）：\n\n")
            for err in error_files:
                out.write(f"📁 {err['file']}: {err['error']}\n")

    # 打印到控制台
    print(f"❌ 质量检查失败：发现{len(issues)}个文件有NaN")
    print(f"   详细报告: {args.out_file}")

    sys.exit(1)


if __name__ == '__main__':
    main()
