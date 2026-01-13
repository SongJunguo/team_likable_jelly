#!/usr/bin/env python3
"""
Evaluate recomputed kinematics vs filtered values on sample days.

Inputs: filtered_clean_eu_v5 (per-day parquet)
Outputs: summary metrics, skip stats, and plots per day.
"""

from __future__ import annotations

import argparse
import math
import multiprocessing as mp
from pathlib import Path
import sys

import numpy as np
import pandas as pd

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tools.common import utils


COLS = [
    "flight_id",
    "timestamp",
    "latitude",
    "longitude",
    "altitude",
    "groundspeed",
    "track",
    "vertical_rate",
]


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    lat1 = np.deg2rad(lat1)
    lon1 = np.deg2rad(lon1)
    lat2 = np.deg2rad(lat2)
    lon2 = np.deg2rad(lon2)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))
    return r * c


def bearing_deg(lat1, lon1, lat2, lon2):
    lat1 = np.deg2rad(lat1)
    lon1 = np.deg2rad(lon1)
    lat2 = np.deg2rad(lat2)
    lon2 = np.deg2rad(lon2)
    dlon = lon2 - lon1
    y = np.sin(dlon) * np.cos(lat2)
    x = np.cos(lat1) * np.sin(lat2) - np.sin(lat1) * np.cos(lat2) * np.cos(dlon)
    brng = np.degrees(np.arctan2(y, x))
    return (brng + 360.0) % 360.0


def angle_diff_deg(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def recompute_for_flight(g, max_dt, min_track_dist):
    g = g.sort_values("timestamp")
    n = len(g)
    if n < 2:
        return g.assign(
            gs_recalc=np.nan,
            track_recalc=np.nan,
            vr_recalc=np.nan,
            dt=np.nan,
            dist_m=np.nan,
        )

    t = g["timestamp"].values.astype("datetime64[ns]")
    lat = g["latitude"].to_numpy(dtype="float64")
    lon = g["longitude"].to_numpy(dtype="float64")
    alt = g["altitude"].to_numpy(dtype="float64")

    dt = (t[1:] - t[:-1]).astype("timedelta64[s]").astype("float64")
    idx = np.arange(1, n)

    mask_dt = (dt > 0.0) & (dt <= float(max_dt))
    mask_pos = (
        np.isfinite(lat[:-1])
        & np.isfinite(lon[:-1])
        & np.isfinite(lat[1:])
        & np.isfinite(lon[1:])
    )
    mask_alt = np.isfinite(alt[:-1]) & np.isfinite(alt[1:])

    dist = np.full_like(dt, np.nan, dtype="float64")
    valid_dist = mask_dt & mask_pos
    if np.any(valid_dist):
        dist[valid_dist] = haversine_m(
            lat[:-1][valid_dist],
            lon[:-1][valid_dist],
            lat[1:][valid_dist],
            lon[1:][valid_dist],
        )

    gs_recalc = np.full(n, np.nan, dtype="float64")
    track_recalc = np.full(n, np.nan, dtype="float64")
    vr_recalc = np.full(n, np.nan, dtype="float64")

    if np.any(valid_dist):
        gs_mps = dist[valid_dist] / dt[valid_dist]
        gs_kt = gs_mps / utils.KTS2MS
        gs_recalc[idx[valid_dist]] = gs_kt

    mask_track = valid_dist & (dist >= float(min_track_dist))
    if np.any(mask_track):
        brng = bearing_deg(
            lat[:-1][mask_track],
            lon[:-1][mask_track],
            lat[1:][mask_track],
            lon[1:][mask_track],
        )
        track_recalc[idx[mask_track]] = brng

    valid_vr = mask_dt & mask_alt
    if np.any(valid_vr):
        vr = (alt[1:] - alt[:-1]) / dt * 60.0
        vr_recalc[idx[valid_vr]] = vr[valid_vr]

    out = g.copy()
    out["gs_recalc"] = gs_recalc
    out["track_recalc"] = track_recalc
    out["vr_recalc"] = vr_recalc
    out["dt"] = np.r_[np.nan, dt]
    out["dist_m"] = np.r_[np.nan, dist]
    return out


def process_flight(args):
    g, max_dt, min_track_dist = args
    g = g.sort_values("timestamp")
    n = len(g)
    if n < 2:
        return {
            "gs": {"orig": np.array([]), "recalc": np.array([]), "err": np.array([]), "counts": {}},
            "track": {"orig": np.array([]), "recalc": np.array([]), "err": np.array([]), "counts": {}},
            "vr": {"orig": np.array([]), "recalc": np.array([]), "err": np.array([]), "counts": {}},
        }

    t = g["timestamp"].values.astype("datetime64[ns]")
    lat = g["latitude"].to_numpy(dtype="float64")
    lon = g["longitude"].to_numpy(dtype="float64")
    alt = g["altitude"].to_numpy(dtype="float64")
    gs = g["groundspeed"].to_numpy(dtype="float64")
    track = g["track"].to_numpy(dtype="float64")
    vr = g["vertical_rate"].to_numpy(dtype="float64")

    dt = (t[1:] - t[:-1]).astype("timedelta64[s]").astype("float64")
    idx = np.arange(1, n)

    mask_dt = (dt > 0.0) & (dt <= float(max_dt))
    mask_pos = (
        np.isfinite(lat[:-1])
        & np.isfinite(lon[:-1])
        & np.isfinite(lat[1:])
        & np.isfinite(lon[1:])
    )
    mask_alt = np.isfinite(alt[:-1]) & np.isfinite(alt[1:])

    dist = np.full_like(dt, np.nan, dtype="float64")
    valid_dist = mask_dt & mask_pos
    if np.any(valid_dist):
        dist[valid_dist] = haversine_m(
            lat[:-1][valid_dist],
            lon[:-1][valid_dist],
            lat[1:][valid_dist],
            lon[1:][valid_dist],
        )

    gs_recalc = np.full(n, np.nan, dtype="float64")
    track_recalc = np.full(n, np.nan, dtype="float64")
    vr_recalc = np.full(n, np.nan, dtype="float64")

    if np.any(valid_dist):
        gs_mps = dist[valid_dist] / dt[valid_dist]
        gs_kt = gs_mps / utils.KTS2MS
        gs_recalc[idx[valid_dist]] = gs_kt

    mask_track = valid_dist & (dist >= float(min_track_dist))
    if np.any(mask_track):
        brng = bearing_deg(
            lat[:-1][mask_track],
            lon[:-1][mask_track],
            lat[1:][mask_track],
            lon[1:][mask_track],
        )
        track_recalc[idx[mask_track]] = brng

    valid_vr = mask_dt & mask_alt
    if np.any(valid_vr):
        vr_calc = (alt[1:] - alt[:-1]) / dt * 60.0
        vr_recalc[idx[valid_vr]] = vr_calc[valid_vr]

    def build_metric(orig, recalc, is_angle=False):
        mask = np.isfinite(orig) & np.isfinite(recalc)
        if not np.any(mask):
            return np.array([]), np.array([]), np.array([])
        orig_v = orig[mask]
        recalc_v = recalc[mask]
        if is_angle:
            diff = angle_diff_deg(recalc_v, orig_v)
            err = np.abs(diff)
        else:
            err = np.abs(recalc_v - orig_v)
        return orig_v, recalc_v, err

    gs_orig, gs_rec, gs_err = build_metric(gs, gs_recalc)
    tr_orig, tr_rec, tr_err = build_metric(track, track_recalc, is_angle=True)
    vr_orig, vr_rec, vr_err = build_metric(vr, vr_recalc)

    total_pairs = n - 1
    gs_counts = {
        "total_pairs": total_pairs,
        "dt_invalid": int((~mask_dt).sum()),
        "pos_missing": int((~mask_pos).sum()),
        "orig_missing": int((valid_dist & ~np.isfinite(gs[1:])).sum()),
        "compared": int(len(gs_err)),
    }
    tr_counts = {
        "total_pairs": total_pairs,
        "dt_invalid": int((~mask_dt).sum()),
        "pos_missing": int((~mask_pos).sum()),
        "track_small_move": int((valid_dist & (dist < float(min_track_dist))).sum()),
        "orig_missing": int((mask_track & ~np.isfinite(track[1:])).sum()),
        "compared": int(len(tr_err)),
    }
    vr_counts = {
        "total_pairs": total_pairs,
        "dt_invalid": int((~mask_dt).sum()),
        "alt_missing": int((~mask_alt).sum()),
        "orig_missing": int((valid_vr & ~np.isfinite(vr[1:])).sum()),
        "compared": int(len(vr_err)),
    }

    return {
        "gs": {"orig": gs_orig, "recalc": gs_rec, "err": gs_err, "counts": gs_counts},
        "track": {"orig": tr_orig, "recalc": tr_rec, "err": tr_err, "counts": tr_counts},
        "vr": {"orig": vr_orig, "recalc": vr_rec, "err": vr_err, "counts": vr_counts},
    }


def summarize_metric(orig, recalc, err, is_angle=False):
    if len(err) == 0:
        return {
            "count": 0,
            "mae": math.nan,
            "median": math.nan,
            "p95": math.nan,
            "max": math.nan,
            "corr": math.nan,
        }
    corr = math.nan
    if len(orig) > 1:
        if is_angle:
            diff = angle_diff_deg(recalc, orig)
            corr = float(np.mean(np.cos(np.deg2rad(diff))))
        else:
            corr = float(np.corrcoef(orig, recalc)[0, 1])
    return {
        "count": int(len(err)),
        "mae": float(np.mean(err)),
        "median": float(np.median(err)),
        "p95": float(np.percentile(err, 95)),
        "max": float(np.max(err)),
        "corr": corr,
    }


def plot_scatter(x, y, title, xlabel, ylabel, out_path, sample_size, seed):
    if len(x) == 0:
        return
    rng = np.random.default_rng(seed)
    if len(x) > sample_size:
        idx = rng.choice(len(x), size=sample_size, replace=False)
        x = x[idx]
        y = y[idx]
    plt.figure(figsize=(6, 6))
    plt.scatter(x, y, s=2, alpha=0.2)
    xmin = np.nanmin([x.min(), y.min()])
    xmax = np.nanmax([x.max(), y.max()])
    plt.plot([xmin, xmax], [xmin, xmax], color="red", linewidth=1, linestyle="--")
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_hist(err, title, xlabel, out_path):
    if len(err) == 0:
        return
    xmax = np.percentile(err, 99.5)
    plt.figure(figsize=(6, 4))
    plt.hist(err, bins=120, range=(0, xmax), alpha=0.8)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_cdf(err, title, xlabel, out_path):
    if len(err) == 0:
        return
    x = np.sort(err)
    y = np.arange(1, len(x) + 1) / len(x)
    plt.figure(figsize=(6, 4))
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel("CDF")
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_timeseries(df, flight_id, out_path):
    if df.empty:
        return
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    axes[0].plot(df["timestamp"], df["groundspeed"], label="orig", linewidth=1)
    axes[0].plot(df["timestamp"], df["gs_recalc"], label="recalc", linewidth=1)
    axes[0].set_ylabel("groundspeed (kt)")
    axes[0].legend(loc="upper right", fontsize=8)

    axes[1].plot(df["timestamp"], df["track"], label="orig", linewidth=1)
    axes[1].plot(df["timestamp"], df["track_recalc"], label="recalc", linewidth=1)
    axes[1].set_ylabel("track (deg)")
    axes[1].legend(loc="upper right", fontsize=8)

    axes[2].plot(df["timestamp"], df["vertical_rate"], label="orig", linewidth=1)
    axes[2].plot(df["timestamp"], df["vr_recalc"], label="recalc", linewidth=1)
    axes[2].set_ylabel("vertical_rate (ft/min)")
    axes[2].legend(loc="upper right", fontsize=8)

    fig.suptitle(f"flight {flight_id}")
    fig.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def evaluate_day(day, input_dir, output_dir, max_dt, min_track_dist, procs, sample_size, seed):
    in_path = input_dir / f"{day}.parquet"
    if not in_path.exists():
        print(f"[skip] missing {in_path}")
        return

    print(f"[day] {day} -> {in_path}")
    df = pd.read_parquet(in_path, columns=COLS)
    if df.empty:
        print(f"[skip] empty {in_path}")
        return

    df = df.sort_values(["flight_id", "timestamp"])
    groups = [g for _, g in df.groupby("flight_id", sort=False)]
    if not groups:
        print(f"[skip] no flights in {day}")
        return

    workers = min(procs, len(groups))
    print(f"  flights: {len(groups)}, workers: {workers}")

    with mp.Pool(processes=workers) as pool:
        results = pool.map(process_flight, [(g, max_dt, min_track_dist) for g in groups])

    agg = {
        "gs": {"orig": [], "recalc": [], "err": [], "counts": []},
        "track": {"orig": [], "recalc": [], "err": [], "counts": []},
        "vr": {"orig": [], "recalc": [], "err": [], "counts": []},
    }

    for res in results:
        for key in ["gs", "track", "vr"]:
            agg[key]["orig"].append(res[key]["orig"])
            agg[key]["recalc"].append(res[key]["recalc"])
            agg[key]["err"].append(res[key]["err"])
            agg[key]["counts"].append(res[key]["counts"])

    for key in ["gs", "track", "vr"]:
        agg[key]["orig"] = np.concatenate(agg[key]["orig"]) if agg[key]["orig"] else np.array([])
        agg[key]["recalc"] = np.concatenate(agg[key]["recalc"]) if agg[key]["recalc"] else np.array([])
        agg[key]["err"] = np.concatenate(agg[key]["err"]) if agg[key]["err"] else np.array([])

    summary_rows = []
    for key, is_angle in [("gs", False), ("track", True), ("vr", False)]:
        stats = summarize_metric(agg[key]["orig"], agg[key]["recalc"], agg[key]["err"], is_angle=is_angle)
        summary_rows.append(
            {
                "date": day,
                "metric": key,
                **stats,
            }
        )

    summary_df = pd.DataFrame(summary_rows)

    def sum_counts(counts_list, keys):
        out = {k: 0 for k in keys}
        for c in counts_list:
            for k in keys:
                out[k] += int(c.get(k, 0))
        return out

    skip_rows = []
    gs_keys = ["total_pairs", "dt_invalid", "pos_missing", "orig_missing", "compared"]
    tr_keys = ["total_pairs", "dt_invalid", "pos_missing", "track_small_move", "orig_missing", "compared"]
    vr_keys = ["total_pairs", "dt_invalid", "alt_missing", "orig_missing", "compared"]

    gs_counts = sum_counts(agg["gs"]["counts"], gs_keys)
    tr_counts = sum_counts(agg["track"]["counts"], tr_keys)
    vr_counts = sum_counts(agg["vr"]["counts"], vr_keys)

    skip_rows.append({"date": day, "metric": "gs", **gs_counts})
    skip_rows.append({"date": day, "metric": "track", **tr_counts})
    skip_rows.append({"date": day, "metric": "vr", **vr_counts})

    skip_df = pd.DataFrame(skip_rows)

    out_dir = output_dir / day
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    summary_df.to_csv(out_dir / "summary_metrics.csv", index=False)
    skip_df.to_csv(out_dir / "skip_stats.csv", index=False)

    plot_scatter(
        agg["gs"]["orig"],
        agg["gs"]["recalc"],
        f"{day} groundspeed: orig vs recalc",
        "orig groundspeed (kt)",
        "recalc groundspeed (kt)",
        plots_dir / "scatter_groundspeed.png",
        sample_size,
        seed,
    )
    plot_scatter(
        agg["track"]["orig"],
        agg["track"]["recalc"],
        f"{day} track: orig vs recalc",
        "orig track (deg)",
        "recalc track (deg)",
        plots_dir / "scatter_track.png",
        sample_size,
        seed,
    )
    plot_scatter(
        agg["vr"]["orig"],
        agg["vr"]["recalc"],
        f"{day} vertical_rate: orig vs recalc",
        "orig vertical_rate (ft/min)",
        "recalc vertical_rate (ft/min)",
        plots_dir / "scatter_vertical_rate.png",
        sample_size,
        seed,
    )

    plot_hist(
        agg["gs"]["err"],
        f"{day} groundspeed abs error",
        "abs error (kt)",
        plots_dir / "hist_groundspeed_err.png",
    )
    plot_hist(
        agg["track"]["err"],
        f"{day} track abs error",
        "abs error (deg)",
        plots_dir / "hist_track_err.png",
    )
    plot_hist(
        agg["vr"]["err"],
        f"{day} vertical_rate abs error",
        "abs error (ft/min)",
        plots_dir / "hist_vertical_rate_err.png",
    )

    plot_cdf(
        agg["gs"]["err"],
        f"{day} groundspeed abs error CDF",
        "abs error (kt)",
        plots_dir / "cdf_groundspeed_err.png",
    )
    plot_cdf(
        agg["track"]["err"],
        f"{day} track abs error CDF",
        "abs error (deg)",
        plots_dir / "cdf_track_err.png",
    )
    plot_cdf(
        agg["vr"]["err"],
        f"{day} vertical_rate abs error CDF",
        "abs error (ft/min)",
        plots_dir / "cdf_vertical_rate_err.png",
    )

    top_flights = (
        df.groupby("flight_id", sort=False)
        .size()
        .sort_values(ascending=False)
        .head(3)
        .index
        .to_list()
    )
    for fid in top_flights:
        g = df[df["flight_id"] == fid]
        g_eval = recompute_for_flight(g, max_dt, min_track_dist)
        plot_timeseries(g_eval, fid, plots_dir / f"timeseries_flight_{fid}.png")


def parse_dates(value):
    if not value:
        return []
    items = [v.strip() for v in value.split(",") if v.strip()]
    return items


def main():
    parser = argparse.ArgumentParser(description="Evaluate recomputed kinematics on sample days.")
    parser.add_argument(
        "--input-dir",
        default="opensky_2024_PRC_dataset/filtered_clean_eu_v5",
        help="Input filtered directory",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/kinematics_recompute_eval",
        help="Output report directory",
    )
    parser.add_argument(
        "--dates",
        default="2022-01-01,2022-02-01",
        help="Comma-separated dates (YYYY-MM-DD)",
    )
    parser.add_argument("--max-dt", type=float, default=120.0, help="Max dt (seconds)")
    parser.add_argument("--min-track-dist", type=float, default=50.0, help="Min distance for track (m)")
    parser.add_argument("--procs", type=int, default=4, help="Worker processes")
    parser.add_argument("--scatter-sample", type=int, default=200000, help="Scatter sample size")
    parser.add_argument("--seed", type=int, default=7, help="Random seed")
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    dates = parse_dates(args.dates)
    if not dates:
        raise SystemExit("No dates provided.")

    for day in dates:
        evaluate_day(
            day,
            input_dir,
            output_dir,
            args.max_dt,
            args.min_track_dist,
            args.procs,
            args.scatter_sample,
            args.seed,
        )


if __name__ == "__main__":
    main()
