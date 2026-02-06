#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare motion fields in interpolated ADS-B data against values derived from
latitude/longitude/altitude using dt==1s pairs.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import math
import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


NS_PER_S = 1_000_000_000
MPS_TO_KT = 1.9438444924406048
FTPM_TO_MPS = 0.00508


@dataclasses.dataclass
class StatsAgg:
    count: int = 0
    sum: float = 0.0
    sum_abs: float = 0.0
    sum_sq: float = 0.0
    min: float = math.inf
    max: float = -math.inf

    def update(self, values: np.ndarray) -> None:
        if values.size == 0:
            return
        vals = values[np.isfinite(values)]
        if vals.size == 0:
            return
        self.count += int(vals.size)
        self.sum += float(vals.sum())
        self.sum_abs += float(np.abs(vals).sum())
        self.sum_sq += float(np.square(vals).sum())
        vmin = float(vals.min())
        vmax = float(vals.max())
        if vmin < self.min:
            self.min = vmin
        if vmax > self.max:
            self.max = vmax

    def merge(self, other: "StatsAgg") -> None:
        self.count += other.count
        self.sum += other.sum
        self.sum_abs += other.sum_abs
        self.sum_sq += other.sum_sq
        if other.min < self.min:
            self.min = other.min
        if other.max > self.max:
            self.max = other.max

    def finalize(self) -> Dict[str, float]:
        if self.count == 0:
            return {
                "count": 0,
                "bias": math.nan,
                "mae": math.nan,
                "rmse": math.nan,
                "min": math.nan,
                "max": math.nan,
            }
        bias = self.sum / self.count
        mae = self.sum_abs / self.count
        rmse = math.sqrt(self.sum_sq / self.count)
        return {
            "count": self.count,
            "bias": bias,
            "mae": mae,
            "rmse": rmse,
            "min": self.min,
            "max": self.max,
        }


@dataclasses.dataclass
class HistAgg:
    edges: np.ndarray
    counts: np.ndarray
    under: int = 0
    over: int = 0

    def update(self, values: np.ndarray) -> None:
        if values.size == 0:
            return
        vals = values[np.isfinite(values)]
        if vals.size == 0:
            return
        min_edge = float(self.edges[0])
        max_edge = float(self.edges[-1])
        self.under += int(np.sum(vals < min_edge))
        self.over += int(np.sum(vals > max_edge))
        hist, _ = np.histogram(vals, bins=self.edges)
        self.counts += hist.astype(np.int64, copy=False)

    def merge(self, other: "HistAgg") -> None:
        self.counts += other.counts
        self.under += other.under
        self.over += other.over


def _angle_diff_deg(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return (a - b + 180.0) % 360.0 - 180.0


def _bearing_haversine(
    lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    lat1_rad = np.deg2rad(lat1)
    lat2_rad = np.deg2rad(lat2)
    dlat = lat2_rad - lat1_rad
    dlon = np.deg2rad(lon2 - lon1)
    a = (
        np.sin(dlat / 2.0) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2.0) ** 2
    )
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    distance_m = 6371000.0 * c
    y = np.sin(dlon) * np.cos(lat2_rad)
    x = np.cos(lat1_rad) * np.sin(lat2_rad) - np.sin(lat1_rad) * np.cos(lat2_rad) * np.cos(dlon)
    bearing = (np.degrees(np.arctan2(y, x)) + 360.0) % 360.0
    return distance_m, bearing


def _compute_geo(
    lat1: np.ndarray,
    lon1: np.ndarray,
    lat2: np.ndarray,
    lon2: np.ndarray,
    dt_s: np.ndarray,
    method: str,
) -> Tuple[np.ndarray, np.ndarray]:
    if method == "pyproj":
        try:
            from pyproj import Geod
        except Exception:
            method = "haversine"
        else:
            geod = Geod(ellps="WGS84")
            az_fwd, _, dist_m = geod.inv(lon1, lat1, lon2, lat2)
            bearing = (az_fwd + 360.0) % 360.0
            speed_kt = (dist_m / dt_s) * MPS_TO_KT
            return speed_kt, bearing
    if method == "haversine":
        dist_m, bearing = _bearing_haversine(lat1, lon1, lat2, lon2)
        speed_kt = (dist_m / dt_s) * MPS_TO_KT
        return speed_kt, bearing
    raise ValueError(f"Unsupported geo method: {method}")


def _parse_date_from_name(name: str) -> dt.date | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    if not match:
        return None
    return dt.date.fromisoformat(match.group(1))


def _iter_files(data_dir: str, date_from: dt.date, date_to: dt.date) -> List[str]:
    files: List[Tuple[dt.date, str]] = []
    for fname in os.listdir(data_dir):
        if not fname.endswith(".parquet"):
            continue
        fdate = _parse_date_from_name(fname)
        if fdate is None:
            continue
        if fdate < date_from or fdate > date_to:
            continue
        files.append((fdate, os.path.join(data_dir, fname)))
    files.sort(key=lambda x: x[0])
    return [path for _, path in files]


def _split_flights(flight_id: np.ndarray) -> Iterable[Tuple[int, int]]:
    if flight_id.size == 0:
        return
    cuts = np.flatnonzero(flight_id[1:] != flight_id[:-1]) + 1
    starts = np.concatenate(([0], cuts))
    ends = np.concatenate((cuts, [flight_id.size]))
    for start, end in zip(starts, ends):
        if end - start >= 2:
            yield int(start), int(end)


def _build_edges(min_val: float, max_val: float, width: float) -> np.ndarray:
    bins = int(math.ceil((max_val - min_val) / width))
    return min_val + np.arange(bins + 1) * width


def _init_hist(min_val: float, max_val: float, width: float) -> HistAgg:
    edges = _build_edges(min_val, max_val, width)
    counts = np.zeros(edges.size - 1, dtype=np.int64)
    return HistAgg(edges=edges, counts=counts)


def _parse_speed_bins(text: str) -> List[float]:
    parts = [item.strip() for item in text.split(",") if item.strip()]
    if len(parts) < 2:
        raise ValueError("speed bins 需要至少两个边界值，例如 0,50,150,300")
    bins: List[float] = []
    for part in parts:
        lower = part.lower()
        if lower in ("inf", "infty", "infinite"):
            bins.append(math.inf)
        else:
            bins.append(float(part))
    for idx in range(1, len(bins)):
        if not bins[idx] > bins[idx - 1]:
            raise ValueError("speed bins 必须严格递增")
    return bins


def _build_speed_bin_pairs(edges: List[float]) -> List[Tuple[float, float]]:
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def _update_stats(stats: StatsAgg, diff: np.ndarray, mask: np.ndarray) -> None:
    if np.any(mask):
        stats.update(diff[mask])


def _merge_hist_dict(target: Dict[str, HistAgg], payload: Dict[str, object]) -> None:
    for key, hist in target.items():
        _merge_hist(hist, payload[key])


def _bin_label(low: float, high: float) -> str:
    if math.isinf(high):
        return f"{low:g}+"
    return f"{low:g}-{high:g}"


def _bin_dir_name(label: str) -> str:
    name = label.replace("+", "plus").replace("-", "_").replace(".", "p")
    return f"bin_{name}"


def _format_speed_bin_title(low: float, high: float) -> str:
    low_ms = low * 0.5144444444444445
    if math.isinf(high):
        return f"speed bin {low:g}+ kt / {low_ms:.1f}+ m/s"
    high_ms = high * 0.5144444444444445
    return f"speed bin {low:g}-{high:g} kt / {low_ms:.1f}-{high_ms:.1f} m/s"


def _process_file(
    path: str,
    geo_method: str,
    dt_seconds: int,
    lag_shifts: List[int],
    hist_cfg: Dict[str, Tuple[float, float, float]],
    min_groundspeed: float,
    min_altitude: float,
    speed_bins: List[float],
) -> Dict[str, object]:
    columns = [
        "timestamp",
        "latitude",
        "longitude",
        "altitude",
        "groundspeed",
        "track",
        "vertical_rate",
        "flight_id",
    ]
    table = pq.read_table(path, columns=columns)
    df = table.to_pandas(use_threads=True)
    df = df.sort_values(["flight_id", "timestamp"], kind="mergesort")

    flight_id = df["flight_id"].to_numpy(np.int64, copy=False)
    bin_pairs = _build_speed_bin_pairs(speed_bins)
    empty_bins = [
        {k: dataclasses.asdict(StatsAgg()) for k in ("speed", "track", "vrate")} for _ in bin_pairs
    ]
    if flight_id.size == 0:
        empty_stats = {k: dataclasses.asdict(StatsAgg()) for k in ("speed", "track", "vrate")}
        return {
            "file": path,
            "rows": 0,
            "stats": {"all": empty_stats, "filtered": empty_stats, "bins": empty_bins},
            "hist": {},
            "lag": {},
        }
    ts_ns = df["timestamp"].to_numpy(dtype="datetime64[ns]").astype("int64", copy=False)
    lat = df["latitude"].to_numpy(np.float64, copy=False)
    lon = df["longitude"].to_numpy(np.float64, copy=False)
    alt = df["altitude"].to_numpy(np.float64, copy=False)

    groundspeed = df["groundspeed"].to_numpy(np.float64, copy=False)
    track = df["track"].to_numpy(np.float64, copy=False)
    vertical_rate = df["vertical_rate"].to_numpy(np.float64, copy=False)

    n = flight_id.size
    derived_speed = np.full(n, np.nan, dtype=np.float64)
    derived_track = np.full(n, np.nan, dtype=np.float64)
    derived_vrate = np.full(n, np.nan, dtype=np.float64)

    same_flight = flight_id[1:] == flight_id[:-1]
    dt_ns = ts_ns[1:] - ts_ns[:-1]
    target_ns = int(dt_seconds) * NS_PER_S
    mask_dt = same_flight & (dt_ns == target_ns)
    if np.any(mask_dt):
        pair_idx = np.nonzero(mask_dt)[0]
        idx_curr = pair_idx + 1
        dt_s = dt_ns[mask_dt].astype(np.float64) / NS_PER_S

        lat1 = lat[pair_idx]
        lat2 = lat[idx_curr]
        lon1 = lon[pair_idx]
        lon2 = lon[idx_curr]
        valid_geo = np.isfinite(lat1) & np.isfinite(lat2) & np.isfinite(lon1) & np.isfinite(lon2)
        if np.any(valid_geo):
            speed_kt, bearing = _compute_geo(
                lat1[valid_geo],
                lon1[valid_geo],
                lat2[valid_geo],
                lon2[valid_geo],
                dt_s[valid_geo],
                geo_method,
            )
            derived_speed[idx_curr[valid_geo]] = speed_kt
            derived_track[idx_curr[valid_geo]] = bearing

        alt1 = alt[pair_idx]
        alt2 = alt[idx_curr]
        valid_alt = np.isfinite(alt1) & np.isfinite(alt2)
        if np.any(valid_alt):
            vrate = (alt2[valid_alt] - alt1[valid_alt]) / dt_s[valid_alt] * 60.0
            derived_vrate[idx_curr[valid_alt]] = vrate

    stats_speed = StatsAgg()
    stats_track = StatsAgg()
    stats_vrate = StatsAgg()
    stats_speed_filtered = StatsAgg()
    stats_track_filtered = StatsAgg()
    stats_vrate_filtered = StatsAgg()
    stats_bins = [
        {"speed": StatsAgg(), "track": StatsAgg(), "vrate": StatsAgg()} for _ in bin_pairs
    ]
    hist_speed = _init_hist(*hist_cfg["speed"])
    hist_track = _init_hist(*hist_cfg["track"])
    hist_vrate = _init_hist(*hist_cfg["vrate"])
    bin_hists = [
        {
            "speed": _init_hist(*hist_cfg["speed"]),
            "track": _init_hist(*hist_cfg["track"]),
            "vrate": _init_hist(*hist_cfg["vrate"]),
        }
        for _ in bin_pairs
    ]

    speed_diff = derived_speed - groundspeed
    track_diff = _angle_diff_deg(derived_track, track)
    vrate_diff = derived_vrate - vertical_rate
    mask_speed = np.isfinite(derived_speed) & np.isfinite(groundspeed)
    mask_track = np.isfinite(derived_track) & np.isfinite(track)
    mask_vrate = np.isfinite(derived_vrate) & np.isfinite(vertical_rate)

    filter_mask = (
        np.isfinite(groundspeed)
        & np.isfinite(alt)
        & (groundspeed >= min_groundspeed)
        & (alt >= min_altitude)
    )

    _update_stats(stats_speed, speed_diff, mask_speed)
    _update_stats(stats_track, track_diff, mask_track)
    _update_stats(stats_vrate, vrate_diff, mask_vrate)

    _update_stats(stats_speed_filtered, speed_diff, mask_speed & filter_mask)
    _update_stats(stats_track_filtered, track_diff, mask_track & filter_mask)
    _update_stats(stats_vrate_filtered, vrate_diff, mask_vrate & filter_mask)

    for idx, (low, high) in enumerate(bin_pairs):
        if math.isinf(high):
            bin_mask = groundspeed >= low
        elif idx == len(bin_pairs) - 1:
            bin_mask = (groundspeed >= low) & (groundspeed <= high)
        else:
            bin_mask = (groundspeed >= low) & (groundspeed < high)
        _update_stats(stats_bins[idx]["speed"], speed_diff, mask_speed & bin_mask)
        _update_stats(stats_bins[idx]["track"], track_diff, mask_track & bin_mask)
        _update_stats(stats_bins[idx]["vrate"], vrate_diff, mask_vrate & bin_mask)
        bin_hists[idx]["speed"].update(speed_diff[mask_speed & bin_mask])
        bin_hists[idx]["track"].update(track_diff[mask_track & bin_mask])
        bin_hists[idx]["vrate"].update(vrate_diff[mask_vrate & bin_mask])

    hist_speed.update(speed_diff)
    hist_track.update(track_diff)
    hist_vrate.update(vrate_diff)

    lag_acc = {var: {shift: [0.0, 0] for shift in lag_shifts} for var in ("speed", "track", "vrate")}

    for start, end in _split_flights(flight_id):
        ds = derived_speed[start:end]
        dtk = derived_track[start:end]
        dv = derived_vrate[start:end]
        os = groundspeed[start:end]
        ot = track[start:end]
        ov = vertical_rate[start:end]

        for shift in lag_shifts:
            if shift > 0:
                ds_a, os_a = ds[:-shift], os[shift:]
                dt_a, ot_a = dtk[:-shift], ot[shift:]
                dv_a, ov_a = dv[:-shift], ov[shift:]
            elif shift < 0:
                ds_a, os_a = ds[-shift:], os[:shift]
                dt_a, ot_a = dtk[-shift:], ot[:shift]
                dv_a, ov_a = dv[-shift:], ov[:shift]
            else:
                ds_a, os_a = ds, os
                dt_a, ot_a = dtk, ot
                dv_a, ov_a = dv, ov

            if ds_a.size == 0:
                continue

            mask_speed = np.isfinite(ds_a) & np.isfinite(os_a)
            if np.any(mask_speed):
                diff = ds_a[mask_speed] - os_a[mask_speed]
                lag_acc["speed"][shift][0] += float(np.abs(diff).sum())
                lag_acc["speed"][shift][1] += int(mask_speed.sum())

            mask_track = np.isfinite(dt_a) & np.isfinite(ot_a)
            if np.any(mask_track):
                diff = _angle_diff_deg(dt_a[mask_track], ot_a[mask_track])
                lag_acc["track"][shift][0] += float(np.abs(diff).sum())
                lag_acc["track"][shift][1] += int(mask_track.sum())

            mask_vrate = np.isfinite(dv_a) & np.isfinite(ov_a)
            if np.any(mask_vrate):
                diff = dv_a[mask_vrate] - ov_a[mask_vrate]
                lag_acc["vrate"][shift][0] += float(np.abs(diff).sum())
                lag_acc["vrate"][shift][1] += int(mask_vrate.sum())

    return {
        "file": path,
        "rows": int(n),
        "stats": {
            "all": {
                "speed": dataclasses.asdict(stats_speed),
                "track": dataclasses.asdict(stats_track),
                "vrate": dataclasses.asdict(stats_vrate),
            },
            "filtered": {
                "speed": dataclasses.asdict(stats_speed_filtered),
                "track": dataclasses.asdict(stats_track_filtered),
                "vrate": dataclasses.asdict(stats_vrate_filtered),
            },
            "bins": [
                {
                    "speed": dataclasses.asdict(stats["speed"]),
                    "track": dataclasses.asdict(stats["track"]),
                    "vrate": dataclasses.asdict(stats["vrate"]),
                }
                for stats in stats_bins
            ],
        },
        "hist": {
            "speed": {
                "counts": hist_speed.counts.tolist(),
                "under": hist_speed.under,
                "over": hist_speed.over,
            },
            "track": {
                "counts": hist_track.counts.tolist(),
                "under": hist_track.under,
                "over": hist_track.over,
            },
            "vrate": {
                "counts": hist_vrate.counts.tolist(),
                "under": hist_vrate.under,
                "over": hist_vrate.over,
            },
        },
        "bin_hists": [
            {
                "speed": {
                    "counts": hist["speed"].counts.tolist(),
                    "under": hist["speed"].under,
                    "over": hist["speed"].over,
                },
                "track": {
                    "counts": hist["track"].counts.tolist(),
                    "under": hist["track"].under,
                    "over": hist["track"].over,
                },
                "vrate": {
                    "counts": hist["vrate"].counts.tolist(),
                    "under": hist["vrate"].under,
                    "over": hist["vrate"].over,
                },
            }
            for hist in bin_hists
        ],
        "lag": {
            var: {str(shift): {"sum_abs": acc[0], "count": acc[1]} for shift, acc in shifts.items()}
            for var, shifts in lag_acc.items()
        },
    }


def _merge_stats(target: StatsAgg, payload: Dict[str, float]) -> None:
    other = StatsAgg(**payload)
    target.merge(other)


def _merge_hist(target: HistAgg, payload: Dict[str, object]) -> None:
    target.under += int(payload["under"])
    target.over += int(payload["over"])
    target.counts += np.asarray(payload["counts"], dtype=np.int64)


def _write_hist_csv(path: str, hist: HistAgg) -> None:
    edges = hist.edges
    left = edges[:-1]
    right = edges[1:]
    center = (left + right) / 2.0
    df = pd.DataFrame(
        {
            "bin_left": left,
            "bin_right": right,
            "bin_center": center,
            "count": hist.counts,
        }
    )
    df.to_csv(path, index=False)


def _scale_hist(hist: HistAgg, factor: float) -> HistAgg:
    return HistAgg(
        edges=hist.edges * factor,
        counts=hist.counts.copy(),
        under=hist.under,
        over=hist.over,
    )


def _plot_hist(path: str, hist: HistAgg, title: str, xlabel: str, dpi: int) -> None:
    import matplotlib.pyplot as plt

    edges = hist.edges
    left = edges[:-1]
    width = float(edges[1] - edges[0])
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(left, hist.counts, width=width, align="edge", color="#2c7fb8")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("count")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)


def _plot_hist_with_scale(
    path: str,
    hist: HistAgg,
    title: str,
    xlabel: str,
    dpi: int,
    yscale: str,
) -> None:
    import matplotlib.pyplot as plt

    edges = hist.edges
    left = edges[:-1]
    width = float(edges[1] - edges[0])
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(left, hist.counts, width=width, align="edge", color="#2c7fb8")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("count")
    ax.set_yscale(yscale)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)


def _default_processes() -> int:
    cpu = os.cpu_count() or 1
    return max(1, min(8, cpu // 2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare interpolated motion with geo-derived motion.")
    parser.add_argument(
        "--data-dir",
        default="opensky_2024_PRC_dataset/interpolated_clean_eu_v5",
        help="输入目录（interpolated_clean_eu_v5）",
    )
    parser.add_argument("--date-from", default="2022-01-01", help="起始日期 YYYY-MM-DD")
    parser.add_argument("--date-to", default="2022-01-31", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--processes", type=int, default=_default_processes(), help="并发进程数")
    parser.add_argument("--geo-method", choices=["pyproj", "haversine"], default="pyproj")
    parser.add_argument("--dt-seconds", type=int, default=1, help="仅使用相邻点 dt=该值")
    parser.add_argument("--lag-min", type=int, default=-5, help="迟滞搜索最小秒数")
    parser.add_argument("--lag-max", type=int, default=5, help="迟滞搜索最大秒数")
    parser.add_argument("--min-groundspeed", type=float, default=30.0, help="过滤统计：最低地速 kt")
    parser.add_argument("--min-altitude", type=float, default=1000.0, help="过滤统计：最低高度 ft")
    parser.add_argument(
        "--speed-bins",
        default="0,50,150,300,500,700",
        help="按地速分箱边界(kt)，逗号分隔，可用 inf 作为最后边界",
    )
    parser.add_argument(
        "--bin-hist-yscale",
        choices=["linear", "log", "both"],
        default="linear",
        help="分箱直方图 y 轴刻度",
    )
    parser.add_argument("--output-dir", default="reports/spd_compare", help="输出目录")
    parser.add_argument("--hist-dpi", type=int, default=600, help="直方图 DPI")
    parser.add_argument("--no-plot", action="store_true", help="不输出 PNG 直方图")
    parser.add_argument("--speed-diff-min", type=float, default=-50.0)
    parser.add_argument("--speed-diff-max", type=float, default=50.0)
    parser.add_argument("--speed-diff-bin", type=float, default=0.1)
    parser.add_argument("--track-diff-min", type=float, default=-30.0)
    parser.add_argument("--track-diff-max", type=float, default=30.0)
    parser.add_argument("--track-diff-bin", type=float, default=0.1)
    parser.add_argument("--vrate-diff-min", type=float, default=-1500.0)
    parser.add_argument("--vrate-diff-max", type=float, default=1500.0)
    parser.add_argument("--vrate-diff-bin", type=float, default=5.0)

    args = parser.parse_args()
    date_from = dt.date.fromisoformat(args.date_from)
    date_to = dt.date.fromisoformat(args.date_to)
    speed_bins = _parse_speed_bins(args.speed_bins)
    bin_pairs = _build_speed_bin_pairs(speed_bins)

    files = _iter_files(args.data_dir, date_from, date_to)
    if not files:
        raise SystemExit("未找到符合日期范围的 parquet 文件。")

    os.makedirs(args.output_dir, exist_ok=True)

    hist_cfg = {
        "speed": (args.speed_diff_min, args.speed_diff_max, args.speed_diff_bin),
        "track": (args.track_diff_min, args.track_diff_max, args.track_diff_bin),
        "vrate": (args.vrate_diff_min, args.vrate_diff_max, args.vrate_diff_bin),
    }

    hist_speed = _init_hist(*hist_cfg["speed"])
    hist_track = _init_hist(*hist_cfg["track"])
    hist_vrate = _init_hist(*hist_cfg["vrate"])
    bin_hists = [
        {
            "speed": _init_hist(*hist_cfg["speed"]),
            "track": _init_hist(*hist_cfg["track"]),
            "vrate": _init_hist(*hist_cfg["vrate"]),
        }
        for _ in bin_pairs
    ]

    stats_speed = StatsAgg()
    stats_track = StatsAgg()
    stats_vrate = StatsAgg()
    stats_speed_filtered = StatsAgg()
    stats_track_filtered = StatsAgg()
    stats_vrate_filtered = StatsAgg()
    stats_bins = [
        {"speed": StatsAgg(), "track": StatsAgg(), "vrate": StatsAgg()} for _ in bin_pairs
    ]

    lag_shifts = list(range(args.lag_min, args.lag_max + 1))
    lag_acc = {var: {shift: [0.0, 0] for shift in lag_shifts} for var in ("speed", "track", "vrate")}

    total_rows = 0
    futures = []
    with ProcessPoolExecutor(max_workers=args.processes) as executor:
        for path in files:
            futures.append(
                executor.submit(
                    _process_file,
                    path,
                    args.geo_method,
                    args.dt_seconds,
                    lag_shifts,
                    hist_cfg,
                    args.min_groundspeed,
                    args.min_altitude,
                    speed_bins,
                )
            )

        for fut in as_completed(futures):
            result = fut.result()
            total_rows += int(result["rows"])
            _merge_stats(stats_speed, result["stats"]["all"]["speed"])
            _merge_stats(stats_track, result["stats"]["all"]["track"])
            _merge_stats(stats_vrate, result["stats"]["all"]["vrate"])
            _merge_stats(stats_speed_filtered, result["stats"]["filtered"]["speed"])
            _merge_stats(stats_track_filtered, result["stats"]["filtered"]["track"])
            _merge_stats(stats_vrate_filtered, result["stats"]["filtered"]["vrate"])

            for idx, payload in enumerate(result["stats"]["bins"]):
                _merge_stats(stats_bins[idx]["speed"], payload["speed"])
                _merge_stats(stats_bins[idx]["track"], payload["track"])
                _merge_stats(stats_bins[idx]["vrate"], payload["vrate"])

            _merge_hist(hist_speed, result["hist"]["speed"])
            _merge_hist(hist_track, result["hist"]["track"])
            _merge_hist(hist_vrate, result["hist"]["vrate"])
            for idx, payload in enumerate(result["bin_hists"]):
                _merge_hist_dict(bin_hists[idx], payload)

            for var in ("speed", "track", "vrate"):
                for shift, payload in result["lag"][var].items():
                    lag_acc[var][int(shift)][0] += float(payload["sum_abs"])
                    lag_acc[var][int(shift)][1] += int(payload["count"])

    summary_rows = []
    for name, stats in (
        ("speed_diff", stats_speed),
        ("track_diff", stats_track),
        ("vrate_diff", stats_vrate),
    ):
        row = stats.finalize()
        row["metric"] = name
        summary_rows.append(row)

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df[["metric", "count", "bias", "mae", "rmse", "min", "max"]]
    summary_df.to_csv(os.path.join(args.output_dir, "summary_all.csv"), index=False)

    summary_filtered_rows = []
    for name, stats in (
        ("speed_diff", stats_speed_filtered),
        ("track_diff", stats_track_filtered),
        ("vrate_diff", stats_vrate_filtered),
    ):
        row = stats.finalize()
        row["metric"] = name
        summary_filtered_rows.append(row)

    summary_filtered_df = pd.DataFrame(summary_filtered_rows)
    summary_filtered_df = summary_filtered_df[
        ["metric", "count", "bias", "mae", "rmse", "min", "max"]
    ]
    summary_filtered_df.to_csv(
        os.path.join(args.output_dir, "summary_filtered.csv"), index=False
    )

    bin_rows = []
    var_map = {"speed": "speed_diff", "track": "track_diff", "vrate": "vrate_diff"}
    for idx, (low, high) in enumerate(bin_pairs):
        if math.isinf(high):
            bin_label = f"{low}+"
            bin_right = math.nan
        else:
            bin_label = f"{low}-{high}"
            bin_right = high
        for var, metric_name in var_map.items():
            row = stats_bins[idx][var].finalize()
            row.update(
                {
                    "bin_left": low,
                    "bin_right": bin_right,
                    "bin_label": bin_label,
                    "metric": metric_name,
                }
            )
            bin_rows.append(row)

    bin_df = pd.DataFrame(bin_rows)
    bin_df = bin_df[
        ["bin_left", "bin_right", "bin_label", "metric", "count", "bias", "mae", "rmse", "min", "max"]
    ]
    bin_df.to_csv(os.path.join(args.output_dir, "summary_by_speed_bin.csv"), index=False)

    lag_rows = []
    for var in ("speed", "track", "vrate"):
        best_shift = None
        best_mae = math.inf
        best_count = 0
        for shift in lag_shifts:
            sum_abs, count = lag_acc[var][shift]
            mae = sum_abs / count if count > 0 else math.nan
            lag_rows.append(
                {
                    "variable": var,
                    "shift_seconds": shift,
                    "mae": mae,
                    "count": count,
                }
            )
            if count > 0 and mae < best_mae:
                best_mae = mae
                best_shift = shift
                best_count = count
        lag_rows.append(
            {
                "variable": f"{var}__best",
                "shift_seconds": best_shift,
                "mae": best_mae if best_shift is not None else math.nan,
                "count": best_count,
            }
        )

    lag_df = pd.DataFrame(lag_rows)
    lag_df.to_csv(os.path.join(args.output_dir, "lag_best_shift.csv"), index=False)

    _write_hist_csv(os.path.join(args.output_dir, "hist_speed_diff.csv"), hist_speed)
    _write_hist_csv(os.path.join(args.output_dir, "hist_track_diff.csv"), hist_track)
    _write_hist_csv(os.path.join(args.output_dir, "hist_vrate_diff.csv"), hist_vrate)
    hist_vrate_ms = _scale_hist(hist_vrate, FTPM_TO_MPS)
    _write_hist_csv(os.path.join(args.output_dir, "hist_vrate_diff_ms.csv"), hist_vrate_ms)

    bin_hist_dir = os.path.join(args.output_dir, "bin_hists")
    os.makedirs(bin_hist_dir, exist_ok=True)
    for (low, high), hist_set in zip(bin_pairs, bin_hists):
        label = _bin_label(low, high)
        subdir = os.path.join(bin_hist_dir, _bin_dir_name(label))
        os.makedirs(subdir, exist_ok=True)
        _write_hist_csv(os.path.join(subdir, "hist_speed_diff.csv"), hist_set["speed"])
        _write_hist_csv(os.path.join(subdir, "hist_track_diff.csv"), hist_set["track"])
        _write_hist_csv(os.path.join(subdir, "hist_vrate_diff.csv"), hist_set["vrate"])
        hist_vrate_bin_ms = _scale_hist(hist_set["vrate"], FTPM_TO_MPS)
        _write_hist_csv(os.path.join(subdir, "hist_vrate_diff_ms.csv"), hist_vrate_bin_ms)

        if not args.no_plot:
            title_suffix = f"({_format_speed_bin_title(low, high)})"
            if args.bin_hist_yscale in ("linear", "both"):
                _plot_hist(
                    os.path.join(subdir, "hist_speed_diff.png"),
                    hist_set["speed"],
                    f"Speed diff {title_suffix}",
                    "kt",
                    args.hist_dpi,
                )
                _plot_hist(
                    os.path.join(subdir, "hist_track_diff.png"),
                    hist_set["track"],
                    f"Track diff {title_suffix}",
                    "deg",
                    args.hist_dpi,
                )
                _plot_hist(
                    os.path.join(subdir, "hist_vrate_diff.png"),
                    hist_set["vrate"],
                    f"Vertical rate diff {title_suffix}",
                    "ft/min",
                    args.hist_dpi,
                )
                _plot_hist(
                    os.path.join(subdir, "hist_vrate_diff_ms.png"),
                    hist_vrate_bin_ms,
                    f"Vertical rate diff {title_suffix}",
                    "m/s",
                    args.hist_dpi,
                )
            if args.bin_hist_yscale in ("log", "both"):
                _plot_hist_with_scale(
                    os.path.join(subdir, "hist_speed_diff_log.png"),
                    hist_set["speed"],
                    f"Speed diff {title_suffix}",
                    "kt",
                    args.hist_dpi,
                    "log",
                )
                _plot_hist_with_scale(
                    os.path.join(subdir, "hist_track_diff_log.png"),
                    hist_set["track"],
                    f"Track diff {title_suffix}",
                    "deg",
                    args.hist_dpi,
                    "log",
                )
                _plot_hist_with_scale(
                    os.path.join(subdir, "hist_vrate_diff_log.png"),
                    hist_set["vrate"],
                    f"Vertical rate diff {title_suffix}",
                    "ft/min",
                    args.hist_dpi,
                    "log",
                )
                _plot_hist_with_scale(
                    os.path.join(subdir, "hist_vrate_diff_ms_log.png"),
                    hist_vrate_bin_ms,
                    f"Vertical rate diff {title_suffix}",
                    "m/s",
                    args.hist_dpi,
                    "log",
                )

    meta = {
        "date_from": args.date_from,
        "date_to": args.date_to,
        "data_dir": args.data_dir,
        "geo_method": args.geo_method,
        "dt_seconds": args.dt_seconds,
        "lag_min": args.lag_min,
        "lag_max": args.lag_max,
        "min_groundspeed": args.min_groundspeed,
        "min_altitude": args.min_altitude,
        "speed_bins": speed_bins,
        "bin_hist_yscale": args.bin_hist_yscale,
        "total_rows": total_rows,
        "hist_cfg": hist_cfg,
        "hist_under_over": {
            "speed": {"under": hist_speed.under, "over": hist_speed.over},
            "track": {"under": hist_track.under, "over": hist_track.over},
            "vrate": {"under": hist_vrate.under, "over": hist_vrate.over},
        },
    }
    pd.Series(meta).to_json(os.path.join(args.output_dir, "run_meta.json"), indent=2)

    if not args.no_plot:
        _plot_hist(
            os.path.join(args.output_dir, "hist_speed_diff.png"),
            hist_speed,
            "Speed diff (derived - groundspeed)",
            "kt",
            args.hist_dpi,
        )
        _plot_hist(
            os.path.join(args.output_dir, "hist_track_diff.png"),
            hist_track,
            "Track diff (derived - track, wrapped)",
            "deg",
            args.hist_dpi,
        )
        _plot_hist(
            os.path.join(args.output_dir, "hist_vrate_diff.png"),
            hist_vrate,
            "Vertical rate diff (derived - vertical_rate)",
            "ft/min",
            args.hist_dpi,
        )
        _plot_hist(
            os.path.join(args.output_dir, "hist_vrate_diff_ms.png"),
            hist_vrate_ms,
            "Vertical rate diff (derived - vertical_rate)",
            "m/s",
            args.hist_dpi,
        )


if __name__ == "__main__":
    main()
