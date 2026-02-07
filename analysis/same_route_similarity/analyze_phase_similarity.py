#!/usr/bin/env python3
"""
Analyze phase-level trajectory similarity from selected flights and pair metrics.

This script reads:
- selected_flights.csv
- pairwise_metrics.csv

Then it reconstructs trajectory arrays for selected flights, computes phase metrics,
and exports CSV summaries and figures for README/report usage.
"""

from __future__ import annotations

import argparse
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

EARTH_RADIUS_KM = 6371.0
DATE_PATTERN = re.compile(r"interpolated_(\d{4}-\d{2}-\d{2})\.parquet")

ALL_PAIR_TYPES = [
    "same_flight_cross_day",
    "same_route_cross_day",
    "same_route_same_day",
    "diff_route_random",
]

FOCUS_PAIR_TYPES = [
    "same_flight_cross_day",
    "same_route_cross_day",
    "same_route_same_day",
]


@dataclass
class TrajectoryEntry:
    flight_id: int
    lat: np.ndarray
    lon: np.ndarray


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Phase-level trajectory similarity analysis")
    parser.add_argument(
        "--interp-dir",
        default="opensky_2024_PRC_dataset/interpolated_clean_eu_v5",
        help="Interpolated trajectory parquet directory",
    )
    parser.add_argument(
        "--selected-flights-csv",
        default="analysis/same_route_similarity/output/selected_flights.csv",
        help="CSV from evaluate_same_route_similarity.py",
    )
    parser.add_argument(
        "--pairwise-csv",
        default="analysis/same_route_similarity/output/pairwise_metrics.csv",
        help="Pairwise metrics CSV",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis/same_route_similarity/output",
        help="Output directory",
    )
    parser.add_argument(
        "--resample-points",
        type=int,
        default=200,
        help="Trajectory resample points (must be >= 100)",
    )
    parser.add_argument(
        "--min-traj-points",
        type=int,
        default=20,
        help="Minimum raw points to keep one trajectory",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) // 2),
        help="Worker process count for daily loading",
    )
    return parser.parse_args()


def extract_date_from_file(name: str) -> str | None:
    match = DATE_PATTERN.fullmatch(name)
    return None if match is None else match.group(1)


def list_daily_files(interp_dir: Path, date_set: set[str]) -> List[Tuple[str, Path]]:
    out: List[Tuple[str, Path]] = []
    for path in sorted(interp_dir.glob("interpolated_*.parquet")):
        date_str = extract_date_from_file(path.name)
        if date_str is None:
            continue
        if date_str not in date_set:
            continue
        out.append((date_str, path))
    return out


def haversine_vec(
    lat1_deg: np.ndarray,
    lon1_deg: np.ndarray,
    lat2_deg: np.ndarray,
    lon2_deg: np.ndarray,
) -> np.ndarray:
    lat1 = np.radians(lat1_deg)
    lon1 = np.radians(lon1_deg)
    lat2 = np.radians(lat2_deg)
    lon2 = np.radians(lon2_deg)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    c = 2.0 * np.arcsin(np.sqrt(a))
    return EARTH_RADIUS_KM * c


def resample_track(
    ts_ns: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    resample_points: int,
    min_traj_points: int,
) -> Tuple[np.ndarray, np.ndarray] | None:
    if ts_ns.size < min_traj_points:
        return None

    keep = np.empty(ts_ns.shape, dtype=bool)
    keep[0] = True
    keep[1:] = ts_ns[1:] > ts_ns[:-1]
    ts = ts_ns[keep]
    lat = lat[keep]
    lon = lon[keep]

    if ts.size < min_traj_points:
        return None

    span = ts[-1] - ts[0]
    if span <= 0:
        return None

    progress = (ts - ts[0]) / float(span)
    target = np.linspace(0.0, 1.0, resample_points, dtype=np.float64)
    lat_i = np.interp(target, progress, lat)
    lon_i = np.interp(target, progress, lon)
    return lat_i, lon_i


def load_day_worker(
    file_path: str,
    selected_ids: Sequence[int],
    resample_points: int,
    min_traj_points: int,
) -> List[TrajectoryEntry]:
    table = pq.read_table(
        file_path,
        columns=["original_flight_id", "timestamp", "latitude", "longitude"],
        filters=[("original_flight_id", "in", list(selected_ids))],
    )
    if table.num_rows == 0:
        return []

    df = table.to_pandas()
    df = df.dropna(subset=["original_flight_id", "timestamp", "latitude", "longitude"])
    if df.empty:
        return []

    df["original_flight_id"] = df["original_flight_id"].astype(np.int64)
    df = df.sort_values(["original_flight_id", "timestamp"], kind="mergesort")

    out: List[TrajectoryEntry] = []
    for flight_id, sub in df.groupby("original_flight_id", sort=False):
        sub = sub.drop_duplicates(subset=["timestamp"], keep="first")
        if len(sub) < min_traj_points:
            continue

        ts_ns = pd.to_datetime(sub["timestamp"], utc=True).astype("int64").to_numpy(dtype=np.int64)
        lat = sub["latitude"].to_numpy(dtype=np.float64, copy=False)
        lon = sub["longitude"].to_numpy(dtype=np.float64, copy=False)

        resampled = resample_track(
            ts_ns=ts_ns,
            lat=lat,
            lon=lon,
            resample_points=resample_points,
            min_traj_points=min_traj_points,
        )
        if resampled is None:
            continue

        lat_i, lon_i = resampled
        out.append(TrajectoryEntry(flight_id=int(flight_id), lat=lat_i, lon=lon_i))

    return out


def load_trajectories(
    interp_dir: Path,
    selected_flights: pd.DataFrame,
    resample_points: int,
    min_traj_points: int,
    workers: int,
) -> Dict[int, TrajectoryEntry]:
    date_to_ids: Dict[str, List[int]] = (
        selected_flights.groupby("date_str")["flight_id"]
        .apply(lambda s: s.astype(int).tolist())
        .to_dict()
    )

    date_set = set(date_to_ids.keys())
    daily_files = list_daily_files(interp_dir, date_set)

    tasks: List[Tuple[str, List[int], int, int]] = []
    for date_str, file_path in daily_files:
        ids = date_to_ids.get(date_str)
        if not ids:
            continue
        tasks.append((str(file_path), ids, resample_points, min_traj_points))

    traj_map: Dict[int, TrajectoryEntry] = {}
    max_workers = max(1, min(workers, os.cpu_count() or 1))

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(load_day_worker, *task) for task in tasks]
        for future in as_completed(futures):
            entries = future.result()
            for entry in entries:
                traj_map[entry.flight_id] = entry

    return traj_map


def compute_phase_pair_metrics(
    pair_df: pd.DataFrame,
    traj_map: Dict[int, TrajectoryEntry],
    resample_points: int,
) -> pd.DataFrame:
    if resample_points < 100:
        raise ValueError("resample_points must be >= 100")

    phase_rows: List[dict] = []

    bin_edges = np.linspace(0, resample_points, 11, dtype=np.int32)
    bin_names = [f"{i*10}-{(i+1)*10}%" for i in range(10)]

    for row in pair_df.itertuples(index=False):
        t1 = traj_map.get(int(row.flight_id_1))
        t2 = traj_map.get(int(row.flight_id_2))
        if t1 is None or t2 is None:
            continue

        d = haversine_vec(t1.lat, t1.lon, t2.lat, t2.lon)

        phase = {
            "pair_type": row.pair_type,
            "flight_id_1": int(row.flight_id_1),
            "flight_id_2": int(row.flight_id_2),
            "full_0_100": float(np.mean(d)),
            "dep_0_5": float(np.mean(d[0 : max(1, int(resample_points * 0.05))])),
            "dep_0_10": float(np.mean(d[0 : max(1, int(resample_points * 0.10))])),
            "mid_45_55": float(
                np.mean(d[int(resample_points * 0.45) : int(resample_points * 0.55)])
            ),
            "app_80_95": float(
                np.mean(d[int(resample_points * 0.80) : int(resample_points * 0.95)])
            ),
            "app_90_100": float(np.mean(d[int(resample_points * 0.90) :])),
            "app_95_100": float(np.mean(d[int(resample_points * 0.95) :])),
        }

        for i, name in enumerate(bin_names):
            s = int(bin_edges[i])
            e = int(bin_edges[i + 1])
            phase[f"bin_{name}"] = float(np.mean(d[s:e]))

        phase_rows.append(phase)

    return pd.DataFrame(phase_rows)


def build_phase_similarity_summary(phase_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[dict] = []
    for pair_type, sub in phase_df.groupby("pair_type", sort=False):
        rows.append(
            {
                "pair_type": pair_type,
                "n": int(len(sub)),
                "full_mean_median": float(sub["full_0_100"].median()),
                "dep_median": float(sub["dep_0_10"].median()),
                "mid_median": float(sub["mid_45_55"].median()),
                "app_median": float(sub["app_90_100"].median()),
                "app_vs_full_ratio_median": float(
                    (sub["app_90_100"] / sub["full_0_100"]).median()
                ),
                "app_lt_mid_ratio": float((sub["app_90_100"] < sub["mid_45_55"]).mean()),
                "app_lt_dep_ratio": float((sub["app_90_100"] < sub["dep_0_10"]).mean()),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    order = {name: i for i, name in enumerate(ALL_PAIR_TYPES)}
    out["order"] = out["pair_type"].map(order).fillna(999)
    return out.sort_values(["order", "pair_type"]).drop(columns=["order"])


def build_progress_profile_summary(phase_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[dict] = []
    bin_names = [f"{i*10}-{(i+1)*10}%" for i in range(10)]

    for pair_type, sub in phase_df.groupby("pair_type", sort=False):
        for name in bin_names:
            col = f"bin_{name}"
            rows.append(
                {
                    "pair_type": pair_type,
                    "progress_bin": name,
                    "median_km": float(sub[col].median()),
                }
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    order = {name: i for i, name in enumerate(ALL_PAIR_TYPES)}
    out["pair_order"] = out["pair_type"].map(order).fillna(999)
    out["bin_order"] = out["progress_bin"].str.extract(r"^(\d+)-")[0].astype(int)
    out = out.sort_values(["pair_order", "bin_order", "pair_type"])
    return out.drop(columns=["pair_order", "bin_order"])


def build_takeoff_landing_summary(phase_df: pd.DataFrame) -> pd.DataFrame:
    focus = phase_df[phase_df["pair_type"].isin(["same_flight_cross_day", "same_route_cross_day"])].copy()
    rows: List[dict] = []
    for pair_type, sub in focus.groupby("pair_type", sort=False):
        full = sub["full_0_100"]
        rows.append(
            {
                "pair_type": pair_type,
                "n_pairs": int(len(sub)),
                "dep_0_5_median": float(sub["dep_0_5"].median()),
                "dep_0_10_median": float(sub["dep_0_10"].median()),
                "app_90_100_median": float(sub["app_90_100"].median()),
                "app_95_100_median": float(sub["app_95_100"].median()),
                "full_median": float(full.median()),
                "dep_0_5_over_full": float((sub["dep_0_5"] / full).median()),
                "app_95_100_over_full": float((sub["app_95_100"] / full).median()),
            }
        )
    return pd.DataFrame(rows)


def plot_phase_profile_all(profile_df: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for pair_type in ALL_PAIR_TYPES:
        sub = profile_df[profile_df["pair_type"] == pair_type]
        if sub.empty:
            continue
        ax.plot(sub["progress_bin"], sub["median_km"], marker="o", linewidth=2.0, label=pair_type)

    ax.set_yscale("log")
    ax.set_xlabel("normalized progress bins")
    ax.set_ylabel("median pointwise distance (km, log scale)")
    ax.set_title("Phase Similarity Profile by Trajectory Progress (All Pair Types)")
    ax.grid(True, linestyle="--", alpha=0.25)
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_phase_profile_focus(profile_df: pd.DataFrame, output_path: Path) -> None:
    color_map = {
        "same_flight_cross_day": "#2E86AB",
        "same_route_cross_day": "#F18F01",
        "same_route_same_day": "#6A994E",
    }

    fig, ax = plt.subplots(figsize=(11, 6.5))
    for pair_type in FOCUS_PAIR_TYPES:
        sub = profile_df[profile_df["pair_type"] == pair_type]
        if sub.empty:
            continue
        ax.plot(
            sub["progress_bin"],
            sub["median_km"],
            marker="o",
            linewidth=2.2,
            label=pair_type,
            color=color_map.get(pair_type),
        )

    ax.set_xlabel("normalized progress bins")
    ax.set_ylabel("median pointwise distance (km)")
    ax.set_title("Phase Similarity Profile (Route/Flight Focus)")
    ax.grid(True, linestyle="--", alpha=0.25)
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_stage_bar(summary_df: pd.DataFrame, output_path: Path) -> None:
    stage = summary_df[summary_df["pair_type"].isin(FOCUS_PAIR_TYPES)].copy()
    if stage.empty:
        return

    stage = stage[["pair_type", "dep_median", "mid_median", "app_median", "full_mean_median"]]
    stage = stage.rename(
        columns={
            "dep_median": "dep_0_10",
            "mid_median": "mid_45_55",
            "app_median": "app_90_100",
            "full_mean_median": "full_0_100",
        }
    )

    stage["order"] = stage["pair_type"].map({name: i for i, name in enumerate(FOCUS_PAIR_TYPES)})
    stage = stage.sort_values(["order", "pair_type"]).drop(columns=["order"])

    x = np.arange(len(stage))
    width = 0.2

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.bar(x - 1.5 * width, stage["dep_0_10"], width=width, label="dep_0_10")
    ax.bar(x - 0.5 * width, stage["mid_45_55"], width=width, label="mid_45_55")
    ax.bar(x + 0.5 * width, stage["app_90_100"], width=width, label="app_90_100")
    ax.bar(x + 1.5 * width, stage["full_0_100"], width=width, label="full_0_100", alpha=0.6)

    ax.set_xticks(x)
    ax.set_xticklabels(stage["pair_type"], rotation=0)
    ax.set_ylabel("median distance (km)")
    ax.set_title("Stage-Level Similarity Comparison")
    ax.grid(True, axis="y", linestyle="--", alpha=0.25)
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()

    interp_dir = Path(args.interp_dir)
    output_dir = Path(args.output_dir)
    fig_dir = output_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    selected_flights = pd.read_csv(args.selected_flights_csv)
    pair_df = pd.read_csv(args.pairwise_csv)

    selected_flights["flight_id"] = selected_flights["flight_id"].astype(np.int64)
    selected_flights["date_str"] = selected_flights["date_str"].astype(str)

    pair_df["flight_id_1"] = pair_df["flight_id_1"].astype(np.int64)
    pair_df["flight_id_2"] = pair_df["flight_id_2"].astype(np.int64)
    pair_df = pair_df[pair_df["pair_type"].isin(ALL_PAIR_TYPES)].copy()

    selected_ids = set(selected_flights["flight_id"].tolist())
    pair_df = pair_df[
        pair_df["flight_id_1"].isin(selected_ids) & pair_df["flight_id_2"].isin(selected_ids)
    ].copy()

    print(f"selected flights: {len(selected_flights)}")
    print(f"input pairs: {len(pair_df)}")

    traj_map = load_trajectories(
        interp_dir=interp_dir,
        selected_flights=selected_flights,
        resample_points=args.resample_points,
        min_traj_points=args.min_traj_points,
        workers=args.workers,
    )
    print(f"loaded trajectories: {len(traj_map)}")

    pair_df = pair_df[
        pair_df["flight_id_1"].isin(traj_map.keys()) & pair_df["flight_id_2"].isin(traj_map.keys())
    ].copy()
    print(f"usable pairs: {len(pair_df)}")

    phase_pair_df = compute_phase_pair_metrics(
        pair_df=pair_df,
        traj_map=traj_map,
        resample_points=args.resample_points,
    )
    if phase_pair_df.empty:
        raise RuntimeError("No phase pair metrics generated.")

    phase_summary_df = build_phase_similarity_summary(phase_pair_df)
    progress_profile_df = build_progress_profile_summary(phase_pair_df)
    takeoff_landing_df = build_takeoff_landing_summary(phase_pair_df)

    phase_pair_path = output_dir / "phase_pair_metrics.csv"
    phase_summary_path = output_dir / "phase_similarity_summary.csv"
    progress_profile_path = output_dir / "phase_profile_by_progress.csv"
    takeoff_landing_path = output_dir / "takeoff_landing_segment_summary.csv"

    phase_pair_df.to_csv(phase_pair_path, index=False)
    phase_summary_df.to_csv(phase_summary_path, index=False)
    progress_profile_df.to_csv(progress_profile_path, index=False)
    takeoff_landing_df.to_csv(takeoff_landing_path, index=False)

    plot_phase_profile_all(progress_profile_df, fig_dir / "phase_profile_all_log.png")
    plot_phase_profile_focus(progress_profile_df, fig_dir / "phase_profile_focus_linear.png")
    plot_stage_bar(phase_summary_df, fig_dir / "phase_stage_bar.png")

    print("\nphase summary:")
    print(phase_summary_df.to_string(index=False))
    print(f"\nOutputs saved to: {output_dir}")


if __name__ == "__main__":
    main()
