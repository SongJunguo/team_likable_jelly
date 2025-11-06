#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
可视化单日单航班：Raw vs Filter（含 FilterShortBurst 后的结果）

示例：
  conda activate opensky
  python test_python/analysis/plot_flight_before_after_filter.py \
    --date 2022-03-06 \
    --flight-id 249935181 \
    --raw-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories \
    --filt-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories__shortburst_v1 \
    --out-pdf reports/filter_shortburst_smoketest/plot_raw_vs_filter_2022-03-06_249935181.pdf
"""

from __future__ import annotations

import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt


def load_day(path: str, columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=columns)
    # 基础规范：类型与排序
    if "flight_id" in df.columns:
        df["flight_id"] = df["flight_id"].astype("int64")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.sort_values(["flight_id", "timestamp"]).dropna(subset=["timestamp"]).reset_index(drop=True)
    return df


def plot_compare(df_raw: pd.DataFrame, df_filt: pd.DataFrame, flight_id: int, out_pdf: str) -> None:
    r = df_raw[df_raw["flight_id"] == flight_id]
    f = df_filt[df_filt["flight_id"] == flight_id]
    fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
    pairs = [
        ("longitude", "Longitude (°)"),
        ("latitude", "Latitude (°)"),
        ("altitude", "Altitude (ft)")
    ]
    for ax, (col, lab) in zip(axes, pairs):
        if col in r.columns and len(r) > 0:
            ax.plot(r["timestamp"], r[col], ".", color="tab:gray", alpha=0.5, label="Raw")
        if col in f.columns and len(f) > 0:
            ax.plot(f["timestamp"], f[col], ".", color="tab:blue", alpha=0.9, label="Filter")
        ax.set_ylabel(lab)
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best")
    axes[-1].set_xlabel("UTC time")
    fig.suptitle(f"Raw vs Filter — flight_id={flight_id}")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)
    fig.savefig(out_pdf)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Plot single flight Raw vs Filter")
    ap.add_argument("--date", required=True)
    ap.add_argument("--flight-id", type=int, required=True)
    ap.add_argument("--raw-dir", required=True)
    ap.add_argument("--filt-dir", required=True)
    ap.add_argument("--out-pdf", required=True)
    args = ap.parse_args()

    raw_file = os.path.join(args.raw_dir, f"{args.date}.parquet")
    filt_file = os.path.join(args.filt_dir, f"{args.date}.parquet")

    cols = ["flight_id", "timestamp", "latitude", "longitude", "altitude"]
    dfr = load_day(raw_file, columns=cols)
    dff = load_day(filt_file, columns=cols)
    plot_compare(dfr, dff, args.flight_id, args.out_pdf)
    print("✅ saved:", args.out_pdf)


if __name__ == "__main__":
    main()
