#!/usr/bin/env python3
"""
多进程检查 opensky_2024_PRC_dataset/rawtrajectories 关键字段的缺失情况。

默认检查 timestamp、latitude、longitude、altitude 四个字段，任何一个字段存在缺失值时退出码为 1。
"""

from __future__ import annotations

import argparse
import multiprocessing as mp
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

# 关键字段
COLUMNS: Tuple[str, ...] = ("timestamp", "latitude", "longitude", "altitude")


@dataclass
class FileCheckResult:
    filename: str
    rows: int
    missing: Dict[str, int]
    error: Optional[str] = None


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent.parent.parent
    default_dir = repo_root / "opensky_2024_PRC_dataset" / "rawtrajectories"

    parser = argparse.ArgumentParser(
        description="多进程检查 rawtrajectories 关键字段缺失情况",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=default_dir,
        help="待检查的 parquet 数据目录",
    )
    parser.add_argument(
        "--processes",
        type=int,
        default=None,
        help="进程数；默认为 CPU 核心数与文件数的较小值",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅检查前 N 个文件（用于快速验证）",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="仅输出汇总信息，隐藏逐文件结果",
    )
    return parser.parse_args()


def iter_files(data_dir: Path, limit: Optional[int]) -> List[Path]:
    files = sorted(p for p in data_dir.glob("*.parquet") if p.is_file())
    if not files:
        raise FileNotFoundError(f"目录 {data_dir} 中未找到 parquet 文件")
    if limit is not None:
        files = files[:limit]
    return files


def check_file(file_path: Path) -> FileCheckResult:
    try:
        df = pd.read_parquet(file_path, columns=list(COLUMNS))
    except Exception as exc:  # pragma: no cover
        return FileCheckResult(
            filename=file_path.name,
            rows=0,
            missing={col: 0 for col in COLUMNS},
            error=str(exc),
        )

    missing_series = df.isna().sum()
    missing_counts = {col: int(missing_series[col]) for col in COLUMNS}
    return FileCheckResult(
        filename=file_path.name,
        rows=len(df),
        missing=missing_counts,
    )


def run_checks(files: Iterable[Path], processes: int, quiet: bool) -> Tuple[Dict[str, int], int, List[FileCheckResult]]:
    totals = {col: 0 for col in COLUMNS}
    total_rows = 0
    results: List[FileCheckResult] = []

    with mp.Pool(processes=processes) as pool:
        for result in pool.imap_unordered(check_file, files):
            results.append(result)

    for result in results:
        if result.error:
            raise RuntimeError(f"读取 {result.filename} 时出错: {result.error}")

        total_rows += result.rows
        for col in COLUMNS:
            totals[col] += result.missing[col]

        if not quiet and any(result.missing.values()):
            missing_desc = ", ".join(f"{col}={result.missing[col]}" for col in COLUMNS if result.missing[col])
            print(f"[缺失告警] {result.filename}: {missing_desc}")

    return totals, total_rows, results


def main() -> None:
    args = parse_args()
    files = iter_files(args.data_dir, args.limit)

    processes = args.processes or min(mp.cpu_count(), len(files))
    print(f"待检查文件数: {len(files)}，使用进程数: {processes}")

    totals, total_rows, results = run_checks(files, processes, args.quiet)

    print("\n=== 汇总结果 ===")
    print(f"总行数: {total_rows:,}")
    for col in COLUMNS:
        print(f"{col} 缺失值: {totals[col]:,}")

    total_missing = sum(totals.values())
    if total_missing == 0:
        print("\n✅ 所有检查列均无缺失值")
    else:
        problematic = [
            r for r in results if any(r.missing[col] > 0 for col in COLUMNS)
        ]
        print(f"\n❌ 发现缺失值，涉及 {len(problematic)} 个文件")
        for r in problematic[:5]:
            missing_desc = ", ".join(f"{col}={r.missing[col]}" for col in COLUMNS if r.missing[col])
            print(f"  - {r.filename}: {missing_desc}")
        if len(problematic) > 5:
            print(f"  ... 其余 {len(problematic) - 5} 个文件略")
        raise SystemExit(1)


if __name__ == "__main__":
    mp.set_start_method("spawn", force=True)
    main()
