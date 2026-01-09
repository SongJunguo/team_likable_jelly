#!/usr/bin/env python3
"""
Compute airport proximity for interpolated_clean_eu_v4 trajectories.
Aggregate by original_flight_id and output start->adep and end->ades distances.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp
from pathlib import Path
import time

import numpy as np
import pandas as pd

FLIGHT_ADEP = {}
FLIGHT_ADES = {}
IATA_COORDS = {}
ICAO_COORDS = {}
DISTANCE_THRESHOLD_KM = 50.0

REQ_COLUMNS = ["flight_id", "original_flight_id", "timestamp", "latitude", "longitude"]
OUTPUT_COLUMNS = [
    "flight_id",
    "adep",
    "ades",
    "start_distance_km",
    "end_distance_km",
    "complete_by_threshold",
    "file_name",
]


def _normalize_code(series: pd.Series) -> pd.Series:
    return series.astype("string").str.upper().str.strip()


def _build_flight_maps(flights_path: Path) -> tuple[dict[int, str], dict[int, str]]:
    df = pd.read_parquet(flights_path, columns=["flight_id", "adep", "ades"])
    df = df.drop_duplicates(subset=["flight_id"], keep="last")
    df["adep"] = _normalize_code(df["adep"])
    df["ades"] = _normalize_code(df["ades"])
    flight_adep = pd.Series(df["adep"].values, index=df["flight_id"]).to_dict()
    flight_ades = pd.Series(df["ades"].values, index=df["flight_id"]).to_dict()
    return flight_adep, flight_ades


def _build_airport_maps(airports_path: Path) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    df = pd.read_parquet(
        airports_path,
        columns=["iata_code", "icao_code", "latitude_deg", "longitude_deg"],
    )
    df["iata_code"] = _normalize_code(df["iata_code"])
    df["icao_code"] = _normalize_code(df["icao_code"])

    iata_df = df.dropna(subset=["iata_code"]).drop_duplicates(subset=["iata_code"])
    icao_df = df.dropna(subset=["icao_code"]).drop_duplicates(subset=["icao_code"])

    iata_coords = dict(
        zip(iata_df["iata_code"], zip(iata_df["latitude_deg"], iata_df["longitude_deg"]))
    )
    icao_coords = dict(
        zip(icao_df["icao_code"], zip(icao_df["latitude_deg"], icao_df["longitude_deg"]))
    )
    return iata_coords, icao_coords


def _init_worker(flight_adep, flight_ades, iata_coords, icao_coords, threshold_km):
    global FLIGHT_ADEP, FLIGHT_ADES, IATA_COORDS, ICAO_COORDS, DISTANCE_THRESHOLD_KM
    FLIGHT_ADEP = flight_adep
    FLIGHT_ADES = flight_ades
    IATA_COORDS = iata_coords
    ICAO_COORDS = icao_coords
    DISTANCE_THRESHOLD_KM = threshold_km


def _coords_from_codes(codes: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    coords = codes.map(IATA_COORDS)
    coords = coords.where(coords.notna(), codes.map(ICAO_COORDS))
    coords_list = coords.to_list()
    lat = np.array(
        [c[0] if isinstance(c, tuple) else np.nan for c in coords_list], dtype="float64"
    )
    lon = np.array(
        [c[1] if isinstance(c, tuple) else np.nan for c in coords_list], dtype="float64"
    )
    return lat, lon


def _haversine_km(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1 = np.radians(lat1.astype("float64"))
    lon1 = np.radians(lon1.astype("float64"))
    lat2 = np.radians(lat2.astype("float64"))
    lon2 = np.radians(lon2.astype("float64"))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return 6371.0 * c


def _process_file(file_path: Path) -> pd.DataFrame:
    df = pd.read_parquet(file_path, columns=REQ_COLUMNS)
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = df.dropna(subset=["latitude", "longitude", "original_flight_id"])
    if df.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    df = df.sort_values(["original_flight_id", "timestamp"], kind="mergesort")
    grouped = df.groupby("original_flight_id", sort=False)
    start = grouped.first()
    end = grouped.last()
    point_count = grouped.size()

    summary = pd.DataFrame(
        {
            "flight_id": start.index.to_numpy(),
            "start_lat": start["latitude"].to_numpy(),
            "start_lon": start["longitude"].to_numpy(),
            "end_lat": end["latitude"].to_numpy(),
            "end_lon": end["longitude"].to_numpy(),
            "file_name": file_path.name,
            "point_count": point_count.to_numpy(),
        }
    )

    summary["adep"] = summary["flight_id"].map(FLIGHT_ADEP)
    summary["ades"] = summary["flight_id"].map(FLIGHT_ADES)

    adep_lat, adep_lon = _coords_from_codes(summary["adep"])
    ades_lat, ades_lon = _coords_from_codes(summary["ades"])

    summary["start_distance_km"] = _haversine_km(
        summary["start_lat"].to_numpy(),
        summary["start_lon"].to_numpy(),
        adep_lat,
        adep_lon,
    )
    summary["end_distance_km"] = _haversine_km(
        summary["end_lat"].to_numpy(),
        summary["end_lon"].to_numpy(),
        ades_lat,
        ades_lon,
    )
    summary["complete_by_threshold"] = (
        (summary["start_distance_km"] <= DISTANCE_THRESHOLD_KM)
        & (summary["end_distance_km"] <= DISTANCE_THRESHOLD_KM)
    )

    return summary[OUTPUT_COLUMNS]


def main() -> None:
    parser = argparse.ArgumentParser(description="Airport proximity for interpolated_clean_eu_v4")
    parser.add_argument(
        "--trajectory-dir",
        default="opensky_2024_PRC_dataset/interpolated_clean_eu_v4",
        help="Directory with interpolated parquet files",
    )
    parser.add_argument(
        "--flights-file",
        default="opensky_2024_PRC_dataset/flights/challenge_set.parquet",
        help="challenge_set.parquet path",
    )
    parser.add_argument(
        "--airports-file",
        default="opensky_2024_PRC_dataset/airports_tz.parquet",
        help="airports_tz.parquet path",
    )
    parser.add_argument(
        "--output-file",
        default="reports/interpolated_clean_eu_v4_airport_proximity.parquet",
        help="Output parquet path",
    )
    parser.add_argument(
        "--distance-threshold-km",
        type=float,
        default=50.0,
        help="Distance threshold in km",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max worker processes (default: min(24, cpu_count))",
    )
    parser.add_argument(
        "--limit-files",
        type=int,
        default=None,
        help="Limit number of parquet files for testing",
    )
    args = parser.parse_args()

    trajectory_dir = Path(args.trajectory_dir)
    flights_path = Path(args.flights_file)
    airports_path = Path(args.airports_file)
    output_path = Path(args.output_file)

    if not trajectory_dir.exists():
        raise FileNotFoundError(f"Trajectory dir not found: {trajectory_dir}")
    if not flights_path.exists():
        raise FileNotFoundError(f"Flights file not found: {flights_path}")
    if not airports_path.exists():
        raise FileNotFoundError(f"Airports file not found: {airports_path}")

    flight_adep, flight_ades = _build_flight_maps(flights_path)
    iata_coords, icao_coords = _build_airport_maps(airports_path)

    parquet_files = sorted(trajectory_dir.glob("*.parquet"))
    if args.limit_files:
        parquet_files = parquet_files[: args.limit_files]
    if not parquet_files:
        raise FileNotFoundError(f"No parquet files found in {trajectory_dir}")

    max_workers = args.max_workers or min(24, mp.cpu_count() or 1, len(parquet_files))

    start_time = time.time()
    frames = []
    errors = []

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_worker,
        initargs=(flight_adep, flight_ades, iata_coords, icao_coords, args.distance_threshold_km),
    ) as executor:
        future_to_file = {executor.submit(_process_file, path): path for path in parquet_files}
        for idx, future in enumerate(as_completed(future_to_file), start=1):
            path = future_to_file[future]
            try:
                frame = future.result()
                if not frame.empty:
                    frames.append(frame)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
            if idx % 10 == 0 or idx == len(parquet_files):
                print(f"Processed {idx}/{len(parquet_files)} files")

    result = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output_path, index=False)

    elapsed = time.time() - start_time
    print(f"Saved: {output_path} ({len(result):,} rows) in {elapsed:.1f}s")

    if not result.empty:
        start_within = (result["start_distance_km"] <= args.distance_threshold_km).mean() * 100
        end_within = (result["end_distance_km"] <= args.distance_threshold_km).mean() * 100
        both_within = result["complete_by_threshold"].mean() * 100
        print(f"Start within {args.distance_threshold_km} km: {start_within:.2f}%")
        print(f"End within {args.distance_threshold_km} km: {end_within:.2f}%")
        print(f"Both within {args.distance_threshold_km} km: {both_within:.2f}%")

    if errors:
        print("Errors:")
        for err in errors[:10]:
            print(f"  {err}")


if __name__ == "__main__":
    main()
