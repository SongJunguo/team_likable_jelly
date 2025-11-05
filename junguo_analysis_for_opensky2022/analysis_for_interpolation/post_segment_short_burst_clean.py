#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Post-clean 短簇剔除（分段后）：
- 输入：segmented_v2（Δt≤20s、必需列0 NaN）
- 轻筛：基于经纬速度/加速度的滑窗稳健阈值，标记可疑“种子”
- 精筛：仅对种子±窗口做 2D-DBSCAN（ENU km），可选高度垂直复核
- 短簇门：连续异常长度≤L_short 的簇整体删除
- 输出：segmented_v3（必要时拆段、重排 segment_index 与 flight_id）
- 可选：指定 original_flight_id 生成 before/after PDF 可视化

建议与默认：
- 窗口 60s，步长 20s；DBSCAN 空中 eps=1.0 km，min_samples=3；L_short=2
- v_abs=1000 km/h, v_ratio=3；a_abs=15 m/s², a_ratio=5
- 高度复核：z_abs=300 m, z_ratio=3，覆盖率≥0.8 时启用，权重 α=0.7（700m≈1km）
"""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
import matplotlib.pyplot as plt


R_EARTH_KM = 6371.0


def haversine_km(lat1, lon1, lat2, lon2):
    lat1 = np.radians(lat1)
    lon1 = np.radians(lon1)
    lat2 = np.radians(lat2)
    lon2 = np.radians(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    a = np.clip(a, 0.0, 1.0)
    return 2 * R_EARTH_KM * np.arcsin(np.sqrt(a))


def enu_km(lat, lon, lat0=None, lon0=None):
    """近似将经纬度投影到局部平面（km）。"""
    if lat0 is None:
        lat0 = np.nanmean(lat)
    if lon0 is None:
        lon0 = np.nanmean(lon)
    lat0r = math.radians(lat0)
    dlat = np.radians(lat - lat0)
    dlon = np.radians(lon - lon0)
    x = R_EARTH_KM * np.cos(lat0r) * dlon
    y = R_EARTH_KM * dlat
    return x, y


def rolling_median(series: pd.Series, win: int) -> pd.Series:
    return series.rolling(win, center=True, min_periods=max(3, win // 3)).median()


def rolling_mad(series: pd.Series, win: int) -> pd.Series:
    med = rolling_median(series, win)
    mad = (series - med).abs().rolling(win, center=True, min_periods=max(3, win // 3)).median()
    return mad.fillna(mad.median())


@dataclass
class Params:
    win_sec: int = 60
    step_sec: int = 20
    seed_half_sec: int = 45
    v_abs_kmh: float = 1000.0
    v_ratio: float = 3.0
    a_abs_mps2: float = 15.0
    a_ratio: float = 5.0
    eps_km: float = 1.0
    min_samples: int = 3
    l_short: int = 2
    alt_cover: float = 0.8
    alpha_alt: float = 0.7  # 700 m ≈ 1 km 等效
    z_abs_m: float = 300.0
    z_ratio: float = 3.0
    max_dt_gap: float = 20.0
    min_points: int = 30
    min_duration_s: int = 120


def compute_kinematics(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    ts = df["timestamp"].values.astype("datetime64[ns]")
    lat = df["latitude"].values.astype(float)
    lon = df["longitude"].values.astype(float)
    dt = (ts[1:] - ts[:-1]).astype("timedelta64[s]").astype(float)
    dt[np.isnan(dt) | (dt <= 0)] = np.nan
    dist = haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
    v_kmh = np.full(lat.shape, np.nan)
    v_kmh[1:] = dist / (dt / 3600.0)
    a_mps2 = np.full(lat.shape, np.nan)
    # 速度（km/h）→ m/s
    v_mps = v_kmh / 3.6
    dt2 = (ts[2:] - ts[:-2]).astype("timedelta64[s]").astype(float)
    a_mps2[1:-1] = 2 * (v_mps[2:] - v_mps[:-2]) / dt2
    dt_s = np.full(lat.shape, np.nan)
    dt_s[1:] = dt
    return v_kmh, a_mps2, dt_s


def light_seeds(df: pd.DataFrame, p: Params) -> np.ndarray:
    v_kmh, a_mps2, _ = compute_kinematics(df)
    n = len(df)
    win = p.win_sec
    v = pd.Series(v_kmh)
    a = pd.Series(a_mps2)
    v_med = rolling_median(v, win).fillna(v.median())
    a_mad = rolling_mad(a.abs(), win)
    cond_v = v_kmh >= np.maximum(p.v_abs_kmh, p.v_ratio * v_med.values)
    cond_a = np.abs(a_mps2) >= np.maximum(p.a_abs_mps2, p.a_ratio * a_mad.values)
    seeds = np.where(np.nan_to_num(cond_v | cond_a, nan=False))[0]
    return seeds


def dbscan_window(df: pd.DataFrame, idx0: int, p: Params) -> np.ndarray:
    ts = df["timestamp"].values.astype("datetime64[ns]")
    t0 = ts[idx0]
    tmin = t0 - np.timedelta64(p.seed_half_sec, "s")
    tmax = t0 + np.timedelta64(p.seed_half_sec, "s")
    wmask = (ts >= tmin) & (ts <= tmax)
    idc = np.where(wmask)[0]
    if len(idc) < 5:
        return np.array([], dtype=int)
    lat = df["latitude"].values[idc]
    lon = df["longitude"].values[idc]
    x, y = enu_km(lat, lon)
    feats = [x, y]
    # 高度可选复核：作为附加特征仅在覆盖率足够时加入
    bad_rows_alt = 0
    if "altitude" in df.columns:
        alt = df["altitude"].values[idc]
        cover = np.isfinite(alt).mean()
        if cover >= p.alt_cover:
            feats.append((alt - np.nanmedian(alt)) / 1000.0 * p.alpha_alt)
        else:
            bad_rows_alt = len(alt) - np.isfinite(alt).sum()
    X = np.vstack(feats).T
    # DBSCAN（欧氏）
    db = DBSCAN(eps=p.eps_km, min_samples=p.min_samples, metric="euclidean")
    labels = db.fit_predict(X)
    bad_local = idc[labels == -1]
    # 垂直复核（可选）：仅对异常点做 |Δalt| 门
    if ("altitude" in df.columns) and (len(bad_local) > 0):
        alt_all = df["altitude"].values
        # 用窗口中的 MAD 作为参照
        alt_w = alt_all[idc]
        if np.isfinite(alt_w).mean() >= p.alt_cover:
            a_med = np.nanmedian(alt_w)
            dev = np.abs(alt_all[bad_local] - a_med)
            mad = np.nanmedian(np.abs(alt_w - a_med))
            z_thr = max(p.z_abs_m, p.z_ratio * (mad if np.isfinite(mad) and mad > 0 else p.z_abs_m))
            keep_mask = dev >= z_thr
            bad_local = bad_local[keep_mask]
    return bad_local.astype(int)


def remove_short_clusters(n: int, bad_mask: np.ndarray, l_short: int) -> np.ndarray:
    bad = bad_mask.copy()
    i = 0
    while i < n:
        if bad[i]:
            j = i
            while j < n and bad[j]:
                j += 1
            if (j - i) <= l_short:
                bad[i:j] = True  # 保持删除（短簇）
            else:
                bad[i:j] = False  # 长异常簇保留（不在本策略删除）
            i = j
        else:
            i += 1
    return bad


def split_after_removal(df: pd.DataFrame, p: Params) -> List[pd.DataFrame]:
    if df.empty:
        return []
    ts = df["timestamp"].values.astype("datetime64[ns]")
    keep = ~df["_bad"].values
    if keep.sum() < p.min_points:
        return []
    df2 = df.loc[keep].copy().reset_index(drop=True)
    # 按时间裂段（Δt>max_dt_gap）
    t = df2["timestamp"].values.astype("datetime64[ns]")
    dt = np.r_[np.timedelta64(0, "s"), (t[1:] - t[:-1])]
    breaks = dt > np.timedelta64(int(p.max_dt_gap), "s")
    segid = breaks.cumsum()
    out: List[pd.DataFrame] = []
    for _, g in df2.groupby(segid):
        if len(g) < p.min_points:
            continue
        dur = (g["timestamp"].iloc[-1] - g["timestamp"].iloc[0]) / pd.to_timedelta(1, "s")
        if dur < p.min_duration_s:
            continue
        out.append(g.drop(columns=["_bad"]))
    return out


def process_segment(dfseg: pd.DataFrame, p: Params) -> List[pd.DataFrame]:
    df = dfseg.sort_values("timestamp").reset_index(drop=True).copy()
    n = len(df)
    if n < p.min_points:
        return [df.drop(columns=[c for c in ["_bad"] if c in df.columns])]

    seeds = light_seeds(df, p)
    bad = np.zeros(n, dtype=bool)
    for idx in seeds:
        bad_local = dbscan_window(df, int(idx), p)
        bad[bad_local] = True
    # 仅删除短簇（长度≤L）
    bad = remove_short_clusters(n, bad, p.l_short)
    df["_bad"] = bad
    return split_after_removal(df, p)


def reassign_segment_ids(df_all: pd.DataFrame) -> pd.DataFrame:
    # 对每个 original_flight_id 重新计算 segment_index 与 flight_id
    out_parts: List[pd.DataFrame] = []
    for ofid, g in df_all.groupby("original_flight_id", sort=False):
        segs = []
        for _, seg in g.groupby("_tmp_seg", sort=True):
            segs.append(seg.sort_values("timestamp"))
        segs.sort(key=lambda x: x["timestamp"].iloc[0])
        for k, seg in enumerate(segs, start=1):
            seg = seg.copy()
            seg["segment_index"] = np.int32(k)
            seg["flight_id"] = np.int64(int(ofid) * 10000 + k)
            t0 = pd.to_datetime(seg["timestamp"].iloc[0], utc=True)
            t1 = pd.to_datetime(seg["timestamp"].iloc[-1], utc=True)
            seg["flight_seg_info"] = f"{int(ofid)}_s{k}_{t0.strftime('%Y%m%dT%H%M%S')}Z_{t1.strftime('%H%M%S')}"
            out_parts.append(seg)
    out = pd.concat(out_parts, ignore_index=True)
    return out


def visualize_before_after(df_before: pd.DataFrame, df_after: pd.DataFrame, ofid: int, out_pdf: str):
    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)
    for ax, col, lab in zip(axes, ["longitude", "latitude", "altitude"], ["Longitude", "Latitude", "Altitude (ft)"]):
        if col in df_before.columns:
            ax.plot(df_before["timestamp"], df_before[col], ".", color="tab:gray", alpha=0.6, label="before")
        if col in df_after.columns:
            ax.plot(df_after["timestamp"], df_after[col], ".", color="tab:blue", alpha=0.9, label="after")
        ax.set_ylabel(lab)
        ax.grid(True, alpha=0.2)
        ax.legend(loc="best")
    axes[-1].set_xlabel("UTC time")
    fig.suptitle(f"original_flight_id={ofid} (before/after)")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    fig.savefig(out_pdf)
    plt.close(fig)


def process_file(input_path: str, output_path: str, p: Params, plot_fids: Optional[List[int]] = None, plot_dir: Optional[str] = None):
    df = pd.read_parquet(input_path)
    if df.empty:
        pd.DataFrame().to_parquet(output_path, index=False)
        return
    out_parts: List[pd.DataFrame] = []
    # 用 (original_flight_id, flight_id) 组织，确保每个段独立处理
    for ofid, g_of in df.groupby("original_flight_id", sort=False):
        new_segs: List[pd.DataFrame] = []
        for _, g_seg in g_of.groupby("flight_id", sort=False):
            for seg in process_segment(g_seg, p):
                seg = seg.copy()
                seg["_tmp_seg"] = seg["timestamp"].iloc[0]  # 暂存排序键
                new_segs.append(seg)
        if not new_segs:
            continue
        g_new = reassign_segment_ids(pd.concat(new_segs, ignore_index=True))
        out_parts.append(g_new)
        # 可视化（可选）
        if plot_fids and int(ofid) in plot_fids and plot_dir:
            before = g_of.sort_values(["flight_id", "timestamp"])  # 合并原段
            after = g_new.sort_values(["flight_id", "timestamp"])  # 合并新段
            out_pdf = os.path.join(plot_dir, f"clean_{os.path.basename(input_path).replace('.parquet','')}_{int(ofid)}.pdf")
            visualize_before_after(before, after, int(ofid), out_pdf)

    if out_parts:
        res = pd.concat(out_parts, ignore_index=True)
    else:
        res = pd.DataFrame(columns=list(df))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    res.to_parquet(output_path, index=False)


def run_one_entry(in_dir_: str, out_dir_: str, fname_: str, params: Params) -> Tuple[str, Optional[str]]:
    """顶层可 Pickle 的子进程入口。"""
    try:
        ip = os.path.join(in_dir_, fname_)
        op = os.path.join(out_dir_, fname_.replace("segmented_", "segmented_v3_"))
        process_file(ip, op, params, plot_fids=None, plot_dir=None)
        return fname_, None
    except Exception as e:  # pragma: no cover
        return fname_, str(e)


def main():
    ap = argparse.ArgumentParser(description="Post-clean segmented trajectories: short-burst removal (light+refine)")
    ap.add_argument("--input-dir", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--from", dest="date_from", default=None)
    ap.add_argument("--to", dest="date_to", default=None)
    ap.add_argument("--procs", type=int, default=8)
    ap.add_argument("--plot-flight-ids", default=None, help="逗号分隔的 original_flight_id 列表，用于生成 before/after PDF")
    ap.add_argument("--plot-dir", default="reports/postclean_plots")
    # 参数
    ap.add_argument("--win", type=int, default=60)
    ap.add_argument("--step", type=int, default=20)
    ap.add_argument("--seed-half", type=int, default=45)
    ap.add_argument("--v-abs", type=float, default=1000.0)
    ap.add_argument("--v-ratio", type=float, default=3.0)
    ap.add_argument("--a-abs", type=float, default=15.0)
    ap.add_argument("--a-ratio", type=float, default=5.0)
    ap.add_argument("--eps-km", type=float, default=1.0)
    ap.add_argument("--min-samples", type=int, default=3)
    ap.add_argument("--l-short", type=int, default=2)
    ap.add_argument("--alt-cover", type=float, default=0.8)
    ap.add_argument("--alpha-alt", type=float, default=0.7)
    ap.add_argument("--z-abs", type=float, default=300.0)
    ap.add_argument("--z-ratio", type=float, default=3.0)
    ap.add_argument("--min-points", type=int, default=30)
    ap.add_argument("--min-duration", type=int, default=120)
    args = ap.parse_args()

    p = Params(
        win_sec=args.win,
        step_sec=args.step,
        seed_half_sec=args.seed_half,
        v_abs_kmh=args.v_abs,
        v_ratio=args.v_ratio,
        a_abs_mps2=args.a_abs,
        a_ratio=args.a_ratio,
        eps_km=args.eps_km,
        min_samples=args.min_samples,
        l_short=args.l_short,
        alt_cover=args.alt_cover,
        alpha_alt=args.alpha_alt,
        z_abs_m=args.z_abs,
        z_ratio=args.z_ratio,
        min_points=args.min_points,
        min_duration_s=args.min_duration,
    )

    in_dir = args.input_dir
    out_dir = args.output_dir
    os.makedirs(out_dir, exist_ok=True)

    plot_fids = None
    if args.plot_flight_ids:
        plot_fids = [int(x) for x in args.plot_flight_ids.split(",") if x.strip()]

    # 列出文件
    # 列出输入目录中的 parquet 文件
    files = [f for f in sorted(os.listdir(in_dir)) if f.endswith(".parquet")]
    if args.date_from or args.date_to:
        tmp = []
        for f in files:
            # 提取 YYYY-MM-DD
            import re
            m = re.search(r"(\d{4}-\d{2}-\d{2})", f)
            if not m:
                continue
            d = m.group(1)
            if args.date_from and d < args.date_from:
                continue
            if args.date_to and d > args.date_to:
                continue
            tmp.append(f)
        files = tmp

    # 并行处理（按天）
    from concurrent.futures import ProcessPoolExecutor, as_completed
    with ProcessPoolExecutor(max_workers=max(1, int(args.procs))) as ex:
        futs = [ex.submit(run_one_entry, in_dir, out_dir, f, p) for f in files]
        total = len(futs)
        for i, fut in enumerate(as_completed(futs), 1):
            fname, err = fut.result()
            if err:
                print(f"[{i}/{total}] failed: {fname} -> {err}")
            else:
                print(f"[{i}/{total}] cleaned: {fname}")

    # 可视化（仅对指定航班，在主进程逐日绘制）
    if plot_fids:
        for f in files:
            ip = os.path.join(in_dir, f)
            op = os.path.join(out_dir, f.replace("segmented_", "segmented_v3_"))
            if not (os.path.exists(ip) and os.path.exists(op)):
                continue
            dfb = pd.read_parquet(ip)
            dfa = pd.read_parquet(op)
            for ofid in plot_fids:
                if (dfb["original_flight_id"] == ofid).any():
                    out_pdf = os.path.join(args.plot_dir, f"clean_{f.replace('.parquet','')}_{ofid}.pdf")
                    visualize_before_after(
                        dfb[dfb["original_flight_id"] == ofid],
                        dfa[dfa["original_flight_id"] == ofid],
                        ofid,
                        out_pdf,
                    )


if __name__ == "__main__":
    main()
