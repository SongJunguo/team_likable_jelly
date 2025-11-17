#!/usr/bin/env python3
"""根据跳变检测报告删除插值结果中的异常航迹."""

from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = REPO_ROOT / "reports/quality_check_clean__PCA_v4_manual/jump_detection/jump_events_all.csv"
DEFAULT_DATA_DIR = REPO_ROOT / "opensky_2024_PRC_dataset/interpolated_clean__PCA_v4"


@dataclass
class TaskResult:
    day_file: str
    total_rows: int
    removed_rows: int
    duration: float
    status: str
    message: str = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="读取 jump_events_all.csv 中的 flight_id 列表, 并从 interpolated parquet 中删除对应航迹"
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=Path,
        default=DEFAULT_CSV,
        help=f"跳变报告路径 (默认: {DEFAULT_CSV})",
    )
    parser.add_argument(
        "--data-dir",
        dest="data_dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"插值后轨迹目录 (默认: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--processes",
        dest="processes",
        type=int,
        default=min(32, os.cpu_count() or 1),
        help="并行进程数 (默认: min(32, CPU核数))",
    )
    parser.add_argument(
        "--limit",
        dest="limit",
        type=int,
        default=0,
        help="仅处理前 N 个匹配文件 (调试用)",
    )
    parser.add_argument(
        "--day-file",
        dest="day_files",
        action="append",
        default=None,
        help="只处理指定的 parquet 文件名 (可重复传参)",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="仅统计将要删除的行数, 不写回",
    )
    parser.add_argument(
        "--verbose",
        dest="verbose",
        action="store_true",
        help="打印更详细的进度日志",
    )
    return parser.parse_args()


def load_jump_events(csv_path: Path, day_filter: Iterable[str] | None) -> Dict[str, List[int]]:
    if not csv_path.exists():
        raise FileNotFoundError(f"找不到跳变报告: {csv_path}")

    df = pd.read_csv(csv_path, usecols=["day_file", "flight_id"])
    df = df.dropna(subset=["day_file", "flight_id"])
    df["day_file"] = df["day_file"].astype(str).str.strip()
    df = df[df["day_file"] != ""]
    df["flight_id"] = df["flight_id"].astype("Int64")

    selected = set(day_filter) if day_filter else None
    mapping: Dict[str, List[int]] = {}
    for row in df.itertuples(index=False):
        day_file = row.day_file
        if selected and day_file not in selected:
            continue
        fid_val = int(row.flight_id)
        mapping.setdefault(day_file, []).append(fid_val)
    return mapping


def _cast_value_array(flight_column: pa.ChunkedArray, flight_ids: Sequence[int]) -> Tuple[pa.ChunkedArray, pa.Array]:
    """返回 (数据列, 目标取值数组), 如类型不兼容则退化到 string."""
    column = flight_column
    try:
        value_arr = pa.array(flight_ids, type=column.type)
        return column, value_arr
    except pa.ArrowInvalid:
        string_col = pc.cast(column, pa.string())
        value_arr = pa.array([str(fid) for fid in flight_ids], type=pa.string())
        return string_col, value_arr


def process_single_file(
    data_dir: Path,
    day_file: str,
    flight_ids: Sequence[int],
    dry_run: bool = False,
) -> TaskResult:
    start = time.time()
    file_path = data_dir / day_file
    if not file_path.exists():
        return TaskResult(day_file, 0, 0, 0.0, "missing", f"文件不存在: {file_path}")

    table = pq.read_table(file_path)
    if "flight_id" not in table.schema.names:
        return TaskResult(day_file, table.num_rows, 0, time.time() - start, "error", "缺少 flight_id 列")

    column = table.column("flight_id")
    unique_fids = sorted(set(flight_ids))
    column_for_match, value_arr = _cast_value_array(column, unique_fids)
    mask = pc.is_in(column_for_match, value_set=value_arr, skip_nulls=True)
    keep_mask = pc.invert(mask)
    filtered = table.filter(keep_mask)
    removed = table.num_rows - filtered.num_rows

    if removed == 0:
        return TaskResult(day_file, table.num_rows, 0, time.time() - start, "skip", "无匹配航迹")

    duration = time.time() - start
    if dry_run:
        return TaskResult(day_file, table.num_rows, removed, duration, "dry-run", "仅统计, 未写回")

    tmp_path = file_path.with_suffix(file_path.suffix + f".tmp_{uuid.uuid4().hex}")
    try:
        pq.write_table(filtered, tmp_path)
        os.replace(tmp_path, file_path)
    except Exception as exc:  # noqa: BLE001
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return TaskResult(
        day_file,
        table.num_rows,
        removed,
        duration,
        "updated",
        f"写回 {file_path}",
    )


def _worker(payload: Tuple[str, Sequence[int], str, bool]) -> TaskResult:
    day_file, flight_ids, data_dir_str, dry_run = payload
    return process_single_file(Path(data_dir_str), day_file, flight_ids, dry_run)


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir.resolve()
    csv_path = args.csv_path.resolve()

    if not data_dir.is_dir():
        print(f"❌ 数据目录不存在: {data_dir}")
        return 1

    files_map = load_jump_events(csv_path, args.day_files)
    if not files_map:
        print("⚠️ 跳变报告中没有匹配的 day_file / flight_id 记录，直接退出")
        return 0

    tasks = []
    missing_files: List[str] = []
    for day_file, flight_ids in sorted(files_map.items()):
        if not flight_ids:
            continue
        if not (data_dir / day_file).exists():
            missing_files.append(day_file)
            continue
        tasks.append((day_file, tuple(flight_ids), str(data_dir), args.dry_run))

    if args.limit > 0:
        tasks = tasks[: args.limit]

    if not tasks:
        print("⚠️ 没有需要处理的文件 (可能都不存在于 data_dir)")
        if missing_files:
            print("缺失的 parquet:")
            for day_file in missing_files[:20]:
                print(f"  - {day_file}")
        return 0

    worker_count = max(1, args.processes)
    print(
        f"==> 将在 {data_dir} 中处理 {len(tasks)} 个文件，删除 jump_events_all 中列出的航迹；"
        f" 进程数={worker_count}, dry_run={args.dry_run}"
    )

    total_rows = 0
    total_removed = 0
    changed_files = 0
    errors: List[str] = []

    def handle_result(result: TaskResult) -> None:
        nonlocal total_rows, total_removed, changed_files
        total_rows += result.total_rows
        total_removed += result.removed_rows
        if result.status == "updated":
            changed_files += 1
        if args.verbose or result.removed_rows > 0:
            print(
                f"[{result.status}] {result.day_file}: 删除 {result.removed_rows} / {result.total_rows} 行, "
                f"耗时 {result.duration:.2f}s - {result.message}"
            )
        elif result.status not in {"skip", "dry-run"}:
            print(f"[{result.status}] {result.day_file}: {result.message}")

    if worker_count == 1:
        for payload in tasks:
            try:
                handle_result(_worker(payload))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{payload[0]}: {exc}")
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(_worker, payload): payload[0] for payload in tasks}
            for future in as_completed(futures):
                day_file = futures[future]
                try:
                    handle_result(future.result())
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{day_file}: {exc}")

    print(
        f"==> 完成: {len(tasks)} 个文件, {changed_files} 个文件写回, 删除 {total_removed} / {total_rows} 行"
    )
    if missing_files:
        print(f"⚠️ 跳过 {len(missing_files)} 个报告中存在但目录缺失的文件 (前20个):")
        for name in missing_files[:20]:
            print(f"  - {name}")
    if errors:
        print("❌ 以下文件处理失败:")
        for msg in errors:
            print(f"  - {msg}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
