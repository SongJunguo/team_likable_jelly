# -*- coding: utf-8 -*-
import logging

import numpy as np
import pandas as pd
from numba import jit
from numpy import arctan2, cos, degrees, radians, sin
from scipy.ndimage import gaussian_filter1d


def setup_logging(log_level: str) -> None:
    level = getattr(logging, str(log_level).upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


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
    opening_result = np.empty(n, dtype=data.dtype)
    for i in range(n):
        start = max(0, i - half_window)
        end = min(n, i + half_window + 1)
        opening_result[i] = np.max(temp[start:end])

    # --- 步骤 2: Closing (去除向下的尖刺) ---
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
    """计算两点间的米制距离 (Haversine公式)"""
    r = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2.0) ** 2
    return 2 * r * arctan2(np.sqrt(a), np.sqrt(1 - a))


@jit(nopython=True)
def numba_kinematic_reconstruction(
    lats, lons, gs_smooth, trk_smooth, timestamps, max_speed_error_factor=2.0
):
    """
    使用地速和航向角约束经纬度：检测 GPS 跳变并用航位推算 (Dead Reckoning) 重构。
    """
    n = len(lats)
    lats_out = np.empty(n, dtype=np.float32)
    lons_out = np.empty(n, dtype=np.float32)

    lats_out[0] = lats[0]
    lons_out[0] = lons[0]

    r = 6371000.0

    for i in range(1, n):
        dt = timestamps[i] - timestamps[i - 1]

        if dt <= 0 or dt > 10.0:
            lats_out[i] = lats_out[i - 1]
            lons_out[i] = lons_out[i - 1]
            continue

        # gs_smooth 单位 knots，转 m/s
        v_mps = gs_smooth[i] * 0.514444
        expected_dist = v_mps * dt

        # 允许一定的误差缓冲区 (例如 2.0 倍 + 50米)
        limit_dist = expected_dist * max_speed_error_factor + 50.0

        meas_dist = haversine_dist(lats_out[i - 1], lons_out[i - 1], lats[i], lons[i])

        if meas_dist <= limit_dist:
            lats_out[i] = lats[i]
            lons_out[i] = lons[i]
        else:
            trk_rad = radians(trk_smooth[i])
            vn = v_mps * cos(trk_rad)
            ve = v_mps * sin(trk_rad)

            d_lat_rad = vn * dt / r
            new_lat_rad = radians(lats_out[i - 1]) + d_lat_rad
            lats_out[i] = degrees(new_lat_rad)

            d_lon_rad = ve * dt / (r * cos(new_lat_rad))
            lons_out[i] = degrees(radians(lons_out[i - 1]) + d_lon_rad)

    return lats_out, lons_out


@jit(nopython=True)
def numba_complementary_filter(alt_raw, vr_data, timestamps, base_alpha, vr_min, vr_max):
    """高度重构 (互补滤波)"""
    n = len(alt_raw)
    alt_fused = np.empty(n, dtype=np.float32)

    if np.isnan(alt_raw[0]):
        alt_fused[0] = 0.0
    else:
        alt_fused[0] = alt_raw[0]

    for i in range(1, n):
        dt = timestamps[i] - timestamps[i - 1]

        if dt <= 0 or dt > 15.0:
            alt_fused[i] = alt_fused[i - 1] if np.isnan(alt_raw[i]) else alt_raw[i]
            continue

        current_vr_min = abs(vr_data[i] * 60.0)
        dynamic_factor = 1.0
        if current_vr_min > 3000:
            excess = (current_vr_min - 3000) / 3000.0
            if excess > 1.0:
                excess = 1.0
            dynamic_factor = 1.0 - (0.1 * excess)

        alpha = base_alpha * dynamic_factor

        pred_alt = alt_fused[i - 1] + vr_data[i] * dt

        if np.isnan(alt_raw[i]):
            alt_fused[i] = pred_alt
        else:
            alt_fused[i] = alpha * pred_alt + (1 - alpha) * alt_raw[i]

    return alt_fused


class FlightProcessor:
    def __init__(self, config):
        self.config = config
        self.MS_TO_KNOTS = 1.94384

    def _calc_tas(self, df: pd.DataFrame) -> pd.DataFrame:
        req_cols = ["groundspeed", "track", "u_component_of_wind", "v_component_of_wind"]
        if not all(c in df.columns for c in req_cols):
            return df

        gs = df["groundspeed"].values.astype(np.float32)
        trk_rad = np.deg2rad(df["track"].values.astype(np.float32))

        u_ground = gs * np.sin(trk_rad)
        v_ground = gs * np.cos(trk_rad)

        u_wind = df["u_component_of_wind"].values * self.MS_TO_KNOTS
        v_wind = df["v_component_of_wind"].values * self.MS_TO_KNOTS

        df["TAS"] = np.sqrt((u_ground - u_wind) ** 2 + (v_ground - v_wind) ** 2).astype(
            np.float32
        )
        return df

    def process(self, df: pd.DataFrame):
        # =========================================================
        # 1) 元数据列（若上游已 merge 进来，则在此提取并暂存）
        # =========================================================
        meta_cols = ["ades", "adep", "aircraft_type"]
        metadata = {}
        for col in meta_cols:
            if col in df.columns:
                metadata[col] = df[col].iloc[0]
                df = df.drop(columns=[col])

        if "groundspeed" in df.columns:
            mask = (df["groundspeed"] >= self.config.gs_min) & (df["groundspeed"] <= self.config.gs_max)
            df = df[mask].copy()
            if len(df) < self.config.min_len:
                return None

        limits = {
            "latitude": (-90, 90),
            "longitude": (-180, 180),
            "altitude": (self.config.h_min, self.config.h_max),
        }
        for col, (vmin, vmax) in limits.items():
            if col in df.columns:
                df[col] = df[col].clip(lower=vmin, upper=vmax)

        # =========================================================
        # 2) 按时间戳排序
        # =========================================================
        if "timestamp" not in df.columns:
            return None
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        # =========================================================
        # 3) 去除静态数据：经纬度不变的行
        # =========================================================
        lat_diff = df["latitude"].diff()
        lon_diff = df["longitude"].diff()
        is_static = (lat_diff == 0) & (lon_diff == 0)
        is_static.iloc[0] = False
        df = df[~is_static].copy()
        if len(df) < self.config.min_len:
            return None

        # =========================================================
        # 4) 时间间隔切段：dt > 5s 切分；每段 < 60 点丢弃
        # =========================================================
        df = df.sort_values("timestamp")
        df["dt"] = df["timestamp"].diff().dt.total_seconds().fillna(0)
        segment_ids = (df["dt"] > 5.0).cumsum()

        valid_segments = []
        for _, group in df.groupby(segment_ids):
            if len(group) >= 60:
                valid_segments.append(group)

        if not valid_segments:
            logging.debug("所有分段长度均小于 60，丢弃该航班。")
            return None

        df = pd.concat(valid_segments).reset_index(drop=True)
        logging.debug(f"分段清洗完成: 保留了 {len(valid_segments)} 个有效段，总行数 {len(df)}")
        if len(df) < self.config.min_len:
            return None

        # =========================================================
        # 5) Resample：按秒重采样 + 线性插值
        # =========================================================
        df = df.set_index("timestamp")
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df_resampled = df[numeric_cols].resample(self.config.resample_freq).mean()
        df_resampled = df_resampled.interpolate(method="linear", limit_direction="both")
        df = df_resampled.reset_index()
        df = df.dropna(subset=["latitude", "longitude"])
        if len(df) < self.config.min_len:
            return None

        # =========================================================
        # 6) 对地速/航向角高斯平滑
        # =========================================================
        sigma = self.config.gaussian_sigma
        df["groundspeed"] = gaussian_filter1d(df["groundspeed"].values, sigma=sigma)

        trk_rad = np.deg2rad(df["track"].values)
        trk_sin = np.sin(trk_rad)
        trk_cos = np.cos(trk_rad)
        trk_sin_smooth = gaussian_filter1d(trk_sin, sigma=sigma)
        trk_cos_smooth = gaussian_filter1d(trk_cos, sigma=sigma)
        df["track"] = np.rad2deg(np.arctan2(trk_sin_smooth, trk_cos_smooth))
        df["track"] = (df["track"] + 360) % 360

        # =========================================================
        # 7) 动力学约束重构 + 最终平滑
        # =========================================================
        ts_nanos = df["timestamp"].values.astype(np.int64)
        ts_float = ts_nanos.astype(np.float64) / 1e9
        lats = df["latitude"].values.astype(np.float32)
        lons = df["longitude"].values.astype(np.float32)
        gs = df["groundspeed"].values.astype(np.float32)
        trk = df["track"].values.astype(np.float32)

        lats_recon, lons_recon = numba_kinematic_reconstruction(
            lats, lons, gs, trk, ts_float, max_speed_error_factor=2.0
        )

        geo_sigma = max(1.0, sigma * 0.5)
        df["latitude"] = gaussian_filter1d(lats_recon, sigma=geo_sigma)
        df["longitude"] = gaussian_filter1d(lons_recon, sigma=geo_sigma)

        # =========================================================
        # 8) 合成真空速 (TAS)
        # =========================================================
        df = self._calc_tas(df)

        # =========================================================
        # 9) 高度重构：垂直速率插值/平滑/截断 + 互补滤波 + 形态学滤波
        # =========================================================
        if "vertical_rate" in df.columns and "altitude" in df.columns:
            df["vertical_rate"] = df["vertical_rate"].interpolate(
                method="linear", limit_direction="both"
            )
            df["vertical_rate"] = df["vertical_rate"].fillna(0)
            df["vertical_rate"] = gaussian_filter1d(
                df["vertical_rate"].values, sigma=self.config.gaussian_sigma
            )
            df["vertical_rate"] = df["vertical_rate"].clip(self.config.vr_min, self.config.vr_max)

            df["altitude"] = df["altitude"].interpolate().bfill()

            alt_raw = df["altitude"].values.astype(np.float64)
            vr_fps = (df["vertical_rate"] / 60.0).values.astype(np.float64)

            alt_fused = numba_complementary_filter(
                alt_raw,
                vr_fps,
                ts_float,
                self.config.alt_fusion_weight,
                self.config.vr_min,
                self.config.vr_max,
            )

            alt_final = numba_morphological_filter(alt_fused, window_size=20)
            df["altitude"] = alt_final.astype(np.float32)

        # =========================================================
        # 收尾：把元数据加回去（若存在）
        # =========================================================
        for col, val in metadata.items():
            df[col] = val

        return df


def worker_process_flight(group_data, config):
    flight_id, df = group_data
    setup_logging(config.log_level)

    if df.empty:
        return None

    if "flight_id" not in df.columns:
        df["flight_id"] = flight_id

    processor = FlightProcessor(config)
    try:
        processed_df = processor.process(df.copy())
        if processed_df is not None:
            processed_df["flight_id"] = flight_id
            return processed_df
    except Exception:
        if str(config.log_level).upper() == "DEBUG":
            logging.exception(f"Flight {flight_id} error")
        return None

    return None

