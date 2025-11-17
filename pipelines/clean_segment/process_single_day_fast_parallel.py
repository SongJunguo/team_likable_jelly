#!/usr/bin/env python3
"""
一口气处理单日数据（轨迹级并行版）

相比process_single_day_fast.py的改进：
- 文件级串行：一个parquet一个parquet处理
- 轨迹级并行：每个parquet内部按flight_id并行
- 适合测试单日数据（充分利用多核）

优势：
- 单个文件内部充分并行
- 测试单日数据时速度快
- 避免文件级并行的I/O竞争

用法：
    python process_single_day_fast_parallel.py \
        -t_in rawtrajectories/2022-01-01.parquet \
        -t_out interpolated_clean_v1/interpolated_2022-01-01.parquet \
        -strategy clean_segment_interp \
        -smooth 1e-2 \
        --workers 24
"""

import argparse
import os
import sys
from functools import partial
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def import_modules():
    """延迟导入，避免路径问题"""
    global read_trajectories, interpolate, readers

    from pipelines.clean_segment import filter_trajs as filter_trajs_module
    from pipelines.clean_segment import interpolate as interpolate_module
    from tools.io import readers as readers_module

    read_trajectories = filter_trajs_module.read_trajectories
    interpolate = interpolate_module.interpolate
    readers = readers_module


import_modules()


# ========== 阶段2：切分（单个flight_id） ==========

def split_one_flight(args):
    """处理单个flight_id的切分

    Args:
        args: (fid, group, required_cols, max_dt, min_points, min_duration)

    Returns:
        切分后的segments列表
    """
    fid, g, required_cols, max_dt, min_points, min_duration = args

    # 排序
    g = g.sort_values('timestamp').reset_index(drop=True)

    # 仅保留必需列均非NaN的行
    g_valid = g.dropna(subset=required_cols)
    if g_valid.shape[0] < min_points:
        return []

    # 以Δt大于阈值切段
    ts = g_valid['timestamp'].values.astype('datetime64[ns]')
    if len(ts) == 0:
        return []

    dt = np.r_[0, (ts[1:] - ts[:-1]).astype('timedelta64[s]').astype(np.int64)]
    breaks = dt > max_dt
    group_id = breaks.cumsum()

    # 分组过滤
    segments = []
    for gid, seg in g_valid.groupby(group_id, sort=True):
        if seg.shape[0] < min_points:
            continue

        dur = int((seg['timestamp'].iloc[-1] - seg['timestamp'].iloc[0]) / pd.to_timedelta(1, 's'))
        if dur < min_duration:
            continue

        segments.append(seg.copy())

    return segments


def split_by_time_parallel(df, required_cols, max_dt=20, min_points=30, min_duration=120, workers=24):
    """并行按时间切分轨迹（flight_id级并行）

    Args:
        df: 过滤后的DataFrame
        required_cols: 必需的列（不能有NaN）
        max_dt: 最大时间间隔（秒）
        min_points: 最小点数
        min_duration: 最小时长（秒）
        workers: 并行worker数

    Returns:
        切分后的DataFrame（带segment标识）
    """
    if df.empty:
        return pd.DataFrame()

    # 按flight_id分组，准备并行任务
    tasks = []
    for fid, g in df.groupby('flight_id', sort=False):
        tasks.append((fid, g, required_cols, max_dt, min_points, min_duration))

    # 并行处理
    with Pool(workers) as pool:
        results = pool.map(split_one_flight, tasks)

    # 收集所有segments
    all_segments = []
    for segs in results:
        all_segments.extend(segs)

    if not all_segments:
        return pd.DataFrame()

    # 按时间排序所有segments并重新编号
    all_segs = []
    seg_idx = 1

    for seg in all_segments:
        fid = seg['flight_id'].iloc[0]
        seg = seg.copy()
        seg['original_flight_id'] = np.int64(fid)
        seg['segment_index'] = np.int32(seg_idx)
        seg['flight_id'] = np.int64(fid * 10000 + seg_idx)

        t0 = pd.to_datetime(seg['timestamp'].iloc[0], utc=True)
        t1 = pd.to_datetime(seg['timestamp'].iloc[-1], utc=True)
        seg['flight_seg_info'] = (
            f"{int(fid)}_s{seg_idx}_{t0.strftime('%Y%m%dT%H%M%S')}Z_{t1.strftime('%H%M%S')}"
        )

        all_segs.append(seg)
        seg_idx += 1

    return pd.concat(all_segs, ignore_index=True)


# ========== 阶段3：插值（直接调用interpolate.py） ==========

def interpolate_one_segment(args):
    """对单个segment插值（直接调用interpolate.py的interpolate函数）

    Args:
        args: (flight_id, segment_df, smooth, max_hole_size)

    Returns:
        插值后的segment
    """
    flight_id, df, smooth, max_hole_size = args

    if df.empty:
        return df

    try:
        # 直接调用interpolate.py的interpolate函数
        result = interpolate(df, smooth, max_hole_size)

        # 转换track_unwrapped为track（原interpolate()输出track_unwrapped）
        if "track_unwrapped" in result.columns:
            result["track"] = result["track_unwrapped"] % 360
            result = result.drop(columns="track_unwrapped", errors='ignore')

        return result

    except Exception as e:
        print(f"⚠️  插值失败 flight_id={flight_id}: {e}")
        return pd.DataFrame()


def interpolate_parallel(df, smooth=1e-2, workers=24, max_hole_size=20):
    """并行插值所有segments（segment级并行）

    Args:
        df: 切分后的DataFrame
        smooth: 平滑系数
        workers: 并行worker数

    Returns:
        插值后的DataFrame
    """
    if df.empty:
        return df

    # 准备（与interpolate.py:136-137一致）
    for v in ["flight_id", "icao24"]:
        if v in df.columns:
            df[v] = df[v].astype(np.int64)

    # 添加特征（与interpolate.py:137一致）
    df = readers.convert_from_SI(
        readers.add_features_trajectories(
            readers.convert_to_SI(df)
        )
    )

    # 按flight_id分组，准备并行任务
    tasks = []
    for fid, group in df.groupby("flight_id", sort=False):
        tasks.append((fid, group, smooth, max_hole_size))

    print(f"    并行插值 {len(tasks)} 个segments（{workers} workers）...")

    # 并行处理
    with Pool(workers) as pool:
        results = pool.map(interpolate_one_segment, tasks)

    # 过滤空结果并合并
    valid_results = [r for r in results if not r.empty]

    if not valid_results:
        return pd.DataFrame()

    result = pd.concat(valid_results, ignore_index=True)

    # 清理level_1列（与interpolate.py:139一致）
    result = result.drop(columns="level_1", errors='ignore')

    # 确保track_unwrapped转换为track（每个segment已转换，这里double-check）
    if "track_unwrapped" in result.columns:
        result["track"] = result["track_unwrapped"] % 360
        result = result.drop(columns="track_unwrapped", errors='ignore')

    return result


# ========== 主流程 ==========

def process_one_day_fast_parallel(input_file, output_file, strategy='clean_segment_interp', smooth=1e-2,
                                   max_dt=20, min_points=30, min_duration=120, workers=24,
                                   max_hole_size=20):
    """一口气处理单日数据（轨迹级并行）

    Args:
        input_file: 输入原始轨迹文件
        output_file: 输出插值轨迹文件
        strategy: 过滤策略
        smooth: 插值平滑系数
        max_dt: 最大时间间隔（秒）
        min_points: 最小点数
        min_duration: 最小时长（秒）
        workers: 并行worker数
    """
    print(f"▶️  快速并行处理: {os.path.basename(input_file)}")
    print(f"    并行度: {workers} workers")

    # 阶段1：过滤（串行，因为filter链不好并行化）
    print(f"  [1/3] 过滤... (串行)")
    df_filtered = read_trajectories(input_file, strategy)
    num_flights = df_filtered['flight_id'].nunique() if not df_filtered.empty else 0
    print(f"    过滤后: {num_flights} 个航班, {len(df_filtered):,} 行")

    if df_filtered.empty:
        print("    ⚠️  过滤后无数据")
        pd.DataFrame().to_parquet(output_file, index=False)
        return

    # 阶段2：切分（并行）
    print(f"  [2/3] 切分... (轨迹级并行)")
    required_cols = ['latitude', 'longitude', 'altitude']
    df_segmented = split_by_time_parallel(
        df_filtered,
        required_cols=required_cols,
        max_dt=max_dt,
        min_points=min_points,
        min_duration=min_duration,
        workers=workers
    )

    if df_segmented.empty:
        print("    ⚠️  切分后无有效segment")
        pd.DataFrame().to_parquet(output_file, index=False)
        return

    unique_segments = df_segmented['flight_id'].nunique()
    print(f"    切分后: {unique_segments} 个segments, {len(df_segmented):,} 行")

    # 阶段3：插值（并行）
    print(f"  [3/3] 插值... (segment级并行)")
    df_final = interpolate_parallel(df_segmented, smooth, workers, max_hole_size)
    print(f"    插值后: {len(df_final):,} 行")

    # 检查NaN（确保0个）
    nan_count = df_final.isna().sum().sum()
    if nan_count > 0:
        print(f"    ⚠️  警告：发现 {nan_count} 个NaN！")
    else:
        print(f"    ✅ 质量检查：0个NaN")

    # 输出
    os.makedirs(os.path.dirname(output_file) or '.', exist_ok=True)
    df_final.to_parquet(output_file, index=False)
    print(f"  ✅ 完成: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='快速并行模式：一口气处理单日数据（轨迹级并行）'
    )
    parser.add_argument('-t_in', required=True, help='输入原始轨迹文件')
    parser.add_argument('-t_out', required=True, help='输出插值轨迹文件')
    parser.add_argument('-strategy', default='clean_segment_interp', help='过滤策略')
    parser.add_argument('-smooth', type=float, default=1e-2, help='插值平滑系数')
    parser.add_argument('--max-dt', type=int, default=20, help='最大时间间隔（秒）')
    parser.add_argument('--min-points', type=int, default=30, help='最小点数')
    parser.add_argument('--min-duration', type=int, default=120, help='最小时长（秒）')
    parser.add_argument('--workers', type=int, default=24, help='并行worker数')
    parser.add_argument('--max-hole-size', type=int, default=20, help='最大插值间隔（秒）')
    args = parser.parse_args()

    process_one_day_fast_parallel(
        args.t_in,
        args.t_out,
        args.strategy,
        args.smooth,
        args.max_dt,
        args.min_points,
        args.min_duration,
        args.workers,
        args.max_hole_size
    )


if __name__ == '__main__':
    main()
