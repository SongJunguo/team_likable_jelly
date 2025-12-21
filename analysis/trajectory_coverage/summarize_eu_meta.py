#!/usr/bin/env python3
"""
Summarize EU + meta flights from flight_metrics.csv.

Outputs:
- eu_meta_summary.csv
- eu_meta_summary.png
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np


def _parse_int(value: Optional[str]) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def _load_metrics(metrics_csv: Path) -> Tuple[str, Dict[str, float]]:
    flights_total = 0
    flights_eu_meta = 0
    points_total_all = 0
    points_valid_all = 0
    points_total_eu = 0
    points_valid_eu = 0
    dataset_label = ""

    with metrics_csv.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not dataset_label and "dataset" in row:
                dataset_label = row.get("dataset", "") or ""
            flights_total += 1
            points_total_all += _parse_int(row.get("points_total"))
            points_valid_all += _parse_int(row.get("points_valid"))
            is_eu = row.get("is_eu") == "1"
            has_meta = row.get("gc_distance_km") not in (None, "")
            if is_eu and has_meta:
                flights_eu_meta += 1
                points_total_eu += _parse_int(row.get("points_total"))
                points_valid_eu += _parse_int(row.get("points_valid"))

    if not dataset_label:
        dataset_label = metrics_csv.parent.parent.name

    def ratio(num: int, den: int) -> float:
        return float(num) / float(den) if den else float("nan")

    stats = {
        "flights_total": float(flights_total),
        "flights_eu_meta": float(flights_eu_meta),
        "flights_ratio": ratio(flights_eu_meta, flights_total),
        "points_total_all": float(points_total_all),
        "points_total_eu": float(points_total_eu),
        "points_total_ratio": ratio(points_total_eu, points_total_all),
        "points_valid_all": float(points_valid_all),
        "points_valid_eu": float(points_valid_eu),
        "points_valid_ratio": ratio(points_valid_eu, points_valid_all),
    }
    return dataset_label, stats


def _write_summary_csv(out_path: Path, dataset_label: str, stats: Dict[str, float]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "dataset",
                "flights_total",
                "flights_eu_meta",
                "flights_ratio",
                "points_total_all",
                "points_total_eu",
                "points_total_ratio",
                "points_valid_all",
                "points_valid_eu",
                "points_valid_ratio",
            ]
        )
        writer.writerow(
            [
                dataset_label,
                int(stats["flights_total"]),
                int(stats["flights_eu_meta"]),
                stats["flights_ratio"],
                int(stats["points_total_all"]),
                int(stats["points_total_eu"]),
                stats["points_total_ratio"],
                int(stats["points_valid_all"]),
                int(stats["points_valid_eu"]),
                stats["points_valid_ratio"],
            ]
        )


def _plot_summary(out_path: Path, dataset_label: str, stats: Dict[str, float]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), dpi=150)

    # Flights
    ax = axes[0]
    flights_all = stats["flights_total"]
    flights_eu = stats["flights_eu_meta"]
    ax.bar(["all", "eu_meta"], [flights_all, flights_eu], color=["#4C78A8", "#F58518"])
    ax.set_title("Flights (EU + meta)")
    ax.set_ylabel("count")
    ratio = stats["flights_ratio"]
    if np.isfinite(ratio):
        ax.text(
            1,
            flights_eu * 1.02,
            f"ratio={ratio:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4, axis="y")

    # Points
    ax = axes[1]
    labels = ["points_total", "points_valid"]
    all_vals = np.array(
        [stats["points_total_all"], stats["points_valid_all"]], dtype=float
    )
    eu_vals = np.array([stats["points_total_eu"], stats["points_valid_eu"]], dtype=float)
    x = np.arange(len(labels))
    width = 0.35
    ax.bar(x - width / 2, all_vals, width, label="all", color="#4C78A8")
    ax.bar(x + width / 2, eu_vals, width, label="eu_meta", color="#F58518")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_title("Points (EU + meta)")
    ax.set_ylabel("count")
    ax.legend()
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.4, axis="y")
    ratio_total = stats["points_total_ratio"]
    ratio_valid = stats["points_valid_ratio"]
    if np.isfinite(ratio_total):
        ax.text(
            x[0] + width / 2,
            eu_vals[0] * 1.02,
            f"{ratio_total:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    if np.isfinite(ratio_valid):
        ax.text(
            x[1] + width / 2,
            eu_vals[1] * 1.02,
            f"{ratio_valid:.3f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.suptitle(f"EU + Meta Summary ({dataset_label})")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize EU + meta flights metrics.")
    parser.add_argument(
        "--metrics-csv",
        type=Path,
        required=True,
        help="Path to flight_metrics.csv",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory (default: same as metrics csv directory)",
    )
    args = parser.parse_args()

    metrics_csv = args.metrics_csv
    if not metrics_csv.exists():
        raise FileNotFoundError(f"metrics csv not found: {metrics_csv}")

    dataset_label, stats = _load_metrics(metrics_csv)
    out_dir = args.out_dir or metrics_csv.parent
    out_csv = out_dir / "eu_meta_summary.csv"
    out_png = out_dir / "plots" / "eu_meta_summary.png"

    _write_summary_csv(out_csv, dataset_label, stats)
    _plot_summary(out_png, dataset_label, stats)
    print(f"[INFO] wrote {out_csv}")
    print(f"[INFO] wrote {out_png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
