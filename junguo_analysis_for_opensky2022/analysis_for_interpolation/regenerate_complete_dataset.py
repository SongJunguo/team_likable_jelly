#!/usr/bin/env python3
"""
重新生成完整的高质量轨迹数据集
使用正确的数据源，确保包含所有238,217条高质量轨迹
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
import multiprocessing as mp
from functools import partial
import traceback
from datetime import datetime

# 统一与 interpolate.py 的“限洞插值”策略：最大洞宽（秒）
MAX_HOLE_SIZE = 20  # seconds
DICO_HOLE_SIZE: dict[str, float] = {}

# 需要插值且必须满足 20s 限洞的核心测量列
MEASUREMENT_COLUMNS = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']


def compute_holes(t: np.ndarray, inans: np.ndarray) -> np.ndarray:
    """与 interpolate.py 等价的洞宽计算。

    返回数组形状为 (n, 1) 或 (n,)；后续用于按列遮蔽：
    - dt > MAX_HOLE_SIZE → 保持 NaN（不桥接大洞）
    - dt 为 NaN → 同样保持 NaN（无法计算洞宽的边界情况）
    """
    tnan = t.copy()
    tnan[inans] = np.nan
    tf = pd.DataFrame({"tf": tnan}, dtype=np.float64).ffill().values
    tb = pd.DataFrame({"tb": tnan}, dtype=np.float64).bfill().values
    return tb - tf

class CompleteDatasetGenerator:
    """完整数据集生成器"""
    
    def __init__(self):
        self.required_columns = ['flight_id', 'timestamp', *MEASUREMENT_COLUMNS]
    
    def remove_head_tail_nan(self, df):
        """移除头尾的NaN值"""
        if df.empty:
            return df
        
        # 基于经纬度来判断有效数据范围
        lat_valid = df['latitude'].notna()
        lon_valid = df['longitude'].notna()
        position_valid = lat_valid & lon_valid
        
        if not position_valid.any():
            return pd.DataFrame()
        
        # 找到第一个和最后一个有效位置的索引
        valid_indices = df.index[position_valid]
        first_valid = valid_indices[0]
        last_valid = valid_indices[-1]
        
        # 截取有效范围
        return df.loc[first_valid:last_valid].copy()
    
    def interpolate_column(self, series, method='linear'):
        """插值单个列（仅填内部洞，不做头尾外推）。"""
        if series.isna().all():
            return series

        # 对于track列，需要处理角度连续性（同样仅填内部洞）
        if series.name == 'track':
            return self.interpolate_track_angle(series)

        # 其他列使用线性插值，仅填内部洞，避免外推造成“延伸”斜坡
        # pandas>=1.1 支持 limit_area='inside'
        try:
            return series.interpolate(method=method, limit_area='inside')
        except TypeError:
            # 兼容极老版本 pandas：退化为不限定，但后续仍用洞宽遮蔽
            return series.interpolate(method=method)
    
    def interpolate_track_angle(self, track_series):
        """插值track角度，处理0/360度边界，仅填内部洞。"""
        if track_series.isna().all():
            return track_series

        track_rad = np.deg2rad(track_series)
        complex_track = np.exp(1j * track_rad)
        real_part = np.real(complex_track)
        imag_part = np.imag(complex_track)

        try:
            real_interp = (
                pd.Series(real_part, index=track_series.index)
                .interpolate(method='linear', limit_area='inside')
            )
            imag_interp = (
                pd.Series(imag_part, index=track_series.index)
                .interpolate(method='linear', limit_area='inside')
            )
        except TypeError:
            # 兼容极老版本 pandas：退化为不限定，后续仍用洞宽遮蔽
            real_interp = pd.Series(real_part, index=track_series.index).interpolate(method='linear')
            imag_interp = pd.Series(imag_part, index=track_series.index).interpolate(method='linear')

        interpolated_rad = np.angle(real_interp + 1j * imag_interp)
        interpolated_deg = np.rad2deg(interpolated_rad)
        interpolated_deg = (interpolated_deg + 360) % 360
        return pd.Series(interpolated_deg, index=track_series.index)
    
    def process_trajectory(self, df):
        """处理单条轨迹"""
        if df.empty:
            return pd.DataFrame(), {'success': False, 'reason': 'Empty trajectory'}
        
        # 按时间排序并去重，确保后续能用时间戳重建 1 Hz 网格
        df_sorted = df.sort_values('timestamp').drop_duplicates(subset='timestamp').reset_index(drop=True)
        
        # 移除头尾NaN
        df_trimmed = self.remove_head_tail_nan(df_sorted)
        
        if df_trimmed.empty:
            return pd.DataFrame(), {'success': False, 'reason': 'No valid position data after trimming'}

        # 记录列的原始 dtype，便于重采样后恢复（例如 flight_id 仍保持 int64）
        original_dtypes = df_trimmed.dtypes.to_dict()

        # 构建 1 Hz 时间网格，并将观测对齐到统一采样轴
        time_grid = pd.date_range(
            start=df_trimmed['timestamp'].iloc[0],
            end=df_trimmed['timestamp'].iloc[-1],
            freq='1S'
        )
        df_resampled = (
            df_trimmed
            .set_index('timestamp')
            .reindex(time_grid)
            .reset_index()
            .rename(columns={'index': 'timestamp'})
        )

        # 元数据列使用前向/后向填充，避免因 1 Hz 网格产生的新行缺乏 flight_id 等信息
        meta_cols = [c for c in df_resampled.columns if c not in MEASUREMENT_COLUMNS + ['timestamp']]
        if meta_cols:
            meta_filled = df_resampled[meta_cols].ffill().bfill()
            for col in meta_cols:
                target_dtype = original_dtypes.get(col)
                if target_dtype is not None:
                    try:
                        meta_filled[col] = meta_filled[col].astype(target_dtype)
                    except (ValueError, TypeError):
                        # 字段可能含有混合类型，保持填充值即可
                        pass
            df_resampled[meta_cols] = meta_filled

        # 对每个需要的列进行插值（仅填内部洞、不可跨大洞）
        df_interpolated = df_resampled.copy()

        # 时间轴（秒）
        t = ((df_interpolated['timestamp'] - df_interpolated['timestamp'].iloc[0]) / pd.to_timedelta(1, unit='s')).values.astype(np.float64)
        df_interpolated['t'] = t

        cols = MEASUREMENT_COLUMNS

        # 预计算各列洞宽
        ddt = {}
        for col in cols:
            if col in df_interpolated.columns:
                ddt[col] = compute_holes(df_interpolated['t'].values, np.isnan(df_interpolated[col].values))

        # 插值
        for col in cols:
            if col in df_interpolated.columns:
                df_interpolated[col] = self.interpolate_column(df_interpolated[col])

        # 洞宽遮蔽：跨大洞或无法估计洞宽的位置保持 NaN
        for col in cols:
            if col in df_interpolated.columns and col in ddt:
                df_interpolated[col] = df_interpolated[[col]].mask(ddt[col] > DICO_HOLE_SIZE.get(col, MAX_HOLE_SIZE))
                df_interpolated[col] = df_interpolated[[col]].mask(np.isnan(ddt[col]))
        # 清理临时列
        df_interpolated = df_interpolated.drop(columns=['t'])
        
        # 验证插值结果
        missing_counts = {}
        for col in ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 'vertical_rate']:
            if col in df_interpolated.columns:
                missing_counts[col] = df_interpolated[col].isna().sum()
        
        total_missing = sum(missing_counts.values())
        
        return df_interpolated, {
            'success': True,
            'points_before': len(df_sorted),
            'points_after': len(df_interpolated),
            'missing_counts': missing_counts,
            'total_missing': total_missing
        }

def load_high_quality_flight_ids(file_path='high_quality_flight_ids.txt'):
    """加载高质量轨迹ID列表"""
    try:
        with open(file_path, 'r') as f:
            flight_ids = [int(line.strip()) for line in f if line.strip()]
        return set(flight_ids)
    except Exception as e:
        print(f"加载高质量轨迹ID失败: {e}")
        return set()

def process_single_file(args):
    """处理单个日期文件"""
    date_file, target_flight_ids, input_dir, output_dir = args
    
    try:
        print(f"开始处理文件: {date_file}")
        
        # 读取数据
        file_path = os.path.join(input_dir, date_file)
        df = pd.read_parquet(file_path)
        
        # 筛选目标flight_id
        target_df = df[df['flight_id'].isin(target_flight_ids)]
        del df  # 释放内存
        
        if target_df.empty:
            print(f"文件 {date_file} 中没有找到目标轨迹")
            return {
                'date': date_file,
                'found_trajectories': 0,
                'processed_trajectories': 0,
                'success_trajectories': 0,
                'total_points_before': 0,
                'total_points_after': 0,
                'total_missing_after': 0
            }
        
        # 按flight_id分组处理
        generator = CompleteDatasetGenerator()
        processed_data = []
        stats = {
            'date': date_file,
            'found_trajectories': 0,
            'processed_trajectories': 0,
            'success_trajectories': 0,
            'total_points_before': 0,
            'total_points_after': 0,
            'total_missing_after': 0
        }
        
        flight_groups = list(target_df.groupby('flight_id'))
        print(f"文件 {date_file} 找到 {len(flight_groups)} 条目标轨迹")
        
        for i, (flight_id, group) in enumerate(flight_groups):
            if i % 100 == 0 and i > 0:
                print(f"  处理进度: {i}/{len(flight_groups)}")
            
            stats['found_trajectories'] += 1
            stats['processed_trajectories'] += 1
            stats['total_points_before'] += len(group)
            
            # 处理轨迹
            processed_traj, result = generator.process_trajectory(group)
            
            if result['success'] and not processed_traj.empty:
                processed_data.append(processed_traj)
                stats['success_trajectories'] += 1
                stats['total_points_after'] += len(processed_traj)
                stats['total_missing_after'] += result['total_missing']
        
        # 合并并保存处理后的数据
        if processed_data:
            final_df = pd.concat(processed_data, ignore_index=True)
            output_file = os.path.join(output_dir, f"complete_{date_file}")
            final_df.to_parquet(output_file, index=False)
            print(f"文件 {date_file} 处理完成，保存了 {stats['success_trajectories']} 条轨迹")
        else:
            print(f"文件 {date_file} 没有成功处理的轨迹")
        
        return stats
        
    except Exception as e:
        print(f"处理文件 {date_file} 时出错: {e}")
        traceback.print_exc()
        return {
            'date': date_file,
            'found_trajectories': 0,
            'processed_trajectories': 0,
            'success_trajectories': 0,
            'total_points_before': 0,
            'total_points_after': 0,
            'total_missing_after': 0,
            'error': str(e)
        }

def main():
    """主函数"""
    print("🚀 开始重新生成完整的高质量轨迹数据集")
    print("=" * 60)
    
    # 加载高质量轨迹ID
    high_quality_ids = load_high_quality_flight_ids()
    print(f"加载了 {len(high_quality_ids):,} 个高质量轨迹ID")
    
    if not high_quality_ids:
        print("❌ 没有找到高质量轨迹ID")
        return
    
    # 数据目录
    input_dir = "/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories"
    output_dir = "complete_high_quality_trajectories"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有日期文件
    date_files = [f for f in os.listdir(input_dir) if f.startswith('2022-') and f.endswith('.parquet')]
    date_files.sort()
    
    print(f"找到 {len(date_files)} 个日期文件")
    
    # 多进程处理
    num_processes = min(mp.cpu_count()//2, 8)  # 减少进程数，避免内存不足
    print(f"使用 {num_processes} 个进程进行多进程处理")
    
    # 准备参数
    args_list = [(date_file, high_quality_ids, input_dir, output_dir) for date_file in date_files]
    
    # 执行多进程处理
    with mp.Pool(processes=num_processes) as pool:
        results = pool.map(process_single_file, args_list)
    
    # 统计结果
    total_found = sum(r['found_trajectories'] for r in results)
    total_processed = sum(r['processed_trajectories'] for r in results)
    total_success = sum(r['success_trajectories'] for r in results)
    total_points_before = sum(r['total_points_before'] for r in results)
    total_points_after = sum(r['total_points_after'] for r in results)
    total_missing_after = sum(r['total_missing_after'] for r in results)
    files_with_data = sum(1 for r in results if r['found_trajectories'] > 0)
    
    print("\n📊 处理结果统计:")
    print("=" * 60)
    print(f"目标轨迹数量: {len(high_quality_ids):,}")
    print(f"找到轨迹数: {total_found:,}")
    print(f"处理轨迹数: {total_processed:,}")
    print(f"成功轨迹数: {total_success:,}")
    print(f"处理前总点数: {total_points_before:,}")
    print(f"处理后总点数: {total_points_after:,}")
    print(f"处理后缺失值: {total_missing_after:,}")
    print(f"有数据的文件数: {files_with_data}")
    print(f"成功率: {total_success/total_processed*100:.1f}%" if total_processed > 0 else "成功率: 0%")
    print(f"数据点保留率: {total_points_after/total_points_before*100:.1f}%" if total_points_before > 0 else "数据点保留率: 0%")
    print(f"缺失值率: {total_missing_after/total_points_after*100:.4f}%" if total_points_after > 0 else "缺失值率: 0%")
    
    # 生成详细报告
    report_file = f"complete_dataset_regeneration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("完整高质量轨迹数据集重新生成报告\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输出目录: {output_dir}\n\n")
        
        f.write("处理统计:\n")
        f.write(f"  目标轨迹数量: {len(high_quality_ids):,}\n")
        f.write(f"  找到轨迹数: {total_found:,}\n")
        f.write(f"  处理轨迹数: {total_processed:,}\n")
        f.write(f"  成功轨迹数: {total_success:,}\n")
        f.write(f"  处理前总点数: {total_points_before:,}\n")
        f.write(f"  处理后总点数: {total_points_after:,}\n")
        f.write(f"  处理后缺失值: {total_missing_after:,}\n")
        f.write(f"  有数据的文件数: {files_with_data}\n")
        f.write(f"  成功率: {total_success/total_processed*100:.1f}%\n" if total_processed > 0 else "  成功率: 0%\n")
        f.write(f"  数据点保留率: {total_points_after/total_points_before*100:.1f}%\n" if total_points_before > 0 else "  数据点保留率: 0%\n")
        f.write(f"  缺失值率: {total_missing_after/total_points_after*100:.4f}%\n" if total_points_after > 0 else "  缺失值率: 0%\n")
        
        f.write("\n每日处理详情:\n")
        for r in results:
            if r['found_trajectories'] > 0:
                f.write(f"  {r['date']}: 找到{r['found_trajectories']}条, 成功{r['success_trajectories']}条\n")
    
    print(f"\n📄 详细报告已保存到: {report_file}")
    
    if total_success > 0:
        print(f"\n✅ 重新生成完成! 成功处理了 {total_success:,} 条高质量轨迹")
        print(f"📁 输出目录: {output_dir}")
        print(f"🎯 数据质量: 缺失值率 {total_missing_after/total_points_after*100:.4f}%")
    else:
        print("\n❌ 没有成功处理任何轨迹，请检查数据源和ID匹配情况")

if __name__ == "__main__":
    main()
