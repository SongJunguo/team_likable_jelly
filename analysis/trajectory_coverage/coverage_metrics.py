#!/usr/bin/env python3
"""
Compute trajectory coverage metrics and great-circle alignment.

Notes:
- Uses flight_id -> flights/challenge_set.parquet to map adep/ades.
  Airport coordinates and continent are looked up from airports_tz.parquet.
- Designed for daily parquet shards; flight_id is assumed unique per day.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pyarrow.parquet as pq

EARTH_RADIUS_KM = 6371.0
DEFAULT_DATA_DIR = Path("opensky_2024_PRC_dataset/rawtrajectories")
DEFAULT_FLIGHTS_PATH = Path("opensky_2024_PRC_dataset/flights/challenge_set.parquet")
DEFAULT_AIRPORTS_PATH = Path("opensky_2024_PRC_dataset/airports_tz.parquet")
DEFAULT_EUROPE_CONTINENT = "EU"

_WORKER_FLIGHT_META: Optional[Dict[int, Tuple[Optional[str], Optional[str]]]] = None
_WORKER_AIRPORT_META: Optional[
    Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]]
] = None
_WORKER_EUROPE_CONTINENT: str = DEFAULT_EUROPE_CONTINENT


@dataclass
class FlightMetrics:
    flight_id: int
    adep: Optional[str]
    ades: Optional[str]
    adep_lat: Optional[float]
    adep_lon: Optional[float]
    ades_lat: Optional[float]
    ades_lon: Optional[float]
    continent_adep: Optional[str]
    continent_ades: Optional[str]
    is_eu: bool
    points_total: int
    points_valid: int
    points_used: int
    gc_distance_km: Optional[float]
    xt_mean_km: Optional[float]
    xt_std_km: Optional[float]
    xt_median_km: Optional[float]
    xt_p95_km: Optional[float]
    ratio_xt_le_20km: Optional[float]
    ratio_xt_le_30km: Optional[float]
    coverage_ratio: Optional[float]
    max_gap_km: Optional[float]
    gap_threshold_km: Optional[float]


def _extract_date_yyyy_mm_dd(file_name: str) -> Optional[str]:
    for part in file_name.split("_"):
        if len(part) >= 10 and part[:10].count("-") == 2:
            date_str = part[:10]
            if len(date_str) == 10 and date_str[4] == "-" and date_str[7] == "-":
                return date_str
    stem = file_name.split(".")[0]
    if len(stem) == 10 and stem[4] == "-" and stem[7] == "-":
        return stem
    return None


def _iter_parquet_files(
    directory: Path, date_from: Optional[str], date_to: Optional[str]
) -> List[Path]:
    files = sorted(directory.glob("*.parquet"))
    if date_from is None and date_to is None:
        return files

    filtered: List[Path] = []
    for file_path in files:
        date_str = _extract_date_yyyy_mm_dd(file_path.name)
        if date_str is None:
            continue
        if date_from is not None and date_str < date_from:
            continue
        if date_to is not None and date_str > date_to:
            continue
        filtered.append(file_path)
    return filtered


def _load_flights_map(path: Path) -> Dict[int, Tuple[Optional[str], Optional[str]]]:
    table = pq.read_table(path, columns=["flight_id", "adep", "ades"])
    data = table.to_pydict()
    flight_ids = data["flight_id"]
    adep_list = data["adep"]
    ades_list = data["ades"]
    mapping: Dict[int, Tuple[Optional[str], Optional[str]]] = {}
    for fid, adep, ades in zip(flight_ids, adep_list, ades_list):
        if fid is None:
            continue
        mapping[int(fid)] = (adep, ades)
    return mapping


def _load_airports_map(
    path: Path,
) -> Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]]:
    table = pq.read_table(
        path, columns=["icao_code", "latitude_deg", "longitude_deg", "continent"]
    )
    data = table.to_pydict()
    mapping: Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]] = {}
    for code, lat, lon, cont in zip(
        data["icao_code"],
        data["latitude_deg"],
        data["longitude_deg"],
        data["continent"],
    ):
        if code is None:
            continue
        mapping[str(code)] = (lat, lon, cont)
    return mapping


def _init_worker(flights_path: str, airports_path: str, europe_continent: str) -> None:
    global _WORKER_FLIGHT_META, _WORKER_AIRPORT_META, _WORKER_EUROPE_CONTINENT
    _WORKER_FLIGHT_META = _load_flights_map(Path(flights_path))
    _WORKER_AIRPORT_META = _load_airports_map(Path(airports_path))
    _WORKER_EUROPE_CONTINENT = europe_continent


def _bearing_rad(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlon = lon2 - lon1
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.atan2(y, x)


def _central_angle_rad(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> np.ndarray:
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
    return 2.0 * np.arcsin(np.sqrt(a))


def _compute_xt_and_at_km(
    lat_deg: np.ndarray,
    lon_deg: np.ndarray,
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
) -> Tuple[np.ndarray, np.ndarray]:
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)

    d13 = _central_angle_rad(lat1, lon1, lat, lon)
    theta13 = np.arctan2(
        np.sin(lon - lon1) * np.cos(lat),
        np.cos(lat1) * np.sin(lat) - np.sin(lat1) * np.cos(lat) * np.cos(lon - lon1),
    )
    theta12 = _bearing_rad(lat1, lon1, lat2, lon2)

    xt_rad = np.arcsin(np.sin(d13) * np.sin(theta13 - theta12))
    at_rad = np.arctan2(np.sin(d13) * np.cos(theta13 - theta12), np.cos(d13))

    xt_km = np.abs(xt_rad) * EARTH_RADIUS_KM
    at_km = at_rad * EARTH_RADIUS_KM
    return xt_km, at_km


def _great_circle_distance_km(
    lat1_deg: float, lon1_deg: float, lat2_deg: float, lon2_deg: float
) -> float:
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)
    d = _central_angle_rad(
        np.array([lat1]), np.array([lon1]), np.array([lat2]), np.array([lon2])
    )[0]
    return float(d * EARTH_RADIUS_KM)


def _interpolate_great_circle(
    lat1_deg: float,
    lon1_deg: float,
    lat2_deg: float,
    lon2_deg: float,
    num: int = 200,
) -> Tuple[np.ndarray, np.ndarray]:
    lat1 = math.radians(lat1_deg)
    lon1 = math.radians(lon1_deg)
    lat2 = math.radians(lat2_deg)
    lon2 = math.radians(lon2_deg)

    def to_vec(lat: float, lon: float) -> np.ndarray:
        return np.array(
            [
                math.cos(lat) * math.cos(lon),
                math.cos(lat) * math.sin(lon),
                math.sin(lat),
            ],
            dtype=np.float64,
        )

    v1 = to_vec(lat1, lon1)
    v2 = to_vec(lat2, lon2)
    omega = math.acos(np.clip(np.dot(v1, v2), -1.0, 1.0))
    if omega == 0.0:
        lat = np.full(num, lat1)
        lon = np.full(num, lon1)
        return np.rad2deg(lat), np.rad2deg(lon)

    sin_omega = math.sin(omega)
    t = np.linspace(0.0, 1.0, num=num, dtype=np.float64)
    v = (
        np.sin((1.0 - t) * omega)[:, None] * v1[None, :]
        + np.sin(t * omega)[:, None] * v2[None, :]
    ) / sin_omega
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    lat = np.arctan2(z, np.sqrt(x * x + y * y))
    lon = np.arctan2(y, x)
    return np.rad2deg(lat), np.rad2deg(lon)


def _split_into_chunks(items: Sequence[Path], chunks: int) -> List[List[str]]:
    chunks = max(1, min(chunks, len(items)))
    result: List[List[str]] = [[] for _ in range(chunks)]
    for idx, path in enumerate(items):
        result[idx % chunks].append(str(path))
    return [c for c in result if c]


def _start_flight_state(flight_id: int) -> Dict[str, object]:
    if _WORKER_FLIGHT_META is None or _WORKER_AIRPORT_META is None:
        raise RuntimeError("worker meta not initialized")

    adep = None
    ades = None
    adep_lat = None
    adep_lon = None
    ades_lat = None
    ades_lon = None
    cont_adep = None
    cont_ades = None
    path_km = None

    meta = _WORKER_FLIGHT_META.get(int(flight_id))
    if meta is not None:
        adep, ades = meta
        if adep:
            info = _WORKER_AIRPORT_META.get(adep)
            if info:
                adep_lat, adep_lon, cont_adep = info
        if ades:
            info = _WORKER_AIRPORT_META.get(ades)
            if info:
                ades_lat, ades_lon, cont_ades = info
    has_airports = (
        adep_lat is not None
        and adep_lon is not None
        and ades_lat is not None
        and ades_lon is not None
    )
    if has_airports:
        path_km = _great_circle_distance_km(adep_lat, adep_lon, ades_lat, ades_lon)

    is_eu = bool(
        cont_adep == _WORKER_EUROPE_CONTINENT and cont_ades == _WORKER_EUROPE_CONTINENT
    )
    return {
        "flight_id": int(flight_id),
        "adep": adep,
        "ades": ades,
        "adep_lat": adep_lat,
        "adep_lon": adep_lon,
        "ades_lat": ades_lat,
        "ades_lon": ades_lon,
        "continent_adep": cont_adep,
        "continent_ades": cont_ades,
        "is_eu": is_eu,
        "path_km": path_km,
        "points_total": 0,
        "points_valid": 0,
        "s_values": [],
        "xt_values": [],
    }


def _finalize_flight(
    state: Dict[str, object],
    gap_threshold_km: float,
    gap_threshold_ratio: float,
) -> FlightMetrics:
    path_km = state["path_km"]
    points_total = int(state["points_total"])
    points_valid = int(state["points_valid"])
    points_used = 0

    xt_mean = None
    xt_std = None
    xt_median = None
    xt_p95 = None
    ratio_le_20 = None
    ratio_le_30 = None
    coverage_ratio = None
    max_gap_km = None
    gap_threshold = None

    if path_km is not None and path_km > 0 and points_valid > 0:
        s_values: List[np.ndarray] = state["s_values"]
        xt_values: List[np.ndarray] = state["xt_values"]
        if s_values and xt_values:
            s_all = np.concatenate(s_values)
            xt_all = np.concatenate(xt_values)
            s_all = s_all[np.isfinite(s_all)]
            xt_all = xt_all[np.isfinite(xt_all)]
            points_used = int(xt_all.size)
            if xt_all.size > 0:
                xt_mean = float(np.mean(xt_all))
                xt_std = float(np.std(xt_all))
                xt_median = float(np.median(xt_all))
                xt_p95 = float(np.quantile(xt_all, 0.95))
                ratio_le_20 = float(np.mean(xt_all <= 20.0))
                ratio_le_30 = float(np.mean(xt_all <= 30.0))

            if s_all.size > 0:
                s_all = np.clip(s_all, 0.0, float(path_km))
                s_all.sort()
                gaps = np.diff(s_all)
                gap_threshold = max(gap_threshold_km, gap_threshold_ratio * path_km)
                if gaps.size > 0:
                    max_gap_km = float(np.max(gaps))
                    missing = float(np.sum(gaps[gaps > gap_threshold]))
                    coverage_ratio = max(0.0, 1.0 - missing / path_km)
                else:
                    max_gap_km = 0.0
                    coverage_ratio = 1.0
            else:
                gap_threshold = max(gap_threshold_km, gap_threshold_ratio * path_km)

    return FlightMetrics(
        flight_id=int(state["flight_id"]),
        adep=state["adep"],
        ades=state["ades"],
        adep_lat=state["adep_lat"],
        adep_lon=state["adep_lon"],
        ades_lat=state["ades_lat"],
        ades_lon=state["ades_lon"],
        continent_adep=state["continent_adep"],
        continent_ades=state["continent_ades"],
        is_eu=bool(state["is_eu"]),
        points_total=points_total,
        points_valid=points_valid,
        points_used=points_used,
        gc_distance_km=path_km,
        xt_mean_km=xt_mean,
        xt_std_km=xt_std,
        xt_median_km=xt_median,
        xt_p95_km=xt_p95,
        ratio_xt_le_20km=ratio_le_20,
        ratio_xt_le_30km=ratio_le_30,
        coverage_ratio=coverage_ratio,
        max_gap_km=max_gap_km,
        gap_threshold_km=gap_threshold,
    )


def _process_file_chunk(
    file_paths: List[str],
    batch_size: int,
    gap_threshold_km: float,
    gap_threshold_ratio: float,
    flight_id_col: str,
) -> List[FlightMetrics]:
    results: List[FlightMetrics] = []
    current_state: Optional[Dict[str, object]] = None
    current_fid: Optional[int] = None

    for file_path in file_paths:
        parquet = pq.ParquetFile(file_path)
        columns = [flight_id_col, "latitude", "longitude"]

        for batch in parquet.iter_batches(columns=columns, batch_size=batch_size):
            fid = batch.column(0).to_numpy(zero_copy_only=False)
            lat = batch.column(1).to_numpy(zero_copy_only=False)
            lon = batch.column(2).to_numpy(zero_copy_only=False)
            if fid.size == 0:
                continue

            change_idx = np.flatnonzero(fid[1:] != fid[:-1]) + 1
            starts = np.concatenate(([0], change_idx))
            ends = np.concatenate((change_idx, [fid.size]))

            for start, end in zip(starts, ends):
                seg_fid = int(fid[start])
                seg_lat = lat[start:end]
                seg_lon = lon[start:end]
                if current_fid is None or seg_fid != current_fid:
                    if current_state is not None:
                        results.append(
                            _finalize_flight(
                                current_state, gap_threshold_km, gap_threshold_ratio
                            )
                        )
                    current_state = _start_flight_state(seg_fid)
                    current_fid = seg_fid

                if current_state is None:
                    continue

                current_state["points_total"] = int(current_state["points_total"]) + int(
                    seg_lat.size
                )
                mask = np.isfinite(seg_lat) & np.isfinite(seg_lon)
                valid_count = int(np.sum(mask))
                current_state["points_valid"] = int(
                    current_state["points_valid"]
                ) + valid_count
                if valid_count == 0:
                    continue

                if current_state["path_km"] is None:
                    continue

                adep_lat = current_state["adep_lat"]
                adep_lon = current_state["adep_lon"]
                ades_lat = current_state["ades_lat"]
                ades_lon = current_state["ades_lon"]
                if (
                    adep_lat is None
                    or adep_lon is None
                    or ades_lat is None
                    or ades_lon is None
                ):
                    continue

                seg_lat = seg_lat[mask].astype(np.float64, copy=False)
                seg_lon = seg_lon[mask].astype(np.float64, copy=False)
                xt_km, at_km = _compute_xt_and_at_km(
                    seg_lat, seg_lon, adep_lat, adep_lon, ades_lat, ades_lon
                )
                current_state["xt_values"].append(xt_km)
                current_state["s_values"].append(at_km)

    if current_state is not None:
        results.append(
            _finalize_flight(current_state, gap_threshold_km, gap_threshold_ratio)
        )
    return results


def _write_metrics_csv(
    out_path: Path, rows: Iterable[FlightMetrics], dataset_label: str
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "dataset",
                "flight_id",
                "adep",
                "ades",
                "adep_lat",
                "adep_lon",
                "ades_lat",
                "ades_lon",
                "continent_adep",
                "continent_ades",
                "is_eu",
                "points_total",
                "points_valid",
                "points_used",
                "gc_distance_km",
                "xt_mean_km",
                "xt_std_km",
                "xt_median_km",
                "xt_p95_km",
                "ratio_xt_le_20km",
                "ratio_xt_le_30km",
                "coverage_ratio",
                "max_gap_km",
                "gap_threshold_km",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    dataset_label,
                    row.flight_id,
                    row.adep or "",
                    row.ades or "",
                    row.adep_lat if row.adep_lat is not None else "",
                    row.adep_lon if row.adep_lon is not None else "",
                    row.ades_lat if row.ades_lat is not None else "",
                    row.ades_lon if row.ades_lon is not None else "",
                    row.continent_adep or "",
                    row.continent_ades or "",
                    int(row.is_eu),
                    row.points_total,
                    row.points_valid,
                    row.points_used,
                    row.gc_distance_km if row.gc_distance_km is not None else "",
                    row.xt_mean_km if row.xt_mean_km is not None else "",
                    row.xt_std_km if row.xt_std_km is not None else "",
                    row.xt_median_km if row.xt_median_km is not None else "",
                    row.xt_p95_km if row.xt_p95_km is not None else "",
                    row.ratio_xt_le_20km if row.ratio_xt_le_20km is not None else "",
                    row.ratio_xt_le_30km if row.ratio_xt_le_30km is not None else "",
                    row.coverage_ratio if row.coverage_ratio is not None else "",
                    row.max_gap_km if row.max_gap_km is not None else "",
                    row.gap_threshold_km if row.gap_threshold_km is not None else "",
                ]
            )


def _parse_float(value: str) -> Optional[float]:
    if value == "" or value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _load_metrics_csv(path: Path) -> Dict[str, List[float]]:
    cols: Dict[str, List[float]] = {
        "coverage_ratio": [],
        "max_gap_km": [],
        "gc_distance_km": [],
        "ratio_xt_le_20km": [],
        "ratio_xt_le_30km": [],
        "xt_median_km": [],
        "is_eu": [],
        "has_airports": [],
        "flight_id": [],
    }
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cols["flight_id"].append(int(row["flight_id"]))
            is_eu = 1.0 if row["is_eu"] == "1" else 0.0
            cols["is_eu"].append(is_eu)
            has_airports = 1.0 if row["gc_distance_km"] not in ("", None) else 0.0
            cols["has_airports"].append(has_airports)
            for key in [
                "coverage_ratio",
                "max_gap_km",
                "gc_distance_km",
                "ratio_xt_le_20km",
                "ratio_xt_le_30km",
                "xt_median_km",
            ]:
                val = _parse_float(row.get(key, ""))
                if val is not None:
                    cols[key].append(val)
                else:
                    cols[key].append(float("nan"))
    return cols


def _write_summary_csv(
    out_path: Path, metrics: Dict[str, List[float]], dataset_label: str
) -> None:
    def stats(values: np.ndarray) -> Tuple[float, float]:
        if values.size == 0:
            return float("nan"), float("nan")
        return float(np.nanmean(values)), float(np.nanmedian(values))

    arrays = {k: np.array(v, dtype=np.float64) for k, v in metrics.items()}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "dataset",
                "subset",
                "flights",
                "coverage_mean",
                "coverage_median",
                "max_gap_mean_km",
                "max_gap_median_km",
                "gc_distance_mean_km",
                "gc_distance_median_km",
                "xt_median_mean_km",
                "ratio_xt_le_20_mean",
                "ratio_xt_le_30_mean",
            ]
        )

        def write_subset(name: str, mask: np.ndarray) -> None:
            n = int(np.sum(mask))
            if n == 0:
                writer.writerow([dataset_label, name, 0, "", "", "", "", "", "", "", "", ""])
                return
            cov_mean, cov_median = stats(arrays["coverage_ratio"][mask])
            gap_mean, gap_median = stats(arrays["max_gap_km"][mask])
            dist_mean, dist_median = stats(arrays["gc_distance_km"][mask])
            xt_med_mean, _ = stats(arrays["xt_median_km"][mask])
            ratio20_mean = float(np.nanmean(arrays["ratio_xt_le_20km"][mask]))
            ratio30_mean = float(np.nanmean(arrays["ratio_xt_le_30km"][mask]))
            writer.writerow(
                [
                    dataset_label,
                    name,
                    n,
                    cov_mean,
                    cov_median,
                    gap_mean,
                    gap_median,
                    dist_mean,
                    dist_median,
                    xt_med_mean,
                    ratio20_mean,
                    ratio30_mean,
                ]
            )

        all_mask = ~np.isnan(arrays["coverage_ratio"])
        has_airports = arrays["has_airports"] > 0.5
        eu_mask = (arrays["is_eu"] > 0.5) & has_airports
        write_subset("all_with_metrics", all_mask)
        write_subset("has_airports", has_airports)
        write_subset("europe_both", eu_mask)


def _plot_hist_cdf(values: np.ndarray, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return

    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    ax.hist(values, bins=50, range=(0.0, 1.0), color="#4C78A8", alpha=0.85)
    ax.set_xlabel("coverage_ratio")
    ax.set_ylabel("count")
    ax.set_title("Coverage Ratio Histogram")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_dir / "coverage_ratio_hist.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    values_sorted = np.sort(values)
    y = np.arange(1, values_sorted.size + 1) / values_sorted.size
    ax.plot(values_sorted, y, color="#F58518", linewidth=1.5)
    ax.set_xlabel("coverage_ratio")
    ax.set_ylabel("cdf")
    ax.set_title("Coverage Ratio CDF")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_dir / "coverage_ratio_cdf.png")
    plt.close(fig)


def _plot_max_gap(values: np.ndarray, out_dir: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    values = values[np.isfinite(values) & (values > 0)]
    if values.size == 0:
        return

    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    bins = np.logspace(math.log10(values.min()), math.log10(values.max()), 50)
    ax.hist(values, bins=bins, color="#54A24B", alpha=0.85)
    ax.set_xscale("log")
    ax.set_xlabel("max_gap_km (log scale)")
    ax.set_ylabel("count")
    ax.set_title("Max Gap Distribution")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_dir / "max_gap_km_hist.png")
    plt.close(fig)


def _plot_xt_ratios(
    ratio20: np.ndarray, ratio30: np.ndarray, out_dir: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    r20 = ratio20[np.isfinite(ratio20)]
    r30 = ratio30[np.isfinite(ratio30)]
    if r20.size == 0 and r30.size == 0:
        return

    fig, ax = plt.subplots(figsize=(8, 4), dpi=150)
    if r20.size:
        ax.hist(
            r20,
            bins=50,
            range=(0.0, 1.0),
            alpha=0.6,
            label="ratio_xt_le_20km",
        )
    if r30.size:
        ax.hist(
            r30,
            bins=50,
            range=(0.0, 1.0),
            alpha=0.6,
            label="ratio_xt_le_30km",
        )
    ax.set_xlabel("ratio")
    ax.set_ylabel("count")
    ax.set_title("Great-circle Alignment Ratios")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "ratio_xt_hist.png")
    plt.close(fig)


def _plot_coverage_vs_distance(
    coverage: np.ndarray, distance: np.ndarray, out_dir: Path
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    mask = np.isfinite(coverage) & np.isfinite(distance)
    if not np.any(mask):
        return

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    hb = ax.hexbin(
        distance[mask],
        coverage[mask],
        gridsize=60,
        cmap="viridis",
        mincnt=1,
    )
    cb = fig.colorbar(hb, ax=ax)
    cb.set_label("count")
    ax.set_xlabel("great-circle distance (km)")
    ax.set_ylabel("coverage_ratio")
    ax.set_title("Coverage Ratio vs Great-circle Distance")
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
    fig.tight_layout()
    fig.savefig(out_dir / "coverage_vs_distance_hexbin.png")
    plt.close(fig)


def _collect_sample_tracks(
    sample_ids: List[int],
    files: Sequence[Path],
    batch_size: int,
    flight_id_col: str,
) -> Dict[int, Dict[str, List[np.ndarray]]]:
    tracks: Dict[int, Dict[str, List[np.ndarray]]] = {
        fid: {"lat": [], "lon": [], "ts": []} for fid in sample_ids
    }
    if not sample_ids:
        return tracks

    sample_set = set(sample_ids)
    for file_path in files:
        parquet = pq.ParquetFile(str(file_path))
        for batch in parquet.iter_batches(
            columns=[flight_id_col, "timestamp", "latitude", "longitude"],
            batch_size=batch_size,
        ):
            fid = batch.column(0).to_numpy(zero_copy_only=False)
            if fid.size == 0:
                continue
            mask = np.isin(fid, sample_ids)
            if not np.any(mask):
                continue
            fid = fid[mask]
            ts = batch.column(1).to_numpy(zero_copy_only=False)[mask]
            lat = batch.column(2).to_numpy(zero_copy_only=False)[mask]
            lon = batch.column(3).to_numpy(zero_copy_only=False)[mask]

            order = np.argsort(fid)
            fid = fid[order]
            ts = ts[order]
            lat = lat[order]
            lon = lon[order]
            change_idx = np.flatnonzero(fid[1:] != fid[:-1]) + 1
            starts = np.concatenate(([0], change_idx))
            ends = np.concatenate((change_idx, [fid.size]))
            for start, end in zip(starts, ends):
                seg_fid = int(fid[start])
                if seg_fid not in sample_set:
                    continue
                tracks[seg_fid]["ts"].append(ts[start:end])
                tracks[seg_fid]["lat"].append(lat[start:end])
                tracks[seg_fid]["lon"].append(lon[start:end])
    return tracks


def _plot_sample_flights(
    sample_ids: List[int],
    tracks: Dict[int, Dict[str, List[np.ndarray]]],
    flights_map: Dict[int, Tuple[Optional[str], Optional[str]]],
    airports_map: Dict[str, Tuple[Optional[float], Optional[float], Optional[str]]],
    out_dir: Path,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)
    for fid in sample_ids:
        data = tracks.get(fid)
        if data is None or not data["lat"]:
            continue
        lat = np.concatenate(data["lat"])
        lon = np.concatenate(data["lon"])
        ts = np.concatenate(data["ts"])
        mask = np.isfinite(lat) & np.isfinite(lon)
        lat = lat[mask]
        lon = lon[mask]
        ts = ts[mask]
        if lat.size == 0:
            continue
        order = np.argsort(ts)
        lat = lat[order]
        lon = lon[order]

        adep, ades = flights_map.get(int(fid), (None, None))
        adep_lat = adep_lon = ades_lat = ades_lon = None
        if adep:
            info = airports_map.get(adep)
            if info:
                adep_lat, adep_lon, _ = info
        if ades:
            info = airports_map.get(ades)
            if info:
                ades_lat, ades_lon, _ = info
        if (
            adep_lat is None
            or adep_lon is None
            or ades_lat is None
            or ades_lon is None
        ):
            continue

        gc_lat, gc_lon = _interpolate_great_circle(
            adep_lat, adep_lon, ades_lat, ades_lon, num=200
        )

        fig, ax = plt.subplots(figsize=(7, 5), dpi=150)
        ax.plot(lon, lat, color="#4C78A8", linewidth=1.0, alpha=0.8, label="trajectory")
        ax.plot(
            gc_lon,
            gc_lat,
            color="#E45756",
            linewidth=1.2,
            alpha=0.9,
            label="great-circle",
        )
        ax.scatter([adep_lon], [adep_lat], color="#54A24B", s=20, label="adep")
        ax.scatter([ades_lon], [ades_lat], color="#F58518", s=20, label="ades")
        ax.set_xlabel("Longitude (deg)")
        ax.set_ylabel("Latitude (deg)")
        title = f"flight_id={fid}"
        if adep and ades:
            title += f" ({adep}->{ades})"
        ax.set_title(title)
        ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4)
        ax.legend()
        fig.tight_layout()
        fig.savefig(out_dir / f"flight_{fid}.png")
        plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compute trajectory coverage and great-circle alignment metrics."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="Directory with parquet shards (default: rawtrajectories)",
    )
    parser.add_argument(
        "--flights-path",
        type=Path,
        default=DEFAULT_FLIGHTS_PATH,
        help="Flight metadata parquet (default: flights/challenge_set.parquet)",
    )
    parser.add_argument(
        "--airports-path",
        type=Path,
        default=DEFAULT_AIRPORTS_PATH,
        help="Airports metadata parquet (default: airports_tz.parquet)",
    )
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("reports/trajectory_coverage"),
        help="Output root directory",
    )
    parser.add_argument("--label", type=str, default=None, help="Output label name")
    parser.add_argument("--date-from", type=str, default=None, help="Start date YYYY-MM-DD")
    parser.add_argument("--date-to", type=str, default=None, help="End date YYYY-MM-DD")
    parser.add_argument(
        "--workers",
        type=int,
        default=min(max(os.cpu_count() - 2, 1), 28),
        help="Process workers (default: min(cpu-2, 28))",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500_000,
        help="Batch size for parquet iter_batches",
    )
    parser.add_argument(
        "--flight-id-col",
        type=str,
        default=None,
        help="Flight id column name (default: auto choose original_flight_id if present)",
    )
    parser.add_argument(
        "--gap-threshold-km",
        type=float,
        default=50.0,
        help="Coverage gap threshold in km (default: 50)",
    )
    parser.add_argument(
        "--gap-threshold-ratio",
        type=float,
        default=0.05,
        help="Coverage gap threshold as ratio of path length (default: 0.05)",
    )
    parser.add_argument(
        "--europe-continent",
        type=str,
        default=DEFAULT_EUROPE_CONTINENT,
        help="Continent code for Europe (default: EU)",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Skip plot generation",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=20,
        help="Number of sample flights for trajectory plots (default: 20)",
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=42,
        help="Random seed for sampling flights",
    )
    args = parser.parse_args()

    data_dir: Path = args.data_dir
    if not data_dir.exists():
        raise FileNotFoundError(f"data dir not found: {data_dir}")

    files = _iter_parquet_files(data_dir, args.date_from, args.date_to)
    if not files:
        raise FileNotFoundError(f"no parquet files found in {data_dir}")

    label = args.label or data_dir.name
    range_tag = f"{args.date_from or 'all'}__{args.date_to or 'all'}"
    out_dir = args.out_root / label / range_tag
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = _split_into_chunks(files, args.workers)
    sample_parquet = pq.ParquetFile(str(files[0]))
    available_cols = set(sample_parquet.schema.names)
    flight_id_col = args.flight_id_col
    if flight_id_col is None:
        flight_id_col = "original_flight_id" if "original_flight_id" in available_cols else "flight_id"
    if flight_id_col not in available_cols:
        raise RuntimeError(
            f"flight id 列不存在：{flight_id_col}（可用列：{sorted(available_cols)}）"
        )
    print(f"[INFO] data_dir={data_dir}")
    print(f"[INFO] files={len(files)} (date_from={args.date_from}, date_to={args.date_to})")
    print(f"[INFO] workers={args.workers}, batch_size={args.batch_size}")
    print(f"[INFO] out_dir={out_dir}")
    print(f"[INFO] flight_id_col={flight_id_col}")

    from concurrent.futures import ProcessPoolExecutor, as_completed

    rows: List[FlightMetrics] = []
    if len(chunks) == 1 or args.workers == 1:
        _init_worker(str(args.flights_path), str(args.airports_path), args.europe_continent)
        rows.extend(
            _process_file_chunk(
                chunks[0],
                args.batch_size,
                args.gap_threshold_km,
                args.gap_threshold_ratio,
                flight_id_col,
            )
        )
    else:
        with ProcessPoolExecutor(
            max_workers=len(chunks),
            initializer=_init_worker,
            initargs=(str(args.flights_path), str(args.airports_path), args.europe_continent),
        ) as executor:
            futures = [
                executor.submit(
                    _process_file_chunk,
                    chunk,
                    args.batch_size,
                    args.gap_threshold_km,
                    args.gap_threshold_ratio,
                    flight_id_col,
                )
                for chunk in chunks
            ]
            for future in as_completed(futures):
                rows.extend(future.result())

    metrics_path = out_dir / "flight_metrics.csv"
    _write_metrics_csv(metrics_path, rows, label)
    print(f"[INFO] wrote flight_metrics.csv ({len(rows)} flights)")

    metrics = _load_metrics_csv(metrics_path)
    _write_summary_csv(out_dir / "summary.csv", metrics, label)
    print("[INFO] wrote summary.csv")

    if not args.no_plots:
        plots_dir = out_dir / "plots"
        _plot_hist_cdf(np.array(metrics["coverage_ratio"]), plots_dir)
        _plot_max_gap(np.array(metrics["max_gap_km"]), plots_dir)
        _plot_xt_ratios(
            np.array(metrics["ratio_xt_le_20km"]),
            np.array(metrics["ratio_xt_le_30km"]),
            plots_dir,
        )
        _plot_coverage_vs_distance(
            np.array(metrics["coverage_ratio"]),
            np.array(metrics["gc_distance_km"]),
            plots_dir,
        )

        flights_map = _load_flights_map(args.flights_path)
        airports_map = _load_airports_map(args.airports_path)
        rng = random.Random(args.sample_seed)
        ids = [
            int(fid)
            for fid, is_eu, has_airports in zip(
                metrics["flight_id"], metrics["is_eu"], metrics["has_airports"]
            )
            if is_eu > 0.5 and has_airports > 0.5
        ]
        if not ids:
            ids = [
                int(fid)
                for fid, has_airports in zip(metrics["flight_id"], metrics["has_airports"])
                if has_airports > 0.5
            ]
        rng.shuffle(ids)
        sample_ids = ids[: args.sample_size]
        if sample_ids:
            tracks = _collect_sample_tracks(
                sample_ids, files, args.batch_size, flight_id_col
            )
            _plot_sample_flights(
                sample_ids,
                tracks,
                flights_map,
                airports_map,
                plots_dir / "sample_flights",
            )
            print(f"[INFO] wrote sample flight plots ({len(sample_ids)})")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "data_dir": str(data_dir),
        "files_count": len(files),
        "date_from": args.date_from,
        "date_to": args.date_to,
        "gap_threshold_km": args.gap_threshold_km,
        "gap_threshold_ratio": args.gap_threshold_ratio,
        "europe_continent": args.europe_continent,
        "flight_id_col": flight_id_col,
        "sample_size": args.sample_size,
        "sample_seed": args.sample_seed,
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )
    print("[INFO] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
