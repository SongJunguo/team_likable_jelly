#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
小样本重生成 complete 数据（单日），用于验证“仅填内部洞+20s限洞”。

用法（建议在 opensky 环境）：
  python legacy/analysis_for_interpolation/regenerate_complete_sample.py \
    --date 2022-01-01 \
    --input_dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories \
    --output_dir complete_high_quality_trajectories__sample_2022-01-01

不会覆盖原目录；输出文件名为 complete_YYYY-MM-DD.parquet。
"""

import argparse
import os
import pandas as pd
from typing import Set

from regenerate_complete_dataset import CompleteDatasetGenerator


def load_high_quality_ids(path: str = 'high_quality_flight_ids.txt') -> Set[int]:
    ids: Set[int] = set()
    with open(path, 'r') as f:
        for line in f:
            s = line.strip()
            if s:
                ids.add(int(s))
    return ids


def main():
    parser = argparse.ArgumentParser(description='Regenerate complete (single day sample)')
    parser.add_argument('--date', required=True, help='日期，例如 2022-01-01')
    parser.add_argument('--input_dir', required=True, help='输入目录 classic_filtered_trajectories')
    parser.add_argument('--output_dir', required=True, help='输出目录（新的样本测试目录）')
    parser.add_argument('--ids_file', default='high_quality_flight_ids.txt', help='高质量ID列表路径')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    ids = load_high_quality_ids(args.ids_file)
    print(f'载入高质量航班ID: {len(ids):,} 条')

    in_file = os.path.join(args.input_dir, f'{args.date}.parquet')
    if not os.path.exists(in_file):
        raise FileNotFoundError(in_file)
    print(f'读取: {in_file}')
    df = pd.read_parquet(in_file)

    # 过滤航班
    df = df[df['flight_id'].isin(ids)]
    if df.empty:
        print('该日无高质量航班，退出。')
        return
    print(f'该日高质量航班记录数: {len(df):,} 行, 航班数: {df["flight_id"].nunique():,}')

    gen = CompleteDatasetGenerator()
    processed = []
    for i, (fid, g) in enumerate(df.groupby('flight_id'), 1):
        if i % 200 == 0:
            print(f'  进度: {i} 航班')
        out_df, res = gen.process_trajectory(g)
        if res['success'] and not out_df.empty:
            processed.append(out_df)

    if not processed:
        print('没有成功处理的航班。')
        return

    out = pd.concat(processed, ignore_index=True)
    out_file = os.path.join(args.output_dir, f'complete_{args.date}.parquet')
    out.to_parquet(out_file, index=False)
    print(f'✅ 已输出: {out_file}（{len(out):,} 行）')


if __name__ == '__main__':
    main()
