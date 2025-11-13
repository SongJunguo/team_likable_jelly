#!/usr/bin/env python3
"""
插值单日脚本

功能：
- 读取切分后的segments
- 对每个segment独立插值
- 输出：0个NaN的完整轨迹

用法：
    python interpolate_single_day.py \
        -t_in segmented_clean_v1/segmented_2022-01-01.parquet \
        -t_out interpolated_clean_v1/interpolated_2022-01-01.parquet \
        -smooth 1e-2
"""

import pandas as pd
import numpy as np
import argparse
import os
import sys

# 导入现有模块
sys.path.insert(0, os.path.dirname(__file__) + '/..')

from interpolate import interpolate
import readers as readers_module

DEFAULT_MAX_HOLE_SIZE = 20


def interpolate_segment_wrapper(df: pd.DataFrame, smooth: float, max_hole_size: int) -> pd.DataFrame:
    """对单个segment插值（直接调用interpolate.py的interpolate函数）

    注意：segment内部已保证时间连续（≤20s）
    """
    if df.empty:
        return df

    # 直接调用interpolate.py的interpolate函数
    result = interpolate(df, smooth, max_hole_size=max_hole_size)

    # 转换track_unwrapped为track（原interpolate()输出track_unwrapped）
    if "track_unwrapped" in result.columns:
        result["track"] = result["track_unwrapped"] % 360
        result = result.drop(columns="track_unwrapped", errors='ignore')

    return result


def interpolate_all(df, smooth=1e-2, max_hole_size=DEFAULT_MAX_HOLE_SIZE):
    """在内存中插值所有segments"""
    if df.empty:
        return df

    # 准备（与interpolate.py:136-137一致）
    for v in ["flight_id", "icao24"]:
        if v in df.columns:
            df[v] = df[v].astype(np.int64)

    # 添加特征（与interpolate.py:137一致）
    df = readers_module.convert_from_SI(
        readers_module.add_features_trajectories(
            readers_module.convert_to_SI(df)
        )
    )

    # 按flight_id分组插值（每个segment独立，调用interpolate.py）
    result = df.groupby("flight_id").apply(
        lambda x: interpolate_segment_wrapper(x, smooth, max_hole_size),
        include_groups=False
    ).reset_index()

    # 清理level_1列（与interpolate.py:139一致）
    result = result.drop(columns="level_1", errors='ignore')

    # 确保track_unwrapped转换为track（每个segment已转换，这里double-check）
    if "track_unwrapped" in result.columns:
        result["track"] = result["track_unwrapped"] % 360
        result = result.drop(columns="track_unwrapped", errors='ignore')

    return result


def main():
    parser = argparse.ArgumentParser(
        description='插值单日切分后的轨迹数据'
    )
    parser.add_argument('-t_in', required=True, help='输入切分后轨迹文件')
    parser.add_argument('-t_out', required=True, help='输出插值轨迹文件')
    parser.add_argument('-smooth', type=float, default=1e-2, help='插值平滑系数')
    parser.add_argument('--max-hole-size', type=int, default=None, help='最大插值间隔（秒），默认与MAX_DT一致')
    args = parser.parse_args()

    print(f"▶️  插值: {os.path.basename(args.t_in)}")

    # 读取切分后数据
    df = pd.read_parquet(args.t_in)
    num_segs = df['flight_id'].nunique()
    print(f"    输入: {num_segs} 个segments, {len(df):,} 行")

    max_hole_size = args.max_hole_size if args.max_hole_size is not None else DEFAULT_MAX_HOLE_SIZE
    if max_hole_size <= 0:
        raise ValueError("max-hole-size 必须为正数")
    print(f"    参数: smooth={args.smooth}, max_hole_size={max_hole_size}s")

    # 插值
    df_interp = interpolate_all(df, args.smooth, max_hole_size)
    print(f"    输出: {len(df_interp):,} 行")

    # 检查NaN（确保0个）
    nan_count = df_interp.isna().sum().sum()
    if nan_count > 0:
        print(f"    ⚠️  警告：发现 {nan_count} 个NaN！")
    else:
        print(f"    ✅ 质量检查：0个NaN")

    # 保存
    os.makedirs(os.path.dirname(args.t_out) or '.', exist_ok=True)
    df_interp.to_parquet(args.t_out, index=False)
    print(f"  ✅ 完成: {args.t_out}")


if __name__ == '__main__':
    main()
