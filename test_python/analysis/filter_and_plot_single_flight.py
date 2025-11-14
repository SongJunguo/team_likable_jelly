#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对单航班执行过滤并生成 Raw vs Filter PDF。"""

from __future__ import annotations

import argparse
import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from traffic.core import Traffic

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from filter_trajs import build_filter_chain, nointerpolate
from filterclassic import FilterSpatialPCAOutlier
from test_python.analysis.plot_flight_before_after_filter import plot_compare

RAW_DEFAULT = "/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories"
CORE_VALID_COLS = ["latitude", "longitude", "altitude"]
REASON_GROUPS: Dict[str, List[str]] = {
    "经纬约束": ["latitude", "longitude"],
    "高度约束": ["altitude"],
}
SPEED_Y_RANGE = (-100.0, 1000.0)
ACCEL_Y_LIMIT = 500.0
EARTH_RADIUS_M = 6_371_000.0


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def load_single_flight(path: str, flight_id: int) -> pd.DataFrame:
    col_candidates: List[str] = [
        "flight_id",
        "timestamp",
        "icao24",
        "latitude",
        "longitude",
        "altitude",
        "groundspeed",
        "track",
        "vertical_rate",
    ]
    try:
        df = pd.read_parquet(path, filters=[("flight_id", "=", flight_id)])
    except Exception:
        df = pd.read_parquet(path)
        df = df[df["flight_id"] == flight_id]
    if df.empty:
        raise ValueError(f"flight_id {flight_id} not found in {path}")
    cols = [c for c in col_candidates if c in df.columns]
    df = df[cols].copy()
    df["flight_id"] = df["flight_id"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def filter_single_flight(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    chain = build_filter_chain(strategy)
    filtered = (
        Traffic(df)
        .filter(filter=chain, strategy=nointerpolate)
        .eval(max_workers=1)
        .data
    )
    return filtered.reset_index(drop=True)


def _count_valid_points(df: pd.DataFrame, cols: List[str]) -> int:
    if not cols:
        return len(df)
    mask = df[cols].notna().all(axis=1)
    return int(mask.sum())


def _compute_reason_breakdown(df_raw: pd.DataFrame, df_filtered: pd.DataFrame) -> Dict[str, int]:
    if len(df_raw) != len(df_filtered):
        return {}
    breakdown: Dict[str, int] = {}
    for label, cols in REASON_GROUPS.items():
        if not cols:
            continue
        group_mask = np.zeros(len(df_raw), dtype=bool)
        for col in cols:
            if col not in df_raw.columns or col not in df_filtered.columns:
                continue
            raw_vals = df_raw[col].to_numpy()
            filt_vals = df_filtered[col].to_numpy()
            col_mask = (~pd.isna(raw_vals)) & (pd.isna(filt_vals))
            if group_mask.shape[0] != col_mask.shape[0]:
                continue
            group_mask |= col_mask
        count = int(group_mask.sum())
        if count > 0:
            breakdown[label] = count
    return breakdown


def summarize_filter_effect(df_raw: pd.DataFrame, df_filtered: pd.DataFrame) -> Tuple[Dict[str, float], Dict[str, int]]:
    common_cols = [c for c in CORE_VALID_COLS if c in df_raw.columns and c in df_filtered.columns]
    raw_valid = _count_valid_points(df_raw, common_cols)
    filtered_valid = _count_valid_points(df_filtered, common_cols)
    removed = max(raw_valid - filtered_valid, 0)
    retention = filtered_valid / raw_valid if raw_valid > 0 else 0.0
    summary = {
        "raw_valid": raw_valid,
        "filtered_valid": filtered_valid,
        "removed": removed,
        "retention_ratio": retention,
        "removed_ratio": 1 - retention if raw_valid > 0 else 0.0,
    }
    reason_breakdown = _compute_reason_breakdown(df_raw, df_filtered)
    return summary, reason_breakdown


def print_summary(summary: Dict[str, float], breakdown: Dict[str, int]) -> None:
    raw_valid = summary["raw_valid"]
    filtered_valid = summary["filtered_valid"]
    removed = summary["removed"]
    print("📊 过滤统计")
    print(f"  原始有效点数: {raw_valid}")
    print(f"  过滤后有效点数: {filtered_valid}")
    if raw_valid > 0:
        print(f"  保留比例: {filtered_valid / raw_valid:.2%}")
        print(f"  删除点数: {removed} ({removed / raw_valid:.2%})")
    else:
        print("  原始数据无有效点（lat/lon/alt 均缺失）")
    if breakdown:
        print("  主要失效类别（单点可归属多个类别）：")
        for label, count in breakdown.items():
            ratio = (count / raw_valid) if raw_valid > 0 else 0.0
            print(f"    - {label}: {count} ({ratio:.2%})")


def _haversine_distance(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Haversine距离（米），与 FilterMaxSpeedSkipNaNWithVoting 相同原理。"""
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return EARTH_RADIUS_M * c


def _ensure_strictly_increasing(ts: np.ndarray, *arrays: np.ndarray) -> Tuple[np.ndarray, ...]:
    """移除时间非递增的点，保证与过滤器相同的跨NaN逻辑。"""
    if len(ts) == 0:
        return (ts, *arrays)
    keep_indices = [0]
    for i in range(1, len(ts)):
        if ts[i] > ts[keep_indices[-1]]:
            keep_indices.append(i)
    keep_indices_arr = np.array(keep_indices, dtype=int)
    filtered = (ts[keep_indices_arr],) + tuple(arr[keep_indices_arr] for arr in arrays)
    return filtered


def compute_speed_and_accel(df: pd.DataFrame) -> pd.DataFrame:
    """按照跨NaN逻辑计算水平速度/加速度（单位：m/s, m/s²），与 FilterMaxSpeedSkipNaNWithVoting 保持一致。"""
    required = ["timestamp", "latitude", "longitude"]
    if any(col not in df.columns for col in required):
        return pd.DataFrame(columns=["timestamp", "speed_mps", "accel_mps2"])

    timestamps = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    result = pd.DataFrame(
        {
            "timestamp": timestamps,
            "speed_mps": np.full(len(df), np.nan),
            "accel_mps2": np.full(len(df), np.nan),
        }
    )
    if df.empty:
        return result

    lat = df["latitude"].to_numpy(dtype=float)
    lon = df["longitude"].to_numpy(dtype=float)
    ts_numeric = timestamps.to_numpy(dtype="datetime64[ns]").astype("int64") / 1e9

    valid_mask = (~np.isnan(lat)) & (~np.isnan(lon)) & (~timestamps.isna())
    if valid_mask.sum() < 2:
        return result

    idx_valid = np.flatnonzero(valid_mask)
    lat_valid = lat[valid_mask]
    lon_valid = lon[valid_mask]
    ts_valid = ts_numeric[valid_mask]

    ts_valid, lat_valid, lon_valid, idx_valid = _ensure_strictly_increasing(
        ts_valid, lat_valid, lon_valid, idx_valid
    )
    if len(ts_valid) < 2:
        return result

    dt = np.diff(ts_valid)
    if np.any(dt <= 0):
        return result

    ground_dist = _haversine_distance(lat_valid[:-1], lon_valid[:-1], lat_valid[1:], lon_valid[1:])
    speed = ground_dist / dt

    accel = np.full(len(ts_valid), np.nan)
    if len(ts_valid) >= 3:
        diff_speed = np.diff(speed)
        dt_avg = dt[1:] + dt[:-1]
        accel[1:-1] = 2.0 * diff_speed / dt_avg

    result.loc[idx_valid[1:], "speed_mps"] = speed
    if len(idx_valid) > 2:
        result.loc[idx_valid[1:-1], "accel_mps2"] = accel[1:-1]
    return result


def plot_speed_accel(
    df_raw_metrics: pd.DataFrame,
    df_filt_metrics: pd.DataFrame,
    out_pdf: str,
) -> bool:
    """绘制速度/加速度对比图，返回是否成功绘图。"""
    data_pairs = [
        (df_raw_metrics, "Raw", "tab:gray"),
        (df_filt_metrics, "Filter", "tab:blue"),
    ]
    has_speed = any(
        (not df.empty) and df["speed_mps"].notna().any() for df, _, _ in data_pairs
    )
    has_accel = any(
        (not df.empty) and df["accel_mps2"].notna().any() for df, _, _ in data_pairs
    )
    if not (has_speed or has_accel):
        print("⚠️ 无法绘制速度/加速度图：缺少有效数据")
        return False

    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    speed_plotted = False
    accel_plotted = False
    for df_metrics, label, color in data_pairs:
        if df_metrics.empty:
            continue
        if has_speed and df_metrics["speed_mps"].notna().any():
            axes[0].plot(df_metrics["timestamp"], df_metrics["speed_mps"], color=color, alpha=0.85, label=label)
            speed_plotted = True
        if has_accel and df_metrics["accel_mps2"].notna().any():
            axes[1].plot(df_metrics["timestamp"], df_metrics["accel_mps2"], color=color, alpha=0.85, label=label)
            accel_plotted = True

    axes[0].set_ylabel("Speed (m/s)")
    axes[1].set_ylabel("Acceleration (m/s²)")
    axes[1].set_xlabel("UTC time")
    for ax in axes:
        ax.grid(True, alpha=0.3)
    if speed_plotted:
        axes[0].legend(loc="best")
        axes[0].set_ylim(*SPEED_Y_RANGE)
    if accel_plotted:
        axes[1].legend(loc="best")
        axes[1].set_ylim(-ACCEL_Y_LIMIT, ACCEL_Y_LIMIT)
    fig.suptitle("Horizontal Speed/Acceleration (lat/lon only)")
    fig.tight_layout()
    out_path = Path(out_pdf)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)
    plt.close(fig)
    print(f"📈 Saved speed/accel plot to {out_pdf}")
    return True


def default_metrics_path(out_pdf: str) -> str:
    path = Path(out_pdf)
    if path.suffix.lower() == ".pdf":
        return str(path.with_name(f"{path.stem}_metrics{path.suffix}"))
    return f"{out_pdf}_metrics.pdf"


def _attach_metrics(df_target: pd.DataFrame, metrics: Optional[pd.DataFrame], prefix: str = "") -> pd.DataFrame:
    if metrics is None or len(metrics) != len(df_target):
        return df_target
    cols = []
    for col in ["speed_mps", "accel_mps2"]:
        if col in metrics.columns:
            new_col = f"{prefix}{col}" if prefix else col
            df_target[new_col] = metrics[col].to_numpy()
            cols.append(new_col)
    return df_target


def save_filtered_parquet(
    df_raw: pd.DataFrame,
    df_filtered: pd.DataFrame,
    out_path: str,
    metrics_filtered: Optional[pd.DataFrame] = None,
    metrics_raw: Optional[pd.DataFrame] = None,
) -> None:
    """将过滤结果写成 Parquet，并尽量保持原始列顺序，附带 Raw/Filter speed/accel。"""
    df_to_save = df_filtered.copy()
    df_to_save = _attach_metrics(df_to_save, metrics_filtered, prefix="")
    df_to_save = _attach_metrics(df_to_save, metrics_raw, prefix="raw_")
    base_cols = [c for c in df_raw.columns if c in df_to_save.columns]
    ordered_cols = base_cols + [c for c in df_to_save.columns if c not in base_cols]
    df_to_save = df_to_save[ordered_cols]
    out_file = Path(out_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    df_to_save.to_parquet(out_file, index=False)


def detect_spatial_pca_outliers(
    df: pd.DataFrame,
    *,
    min_points: int,
    mad_scale: float,
    window_size: Optional[int],
) -> Tuple[np.ndarray, Dict[str, object]]:
    detector = FilterSpatialPCAOutlier(
        min_points=min_points,
        mad_scale=mad_scale,
        window_size=window_size if window_size and window_size > 0 else None,
        include_altitude=False,
    )
    mask, stats = detector.detect_mask(df)
    return mask.astype(bool, copy=False), stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter single flight and plot Raw vs Filter")
    parser.add_argument("--date", required=True)
    parser.add_argument("--flight-id", type=int, required=True)
    parser.add_argument("--strategy", default="classic_dp_loop")
    parser.add_argument("--raw-dir", default=RAW_DEFAULT)
    parser.add_argument("--out-pdf", required=True)
    parser.add_argument(
        "--out-parquet",
        help="若指定则把过滤后的单航班结果写入该 Parquet 路径（列顺序对齐原始数据）",
    )
    parser.add_argument(
        "--metrics-pdf",
        help="速度/加速度图输出路径（默认: 在 out-pdf 同目录添加 _metrics 后缀）",
    )
    parser.add_argument(
        "--show-pca",
        action="store_true",
        help="在 Raw vs Filter 图上标记 PCA 空间异常点",
    )
    parser.add_argument("--pca-mad-scale", type=float, help="覆盖默认的 MAD scale 参数")
    parser.add_argument("--pca-min-points", type=int, help="覆盖默认的 min_points 参数")
    parser.add_argument(
        "--pca-window-size",
        type=int,
        help="覆盖默认的 PCA 滑窗大小（<=0 表示禁用滑窗）",
    )
    args = parser.parse_args()

    raw_file = os.path.join(args.raw_dir, f"{args.date}.parquet")
    df_raw = load_single_flight(raw_file, args.flight_id)
    df_filt = filter_single_flight(df_raw.copy(), args.strategy)

    pca_annotations = None
    if args.show_pca:
        default_min_points = _env_int("PCA_MIN_POINTS", 80)
        default_mad_scale = _env_float("PCA_MAD_SCALE", 6.0)
        default_window = _env_int("PCA_WINDOW_SIZE", 0)
        min_points = args.pca_min_points or default_min_points
        mad_scale = args.pca_mad_scale or default_mad_scale
        window_size = args.pca_window_size if args.pca_window_size is not None else default_window
        mask, stats = detect_spatial_pca_outliers(
            df_raw,
            min_points=min_points,
            mad_scale=mad_scale,
            window_size=window_size if window_size and window_size > 0 else None,
        )
        flagged = int(stats.get("points_flagged", 0))
        total = int(stats.get("points_total", 0))
        if total < min_points:
            print(
                f"⚠️ PCA 跳过：有效点 {total} < min_points {min_points}"
            )
        else:
            threshold = stats.get("global_threshold")
            print(
                "📍 PCA 结果: "
                f"flagged {flagged}/{total} (threshold={threshold})"
            )
        if mask.any():
            pca_annotations = [
                {
                    "mask": mask,
                    "color": "tab:red",
                    "label": "PCA异常",
                    "columns": {"latitude", "longitude"},
                }
            ]

    summary, reasons = summarize_filter_effect(df_raw, df_filt)
    print_summary(summary, reasons)

    metrics_raw = compute_speed_and_accel(df_raw)
    metrics_filt = compute_speed_and_accel(df_filt)
    metrics_pdf = args.metrics_pdf or default_metrics_path(args.out_pdf)
    plot_speed_accel(metrics_raw, metrics_filt, metrics_pdf)

    if args.out_parquet:
        save_filtered_parquet(
            df_raw,
            df_filt,
            args.out_parquet,
            metrics_filtered=metrics_filt,
            metrics_raw=metrics_raw,
        )
        print(f"💾 Saved filtered trajectory to {args.out_parquet}")

    cols = [c for c in ["flight_id", "timestamp", "latitude", "longitude", "altitude"] if c in df_raw.columns]
    plot_compare(
        df_raw[cols],
        df_filt[cols],
        args.flight_id,
        args.out_pdf,
        annotations=pca_annotations,
    )
    print(f"✅ Saved {args.out_pdf}")


if __name__ == "__main__":
    main()
