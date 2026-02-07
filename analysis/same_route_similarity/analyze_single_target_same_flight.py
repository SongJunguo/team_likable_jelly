#!/usr/bin/env python3
"""
Single-target same-flight similarity analysis with query-window highlighting.

Given one interpolated flight (flight_id in a daily interpolated parquet) and a query
window [t_start, t_end], this script:
1) maps to original_flight_id and same-flight key (callsign+adep+ades),
2) finds same-flight references in interpolated_clean_eu_v5,
3) computes pairwise similarity metrics for full / query window / landing segment,
4) saves CSV summaries,
5) plots an overlay map with query window highlighted and a distance profile.
"""

from __future__ import annotations

import argparse
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

EARTH_RADIUS_KM = 6371.0
DATE_PATTERN = re.compile(r"interpolated_(\d{4}-\d{2}-\d{2})\.parquet")


@dataclass
class ResampledTrajectory:
    flight_id: int
    date_str: str
    lat: np.ndarray
    lon: np.ndarray
    alt: np.ndarray
    ts_min: pd.Timestamp
    ts_max: pd.Timestamp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze one target flight against same-flight references"
    )
    parser.add_argument(
        "--source-file",
        required=True,
        help="Daily interpolated parquet file containing target flight_id",
    )
    parser.add_argument(
        "--flight-id",
        type=int,
        required=True,
        help="Target interpolated flight_id (not original_flight_id)",
    )
    parser.add_argument(
        "--t-start",
        required=True,
        help="Query window start timestamp, e.g. 2022-01-30T09:26:47Z",
    )
    parser.add_argument(
        "--t-end",
        required=True,
        help="Query window end timestamp, e.g. 2022-01-30T09:37:27Z",
    )
    parser.add_argument(
        "--interp-dir",
        default="opensky_2024_PRC_dataset/interpolated_clean_eu_v5",
        help="Interpolated parquet directory",
    )
    parser.add_argument(
        "--meta-parquet",
        default="opensky_2024_PRC_dataset/flights/challenge_set.parquet",
        help="challenge_set parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis/same_route_similarity/output",
        help="Output directory",
    )
    parser.add_argument(
        "--resample-points",
        type=int,
        default=400,
        help="Resample points for trajectory alignment",
    )
    parser.add_argument(
        "--min-traj-points",
        type=int,
        default=20,
        help="Minimum raw points to keep a trajectory",
    )
    parser.add_argument(
        "--top-k-window",
        type=int,
        default=5,
        help="Top-K references by mean_km_window for figure overlay",
    )
    parser.add_argument(
        "--top-k-app95",
        type=int,
        default=5,
        help="Top-K references by mean_km_app_95_100 for figure overlay",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) // 2),
        help="Worker process count for loading references",
    )
    return parser.parse_args()


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
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


def extract_date_from_file_name(name: str) -> Optional[str]:
    match = DATE_PATTERN.fullmatch(name)
    return None if match is None else match.group(1)


def resample_dataframe(
    df: pd.DataFrame,
    resample_points: int,
    min_traj_points: int,
    flight_id: int,
    date_str: str,
) -> Optional[ResampledTrajectory]:
    df = df.dropna(subset=["timestamp", "latitude", "longitude", "altitude"]).copy()
    if len(df) < min_traj_points:
        return None

    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="first")
    if len(df) < min_traj_points:
        return None

    ts = pd.to_datetime(df["timestamp"], utc=True).astype("int64").to_numpy(dtype=np.int64)
    if ts[-1] <= ts[0]:
        return None

    progress = (ts - ts[0]) / float(ts[-1] - ts[0])
    keep = np.empty(progress.shape, dtype=bool)
    keep[0] = True
    keep[1:] = np.diff(progress) > 0
    progress = progress[keep]
    if len(progress) < min_traj_points:
        return None

    lat = df["latitude"].to_numpy(dtype=np.float64)[keep]
    lon = df["longitude"].to_numpy(dtype=np.float64)[keep]
    alt = df["altitude"].to_numpy(dtype=np.float64)[keep]

    target = np.linspace(0.0, 1.0, resample_points, dtype=np.float64)
    lat_i = np.interp(target, progress, lat)
    lon_i = np.interp(target, progress, lon)
    alt_i = np.interp(target, progress, alt)

    return ResampledTrajectory(
        flight_id=flight_id,
        date_str=date_str,
        lat=lat_i,
        lon=lon_i,
        alt=alt_i,
        ts_min=pd.to_datetime(ts[0], utc=True),
        ts_max=pd.to_datetime(ts[-1], utc=True),
    )


def _load_reference_worker(
    file_path: str,
    original_flight_id: int,
    date_str: str,
    resample_points: int,
    min_traj_points: int,
) -> Optional[ResampledTrajectory]:
    table = pq.read_table(
        file_path,
        columns=["original_flight_id", "timestamp", "latitude", "longitude", "altitude"],
        filters=[("original_flight_id", "==", int(original_flight_id))],
    )
    if table.num_rows == 0:
        return None

    df = table.to_pandas()
    return resample_dataframe(
        df=df,
        resample_points=resample_points,
        min_traj_points=min_traj_points,
        flight_id=int(original_flight_id),
        date_str=date_str,
    )


def find_target_trajectory(
    source_file: Path,
    flight_id: int,
    resample_points: int,
    min_traj_points: int,
) -> Tuple[pd.DataFrame, ResampledTrajectory, int]:
    table = pq.read_table(
        source_file,
        columns=["flight_id", "original_flight_id", "timestamp", "latitude", "longitude", "altitude"],
        filters=[("flight_id", "==", int(flight_id))],
    )
    if table.num_rows == 0:
        raise RuntimeError(f"flight_id={flight_id} not found in {source_file}")

    df = table.to_pandas()
    original_ids = df["original_flight_id"].dropna().astype(np.int64).unique().tolist()
    if len(original_ids) != 1:
        raise RuntimeError(f"Expected one original_flight_id, got {original_ids}")

    date_str = extract_date_from_file_name(source_file.name)
    if date_str is None:
        raise RuntimeError(f"Cannot parse date from file name: {source_file.name}")

    target_res = resample_dataframe(
        df=df,
        resample_points=resample_points,
        min_traj_points=min_traj_points,
        flight_id=int(flight_id),
        date_str=date_str,
    )
    if target_res is None:
        raise RuntimeError("Target trajectory cannot be resampled")

    return df, target_res, int(original_ids[0])


def load_target_meta(meta_parquet: Path, original_flight_id: int) -> pd.Series:
    table = pq.read_table(
        meta_parquet,
        columns=["flight_id", "date", "callsign", "adep", "ades", "airline", "aircraft_type"],
        filters=[("flight_id", "==", int(original_flight_id))],
    )
    if table.num_rows == 0:
        raise RuntimeError(f"original_flight_id={original_flight_id} not found in challenge_set")
    return table.to_pandas().iloc[0]


def build_availability_maps(interp_dir: Path) -> Tuple[Dict[str, Path], Dict[str, set[int]]]:
    date_to_file: Dict[str, Path] = {}
    avail_by_date: Dict[str, set[int]] = {}

    for path in sorted(interp_dir.glob("interpolated_*.parquet")):
        date_str = extract_date_from_file_name(path.name)
        if date_str is None:
            continue
        date_to_file[date_str] = path
        table = pq.read_table(path, columns=["original_flight_id"])
        ids = pd.Series(table.column("original_flight_id").to_numpy()).astype("int64").unique().tolist()
        avail_by_date[date_str] = set(int(x) for x in ids)

    return date_to_file, avail_by_date


def collect_same_flight_candidates(
    meta_parquet: Path,
    callsign: str,
    adep: str,
    ades: str,
    avail_by_date: Dict[str, set[int]],
) -> pd.DataFrame:
    meta = pq.read_table(
        meta_parquet,
        columns=["flight_id", "date", "callsign", "adep", "ades"],
    ).to_pandas()
    meta["date_str"] = pd.to_datetime(meta["date"]).dt.strftime("%Y-%m-%d")

    same = meta[
        (meta["callsign"] == callsign)
        & (meta["adep"] == adep)
        & (meta["ades"] == ades)
    ].copy()

    same["available"] = same.apply(
        lambda r: (r["date_str"] in avail_by_date)
        and (int(r["flight_id"]) in avail_by_date[r["date_str"]]),
        axis=1,
    )
    same_avail = same[same["available"]].copy().sort_values("date_str")
    return same_avail


def load_reference_trajectories(
    same_avail: pd.DataFrame,
    target_original_id: int,
    date_to_file: Dict[str, Path],
    resample_points: int,
    min_traj_points: int,
    workers: int,
) -> Dict[int, ResampledTrajectory]:
    tasks: List[Tuple[str, int, str, int, int]] = []

    for row in same_avail.itertuples(index=False):
        fid = int(row.flight_id)
        if fid == target_original_id:
            continue
        date_str = str(row.date_str)
        file_path = date_to_file.get(date_str)
        if file_path is None:
            continue
        tasks.append((str(file_path), fid, date_str, resample_points, min_traj_points))

    refs: Dict[int, ResampledTrajectory] = {}
    max_workers = max(1, min(workers, os.cpu_count() or 1))

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_load_reference_worker, *task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            if result is None:
                continue
            refs[result.flight_id] = result

    return refs


def progress_of_time(ts0: pd.Timestamp, ts1: pd.Timestamp, t: pd.Timestamp) -> float:
    if t <= ts0:
        return 0.0
    if t >= ts1:
        return 1.0
    return float((t - ts0) / (ts1 - ts0))


def compute_similarity_table(
    target: ResampledTrajectory,
    refs: Dict[int, ResampledTrajectory],
    p_start: float,
    p_end: float,
) -> pd.DataFrame:
    n = target.lat.shape[0]
    s0 = int(np.floor(p_start * n))
    s1 = int(np.ceil(p_end * n))
    s0 = max(0, min(n - 1, s0))
    s1 = max(s0 + 1, min(n, s1))
    app90 = int(n * 0.90)
    app95 = int(n * 0.95)

    rows: List[dict] = []
    for ref in refs.values():
        dist = haversine_vec(target.lat, target.lon, ref.lat, ref.lon)
        alt_rmse_m = float(np.sqrt(np.mean((target.alt - ref.alt) ** 2)))

        rows.append(
            {
                "ref_flight_id": int(ref.flight_id),
                "ref_date": ref.date_str,
                "mean_km_full": float(np.mean(dist)),
                "p95_km_full": float(np.quantile(dist, 0.95)),
                "mean_km_window": float(np.mean(dist[s0:s1])),
                "p95_km_window": float(np.quantile(dist[s0:s1], 0.95)),
                "mean_km_app_90_100": float(np.mean(dist[app90:])),
                "mean_km_app_95_100": float(np.mean(dist[app95:])),
                "alt_rmse_m": alt_rmse_m,
            }
        )

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("mean_km_window").reset_index(drop=True)


def build_summary(
    target_interp_id: int,
    target_original_id: int,
    callsign: str,
    adep: str,
    ades: str,
    target_raw_df: pd.DataFrame,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    p_start: float,
    p_end: float,
    same_avail_count: int,
    similarity_df: pd.DataFrame,
) -> dict:
    ts_min = pd.to_datetime(target_raw_df["timestamp"], utc=True).min()
    ts_max = pd.to_datetime(target_raw_df["timestamp"], utc=True).max()

    summary = {
        "target_interp_flight_id": int(target_interp_id),
        "target_original_flight_id": int(target_original_id),
        "same_flight_key": f"{callsign}|{adep}|{ades}",
        "route": f"{adep}|{ades}",
        "available_same_flight_count_in_interp_period": int(same_avail_count),
        "reference_count_excluding_target": int(len(similarity_df)),
        "target_time_min": str(ts_min),
        "target_time_max": str(ts_max),
        "query_window_t_start": str(t_start),
        "query_window_t_end": str(t_end),
        "query_window_progress_start": float(p_start),
        "query_window_progress_end": float(p_end),
        "query_window_progress_width": float(p_end - p_start),
        "window_mean_median_km": float(similarity_df["mean_km_window"].median()),
        "window_mean_p10_km": float(similarity_df["mean_km_window"].quantile(0.10)),
        "window_mean_p90_km": float(similarity_df["mean_km_window"].quantile(0.90)),
        "app_90_100_median_km": float(similarity_df["mean_km_app_90_100"].median()),
        "app_95_100_median_km": float(similarity_df["mean_km_app_95_100"].median()),
        "best_window_mean_km": float(similarity_df["mean_km_window"].iloc[0]),
        "best_window_ref_flight_id": int(similarity_df["ref_flight_id"].iloc[0]),
        "best_window_ref_date": str(similarity_df["ref_date"].iloc[0]),
        "best_app95_mean_km": float(
            similarity_df.sort_values("mean_km_app_95_100")["mean_km_app_95_100"].iloc[0]
        ),
        "best_app95_ref_flight_id": int(
            similarity_df.sort_values("mean_km_app_95_100")["ref_flight_id"].iloc[0]
        ),
        "best_app95_ref_date": str(
            similarity_df.sort_values("mean_km_app_95_100")["ref_date"].iloc[0]
        ),
    }

    for thr in [2, 3, 5, 8, 10, 15, 20, 30]:
        summary[f"ratio_window_le_{thr}km"] = float((similarity_df["mean_km_window"] <= thr).mean())
        summary[f"ratio_app95_le_{thr}km"] = float((similarity_df["mean_km_app_95_100"] <= thr).mean())

    return summary


def select_overlay_references(
    similarity_df: pd.DataFrame,
    refs: Dict[int, ResampledTrajectory],
    top_k_window: int,
    top_k_app95: int,
) -> List[ResampledTrajectory]:
    window_top = similarity_df.sort_values("mean_km_window").head(top_k_window)
    app_top = similarity_df.sort_values("mean_km_app_95_100").head(top_k_app95)
    chosen = pd.concat(
        [window_top[["ref_flight_id"]], app_top[["ref_flight_id"]]],
        ignore_index=True,
    ).drop_duplicates()

    result: List[ResampledTrajectory] = []
    for fid in chosen["ref_flight_id"].astype(int).tolist():
        ref = refs.get(fid)
        if ref is not None:
            result.append(ref)
    return result


def plot_overlay_with_query_window(
    target: ResampledTrajectory,
    refs: Sequence[ResampledTrajectory],
    p_start: float,
    p_end: float,
    route_text: str,
    output_path: Path,
) -> None:
    n = target.lat.shape[0]
    s0 = int(np.floor(p_start * n))
    s1 = int(np.ceil(p_end * n))
    s0 = max(0, min(n - 1, s0))
    s1 = max(s0 + 1, min(n, s1))
    l0 = int(n * 0.90)

    fig, ax = plt.subplots(figsize=(9.2, 7.6))

    cmap = plt.get_cmap("tab20", max(1, len(refs)))
    for i, ref in enumerate(refs):
        ax.plot(
            ref.lon,
            ref.lat,
            color=cmap(i),
            linewidth=1.2,
            alpha=0.80,
            label=f"ref {ref.flight_id} {ref.date_str}",
        )

    ax.plot(
        target.lon,
        target.lat,
        color="black",
        linewidth=2.0,
        alpha=0.9,
        label=f"target {target.flight_id} {target.date_str}",
    )

    # Highlight user query window in red.
    ax.plot(
        target.lon[s0:s1],
        target.lat[s0:s1],
        color="red",
        linewidth=3.8,
        alpha=0.95,
        label="target query window",
    )

    # Keep landing segment indicator for phase reference.
    ax.plot(
        target.lon[l0:],
        target.lat[l0:],
        color="#7A1FA2",
        linewidth=2.8,
        alpha=0.85,
        linestyle="--",
        label="target last 10%",
    )

    ax.scatter(target.lon[s0], target.lat[s0], color="red", s=28, zorder=5)
    ax.scatter(target.lon[s1 - 1], target.lat[s1 - 1], color="red", s=28, zorder=5)

    ax.set_title(f"Target vs Same-Flight References ({route_text})")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.grid(True, alpha=0.22, linestyle="--")
    ax.legend(fontsize=7, ncol=2, frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_distance_profile(
    target: ResampledTrajectory,
    refs: Sequence[ResampledTrajectory],
    p_start: float,
    p_end: float,
    output_path: Path,
) -> None:
    n = target.lat.shape[0]
    progress_pct = np.linspace(0.0, 100.0, n)

    fig, ax = plt.subplots(figsize=(11.0, 6.2))

    cmap = plt.get_cmap("tab20", max(1, len(refs)))
    for i, ref in enumerate(refs):
        dist = haversine_vec(target.lat, target.lon, ref.lat, ref.lon)
        ax.plot(
            progress_pct,
            dist,
            color=cmap(i),
            linewidth=1.2,
            alpha=0.82,
            label=f"ref {ref.flight_id} {ref.date_str}",
        )

    ax.axvspan(p_start * 100.0, p_end * 100.0, color="red", alpha=0.10, label="query window")
    ax.axvspan(90.0, 100.0, color="#7A1FA2", alpha=0.08, label="last 10%")

    ax.set_yscale("log")
    ax.set_xlabel("normalized progress (%)")
    ax.set_ylabel("pointwise distance (km, log scale)")
    ax.set_title("Distance Profile: Target vs Same-Flight References")
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.legend(fontsize=7, ncol=2, frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main() -> None:
    args = parse_args()

    source_file = Path(args.source_file)
    interp_dir = Path(args.interp_dir)
    meta_parquet = Path(args.meta_parquet)
    output_dir = Path(args.output_dir)
    fig_dir = output_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    fig_dir.mkdir(parents=True, exist_ok=True)

    t_start = pd.Timestamp(args.t_start)
    t_end = pd.Timestamp(args.t_end)
    if t_start.tzinfo is None:
        t_start = t_start.tz_localize("UTC")
    else:
        t_start = t_start.tz_convert("UTC")
    if t_end.tzinfo is None:
        t_end = t_end.tz_localize("UTC")
    else:
        t_end = t_end.tz_convert("UTC")

    target_raw_df, target, target_original_id = find_target_trajectory(
        source_file=source_file,
        flight_id=args.flight_id,
        resample_points=args.resample_points,
        min_traj_points=args.min_traj_points,
    )

    target_meta = load_target_meta(meta_parquet, target_original_id)
    callsign = str(target_meta["callsign"])
    adep = str(target_meta["adep"])
    ades = str(target_meta["ades"])

    ts_sorted = pd.to_datetime(
        target_raw_df.sort_values("timestamp")["timestamp"], utc=True
    ).drop_duplicates(keep="first")
    ts0 = ts_sorted.iloc[0]
    ts1 = ts_sorted.iloc[-1]

    p_start = progress_of_time(ts0, ts1, t_start)
    p_end = progress_of_time(ts0, ts1, t_end)
    if p_end < p_start:
        p_start, p_end = p_end, p_start

    date_to_file, avail_by_date = build_availability_maps(interp_dir)
    same_avail = collect_same_flight_candidates(
        meta_parquet=meta_parquet,
        callsign=callsign,
        adep=adep,
        ades=ades,
        avail_by_date=avail_by_date,
    )

    refs = load_reference_trajectories(
        same_avail=same_avail,
        target_original_id=target_original_id,
        date_to_file=date_to_file,
        resample_points=args.resample_points,
        min_traj_points=args.min_traj_points,
        workers=args.workers,
    )
    if not refs:
        raise RuntimeError("No same-flight references available after filtering/resampling")

    similarity_df = compute_similarity_table(
        target=target,
        refs=refs,
        p_start=p_start,
        p_end=p_end,
    )
    if similarity_df.empty:
        raise RuntimeError("No similarity rows generated")

    summary = build_summary(
        target_interp_id=args.flight_id,
        target_original_id=target_original_id,
        callsign=callsign,
        adep=adep,
        ades=ades,
        target_raw_df=target_raw_df,
        t_start=t_start,
        t_end=t_end,
        p_start=p_start,
        p_end=p_end,
        same_avail_count=len(same_avail),
        similarity_df=similarity_df,
    )

    sim_csv = output_dir / f"target_{args.flight_id}_same_flight_similarity.csv"
    sum_csv = output_dir / f"target_{args.flight_id}_summary.csv"
    similarity_df.to_csv(sim_csv, index=False)
    pd.DataFrame([summary]).to_csv(sum_csv, index=False)

    selected_refs = select_overlay_references(
        similarity_df=similarity_df,
        refs=refs,
        top_k_window=args.top_k_window,
        top_k_app95=args.top_k_app95,
    )

    overlay_png = fig_dir / f"target_{args.flight_id}_top_refs_overlay.png"
    overlay_window_png = fig_dir / f"target_{args.flight_id}_top_refs_overlay_query_window.png"
    profile_png = fig_dir / f"target_{args.flight_id}_distance_profile.png"

    route_text = f"{adep}->{ades}"
    plot_overlay_with_query_window(
        target=target,
        refs=selected_refs,
        p_start=p_start,
        p_end=p_end,
        route_text=route_text,
        output_path=overlay_png,
    )
    # Keep an explicit filename for query-window highlighted version.
    if overlay_window_png != overlay_png:
        overlay_window_png.write_bytes(overlay_png.read_bytes())

    plot_distance_profile(
        target=target,
        refs=selected_refs,
        p_start=p_start,
        p_end=p_end,
        output_path=profile_png,
    )

    print("=== TARGET META ===")
    print("target_interp_flight_id:", args.flight_id)
    print("target_original_flight_id:", target_original_id)
    print("same_flight_key:", summary["same_flight_key"])
    print("route:", summary["route"])
    print("query_progress:", f"{summary['query_window_progress_start']:.6f}", "->", f"{summary['query_window_progress_end']:.6f}")
    print("same-flight refs:", summary["reference_count_excluding_target"])

    print("\n=== SUMMARY (key) ===")
    for key in [
        "window_mean_median_km",
        "app_90_100_median_km",
        "app_95_100_median_km",
        "best_window_mean_km",
        "best_window_ref_flight_id",
        "best_app95_mean_km",
        "best_app95_ref_flight_id",
        "ratio_window_le_10km",
        "ratio_app95_le_10km",
    ]:
        value = summary[key]
        if isinstance(value, float):
            print(f"{key}: {value:.6f}")
        else:
            print(f"{key}: {value}")

    print("\nwritten:", sim_csv)
    print("written:", sum_csv)
    print("written:", overlay_png)
    print("written:", overlay_window_png)
    print("written:", profile_png)


if __name__ == "__main__":
    main()
