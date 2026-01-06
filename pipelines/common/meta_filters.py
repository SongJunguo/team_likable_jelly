# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

DEFAULT_EUROPE_CONTINENT = "EU"
UNKNOWN_CODE = "UNKNOWN"


def _clean_code(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    s = s.str.strip().str.upper()
    s = s.fillna(UNKNOWN_CODE)
    s = s.mask(s == "", UNKNOWN_CODE)
    return s


def build_flights_sources(
    flights_parquet: Path,
    include_submission: bool = False,
    include_final: bool = False,
) -> list[Path]:
    flights_parquet = flights_parquet.resolve()
    sources = [flights_parquet]
    flights_dir = flights_parquet.parent
    if include_submission:
        sources.append(flights_dir / "submission_set.parquet")
    if include_final:
        sources.append(flights_dir / "final_submission_set.parquet")

    missing = [p for p in sources if not p.exists()]
    if missing:
        raise FileNotFoundError(f"missing flights sources: {', '.join(p.as_posix() for p in missing)}")
    return sources


def _load_one_flights(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(
        path,
        columns=["flight_id", "adep", "ades", "aircraft_type"],
        engine="pyarrow",
    )
    df = df.dropna(subset=["flight_id"])
    df["flight_id"] = df["flight_id"].astype("int64")
    df["adep"] = _clean_code(df["adep"])
    df["ades"] = _clean_code(df["ades"])
    df["aircraft_type"] = _clean_code(df["aircraft_type"])
    return df


def load_flights_meta(sources: Sequence[Path], procs: int = 4) -> pd.DataFrame:
    if not sources:
        return pd.DataFrame(columns=["flight_id", "adep", "ades", "aircraft_type"])

    if procs <= 1 or len(sources) == 1:
        frames = [_load_one_flights(Path(p)) for p in sources]
    else:
        workers = min(int(procs), len(sources))
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as executor:
            frames = list(executor.map(_load_one_flights, sources))

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["flight_id"])
    logging.info("meta flights dedup: %s -> %s", before, len(combined))
    return combined


def load_airports_table(
    airports_path: Path,
    columns: Sequence[str] | None = None,
) -> pd.DataFrame:
    if columns is None:
        columns = ["icao_code", "continent", "latitude_deg", "longitude_deg"]
    df = pd.read_parquet(airports_path, columns=list(columns), engine="pyarrow")
    if "icao_code" in df.columns:
        df["icao_code"] = df["icao_code"].astype("string").str.strip().str.upper()
    if "continent" in df.columns:
        df["continent"] = df["continent"].astype("string").str.strip().str.upper()
    return df


def _drop_unknown_rows(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    columns = list(dict.fromkeys(columns))
    if not columns:
        return df
    mask = np.ones(len(df), dtype=bool)
    for col in columns:
        if col in df.columns:
            mask &= df[col].ne(UNKNOWN_CODE)
    return df[mask].copy()


def _get_eu_airports(airports: pd.DataFrame, europe_continent: str) -> set[str]:
    if "icao_code" not in airports.columns or "continent" not in airports.columns:
        raise ValueError("airports table must include icao_code and continent columns")
    mask = airports["continent"] == str(europe_continent).upper()
    codes = airports.loc[mask, "icao_code"].dropna()
    return set(codes.astype(str))


def apply_filters(
    flights: pd.DataFrame,
    airports: pd.DataFrame | None,
    *,
    europe_only: bool = False,
    top_airports: int = 0,
    top_aircraft: int = 0,
    europe_continent: str = DEFAULT_EUROPE_CONTINENT,
    drop_unknown: bool = True,
) -> tuple[pd.DataFrame, dict]:
    stats: dict[str, object] = {"total_before": int(len(flights))}
    top_airports = int(top_airports) if top_airports and top_airports > 0 else 0
    top_aircraft = int(top_aircraft) if top_aircraft and top_aircraft > 0 else 0
    filtered = flights.copy()

    if europe_only:
        if airports is None:
            raise ValueError("airports table required for europe_only filter")
        if drop_unknown:
            before = len(filtered)
            filtered = _drop_unknown_rows(filtered, ["adep", "ades"])
            stats["drop_unknown_europe"] = {
                "before": int(before),
                "after": int(len(filtered)),
                "columns": ["adep", "ades"],
            }
        eu_airports = _get_eu_airports(airports, europe_continent)
        before = len(filtered)
        filtered = filtered[
            filtered["adep"].isin(eu_airports) & filtered["ades"].isin(eu_airports)
        ].copy()
        stats["europe_only"] = {
            "before": int(before),
            "after": int(len(filtered)),
            "continent": str(europe_continent).upper(),
            "eu_airports": int(len(eu_airports)),
        }

    if top_airports or top_aircraft:
        base = filtered
        if drop_unknown:
            cols: list[str] = []
            if top_airports:
                cols.extend(["adep", "ades"])
            if top_aircraft:
                cols.append("aircraft_type")
            before = len(base)
            base = _drop_unknown_rows(base, cols)
            stats["drop_unknown_top"] = {
                "before": int(before),
                "after": int(len(base)),
                "columns": sorted(set(cols)),
            }

        top_airports_list: list[str] = []
        top_aircraft_list: list[str] = []
        if top_airports:
            combined = pd.concat([base["adep"], base["ades"]], ignore_index=True)
            counts = combined.value_counts()
            top_airports_list = counts.head(top_airports).index.tolist()
        if top_aircraft:
            counts = base["aircraft_type"].value_counts()
            top_aircraft_list = counts.head(top_aircraft).index.tolist()

        before = len(base)
        mask = np.ones(len(base), dtype=bool)
        if top_airports_list:
            mask &= base["adep"].isin(top_airports_list) & base["ades"].isin(top_airports_list)
        if top_aircraft_list:
            mask &= base["aircraft_type"].isin(top_aircraft_list)
        filtered = base[mask].copy()
        stats["top_filters"] = {
            "before": int(before),
            "after": int(len(filtered)),
            "top_airports": top_airports,
            "top_aircraft": top_aircraft,
            "top_airports_list": top_airports_list,
            "top_aircraft_list": top_aircraft_list,
        }

    stats["total_after"] = int(len(filtered))
    return filtered, stats


def build_allowed_flight_ids(
    *,
    flights_parquet: Path,
    airports_parquet: Path,
    include_submission: bool = False,
    include_final: bool = False,
    europe_only: bool = False,
    top_airports: int = 0,
    top_aircraft: int = 0,
    europe_continent: str = DEFAULT_EUROPE_CONTINENT,
    procs: int = 4,
) -> tuple[np.ndarray, dict]:
    sources = build_flights_sources(
        flights_parquet,
        include_submission=include_submission,
        include_final=include_final,
    )
    flights = load_flights_meta(sources, procs=procs)

    airports = None
    if europe_only:
        airports = load_airports_table(airports_parquet, columns=["icao_code", "continent"])

    filtered, stats = apply_filters(
        flights,
        airports,
        europe_only=europe_only,
        top_airports=top_airports,
        top_aircraft=top_aircraft,
        europe_continent=europe_continent,
        drop_unknown=True,
    )
    allowed_ids = filtered["flight_id"].to_numpy(dtype=np.int64, copy=False)
    return allowed_ids, stats


def format_stats(stats: dict, prefix: str = "[meta_filters]") -> str:
    lines = [
        f"{prefix} flights: {stats.get('total_before', 'NA')} -> {stats.get('total_after', 'NA')}"
    ]
    europe = stats.get("europe_only")
    if europe:
        lines.append(
            f"{prefix} europe_only({europe.get('continent', 'EU')}): "
            f"{europe.get('before', 'NA')} -> {europe.get('after', 'NA')} "
            f"(eu_airports={europe.get('eu_airports', 'NA')})"
        )
    drop_eu = stats.get("drop_unknown_europe")
    if drop_eu:
        lines.append(
            f"{prefix} drop_unknown_europe: {drop_eu.get('before', 'NA')} -> {drop_eu.get('after', 'NA')}"
        )
    drop_top = stats.get("drop_unknown_top")
    if drop_top:
        lines.append(
            f"{prefix} drop_unknown_top: {drop_top.get('before', 'NA')} -> {drop_top.get('after', 'NA')}"
        )
    top_filters = stats.get("top_filters")
    if top_filters:
        lines.append(
            f"{prefix} top_filters: {top_filters.get('before', 'NA')} -> {top_filters.get('after', 'NA')} "
            f"(airports_top={top_filters.get('top_airports', 0)}, "
            f"aircraft_top={top_filters.get('top_aircraft', 0)})"
        )
        airports_list = top_filters.get("top_airports_list", [])
        if airports_list:
            label = ", ".join(airports_list)
            lines.append(f"{prefix} top_airports_list: {label}")
        aircraft_list = top_filters.get("top_aircraft_list", [])
        if aircraft_list:
            label = ", ".join(aircraft_list)
            lines.append(f"{prefix} top_aircraft_list: {label}")
    return "\n".join(lines)


def log_stats(stats: dict, logger: logging.Logger | None = None) -> None:
    logger = logger or logging.getLogger(__name__)
    for line in format_stats(stats).splitlines():
        logger.info("%s", line)
