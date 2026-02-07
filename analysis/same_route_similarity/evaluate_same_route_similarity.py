#!/usr/bin/env python3
"""
Evaluate trajectory similarity with emphasis on cross-day flights on the same route.

Pair categories:
- same_flight_cross_day: same callsign+adep+ades across different days.
- same_route_cross_day: same adep+ades across different days.
- same_route_same_day: same adep+ades within the same day.
- diff_route_random: random pairs from different routes.

Outputs include CSV metrics and visualization figures.
"""

from __future__ import annotations

import argparse
import math
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import polars as pl
import pyarrow.parquet as pq

EARTH_RADIUS_KM = 6371.0
DATE_PATTERN = re.compile(r"interpolated_(\d{4}-\d{2}-\d{2})\.parquet")

PAIR_ORDER = [
    "same_flight_cross_day",
    "same_route_cross_day",
    "same_route_same_day",
    "diff_route_random",
]


@dataclass
class TrajectoryEntry:
    flight_id: int
    date_str: str
    lat: np.ndarray
    lon: np.ndarray
    alt: np.ndarray
    path_len_km: float
    raw_points: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze cross-day same-route trajectory similarity"
    )
    parser.add_argument(
        "--interp-dir",
        default="opensky_2024_PRC_dataset/interpolated_clean_eu_v5",
        help="Directory of interpolated daily parquet files",
    )
    parser.add_argument(
        "--meta-parquet",
        default="opensky_2024_PRC_dataset/flights/challenge_set.parquet",
        help="Flight metadata parquet path",
    )
    parser.add_argument(
        "--output-dir",
        default="analysis/same_route_similarity/output",
        help="Output directory for csv and figures",
    )
    parser.add_argument("--date-from", default=None, help="YYYY-MM-DD inclusive")
    parser.add_argument("--date-to", default=None, help="YYYY-MM-DD inclusive")
    parser.add_argument(
        "--min-route-days",
        type=int,
        default=10,
        help="Route must appear in at least this many unique days",
    )
    parser.add_argument(
        "--min-route-flights",
        type=int,
        default=20,
        help="Route must contain at least this many flights",
    )
    parser.add_argument(
        "--max-routes",
        type=int,
        default=250,
        help="Maximum number of routes to include",
    )
    parser.add_argument(
        "--max-flights-per-route-day",
        type=int,
        default=2,
        help="Sampling cap for each route-day",
    )
    parser.add_argument(
        "--max-flights-per-route",
        type=int,
        default=24,
        help="Sampling cap for each route total",
    )
    parser.add_argument(
        "--resample-points",
        type=int,
        default=200,
        help="Resample each trajectory to fixed number of points",
    )
    parser.add_argument(
        "--min-traj-points",
        type=int,
        default=20,
        help="Minimum raw points to keep one trajectory",
    )
    parser.add_argument(
        "--max-pairs-per-group",
        type=int,
        default=80,
        help="Sampling cap for pair count inside each group",
    )
    parser.add_argument(
        "--diff-route-pairs",
        type=int,
        default=4000,
        help="Target number of random different-route pairs",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) // 2),
        help="Worker processes for day-level trajectory loading",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def extract_date_from_file(file_name: str) -> str | None:
    match = DATE_PATTERN.fullmatch(file_name)
    if match is None:
        return None
    return match.group(1)


def list_daily_files(
    interp_dir: Path, date_from: str | None, date_to: str | None
) -> List[Tuple[str, Path]]:
    daily_files: List[Tuple[str, Path]] = []
    for path in sorted(interp_dir.glob("interpolated_*.parquet")):
        date_str = extract_date_from_file(path.name)
        if date_str is None:
            continue
        if date_from is not None and date_str < date_from:
            continue
        if date_to is not None and date_str > date_to:
            continue
        daily_files.append((date_str, path))
    return daily_files


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


def path_length_km(lat_deg: np.ndarray, lon_deg: np.ndarray) -> float:
    if lat_deg.size < 2:
        return 0.0
    segment = haversine_vec(lat_deg[:-1], lon_deg[:-1], lat_deg[1:], lon_deg[1:])
    return float(np.sum(segment))


def build_progress_from_timestamp(ts_ns: np.ndarray) -> np.ndarray:
    duration = ts_ns[-1] - ts_ns[0]
    if duration <= 0:
        return np.array([], dtype=np.float64)
    return (ts_ns - ts_ns[0]) / float(duration)


def resample_single_flight(
    ts_ns: np.ndarray,
    lat: np.ndarray,
    lon: np.ndarray,
    alt: np.ndarray,
    resample_points: int,
    min_traj_points: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    if ts_ns.size < min_traj_points:
        return None

    keep = np.empty(ts_ns.shape, dtype=bool)
    keep[0] = True
    keep[1:] = ts_ns[1:] > ts_ns[:-1]

    ts = ts_ns[keep]
    lat = lat[keep]
    lon = lon[keep]
    alt = alt[keep]

    if ts.size < min_traj_points:
        return None

    progress = build_progress_from_timestamp(ts)
    if progress.size == 0:
        return None

    target = np.linspace(0.0, 1.0, resample_points, dtype=np.float64)
    lat_i = np.interp(target, progress, lat)
    lon_i = np.interp(target, progress, lon)
    alt_i = np.interp(target, progress, alt)

    return lat_i, lon_i, alt_i


def load_day_trajectories_worker(
    file_path: str,
    date_str: str,
    selected_ids: Sequence[int],
    resample_points: int,
    min_traj_points: int,
) -> List[TrajectoryEntry]:
    columns = ["original_flight_id", "timestamp", "latitude", "longitude", "altitude"]
    table = pq.read_table(
        file_path,
        columns=columns,
        filters=[("original_flight_id", "in", list(selected_ids))],
    )
    if table.num_rows == 0:
        return []

    df = table.to_pandas()
    if df.empty:
        return []

    df = df.dropna(subset=["original_flight_id", "timestamp", "latitude", "longitude", "altitude"])
    if df.empty:
        return []

    df["original_flight_id"] = df["original_flight_id"].astype(np.int64)
    df = df.sort_values(["original_flight_id", "timestamp"], kind="mergesort")

    entries: List[TrajectoryEntry] = []
    for flight_id, sub in df.groupby("original_flight_id", sort=False):
        lat = sub["latitude"].to_numpy(dtype=np.float64, copy=False)
        lon = sub["longitude"].to_numpy(dtype=np.float64, copy=False)
        alt = sub["altitude"].to_numpy(dtype=np.float64, copy=False)
        ts_ns = pd.to_datetime(sub["timestamp"], utc=True).astype("int64").to_numpy(dtype=np.int64)

        resampled = resample_single_flight(
            ts_ns=ts_ns,
            lat=lat,
            lon=lon,
            alt=alt,
            resample_points=resample_points,
            min_traj_points=min_traj_points,
        )
        if resampled is None:
            continue

        lat_i, lon_i, alt_i = resampled
        entries.append(
            TrajectoryEntry(
                flight_id=int(flight_id),
                date_str=date_str,
                lat=lat_i,
                lon=lon_i,
                alt=alt_i,
                path_len_km=path_length_km(lat_i, lon_i),
                raw_points=int(lat.size),
            )
        )

    return entries


def load_metadata(meta_parquet: Path, valid_dates: Sequence[str]) -> pd.DataFrame:
    meta = (
        pl.scan_parquet(str(meta_parquet))
        .select(["flight_id", "date", "callsign", "adep", "ades"])
        .with_columns(
            pl.col("flight_id").cast(pl.Int64),
            pl.col("date").dt.strftime("%Y-%m-%d").alias("date_str"),
            pl.col("callsign").fill_null("").str.strip_chars().alias("callsign"),
        )
        .filter(
            pl.col("date_str").is_in(valid_dates)
            & (pl.col("callsign") != "")
            & pl.col("adep").is_not_null()
            & pl.col("ades").is_not_null()
        )
        .with_columns(
            (pl.col("adep") + pl.lit("|") + pl.col("ades")).alias("route_key"),
            (
                pl.col("callsign")
                + pl.lit("|")
                + pl.col("adep")
                + pl.lit("|")
                + pl.col("ades")
            ).alias("same_flight_key"),
        )
        .collect()
    )
    return meta.to_pandas()


def pick_routes_and_flights(meta_df: pd.DataFrame, args: argparse.Namespace) -> Tuple[pd.DataFrame, pd.DataFrame]:
    route_stats = (
        meta_df.groupby("route_key", as_index=False)
        .agg(n_flights=("flight_id", "size"), n_days=("date_str", "nunique"))
        .query("n_days >= @args.min_route_days and n_flights >= @args.min_route_flights")
        .sort_values(["n_days", "n_flights", "route_key"], ascending=[False, False, True])
    )

    if route_stats.empty:
        return pd.DataFrame(), route_stats

    if args.max_routes > 0:
        route_stats = route_stats.head(args.max_routes).copy()

    chosen_routes = set(route_stats["route_key"].tolist())
    subset = meta_df[meta_df["route_key"].isin(chosen_routes)].copy()

    rng = np.random.default_rng(args.seed)
    sampled_frames: List[pd.DataFrame] = []

    for route_key, route_df in subset.groupby("route_key", sort=False):
        day_samples: List[pd.DataFrame] = []
        for _, day_df in route_df.groupby("date_str", sort=False):
            n = min(args.max_flights_per_route_day, len(day_df))
            if n <= 0:
                continue
            rs = int(rng.integers(0, 2**31 - 1))
            day_samples.append(day_df.sample(n=n, random_state=rs))

        if not day_samples:
            continue

        merged = pd.concat(day_samples, ignore_index=True)
        if len(merged) > args.max_flights_per_route:
            rs = int(rng.integers(0, 2**31 - 1))
            merged = merged.sample(n=args.max_flights_per_route, random_state=rs)

        sampled_frames.append(merged)

    if not sampled_frames:
        return pd.DataFrame(), route_stats

    sampled = pd.concat(sampled_frames, ignore_index=True)
    sampled = sampled.drop_duplicates(subset=["flight_id"], keep="first")
    return sampled, route_stats


def load_selected_trajectories(
    daily_files: Sequence[Tuple[str, Path]],
    selected_meta: pd.DataFrame,
    args: argparse.Namespace,
) -> Tuple[Dict[int, TrajectoryEntry], pd.DataFrame]:
    date_to_ids: Dict[str, List[int]] = (
        selected_meta.groupby("date_str")["flight_id"].apply(lambda s: s.astype(int).tolist()).to_dict()
    )

    tasks: List[Tuple[str, str, List[int], int, int]] = []
    for date_str, file_path in daily_files:
        ids = date_to_ids.get(date_str)
        if not ids:
            continue
        tasks.append(
            (
                str(file_path),
                date_str,
                ids,
                args.resample_points,
                args.min_traj_points,
            )
        )

    traj_map: Dict[int, TrajectoryEntry] = {}
    meta_rows: List[dict] = []

    workers = max(1, min(args.workers, os.cpu_count() or 1))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(load_day_trajectories_worker, *task) for task in tasks]
        for future in as_completed(futures):
            entries = future.result()
            for entry in entries:
                traj_map[entry.flight_id] = entry
                meta_rows.append(
                    {
                        "flight_id": entry.flight_id,
                        "date_str": entry.date_str,
                        "path_len_km": entry.path_len_km,
                        "raw_points": entry.raw_points,
                    }
                )

    traj_meta = pd.DataFrame(meta_rows)
    return traj_map, traj_meta


def sample_pairs_within_group(
    group_df: pd.DataFrame,
    group_col: str,
    pair_type: str,
    max_pairs_per_group: int,
    require_diff_day: bool,
    rng: np.random.Generator,
) -> List[dict]:
    rows: List[dict] = []

    for group_key, sub in group_df.groupby(group_col, sort=False):
        items = sub[["flight_id", "date_str", "route_key", "same_flight_key"]].copy()
        records = items.to_dict("records")

        if len(records) < 2:
            continue

        candidates: List[Tuple[dict, dict]] = []
        for i in range(len(records) - 1):
            for j in range(i + 1, len(records)):
                left = records[i]
                right = records[j]
                if require_diff_day and left["date_str"] == right["date_str"]:
                    continue
                candidates.append((left, right))

        if not candidates:
            continue

        if len(candidates) > max_pairs_per_group:
            idx = rng.choice(len(candidates), size=max_pairs_per_group, replace=False)
            selected = [candidates[int(k)] for k in idx]
        else:
            selected = candidates

        for left, right in selected:
            rows.append(
                {
                    "pair_type": pair_type,
                    "group_key": group_key,
                    "flight_id_1": int(left["flight_id"]),
                    "flight_id_2": int(right["flight_id"]),
                    "date_1": left["date_str"],
                    "date_2": right["date_str"],
                    "route_key_1": left["route_key"],
                    "route_key_2": right["route_key"],
                    "same_flight_key_1": left["same_flight_key"],
                    "same_flight_key_2": right["same_flight_key"],
                }
            )

    return rows


def sample_diff_route_pairs(
    frame: pd.DataFrame,
    n_pairs: int,
    rng: np.random.Generator,
) -> List[dict]:
    records = frame[["flight_id", "date_str", "route_key", "same_flight_key"]].to_dict("records")
    if len(records) < 2:
        return []

    pair_set: set[Tuple[int, int]] = set()
    rows: List[dict] = []

    max_attempts = max(n_pairs * 40, 2000)
    attempts = 0

    while len(rows) < n_pairs and attempts < max_attempts:
        attempts += 1
        i, j = rng.choice(len(records), size=2, replace=False)
        left = records[int(i)]
        right = records[int(j)]

        if left["route_key"] == right["route_key"]:
            continue

        a = int(left["flight_id"])
        b = int(right["flight_id"])
        key = (min(a, b), max(a, b))
        if key in pair_set:
            continue
        pair_set.add(key)

        rows.append(
            {
                "pair_type": "diff_route_random",
                "group_key": "diff_route_random",
                "flight_id_1": a,
                "flight_id_2": b,
                "date_1": left["date_str"],
                "date_2": right["date_str"],
                "route_key_1": left["route_key"],
                "route_key_2": right["route_key"],
                "same_flight_key_1": left["same_flight_key"],
                "same_flight_key_2": right["same_flight_key"],
            }
        )

    return rows


def build_pair_table(valid_meta: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    rng = np.random.default_rng(args.seed)

    same_flight_pairs = sample_pairs_within_group(
        group_df=valid_meta,
        group_col="same_flight_key",
        pair_type="same_flight_cross_day",
        max_pairs_per_group=args.max_pairs_per_group,
        require_diff_day=True,
        rng=rng,
    )

    same_route_cross_day_pairs = sample_pairs_within_group(
        group_df=valid_meta,
        group_col="route_key",
        pair_type="same_route_cross_day",
        max_pairs_per_group=args.max_pairs_per_group,
        require_diff_day=True,
        rng=rng,
    )

    same_route_same_day_rows: List[dict] = []
    for (_, day), sub in valid_meta.groupby(["route_key", "date_str"], sort=False):
        if len(sub) < 2:
            continue
        same_route_same_day_rows.extend(
            sample_pairs_within_group(
                group_df=sub,
                group_col="route_key",
                pair_type="same_route_same_day",
                max_pairs_per_group=max(1, args.max_pairs_per_group // 2),
                require_diff_day=False,
                rng=rng,
            )
        )

    target_diff_route = max(args.diff_route_pairs, len(same_route_cross_day_pairs))
    diff_route_pairs = sample_diff_route_pairs(
        frame=valid_meta,
        n_pairs=target_diff_route,
        rng=rng,
    )

    all_rows = (
        same_flight_pairs
        + same_route_cross_day_pairs
        + same_route_same_day_rows
        + diff_route_pairs
    )
    pair_df = pd.DataFrame(all_rows)

    if pair_df.empty:
        return pair_df

    pair_df = pair_df.drop_duplicates(subset=["pair_type", "flight_id_1", "flight_id_2"])
    return pair_df


def compute_pair_metrics(
    pair_df: pd.DataFrame,
    traj_map: Dict[int, TrajectoryEntry],
) -> pd.DataFrame:
    metric_rows: List[dict] = []

    for row in pair_df.itertuples(index=False):
        entry1 = traj_map.get(int(row.flight_id_1))
        entry2 = traj_map.get(int(row.flight_id_2))
        if entry1 is None or entry2 is None:
            continue

        d_km = haversine_vec(entry1.lat, entry1.lon, entry2.lat, entry2.lon)
        mean_km = float(np.mean(d_km))
        p95_km = float(np.quantile(d_km, 0.95))

        alt_rmse_km = float(np.sqrt(np.mean((entry1.alt - entry2.alt) ** 2)) / 1000.0)

        ref_path = max((entry1.path_len_km + entry2.path_len_km) / 2.0, 1e-6)
        normalized_mean = mean_km / ref_path

        metric_rows.append(
            {
                "pair_type": row.pair_type,
                "group_key": row.group_key,
                "flight_id_1": int(row.flight_id_1),
                "flight_id_2": int(row.flight_id_2),
                "date_1": row.date_1,
                "date_2": row.date_2,
                "route_key_1": row.route_key_1,
                "route_key_2": row.route_key_2,
                "same_flight_key_1": row.same_flight_key_1,
                "same_flight_key_2": row.same_flight_key_2,
                "mean_pointwise_km": mean_km,
                "p95_pointwise_km": p95_km,
                "alt_rmse_km": alt_rmse_km,
                "normalized_mean_dist": normalized_mean,
                "path_len_km_1": entry1.path_len_km,
                "path_len_km_2": entry2.path_len_km,
            }
        )

    return pd.DataFrame(metric_rows)


def summarize_pair_types(metric_df: pd.DataFrame) -> pd.DataFrame:
    rows: List[dict] = []
    for pair_type, sub in metric_df.groupby("pair_type", sort=False):
        rows.append(
            {
                "pair_type": pair_type,
                "n_pairs": int(len(sub)),
                "mean_km_median": float(sub["mean_pointwise_km"].median()),
                "mean_km_p10": float(sub["mean_pointwise_km"].quantile(0.10)),
                "mean_km_p90": float(sub["mean_pointwise_km"].quantile(0.90)),
                "p95_km_median": float(sub["p95_pointwise_km"].median()),
                "alt_rmse_km_median": float(sub["alt_rmse_km"].median()),
                "norm_mean_median": float(sub["normalized_mean_dist"].median()),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    order_map = {name: i for i, name in enumerate(PAIR_ORDER)}
    out["order"] = out["pair_type"].map(order_map).fillna(999)
    out = out.sort_values(["order", "pair_type"]).drop(columns=["order"])
    return out


def summarize_route_level(metric_df: pd.DataFrame, valid_meta: pd.DataFrame) -> pd.DataFrame:
    route_cross = metric_df[metric_df["pair_type"] == "same_route_cross_day"].copy()
    if route_cross.empty:
        return pd.DataFrame()

    route_cross["route_key"] = route_cross["route_key_1"]

    summary = (
        route_cross.groupby("route_key", as_index=False)
        .agg(
            n_pairs=("mean_pointwise_km", "size"),
            median_mean_km=("mean_pointwise_km", "median"),
            p90_mean_km=("mean_pointwise_km", lambda s: float(s.quantile(0.90))),
            median_alt_rmse_km=("alt_rmse_km", "median"),
            median_norm_mean=("normalized_mean_dist", "median"),
        )
        .sort_values("median_mean_km")
    )

    route_days = (
        valid_meta.groupby("route_key", as_index=False)
        .agg(n_days=("date_str", "nunique"), n_flights=("flight_id", "size"))
    )

    return summary.merge(route_days, on="route_key", how="left")


def plot_boxplot(metric_df: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6.2))

    data: List[np.ndarray] = []
    labels: List[str] = []
    for pair_type in PAIR_ORDER:
        sub = metric_df.loc[metric_df["pair_type"] == pair_type, "mean_pointwise_km"].to_numpy()
        if sub.size == 0:
            continue
        data.append(sub)
        labels.append(pair_type)

    if not data:
        plt.close(fig)
        return

    bp = ax.boxplot(data, tick_labels=labels, showfliers=False, patch_artist=True)
    colors = ["#2E86AB", "#F18F01", "#6A994E", "#A23B72"]
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.45)

    ax.set_yscale("log")
    ax.set_ylabel("mean_pointwise_km (log scale)")
    ax.set_title("Trajectory Similarity Distribution by Pair Type")
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.autofmt_xdate(rotation=20)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def plot_cdf(metric_df: pd.DataFrame, output_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(11, 6.2))

    for pair_type in PAIR_ORDER:
        values = (
            metric_df.loc[metric_df["pair_type"] == pair_type, "mean_pointwise_km"]
            .dropna()
            .to_numpy()
        )
        if values.size == 0:
            continue
        values = np.sort(values)
        y = np.arange(1, values.size + 1, dtype=np.float64) / float(values.size)
        ax.plot(values, y, linewidth=2.0, label=f"{pair_type} (n={values.size})")

    ax.set_xscale("log")
    ax.set_xlabel("mean_pointwise_km (log scale)")
    ax.set_ylabel("CDF")
    ax.set_title("CDF of Pointwise Mean Distance")
    ax.grid(True, alpha=0.25, linestyle="--")
    ax.legend(frameon=True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def select_overlay_routes(route_summary: pd.DataFrame) -> List[Tuple[str, str]]:
    if route_summary.empty:
        return []

    ordered = route_summary.sort_values("median_mean_km").reset_index(drop=True)
    n = len(ordered)
    idx_map = {
        "low": int(round((n - 1) * 0.10)),
        "mid": int(round((n - 1) * 0.50)),
        "high": int(round((n - 1) * 0.90)),
    }

    selected: List[Tuple[str, str]] = []
    used_routes: set[str] = set()
    for label, idx in idx_map.items():
        route_key = str(ordered.iloc[idx]["route_key"])
        if route_key in used_routes:
            continue
        used_routes.add(route_key)
        selected.append((label, route_key))

    return selected


def plot_route_overlay(
    route_key: str,
    tag: str,
    valid_meta: pd.DataFrame,
    traj_map: Dict[int, TrajectoryEntry],
    output_dir: Path,
) -> None:
    route_df = (
        valid_meta.loc[valid_meta["route_key"] == route_key, ["flight_id", "date_str"]]
        .sort_values("date_str")
        .drop_duplicates(subset=["flight_id"])
    )

    if route_df.empty:
        return

    fig, ax = plt.subplots(figsize=(8.6, 7.6))

    max_lines = 12
    plotted = 0

    cmap = plt.get_cmap("tab20", max(1, len(route_df)))
    for idx, row in enumerate(route_df.itertuples(index=False)):
        entry = traj_map.get(int(row.flight_id))
        if entry is None:
            continue
        ax.plot(entry.lon, entry.lat, color=cmap(idx), alpha=0.85, linewidth=1.25)
        ax.text(entry.lon[0], entry.lat[0], row.date_str, fontsize=6, alpha=0.85)
        plotted += 1
        if plotted >= max_lines:
            break

    if plotted == 0:
        plt.close(fig)
        return

    adep, ades = route_key.split("|", 1)
    ax.set_title(f"{tag}: {adep} -> {ades} (up to {plotted} flights)")
    ax.set_xlabel("longitude")
    ax.set_ylabel("latitude")
    ax.grid(True, alpha=0.2, linestyle="--")
    fig.tight_layout()

    safe_route = route_key.replace("|", "__")
    out = output_dir / f"overlay_{tag}_{safe_route}.png"
    fig.savefig(out, dpi=180)
    plt.close(fig)


def print_brief_summary(summary_df: pd.DataFrame) -> None:
    print("\n=== Pair-Type Summary ===")
    if summary_df.empty:
        print("No pair metrics were produced.")
        return

    for row in summary_df.itertuples(index=False):
        print(
            f"{row.pair_type:>22} | n={row.n_pairs:6d} | "
            f"median(mean_km)={row.mean_km_median:8.3f} | "
            f"median(p95_km)={row.p95_km_median:8.3f} | "
            f"median(alt_rmse_km)={row.alt_rmse_km_median:7.3f}"
        )


def main() -> None:
    args = parse_args()

    interp_dir = Path(args.interp_dir)
    meta_parquet = Path(args.meta_parquet)
    output_dir = Path(args.output_dir)
    figure_dir = output_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    daily_files = list_daily_files(interp_dir, args.date_from, args.date_to)
    if not daily_files:
        raise RuntimeError("No interpolated parquet files found in the selected date range.")

    valid_dates = [d for d, _ in daily_files]
    print(
        f"Using {len(daily_files)} daily files from {valid_dates[0]} to {valid_dates[-1]}"
    )

    meta_df = load_metadata(meta_parquet, valid_dates)
    if meta_df.empty:
        raise RuntimeError("Metadata is empty after filters.")
    print(f"Metadata rows after date/callsign filter: {len(meta_df)}")

    selected_meta, route_stats = pick_routes_and_flights(meta_df, args)
    if selected_meta.empty:
        raise RuntimeError("No routes/flights left after sampling constraints.")

    print(
        f"Selected routes: {selected_meta['route_key'].nunique()} | "
        f"selected flights: {len(selected_meta)}"
    )

    traj_map, traj_meta = load_selected_trajectories(daily_files, selected_meta, args)
    if not traj_map:
        raise RuntimeError("No valid trajectories loaded after interpolation and quality checks.")

    valid_meta = selected_meta[selected_meta["flight_id"].isin(traj_map.keys())].copy()
    valid_meta = valid_meta.merge(traj_meta, on=["flight_id", "date_str"], how="left")

    print(
        f"Trajectories loaded: {len(traj_map)} | "
        f"routes with trajectories: {valid_meta['route_key'].nunique()}"
    )

    pair_df = build_pair_table(valid_meta, args)
    if pair_df.empty:
        raise RuntimeError("Pair table is empty. Try relaxing sampling constraints.")

    print(f"Pair candidates: {len(pair_df)}")

    metric_df = compute_pair_metrics(pair_df, traj_map)
    if metric_df.empty:
        raise RuntimeError("Metric table is empty after pair evaluation.")

    summary_df = summarize_pair_types(metric_df)
    route_summary_df = summarize_route_level(metric_df, valid_meta)

    metric_path = output_dir / "pairwise_metrics.csv"
    summary_path = output_dir / "pair_type_summary.csv"
    route_path = output_dir / "route_similarity_summary.csv"
    selected_path = output_dir / "selected_flights.csv"

    metric_df.to_csv(metric_path, index=False)
    summary_df.to_csv(summary_path, index=False)
    route_summary_df.to_csv(route_path, index=False)
    valid_meta.to_csv(selected_path, index=False)

    plot_boxplot(metric_df, figure_dir / "distribution_boxplot_log.png")
    plot_cdf(metric_df, figure_dir / "distance_cdf_log.png")

    for tag, route_key in select_overlay_routes(route_summary_df):
        plot_route_overlay(
            route_key=route_key,
            tag=tag,
            valid_meta=valid_meta,
            traj_map=traj_map,
            output_dir=figure_dir,
        )

    print_brief_summary(summary_df)
    print(f"\nOutputs saved to: {output_dir}")


if __name__ == "__main__":
    main()
