# -*- coding: utf-8 -*-
import argparse
import os
import logging
import multiprocessing
import pandas as pd
import numpy as np
import gc
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from scipy.ndimage import gaussian_filter1d
from numba import jit
from numpy import cos, sin, radians, arctan2, degrees, pi

# ==========================================
# 日志配置
# ==========================================
def setup_logging(log_level):
    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

# ==========================================
# Numba 加速核心算法
# ==========================================

@jit(nopython=True)
def numba_morphological_filter(data, window_size=20):
    """
    形态学滤波器 (1D Morphological Filter)
    针对去除宽度小于 window_size 的持续性尖刺。
    
    逻辑:
    1. Opening (开运算): 去除正向尖刺 (先 Min 后 Max)
    2. Closing (闭运算): 去除负向尖刺 (先 Max 后 Min)
    """
    n = len(data)
    temp = np.empty(n, dtype=data.dtype)
    output = np.empty(n, dtype=data.dtype)
    
    half_window = window_size // 2

    # --- 步骤 1: Opening (去除向上的尖刺) ---
    # 1.1 Erosion (腐蚀): 滑动窗口最小值
    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        temp[i] = np.min(data[start:end])
        
    # 1.2 Dilation (膨胀): 滑动窗口最大值 (作用在腐蚀后的数据上)
    # 注意：为了节省内存，我们可以直接写回 output，但做 Closing 时需要再用 output
    # 这里先生成 opening_result
    opening_result = np.empty(n, dtype=data.dtype)
    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        opening_result[i] = np.max(temp[start:end])

    # --- 步骤 2: Closing (去除向下的尖刺) ---
    # 作用在 Opening 的结果上
    
    # 2.1 Dilation (膨胀): 滑动窗口最大值
    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        temp[i] = np.max(opening_result[start:end])
        
    # 2.2 Erosion (腐蚀): 滑动窗口最小值
    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        output[i] = np.min(temp[start:end])
        
    return output

@jit(nopython=True)
def haversine_dist(lat1, lon1, lat2, lon2):
    """
    计算两点间的米制距离 (Haversine公式)
    """
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2.0)**2 + cos(phi1) * cos(phi2) * sin(dlambda/2.0)**2
    return 2 * R * arctan2(np.sqrt(a), np.sqrt(1 - a))

@jit(nopython=True)
def numba_kinematic_reconstruction(lats, lons, gs_smooth, trk_smooth, timestamps, max_speed_error_factor=2.0):
    """
    步骤 7: 使用地速和航向角约束经纬度，进行剔除并且推算
    
    逻辑:
    1. 信任平滑后的 GS 和 Track。
    2. 检查当前点 GPS 位置与上一个可信点的距离。
    3. 如果距离 > (地速 * dt * 系数)，认为 GPS 漂移/跳变。
    4. 对坏点使用航位推算 (Dead Reckoning) 进行重构。
    """
    n = len(lats)
    lats_out = np.empty(n, dtype=np.float32)
    lons_out = np.empty(n, dtype=np.float32)
    
    # 初始点信任
    lats_out[0] = lats[0]
    lons_out[0] = lons[0]
    
    # 地球半径 (近似)
    R = 6371000.0
    
    for i in range(1, n):
        dt = timestamps[i] - timestamps[i-1]
        
        # 异常时间间隔保护 (虽然 resample 后通常是 1s)
        if dt <= 0 or dt > 10.0:
            lats_out[i] = lats_out[i-1]
            lons_out[i] = lons_out[i-1]
            continue
            
        # 当前动力学允许的最大移动距离
        # v (m/s) * t (s)
        # gs_smooth 单位是 knots，转 m/s
        v_mps = gs_smooth[i] * 0.514444
        expected_dist = v_mps * dt
        
        # 允许一定的误差缓冲区 (例如 2.0 倍 + 50米)
        # 如果 GPS 突然跳了几公里，肯定超过这个阈值
        limit_dist = expected_dist * max_speed_error_factor + 50.0
        
        # 计算测量点与上一个可信点(reconstructed)的距离
        meas_dist = haversine_dist(lats_out[i-1], lons_out[i-1], lats[i], lons[i])
        
        # === 核心约束逻辑 ===
        if meas_dist <= limit_dist:
            # 测量值在物理允许范围内，信任测量值
            # (也可以选择在这里做融合，但这里选择信任测量以保留真实轨迹特征)
            lats_out[i] = lats[i]
            lons_out[i] = lons[i]
        else:
            # 测量值超出物理极限 (跳变/异常)，进行推算 (Reconstruct)
            # 使用平滑后的航向和地速推算新位置
            # DR: pos = prev_pos + velocity_vector * dt
            
            trk_rad = radians(trk_smooth[i])
            vn = v_mps * cos(trk_rad)
            ve = v_mps * sin(trk_rad)
            
            d_lat_rad = vn * dt / R
            # 简单球面近似
            new_lat_rad = radians(lats_out[i-1]) + d_lat_rad
            lats_out[i] = degrees(new_lat_rad)
            
            # 经度修正: d_lon = ve * dt / (R * cos(lat))
            d_lon_rad = ve * dt / (R * cos(new_lat_rad))
            lons_out[i] = degrees(radians(lons_out[i-1]) + d_lon_rad)
            
    return lats_out, lons_out

@jit(nopython=True)
def numba_complementary_filter(alt_raw, vr_data, timestamps, base_alpha, vr_min, vr_max):
    """
    步骤 10: 高度重构 (互补滤波)
    """
    n = len(alt_raw)
    alt_fused = np.empty(n, dtype=np.float32)
    
    if np.isnan(alt_raw[0]):
        alt_fused[0] = 0.0
    else:
        alt_fused[0] = alt_raw[0]
        
    for i in range(1, n):
        dt = timestamps[i] - timestamps[i-1]

        if dt <= 0 or dt > 15.0: 
            alt_fused[i] = alt_fused[i-1] if np.isnan(alt_raw[i]) else alt_raw[i]
            continue
        
        # 动态权重
        current_vr_min = abs(vr_data[i] * 60.0)
        dynamic_factor = 1.0
        if current_vr_min > 3000:
            excess = (current_vr_min - 3000) / 3000.0
            if excess > 1.0: excess = 1.0
            dynamic_factor = 1.0 - (0.1 * excess)
            
        alpha = base_alpha * dynamic_factor
        
        # 预测
        pred_alt = alt_fused[i-1] + vr_data[i] * dt
        
        if np.isnan(alt_raw[i]):
            alt_fused[i] = pred_alt
        else:
            alt_fused[i] = alpha * pred_alt + (1 - alpha) * alt_raw[i]
            
    return alt_fused

# ==========================================
# 核心处理类
# ==========================================
class FlightProcessor:
    def __init__(self, config):
        self.config = config
        self.MS_TO_KNOTS = 1.94384

    def _calc_tas(self, df):
        """步骤 9: 合成真空速 (TAS)"""
        req_cols = ['groundspeed', 'track', 'u_component_of_wind', 'v_component_of_wind']
        if not all(c in df.columns for c in req_cols):
            return df
        
        # 使用已经平滑过的 groundspeed 和 track
        gs = df['groundspeed'].values.astype(np.float32)
        trk_rad = np.deg2rad(df['track'].values.astype(np.float32))
        
        u_ground = gs * np.sin(trk_rad)
        v_ground = gs * np.cos(trk_rad)
        
        # 风分量 (m/s -> knots)
        u_wind = df['u_component_of_wind'].values * self.MS_TO_KNOTS
        v_wind = df['v_component_of_wind'].values * self.MS_TO_KNOTS
        
        df['TAS'] = np.sqrt((u_ground - u_wind)**2 + (v_ground - v_wind)**2).astype(np.float32)
        return df

    def process(self, df):

        # =========================================================
        # 1. 提取元数据列
        # =========================================================
        meta_cols = ['ades_id', 'adep_id', 'aircraft_type_id']
        metadata = {}
        for col in meta_cols:
            if col in df.columns:
                # 提取第一行的元数据作为整个航班的属性
                metadata[col] = df[col].iloc[0]
                # 暂时删除，避免干扰后续 resample
                df = df.drop(columns=[col])

        if 'groundspeed' in df.columns:
            # mask 为 True 表示保留，False 表示丢弃
            mask = (df['groundspeed'] >= self.config.gs_min) & \
                   (df['groundspeed'] <= self.config.gs_max)
            
            # 这一步会物理删除 mask 为 False 的所有行
            df = df[mask].copy()
            
            # 如果过滤后剩下的数据太少，直接丢弃整个航班
            if len(df) < self.config.min_len:
                return None
            
        limits = {
            'latitude': (-90, 90), 'longitude': (-180, 180),
            'altitude': (self.config.h_min, self.config.h_max)
        }
        for col, (vmin, vmax) in limits.items():
            if col in df.columns:
                df[col] = df[col].clip(lower=vmin, upper=vmax)

        # =========================================================
        # 2. 按时间戳排序
        # =========================================================
        if 'timestamp' not in df.columns:
            return None
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)

        # =========================================================
        # 3. 去除静态数据
        # 规则: 如果该数据经纬度不变(悬停了)，丢弃这一整行
        # =========================================================
        # 计算经纬度的一阶差分
        lat_diff = df['latitude'].diff()
        lon_diff = df['longitude'].diff()
        
        # 标记变化的行 (第一行默认保留，fillna(True))
        # 这里的逻辑是：如果 lat_diff == 0 且 lon_diff == 0，则是静态
        is_static = (lat_diff == 0) & (lon_diff == 0)
        # 第一行 diff 是 NaN，我们设为 False (不删除)
        is_static.iloc[0] = False
        
        # 过滤掉静态行
        df = df[~is_static].copy()
        
        if len(df) < self.config.min_len: return None

        # =========================================================
        # 4. 计算时间戳间隔与分段保留 (REVISED)
        # 规则: 60s 间隔切段，每段少于 60 点废除，保留剩下的
        # =========================================================
        df = df.sort_values('timestamp') # 再次确保顺序
        df['dt'] = df['timestamp'].diff().dt.total_seconds().fillna(0)
        
        # 1. 标记切分点: 只要时间间隔 > 60s，就是一个新段
        # 2. 使用 cumsum 生成连续的 segment_id (如 0, 0, 0, 1, 1, 2, 2...)
        segment_ids = (df['dt'] > 5.0).cumsum()
        
        valid_segments = []
        
        # 3. 按段分组，筛选长度 >= 60 的段
        for seg_id, group in df.groupby(segment_ids):
            if len(group) >= 60:
                valid_segments.append(group)
        
        if not valid_segments:
            logging.debug("所有分段长度均小于 60，丢弃该航班。")
            return None
            
        # 4. 合并保留的段
        df = pd.concat(valid_segments).reset_index(drop=True)
        logging.debug(f"分段清洗完成: 保留了 {len(valid_segments)} 个有效段，总行数 {len(df)}")

        if len(df) < self.config.min_len: return None

        # =========================================================
        # 5. 开始 Resample (重采样)
        # =========================================================
        df = df.set_index('timestamp')
        
        # 保存非数值列以便恢复 (如果有其他非元数据列)
        # 这里主要关注核心数值
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        
        # Resample 1S 并进行线性插值
        df_resampled = df[numeric_cols].resample(self.config.resample_freq).mean()
        df_resampled = df_resampled.interpolate(method='linear', limit_direction='both')
        
        # 恢复 timestamp 列
        df = df_resampled.reset_index()
        
        # 确保没有全空行
        df = df.dropna(subset=['latitude', 'longitude'])
        
        if len(df) < self.config.min_len: return None

        # =========================================================
        # 6. 对地速航向角进行高斯平滑
        # =========================================================
        sigma = self.config.gaussian_sigma
        
        # 平滑 Groundspeed
        df['groundspeed'] = gaussian_filter1d(df['groundspeed'].values, sigma=sigma)
        
        # 平滑 Track (航向角需要处理 0/360 环绕问题)
        # 将角度分解为 sin/cos 进行平滑，再合成
        trk_rad = np.deg2rad(df['track'].values)
        trk_sin = np.sin(trk_rad)
        trk_cos = np.cos(trk_rad)
        
        trk_sin_smooth = gaussian_filter1d(trk_sin, sigma=sigma)
        trk_cos_smooth = gaussian_filter1d(trk_cos, sigma=sigma)
        
        df['track'] = np.rad2deg(np.arctan2(trk_sin_smooth, trk_cos_smooth))
        # 归一化到 [0, 360)
        df['track'] = (df['track'] + 360) % 360

        # =========================================================
        # 7. 使用地速和航向角约束经纬度，进行剔除并且推算这里的值
        # & 7(b). 对经纬度进行滤波算法
        # =========================================================
        # 准备 Numba 数据
        ts_nanos = df['timestamp'].values.astype(np.int64)
        ts_float = ts_nanos.astype(np.float64) / 1e9
        lats = df['latitude'].values.astype(np.float32)
        lons = df['longitude'].values.astype(np.float32)
        gs = df['groundspeed'].values.astype(np.float32)
        trk = df['track'].values.astype(np.float32)
        
        # 7a. 动力学约束与重构 (Reconstruction)
        lats_recon, lons_recon = numba_kinematic_reconstruction(
            lats, lons, gs, trk, ts_float, max_speed_error_factor=2.0
        )
        
        # 7b. 对重构后的经纬度进行滤波算法 (最终平滑)
        # 这里使用较小的 sigma，因为主要噪声已经被重建步骤去除了
        # 目的是让推算出的直线段和原始段连接处更圆滑
        geo_sigma = max(1.0, sigma * 0.5) 
        df['latitude'] = gaussian_filter1d(lats_recon, sigma=geo_sigma)
        df['longitude'] = gaussian_filter1d(lons_recon, sigma=geo_sigma)
        
        # =========================================================
        # 8. 合成真空速 (TAS)
        # (注：用户描述中步骤顺序有点混，但我按逻辑顺序列出)
        # =========================================================
        df = self._calc_tas(df)

        # =========================================================
        # 9. 高度重构
        # =========================================================
        if 'vertical_rate' in df.columns and 'altitude' in df.columns:
            # 优化垂直速率处理：插值 -> 平滑 -> 截断
            # 1. 线性插值：填补中间的 NaN，而不是简单填 0 (防止爬升/下降过程中断)
            df['vertical_rate'] = df['vertical_rate'].interpolate(method='linear', limit_direction='both')
            
            # 2. 边缘填充：如果首尾还有 NaN，填 0
            df['vertical_rate'] = df['vertical_rate'].fillna(0)
            
            # 3. 高斯平滑：减少传感器噪声 (使用配置的 sigma)
            # 与 groundspeed/track 保持一致的平滑策略
            df['vertical_rate'] = gaussian_filter1d(df['vertical_rate'].values, sigma=self.config.gaussian_sigma)
            
            # 4. 物理范围截断
            df['vertical_rate'] = df['vertical_rate'].clip(self.config.vr_min, self.config.vr_max)
            
            # 高度本身也要插值
            df['altitude'] = df['altitude'].interpolate().bfill()
            
            # 准备数据
            alt_raw = df['altitude'].values.astype(np.float64)
            vr_fps = (df['vertical_rate'] / 60.0).values.astype(np.float64) # ft/min -> ft/sec
            
            alt_fused = numba_complementary_filter(
                alt_raw, vr_fps, ts_float, 
                self.config.alt_fusion_weight, 
                self.config.vr_min, self.config.vr_max
            )

            # 对积分重构后的数据进行形态学滤波
            alt_final = numba_morphological_filter(alt_fused, window_size=20)
            df['altitude'] = alt_final.astype(np.float32)

        # =========================================================
        # 收尾：把元数据加回去
        # =========================================================
        for col, val in metadata.items():
            df[col] = val
            
        return df

# ==========================================
# Worker 函数
# ==========================================
def worker_process_flight(group_data, config):
    flight_id, df = group_data
    # 简单的进程初始化日志（可选）
    setup_logging(config.log_level) 
    
    if df.empty: return None

    # 确保 Flight ID 存在
    if 'flight_id' not in df.columns:
        df['flight_id'] = flight_id
        
    processor = FlightProcessor(config)
    try:
        processed_df = processor.process(df.copy())
        if processed_df is not None:
            processed_df['flight_id'] = flight_id
            return processed_df
    except Exception as e:
        if config.log_level == "DEBUG":
            logging.exception(f"Flight {flight_id} error")
        return None
    return None

# ==========================================
# 主函数
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="航空轨迹数据预处理")
    
    parser.add_argument("--input_file", required=True, help="输入 Parquet 文件")
    parser.add_argument("--output_file", required=True, help="输出 Parquet 文件")
    
    parser.add_argument("--resample_freq", default="1S", help="重采样频率")
    parser.add_argument("--min_len", type=int, default=10, help="最小有效长度")
    parser.add_argument("--gaussian_sigma", type=float, default=2.0, help="平滑 Sigma")
    
    parser.add_argument("--h_min", type=float, default=-1000)
    parser.add_argument("--h_max", type=float, default=60000)
    parser.add_argument("--vr_min", type=float, default=-6000)
    parser.add_argument("--vr_max", type=float, default=6000)
    parser.add_argument("--gs_min", type=float, default=50)
    parser.add_argument("--gs_max", type=float, default=600)
    parser.add_argument("--alt_fusion_weight", type=float, default=0.95)
    
    parser.add_argument("--max_workers", type=int, default=os.cpu_count())
    parser.add_argument("--log_level", default="INFO")

    args = parser.parse_args()
    setup_logging(args.log_level)

    if not os.path.exists(args.input_file):
        logging.error("Input file not found.")
        return

    logging.info("读取数据...")
    
    # 仅读取必要列
    cols = [
        'flight_id', 'timestamp', 'latitude', 'longitude', 
        'altitude', 'groundspeed', 'track', 'vertical_rate',
        'u_component_of_wind', 'v_component_of_wind', 
        'ades_id', 'adep_id', 'aircraft_type_id'
    ]
    
    try:
        df = pd.read_parquet(args.input_file, columns=cols, engine='pyarrow')
        
        # 基础类型优化
        f32_cols = ['latitude', 'longitude', 'altitude', 'groundspeed', 'track', 
                    'vertical_rate', 'u_component_of_wind', 'v_component_of_wind']
        for c in f32_cols:
            if c in df.columns:
                df[c] = df[c].astype('float32')
                
        if 'flight_id' in df.columns:
            df['flight_id'] = df['flight_id'].astype('category')
            
    except Exception as e:
        logging.error(f"读取失败: {e}")
        return

    total = df['flight_id'].nunique()
    logging.info(f"开始处理 {total} 条轨迹...")

    results = []
    flight_groups = df.groupby('flight_id', observed=True)
    
    chunksize = max(1, total // (args.max_workers * 4))
    
    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        worker = partial(worker_process_flight, config=args)
        for i, res in enumerate(executor.map(worker, flight_groups, chunksize=chunksize)):
            if res is not None:
                results.append(res)
            if (i+1) % 1000 == 0:
                logging.info(f"进度: {i+1}/{total}")

    if results:
        logging.info("合并结果...")
        final_df = pd.concat(results, ignore_index=True)
        
        # 最终格式化
        out_cols = ['timestamp', 'flight_id', 'latitude', 'longitude', 
                    'altitude', 'TAS', 'track', 'ades_id', 'adep_id', 'aircraft_type_id']
        final_df = final_df[[c for c in out_cols if c in final_df.columns]]
        
        # 确保类型
        final_df['flight_id'] = final_df['flight_id'].astype(str)
        for c in ['ades_id', 'adep_id', 'aircraft_type_id']:
            if c in final_df.columns:
                final_df[c] = final_df[c].astype(str)
        
        if 'timestamp' in final_df.columns and pd.api.types.is_datetime64_any_dtype(final_df['timestamp']):
             final_df['timestamp'] = final_df['timestamp'].dt.tz_localize(None)

        os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
        final_df.to_parquet(args.output_file, index=False)
        logging.info(f"完成。保留行数: {len(final_df)}")
    else:
        logging.warning("没有数据保留下来。")

if __name__ == "__main__":
    multiprocessing.set_start_method("spawn", force=True)
    main()