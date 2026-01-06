# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[2]
    default_flights_dir = repo_root / "opensky_2024_PRC_dataset" / "flights"
    default_airports_path = repo_root / "opensky_2024_PRC_dataset" / "airports_tz.parquet"
    default_out_dir = repo_root / "reports" / "airport_aircraft_stats"
    default_iso3166_path = Path("/usr/share/iso-codes/json/iso_3166-1.json")

    parser = argparse.ArgumentParser(description="Compute airport/aircraft frequency stats from flights metadata.")
    parser.add_argument("--flights-dir", default=default_flights_dir.as_posix())
    parser.add_argument("--airports-path", default=default_airports_path.as_posix())
    parser.add_argument("--iso3166-path", default=default_iso3166_path.as_posix())
    parser.add_argument("--include-submission", action="store_true")
    parser.add_argument("--include-final", action="store_true")
    parser.add_argument("--top-n", type=int, default=20)
    parser.add_argument("--procs", type=int, default=4, help="Parallel workers for reading sources.")
    parser.add_argument("--out-dir", default=default_out_dir.as_posix())
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def _clean_code(series: pd.Series) -> pd.Series:
    s = series.astype("string")
    s = s.str.strip().str.upper()
    s = s.fillna("UNKNOWN")
    s = s.mask(s == "", "UNKNOWN")
    return s


def _load_one(path: Path) -> pd.DataFrame:
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


def _load_sources(paths: list[Path], procs: int) -> pd.DataFrame:
    if not paths:
        return pd.DataFrame(columns=["flight_id", "adep", "ades", "aircraft_type"])

    if procs <= 1 or len(paths) == 1:
        frames = [_load_one(p) for p in paths]
    else:
        workers = min(procs, len(paths))
        ctx = mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as executor:
            frames = list(executor.map(_load_one, paths))

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["flight_id"])
    logging.info("dedup flight_id: %s -> %s", before, len(combined))
    return combined


def _build_counts(series: pd.Series, label: str) -> pd.DataFrame:
    counts = series.value_counts(dropna=False)
    total = int(counts.sum())
    df = counts.rename("count").reset_index()
    df.columns = [label, "count"]
    df["ratio"] = df["count"] / total if total else 0.0
    return df


def _load_iso3166_country_map(path: Path) -> dict[str, str]:
    if not path.exists():
        logging.warning("iso3166 mapping not found: %s", path)
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        logging.warning("failed to load iso3166 mapping %s: %s", path, exc)
        return {}

    mapping: dict[str, str] = {}
    for entry in payload.get("3166-1", []):
        code = entry.get("alpha_2")
        name = entry.get("name")
        if code and name:
            mapping[str(code).strip().upper()] = str(name)
    return mapping


def _load_airports_meta(path: Path, country_map: dict[str, str]) -> pd.DataFrame:
    df = pd.read_parquet(
        path,
        columns=["icao_code", "iso_country", "continent"],
        engine="pyarrow",
    )
    if df.empty:
        return pd.DataFrame(columns=["airport", "country", "continent"])

    continent_map = {
        "AF": "Africa",
        "AN": "Antarctica",
        "AS": "Asia",
        "EU": "Europe",
        "NA": "North America",
        "OC": "Oceania",
        "SA": "South America",
    }

    df["airport"] = _clean_code(df["icao_code"])
    df["country_code"] = _clean_code(df["iso_country"])
    df["continent_code"] = _clean_code(df["continent"])
    df = df.drop_duplicates(subset=["airport"])
    df["country"] = df["country_code"].map(country_map)
    df["continent"] = df["continent_code"].map(continent_map)
    df["country"] = df["country"].fillna(df["country_code"])
    df["continent"] = df["continent"].fillna(df["continent_code"])
    df["country"] = df["country"].fillna("UNKNOWN")
    df["continent"] = df["continent"].fillna("UNKNOWN")
    return df[["airport", "country", "continent"]]


def _attach_airport_meta(counts: pd.DataFrame, airports_meta: pd.DataFrame) -> pd.DataFrame:
    if counts.empty:
        return counts
    if airports_meta.empty:
        enriched = counts.copy()
        enriched.insert(1, "country", "UNKNOWN")
        enriched.insert(2, "continent", "UNKNOWN")
        return enriched

    merged = counts.merge(airports_meta, how="left", on="airport", sort=False)
    merged["country"] = merged["country"].fillna("UNKNOWN")
    merged["continent"] = merged["continent"].fillna("UNKNOWN")
    return merged[["airport", "country", "continent", "count", "ratio"]]


def _write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _plot_topn(df: pd.DataFrame, label: str, top_n: int, title: str, out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("matplotlib is required to generate plots.") from exc

    if df.empty:
        return

    top = df.head(top_n).iloc[::-1]
    height = max(4.0, 0.35 * len(top) + 1.5)
    fig, ax = plt.subplots(figsize=(10, height))
    ax.barh(top[label], top["count"])
    ax.set_xlabel("count")
    ax.set_ylabel(label)
    ax.set_title(title)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s - [%(levelname)s] - %(message)s",
    )

    flights_dir = Path(args.flights_dir).resolve()
    airports_path = Path(args.airports_path).resolve()
    iso3166_path = Path(args.iso3166_path).resolve()
    out_dir = Path(args.out_dir).resolve()

    if args.top_n <= 0:
        logging.error("--top-n must be positive.")
        return 2

    sources = [flights_dir / "challenge_set.parquet"]
    if args.include_submission:
        sources.append(flights_dir / "submission_set.parquet")
    if args.include_final:
        sources.append(flights_dir / "final_submission_set.parquet")

    missing = [p for p in sources if not p.exists()]
    if missing:
        for p in missing:
            logging.error("missing source: %s", p)
        return 2
    if not airports_path.exists():
        logging.error("missing airports meta: %s", airports_path)
        return 2

    logging.info("sources: %s", ", ".join(p.name for p in sources))
    df = _load_sources(sources, args.procs)
    if df.empty:
        logging.warning("no records after loading sources")
        return 0

    country_map = _load_iso3166_country_map(iso3166_path)
    airports_meta = _load_airports_meta(airports_path, country_map)

    airports_combined = pd.concat([df["adep"], df["ades"]], ignore_index=True)
    airports_adep = df["adep"]
    airports_ades = df["ades"]
    aircraft_types = df["aircraft_type"]

    counts_combined = _build_counts(airports_combined, "airport")
    counts_adep = _build_counts(airports_adep, "airport")
    counts_ades = _build_counts(airports_ades, "airport")
    counts_aircraft = _build_counts(aircraft_types, "aircraft_type")

    counts_combined = _attach_airport_meta(counts_combined, airports_meta)
    counts_adep = _attach_airport_meta(counts_adep, airports_meta)
    counts_ades = _attach_airport_meta(counts_ades, airports_meta)

    _write_csv(counts_combined, out_dir / "airports_combined_counts.csv")
    _write_csv(counts_adep, out_dir / "airports_adep_counts.csv")
    _write_csv(counts_ades, out_dir / "airports_ades_counts.csv")
    _write_csv(counts_aircraft, out_dir / "aircraft_type_counts.csv")

    _plot_topn(
        counts_combined,
        "airport",
        args.top_n,
        f"Top {args.top_n} Airports (Combined)",
        out_dir / "airports_combined_topN.png",
    )
    _plot_topn(
        counts_adep,
        "airport",
        args.top_n,
        f"Top {args.top_n} Airports (ADEP)",
        out_dir / "airports_adep_topN.png",
    )
    _plot_topn(
        counts_ades,
        "airport",
        args.top_n,
        f"Top {args.top_n} Airports (ADES)",
        out_dir / "airports_ades_topN.png",
    )
    _plot_topn(
        counts_aircraft,
        "aircraft_type",
        args.top_n,
        f"Top {args.top_n} Aircraft Types",
        out_dir / "aircraft_type_topN.png",
    )

    logging.info("outputs: %s", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
