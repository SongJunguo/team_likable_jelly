import argparse
import os
from glob import glob
from typing import List, Tuple

import numpy as np
import pandas as pd


def list_parquet_files(data_dir: str) -> List[str]:
    files = sorted(glob(os.path.join(data_dir, "*.parquet")))
    return files


def ensure_datetime64_s(ts: pd.Series) -> pd.Series:
    # Normalize timestamp to UTC-aware datetime64[ns]
    if not np.issubdtype(ts.dtype, np.datetime64):
        ts = pd.to_datetime(ts, utc=True, errors="coerce")
    # Ensure timezone-aware
    if getattr(ts.dtype, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    return ts


def run_lengths(mask: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return start indices and lengths of True-runs in boolean mask.
    """
    if mask.size == 0:
        return np.empty(0, dtype=int), np.empty(0, dtype=int)
    m = mask.astype(np.int8)
    dm = np.diff(np.concatenate(([0], m, [0])))
    starts = np.flatnonzero(dm == 1)
    ends = np.flatnonzero(dm == -1)
    lengths = ends - starts
    return starts, lengths


def analyze_file(fp: str, column: str) -> Tuple[pd.DataFrame, np.ndarray]:
    """
    Returns:
      - per-flight summary DataFrame with columns [flight_id, n_total, n_nan, missing_rate, n_runs, longest_run_sec]
      - array of hole lengths (seconds) for all NaN runs in this file
    """
    use_cols = ["flight_id", "timestamp", column]
    df = pd.read_parquet(fp, columns=use_cols)

    # Types
    df["flight_id"] = df["flight_id"].astype("int64", copy=False)
    df["timestamp"] = ensure_datetime64_s(df["timestamp"])  # UTC

    # Sort within file just in case
    df = df.sort_values(["flight_id", "timestamp"], kind="mergesort")

    per_flight = []
    all_holes_sec = []

    for fid, g in df.groupby("flight_id", sort=False):
        s = g[column]
        mask_nan = s.isna().to_numpy()
        n_total = int(mask_nan.size)
        if n_total == 0:
            continue
        n_nan = int(mask_nan.sum())

        # Missing runs
        starts, lens = run_lengths(mask_nan)
        n_runs = int(lens.size)

        # Compute hole length as (next-valid ts - prev-valid ts) for each run
        ts = g["timestamp"].astype("int64").to_numpy()  # ns since epoch
        hole_secs_this_f = []
        if n_runs:
            for st, ln in zip(starts, lens):
                run_start = st
                run_end = st + ln - 1
                prev_idx = run_start - 1 if run_start - 1 >= 0 else None
                next_idx = run_end + 1 if (run_end + 1) < n_total else None

                if prev_idx is not None and next_idx is not None:
                    # ns → s
                    hole_sec = (ts[next_idx] - ts[prev_idx]) / 1_000_000_000.0
                    hole_secs_this_f.append(hole_sec)
                    all_holes_sec.append(hole_sec)
                else:
                    # Edge (no prev or next valid) → undefined hole size; skip from distribution
                    pass

        longest_run_sec = float(np.nan)
        if hole_secs_this_f:
            longest_run_sec = float(np.max(hole_secs_this_f))

        per_flight.append(
            {
                "flight_id": int(fid),
                "n_total": n_total,
                "n_nan": n_nan,
                "missing_rate": (n_nan / n_total) if n_total else np.nan,
                "n_runs": n_runs,
                "longest_run_sec": longest_run_sec,
            }
        )

    per_flight_df = pd.DataFrame(per_flight)
    return per_flight_df, np.asarray(all_holes_sec, dtype=float)


def summarize_missing(per_flight_df: pd.DataFrame, all_holes_sec: np.ndarray) -> dict:
    res = {}
    if not per_flight_df.empty:
        rates = per_flight_df["missing_rate"].to_numpy()
        res["missing_rate_count"] = int(rates.size)
        for q in (0.5, 0.75, 0.9, 0.95):
            res[f"missing_rate_p{int(q*100)}"] = float(np.nanpercentile(rates, q * 100))
        res["missing_rate_mean"] = float(np.nanmean(rates))

        # Longest run per flight
        lrs = per_flight_df["longest_run_sec"].to_numpy()
        lrs = lrs[~np.isnan(lrs)]
        if lrs.size:
            for q in (0.5, 0.75, 0.9, 0.95):
                res[f"longest_run_sec_p{int(q*100)}"] = float(np.percentile(lrs, q * 100))
            res["longest_run_sec_mean"] = float(np.mean(lrs))
            res["longest_run_count"] = int(lrs.size)
    else:
        res["missing_rate_count"] = 0

    if all_holes_sec.size:
        res["holes_count"] = int(all_holes_sec.size)
        for q in (0.5, 0.75, 0.9, 0.95):
            res[f"hole_sec_p{int(q*100)}"] = float(np.percentile(all_holes_sec, q * 100))
        res["hole_sec_mean"] = float(np.mean(all_holes_sec))
    else:
        res["holes_count"] = 0

    return res


def main():
    parser = argparse.ArgumentParser(description="Analyze NaN rates and missing-window lengths in interpolated trajectories")
    parser.add_argument(
        "--data-dir",
        default="opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories",
        help="Directory with interpolated daily parquet files",
    )
    parser.add_argument("--column", default="groundspeed", help="Column to analyze for NaNs")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of daily files (0=all)")
    parser.add_argument("--out-prefix", default="reports/missing_interp", help="Output prefix for CSV summaries")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out_prefix), exist_ok=True)

    files = list_parquet_files(args.data_dir)
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    all_per_flight = []
    all_holes = []

    for i, fp in enumerate(files, 1):
        print(f"[analyze] {i}/{len(files)}: {os.path.basename(fp)} ...", flush=True)
        try:
            pf, holes = analyze_file(fp, args.column)
        except Exception as e:
            print(f"[warn] failed on {fp}: {e}")
            continue
        pf.insert(0, "day_file", os.path.basename(fp))
        all_per_flight.append(pf)
        if holes.size:
            all_holes.append(holes)

    if all_per_flight:
        per_flight_df = pd.concat(all_per_flight, ignore_index=True)
    else:
        per_flight_df = pd.DataFrame(columns=["day_file", "flight_id", "n_total", "n_nan", "missing_rate", "n_runs", "longest_run_sec"])

    hole_arr = np.concatenate(all_holes) if all_holes else np.asarray([], dtype=float)

    # Save per-flight summary
    per_flight_out = f"{args.out_prefix}_{args.column}_per_flight.csv"
    per_flight_df.to_csv(per_flight_out, index=False)
    print(f"[write] per-flight summary → {per_flight_out}")

    # Global summary
    summary = summarize_missing(per_flight_df, hole_arr)
    summary_out = f"{args.out_prefix}_{args.column}_summary.csv"
    if summary:
        (pd.Series(summary).to_frame("value").rename_axis("metric").reset_index()).to_csv(summary_out, index=False)
    print(f"[write] summary → {summary_out}")

    # Also print key metrics
    print("\n=== Summary (", args.column, ") ===", sep="")
    for k in sorted(summary.keys()):
        print(f"{k}: {summary[k]}")


if __name__ == "__main__":
    main()
