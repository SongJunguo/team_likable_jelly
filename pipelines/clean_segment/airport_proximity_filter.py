#!/usr/bin/env python3
"""
Filter trajectories by airport proximity using challenge_set adep/ades and airports_tz coords.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _clean_code(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip().str.upper()
    s = s.mask(s == "")
    return s


def _load_flights(flights_parquet: Path) -> pd.DataFrame:
    df = pd.read_parquet(flights_parquet, columns=["flight_id", "adep", "ades"])
    df = df.dropna(subset=["flight_id"])
    df["flight_id"] = df["flight_id"].astype("int64")
    df["adep"] = _clean_code(df["adep"])
    df["ades"] = _clean_code(df["ades"])
    df = df.drop_duplicates(subset=["flight_id"], keep="last")
    return df


def _load_airports(airports_parquet: Path) -> tuple[dict[str, tuple[float, float]], dict[str, tuple[float, float]]]:
    df = pd.read_parquet(
        airports_parquet,
        columns=["iata_code", "icao_code", "latitude_deg", "longitude_deg"],
    )
    df["iata_code"] = _clean_code(df["iata_code"])
    df["icao_code"] = _clean_code(df["icao_code"])

    iata_df = df.dropna(subset=["iata_code"]).drop_duplicates(subset=["iata_code"])
    icao_df = df.dropna(subset=["icao_code"]).drop_duplicates(subset=["icao_code"])

    iata_coords = dict(
        zip(iata_df["iata_code"], zip(iata_df["latitude_deg"], iata_df["longitude_deg"]))
    )
    icao_coords = dict(
        zip(icao_df["icao_code"], zip(icao_df["latitude_deg"], icao_df["longitude_deg"]))
    )
    return iata_coords, icao_coords


def _coords_from_codes(
    codes: pd.Series,
    iata_coords: dict[str, tuple[float, float]],
    icao_coords: dict[str, tuple[float, float]],
) -> tuple[np.ndarray, np.ndarray]:
    coords = codes.map(iata_coords)
    coords = coords.where(coords.notna(), codes.map(icao_coords))
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


def filter_by_airport_proximity(
    df: pd.DataFrame,
    flights_parquet: Path | str,
    airports_parquet: Path | str,
    threshold_km: float,
    *,
    verbose: bool = True,
) -> pd.DataFrame:
    if df.empty:
        return df

    flights_parquet = Path(flights_parquet)
    airports_parquet = Path(airports_parquet)

    flights = _load_flights(flights_parquet)
    valid_ids = set(flights["flight_id"].to_numpy())

    before_rows = int(len(df))
    before_flights = int(df["flight_id"].nunique()) if "flight_id" in df.columns else 0

    df = df[df["flight_id"].isin(valid_ids)].copy()
    if df.empty:
        if verbose:
            print(
                f"    机场邻近过滤: flight_id匹配后为空 "
                f"(rows {before_rows} -> 0, flights {before_flights} -> 0)"
            )
        return df

    df_valid = df.dropna(subset=["latitude", "longitude"])
    if df_valid.empty:
        if verbose:
            print(
                f"    机场邻近过滤: 有效经纬度为空 "
                f"(rows {before_rows} -> 0, flights {before_flights} -> 0)"
            )
        return df_valid

    df_valid = df_valid.sort_values(["flight_id", "timestamp"], kind="mergesort")
    grouped = df_valid.groupby("flight_id", sort=False)
    start = grouped.first()
    end = grouped.last()

    summary = pd.DataFrame(
        {
            "flight_id": start.index.to_numpy(),
            "start_lat": start["latitude"].to_numpy(),
            "start_lon": start["longitude"].to_numpy(),
            "end_lat": end["latitude"].to_numpy(),
            "end_lon": end["longitude"].to_numpy(),
        }
    )

    flight_adep = pd.Series(flights["adep"].values, index=flights["flight_id"]).to_dict()
    flight_ades = pd.Series(flights["ades"].values, index=flights["flight_id"]).to_dict()
    summary["adep"] = summary["flight_id"].map(flight_adep)
    summary["ades"] = summary["flight_id"].map(flight_ades)

    iata_coords, icao_coords = _load_airports(airports_parquet)
    adep_lat, adep_lon = _coords_from_codes(summary["adep"], iata_coords, icao_coords)
    ades_lat, ades_lon = _coords_from_codes(summary["ades"], iata_coords, icao_coords)

    start_dist = _haversine_km(
        summary["start_lat"].to_numpy(),
        summary["start_lon"].to_numpy(),
        adep_lat,
        adep_lon,
    )
    end_dist = _haversine_km(
        summary["end_lat"].to_numpy(),
        summary["end_lon"].to_numpy(),
        ades_lat,
        ades_lon,
    )

    mask = (
        np.isfinite(start_dist)
        & np.isfinite(end_dist)
        & (start_dist <= float(threshold_km))
        & (end_dist <= float(threshold_km))
    )

    keep_ids = summary.loc[mask, "flight_id"].to_numpy()
    df = df[df["flight_id"].isin(keep_ids)].copy()

    if verbose:
        after_rows = int(len(df))
        after_flights = int(df["flight_id"].nunique()) if "flight_id" in df.columns else 0
        print(
            f"    机场邻近过滤: flights {before_flights} -> {after_flights}, "
            f"rows {before_rows} -> {after_rows} (<= {threshold_km} km)"
        )

    return df
