#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对单航班执行过滤并生成 Raw vs Filter PDF。"""

from __future__ import annotations

import argparse
import os
from typing import List

import pandas as pd
from traffic.core import Traffic

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from filter_trajs import build_filter_chain, nointerpolate
from test_python.analysis.plot_flight_before_after_filter import plot_compare

RAW_DEFAULT = "/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories"


def load_single_flight(path: str, flight_id: int) -> pd.DataFrame:
    col_candidates: List[str] = [
        "flight_id",
        "timestamp",
        "icao24",
        "latitude",
        "longitude",
        "altitude",
        "groundspeed",
        "track",
        "vertical_rate",
    ]
    try:
        df = pd.read_parquet(path, filters=[("flight_id", "=", flight_id)])
    except Exception:
        df = pd.read_parquet(path)
        df = df[df["flight_id"] == flight_id]
    if df.empty:
        raise ValueError(f"flight_id {flight_id} not found in {path}")
    cols = [c for c in col_candidates if c in df.columns]
    df = df[cols].copy()
    df["flight_id"] = df["flight_id"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def filter_single_flight(df: pd.DataFrame, strategy: str) -> pd.DataFrame:
    chain = build_filter_chain(strategy)
    filtered = (
        Traffic(df)
        .filter(filter=chain, strategy=nointerpolate)
        .eval(max_workers=1)
        .data
    )
    return filtered.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter single flight and plot Raw vs Filter")
    parser.add_argument("--date", required=True)
    parser.add_argument("--flight-id", type=int, required=True)
    parser.add_argument("--strategy", default="classic_dp_loop")
    parser.add_argument("--raw-dir", default=RAW_DEFAULT)
    parser.add_argument("--out-pdf", required=True)
    args = parser.parse_args()

    raw_file = os.path.join(args.raw_dir, f"{args.date}.parquet")
    df_raw = load_single_flight(raw_file, args.flight_id)
    df_filt = filter_single_flight(df_raw.copy(), args.strategy)

    cols = [c for c in ["flight_id", "timestamp", "latitude", "longitude", "altitude"] if c in df_raw.columns]
    plot_compare(df_raw[cols], df_filt[cols], args.flight_id, args.out_pdf)
    print(f"✅ Saved {args.out_pdf}")


if __name__ == "__main__":
    main()
