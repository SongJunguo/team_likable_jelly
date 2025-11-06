#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
评估 double-pass (classic_dp) 相对 classic 的“额外删除”影响。

口径（必要列）：latitude/longitude/altitude 三列均作为判定列：
- pass2_only 删除点：classic 中三列均非 NaN，但 classic_dp 中三列有任意一列为 NaN。

输出：
- per_flight.csv：每航班的 points_classic / points_dp / pass2_only_count / pass2_only_rate
- per_point_sample.csv：抽样明细（flight_id,timestamp, 被删列列表, v_kmh, a_mps2）
- summary.txt：全日摘要（受影响航班占比、删除率分位数）

用法：
  conda activate opensky
  python test_python/analysis/evaluate_doublepass_impact.py \
    --date 2022-03-06 \
    --raw-dir /workspace/.../rawtrajectories \
    --classic-dir /workspace/.../classic_filtered_trajectories \
    --classic-dp-dir /workspace/.../classic_filtered_trajectories__doublepass_v1 \
    --out-dir reports/doublepass_eval
"""

from __future__ import annotations

import argparse
import os
from typing import List, Tuple

import numpy as np
import pandas as pd


NEEDED = ["latitude", "longitude", "altitude"]


def load_day(path: str, cols: List[str]) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["flight_id", "timestamp"] + cols)
    df["flight_id"] = df["flight_id"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values(["flight_id", "timestamp"]).reset_index(drop=True)
    return df


def compute_kinematics(df: pd.DataFrame) -> pd.DataFrame:
    # 返回同 shape 的 v_kmh/a_mps2（按 flight_id 独立计算）
    out = df[["flight_id", "timestamp"]].copy()
    v = np.full(len(df), np.nan)
    a = np.full(len(df), np.nan)
    for fid, g in df.groupby("flight_id", sort=False):
        idx = g.index.to_numpy()
        lat = g["latitude"].to_numpy()
        lon = g["longitude"].to_numpy()
        ts = g["timestamp"].values.astype("datetime64[ns]")
        if len(idx) < 3:
            continue
        dt = (ts[1:] - ts[:-1]).astype("timedelta64[s]").astype(float)
        dt[dt <= 0] = np.nan
        # haversine
        lat1 = np.radians(lat[:-1]); lon1 = np.radians(lon[:-1])
        lat2 = np.radians(lat[1:]);  lon2 = np.radians(lon[1:])
        dlat = lat2 - lat1; dlon = lon2 - lon1
        a_h = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
        a_h = np.clip(a_h, 0.0, 1.0)
        dist = 2*6371.0*np.arcsin(np.sqrt(a_h))  # km
        v_kmh = np.full(len(idx), np.nan)
        v_kmh[1:] = dist/(dt/3600.0)
        v_mps = v_kmh/3.6
        dt2 = (ts[2:] - ts[:-2]).astype("timedelta64[s]").astype(float)
        a_mps2 = np.full(len(idx), np.nan)
        a_mps2[1:-1] = 2*(v_mps[2:] - v_mps[:-2]) / dt2
        v[idx] = v_kmh  # 按原 df 行号写回
        a[idx] = a_mps2
    out["v_kmh"] = v
    out["a_mps2"] = a
    return out


def main():
    ap = argparse.ArgumentParser(description="Evaluate double-pass (classic_dp) extra deletions vs classic")
    ap.add_argument("--date", required=True)
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--classic-dir", required=True)
    ap.add_argument("--classic-dp-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--point-sample", type=int, default=5000)
    args = ap.parse_args()

    raw_path = os.path.join(args.raw_dir, f"{args.date}.parquet")
    c_path = os.path.join(args.classic_dir, f"{args.date}.parquet")
    d_path = os.path.join(args.classic_dp_dir, f"{args.date}.parquet")
    out_dir = os.path.join(args.out_dir, args.date)
    os.makedirs(out_dir, exist_ok=True)

    # 载入
    df_raw = load_day(raw_path, NEEDED)
    df_c = load_day(c_path, NEEDED)
    df_d = load_day(d_path, NEEDED)

    # 键对齐（flight_id+timestamp）
    key_cols = ["flight_id", "timestamp"]
    c_key = df_c[key_cols + NEEDED].copy()
    d_key = df_d[key_cols + NEEDED].copy()

    merged = c_key.merge(d_key, on=key_cols, how="left", suffixes=("_c", "_d"))
    # 经典版有效点（必要列均非 NaN）
    c_valid = (~merged["latitude_c"].isna()) & (~merged["longitude_c"].isna()) & (~merged["altitude_c"].isna())
    # dp 在相同键上被删（任一必要列为 NaN 即视为删除）
    d_deleted = (merged[["latitude_d", "longitude_d", "altitude_d"]].isna().any(axis=1))
    pass2_only_mask = c_valid & d_deleted

    # 计算动力学：用 raw 的速度/加速度估计（与键对齐）
    kin = compute_kinematics(df_raw)
    kin = kin.rename(columns={"v_kmh": "v_kmh_raw", "a_mps2": "a_mps2_raw"})
    m2 = merged[key_cols].merge(kin, on=key_cols, how="left")
    merged["v_kmh_raw"] = m2["v_kmh_raw"]
    merged["a_mps2_raw"] = m2["a_mps2_raw"]

    # per-flight 汇总
    grp = merged.groupby("flight_id")
    classic_valid = ~merged[["latitude_c","longitude_c","altitude_c"]].isna().any(axis=1)
    dp_valid = ~merged[["latitude_d","longitude_d","altitude_d"]].isna().any(axis=1)
    pass2_only = classic_valid & (~dp_valid)

    points_classic = classic_valid.groupby(merged["flight_id"]).sum().astype(int)
    points_dp = dp_valid.groupby(merged["flight_id"]).sum().astype(int)
    pass2_only_count = pass2_only.groupby(merged["flight_id"]).sum().astype(int)
    pass2_only_rate = (pass2_only_count / points_classic.replace(0, np.nan)).astype(float)

    # 被删点的 v/a 统计（仅在 pass2_only 的点集上）
    del_sub = merged.loc[pass2_only, ["flight_id", "v_kmh_raw", "a_mps2_raw"]]
    v_med = del_sub.groupby("flight_id")["v_kmh_raw"].median()
    a_med = del_sub.groupby("flight_id")["a_mps2_raw"].median()
    # groupby.quantile 更稳健（空组返回 NaN，不产生警告）
    v_p95 = del_sub.groupby("flight_id")["v_kmh_raw"].quantile(0.95)
    a_p95 = del_sub.groupby("flight_id")["a_mps2_raw"].quantile(0.95)

    out_f = (
        pd.DataFrame({
            "points_classic": points_classic,
            "points_dp": points_dp,
            "pass2_only_count": pass2_only_count,
            "pass2_only_rate": pass2_only_rate,
        })
        .join(v_med.rename("v_med_deleted"))
        .join(a_med.rename("a_med_deleted"))
        .join(v_p95.rename("v_p95_deleted"))
        .join(a_p95.rename("a_p95_deleted"))
        .reset_index()
    )
    out_f.to_csv(os.path.join(out_dir, "per_flight.csv"), index=False)

    # 明细抽样
    pts = merged.loc[pass2_only_mask, key_cols + [
        "latitude_c","longitude_c","altitude_c","latitude_d","longitude_d","altitude_d","v_kmh_raw","a_mps2_raw"
    ]].copy()
    if len(pts) > args.point_sample:
        pts = pts.sample(args.point_sample, random_state=0)
    pts.to_csv(os.path.join(out_dir, "per_point_sample.csv"), index=False)

    # 摘要
    affected = int((out_f["pass2_only_count"] > 0).sum())
    total = int(len(out_f))
    rates = out_f["pass2_only_rate"].to_numpy(dtype=float)
    rates = rates[~np.isnan(rates)]
    if rates.size == 0:
        p50 = p90 = p95 = 0.0
    else:
        p50 = float(np.percentile(rates, 50))
        p90 = float(np.percentile(rates, 90))
        p95 = float(np.percentile(rates, 95))
    with open(os.path.join(out_dir, "summary.txt"), "w", encoding="utf-8") as f:
        f.write(f"日期: {args.date}\n")
        f.write(f"航班总数: {total}, 受影响航班: {affected} ({affected/max(1,total):.1%})\n")
        f.write(f"删除率分位: p50={p50:.4%}, p90={p90:.4%}, p95={p95:.4%}\n")
        f.write(f"明细抽样: per_point_sample.csv, 航班汇总: per_flight.csv\n")
    print("✅ 输出目录:", out_dir)


if __name__ == "__main__":
    main()
