#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""raw vs classic_filtered double-pass 轨迹统计对比工具。

使用方法：
  conda activate opensky
  python compare_raw_vs_filtered_counts.py \
    --raw-dir /workspace/.../rawtrajectories \
    --filtered-dir /workspace/.../classic_filtered_trajectories_doublepass_loop_v8

该脚本会多进程统计两个目录中每日 parquet 文件的总点数、有效点数（lat/lon/alt 均非 NaN）
和航班数，输出逐日 CSV 和总览 Markdown，方便衡量过滤前后数据的数量差异。
"""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import psutil
import pyarrow.parquet as pq

BASE_DIR = Path('/workspace/aircraft_trajectory/team_likable_jelly')
DEFAULT_RAW_DIR = BASE_DIR / 'opensky_2024_PRC_dataset/rawtrajectories'
DEFAULT_FILTERED_DIR = (
    BASE_DIR / 'opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v8'
)
DEFAULT_OUTPUT_DIR = (
    BASE_DIR / 'junguo_analysis_for_opensky2022/analysis_for_interpolation/raw_vs_filtered_stats'
)

VALID_COLS = ['latitude', 'longitude', 'altitude']


@dataclass
class PairTask:
    """单日文件配对信息"""

    file_name: str
    raw_path: Path
    filtered_path: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='统计 raw vs classic_filtered 数据量差异')
    parser.add_argument(
        '--raw-dir',
        type=Path,
        default=DEFAULT_RAW_DIR,
        help='原始轨迹目录 (默认: opensky_2024_PRC_dataset/rawtrajectories)',
    )
    parser.add_argument(
        '--filtered-dir',
        type=Path,
        default=DEFAULT_FILTERED_DIR,
        help='过滤后轨迹目录 (默认: classic_filtered_..._doublepass_loop_v8)',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help='输出目录 (默认: analysis_for_interpolation/raw_vs_filtered_stats)',
    )
    parser.add_argument('--max-workers', type=int, help='最大并行进程数 (默认自动推算)')
    parser.add_argument('--limit', type=int, help='仅处理前 N 个共有文件 (调试用途)')
    return parser.parse_args()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def list_parquet(directory: Path) -> Dict[str, Path]:
    files = {}
    for path in sorted(directory.glob('*.parquet')):
        files[path.name] = path
    return files


def suggest_workers(max_workers: int | None, job_count: int) -> int:
    if not job_count:
        return 0
    if max_workers:
        return max(1, min(max_workers, job_count))

    cpu_total = psutil.cpu_count(logical=True) or 1
    mem_gb = psutil.virtual_memory().total / (1024 ** 3)
    cpu_limit = max(1, int(cpu_total * 0.5))
    mem_limit = max(1, int(mem_gb // 5))  # 预估每进程 ~5GB
    auto_workers = max(1, min(cpu_limit, mem_limit, 48, job_count))
    return auto_workers


def read_file_stats(file_path: Path) -> Tuple[int, int, int]:
    """返回 (总行数, flight_id 数量, 有效点数)"""

    pq_file = pq.ParquetFile(file_path)
    total_points = int(pq_file.metadata.num_rows)

    columns = ['flight_id'] + VALID_COLS
    df = pd.read_parquet(file_path, columns=columns)

    missing_cols = [col for col in VALID_COLS if col not in df.columns]
    if missing_cols:
        raise ValueError(f'文件 {file_path.name} 缺少必要列: {missing_cols}')

    flights = int(df['flight_id'].dropna().nunique())
    valid_mask = (~df[VALID_COLS].isna()).all(axis=1)
    valid_points = int(valid_mask.sum())
    return total_points, flights, valid_points


def process_pair(task: PairTask) -> Dict[str, float]:
    try:
        raw_points, raw_flights, raw_valid = read_file_stats(task.raw_path)
        filtered_points, filtered_flights, filtered_valid = read_file_stats(task.filtered_path)

        return {
            'file': task.file_name,
            'raw_points': raw_points,
            'filtered_points': filtered_points,
            'points_diff': raw_points - filtered_points,
            'raw_flights': raw_flights,
            'filtered_flights': filtered_flights,
            'flights_diff': raw_flights - filtered_flights,
            'raw_valid_points': raw_valid,
            'filtered_valid_points': filtered_valid,
            'valid_points_diff': raw_valid - filtered_valid,
            'filtered_points_rate': filtered_points / raw_points if raw_points else 0.0,
            'filtered_flights_rate': filtered_flights / raw_flights if raw_flights else 0.0,
            'filtered_valid_points_rate': filtered_valid / raw_valid if raw_valid else 0.0,
            'error': '',
        }
    except Exception as exc:  # pragma: no cover - 仅在异常时触发
        return {
            'file': task.file_name,
            'raw_points': 0,
            'filtered_points': 0,
            'points_diff': 0,
            'raw_flights': 0,
            'filtered_flights': 0,
            'flights_diff': 0,
            'raw_valid_points': 0,
            'filtered_valid_points': 0,
            'valid_points_diff': 0,
            'filtered_points_rate': 0.0,
            'filtered_flights_rate': 0.0,
            'filtered_valid_points_rate': 0.0,
            'error': str(exc),
        }


def iter_tasks(raw_map: Dict[str, Path], filtered_map: Dict[str, Path], limit: int | None) -> List[PairTask]:
    common_files = sorted(set(raw_map) & set(filtered_map))
    if limit:
        common_files = common_files[:limit]
    return [PairTask(name, raw_map[name], filtered_map[name]) for name in common_files]


def run_tasks(tasks: List[PairTask], max_workers: int) -> Tuple[List[Dict[str, float]], List[Dict[str, float]]]:
    results: List[Dict[str, float]] = []
    errors: List[Dict[str, float]] = []

    if not tasks:
        return results, errors

    print(f'🔁 共有 {len(tasks)} 个配对文件，使用 {max_workers} 个进程统计...')
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(process_pair, task): task.file_name for task in tasks}
        for idx, future in enumerate(as_completed(future_map), 1):
            result = future.result()
            if result['error']:
                errors.append(result)
            else:
                results.append(result)

            if idx % 10 == 0 or idx == len(tasks):
                print(f'   进度 {idx}/{len(tasks)} ({idx / len(tasks) * 100:.1f}%)')

    return results, errors


def save_csv(results: List[Dict[str, float]], output_dir: Path) -> Path:
    df = pd.DataFrame(results).sort_values('file')
    csv_path = output_dir / 'raw_vs_filtered_counts.csv'
    df.to_csv(csv_path, index=False)
    return csv_path


def build_markdown(
    summary: Dict[str, float],
    csv_path: Path,
    raw_only: Iterable[str],
    filtered_only: Iterable[str],
    errors: List[Dict[str, float]],
    output_dir: Path,
) -> Path:
    md_path = output_dir / 'raw_vs_filtered_summary.md'
    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    lines: List[str] = []
    lines.append('# raw vs filtered 轨迹数量对比报告')
    lines.append('')
    lines.append(f'- 生成时间：{timestamp}')
    lines.append(f'- 原始目录：{summary["raw_dir"]}')
    lines.append(f'- 过滤目录：{summary["filtered_dir"]}')
    lines.append(f'- 输出 CSV：`{csv_path}`')
    lines.append('')
    lines.append('## 总体统计')
    lines.append('')
    lines.append('| 指标 | Raw | Filtered | 差值 (Raw-Filtered) | Filtered/Raw |')
    lines.append('| --- | ---: | ---: | ---: | ---: |')
    lines.append(
        f"| 轨迹点数 | {summary['raw_points_total']:,} | {summary['filtered_points_total']:,} | "
        f"{summary['points_diff_total']:,} | {summary['points_rate']:.4f} |"
    )
    lines.append(
        f"| 航班数量 | {summary['raw_flights_total']:,} | {summary['filtered_flights_total']:,} | "
        f"{summary['flights_diff_total']:,} | {summary['flights_rate']:.4f} |"
    )
    lines.append(
        f"| 有效点数 (lat/lon/alt 均非 NaN) | {summary['raw_valid_total']:,} | {summary['filtered_valid_total']:,} | "
        f"{summary['valid_diff_total']:,} | {summary['valid_rate']:.4f} |"
    )
    lines.append('')
    lines.append(f'- 配对文件数：{summary["paired_files"]}')
    lines.append(f'- raw 目录缺失的文件：{len(list(filtered_only))}')
    lines.append(f'- filtered 目录缺失的文件：{len(list(raw_only))}')
    lines.append(f'- 统计失败的文件：{len(errors)}')
    lines.append('- 有效点定义：latitude/longitude/altitude 三列均非 NaN 的行')
    lines.append('')

    def format_list(title: str, entries: Iterable[str]) -> None:
        entries = list(entries)
        lines.append(f'### {title} ({len(entries)})')
        if not entries:
            lines.append('- 无')
        else:
            for name in entries[:50]:
                lines.append(f'- {name}')
            if len(entries) > 50:
                lines.append(f'- ... 共 {len(entries)} 个')
        lines.append('')

    format_list('仅在 raw 目录存在的文件', raw_only)
    format_list('仅在 filtered 目录存在的文件', filtered_only)

    if errors:
        lines.append('### 统计失败的文件')
        for err in errors:
            lines.append(f"- {err['file']}: {err['error']}")
        lines.append('')

    md_path.write_text('\n'.join(lines), encoding='utf-8')
    return md_path


def summarize(results: List[Dict[str, float]], raw_dir: Path, filtered_dir: Path) -> Dict[str, float]:
    raw_points_total = sum(r['raw_points'] for r in results)
    filtered_points_total = sum(r['filtered_points'] for r in results)
    raw_flights_total = sum(r['raw_flights'] for r in results)
    filtered_flights_total = sum(r['filtered_flights'] for r in results)
    raw_valid_total = sum(r['raw_valid_points'] for r in results)
    filtered_valid_total = sum(r['filtered_valid_points'] for r in results)

    summary = {
        'raw_dir': str(raw_dir),
        'filtered_dir': str(filtered_dir),
        'paired_files': len(results),
        'raw_points_total': raw_points_total,
        'filtered_points_total': filtered_points_total,
        'points_diff_total': raw_points_total - filtered_points_total,
        'raw_flights_total': raw_flights_total,
        'filtered_flights_total': filtered_flights_total,
        'flights_diff_total': raw_flights_total - filtered_flights_total,
        'raw_valid_total': raw_valid_total,
        'filtered_valid_total': filtered_valid_total,
        'valid_diff_total': raw_valid_total - filtered_valid_total,
        'points_rate': (filtered_points_total / raw_points_total) if raw_points_total else 0,
        'flights_rate': (filtered_flights_total / raw_flights_total) if raw_flights_total else 0,
        'valid_rate': (filtered_valid_total / raw_valid_total) if raw_valid_total else 0,
    }
    return summary


def main() -> None:
    args = parse_args()

    if not args.raw_dir.exists():
        raise FileNotFoundError(f'原始目录不存在: {args.raw_dir}')
    if not args.filtered_dir.exists():
        raise FileNotFoundError(f'过滤目录不存在: {args.filtered_dir}')

    raw_map = list_parquet(args.raw_dir)
    filtered_map = list_parquet(args.filtered_dir)

    raw_only = sorted(set(raw_map) - set(filtered_map))
    filtered_only = sorted(set(filtered_map) - set(raw_map))
    tasks = iter_tasks(raw_map, filtered_map, args.limit)

    if not tasks:
        print('❌ 两个目录没有可配对的文件，请检查输入。')
        return

    ensure_dir(args.output_dir)
    max_workers = suggest_workers(args.max_workers, len(tasks))
    results, errors = run_tasks(tasks, max_workers)

    summary = summarize(results, args.raw_dir, args.filtered_dir)
    csv_path = save_csv(results, args.output_dir)
    md_path = build_markdown(summary, csv_path, raw_only, filtered_only, errors, args.output_dir)

    print('\n=== 总览 ===')
    print(f"配对文件: {summary['paired_files']}")
    print(f"总轨迹点: raw {summary['raw_points_total']:,} vs filtered {summary['filtered_points_total']:,} "
          f"(差 {summary['points_diff_total']:,}, rate {summary['points_rate']:.4f})")
    print(f"总航班数: raw {summary['raw_flights_total']:,} vs filtered {summary['filtered_flights_total']:,} "
          f"(差 {summary['flights_diff_total']:,}, rate {summary['flights_rate']:.4f})")
    print(f"有效点数: raw {summary['raw_valid_total']:,} vs filtered {summary['filtered_valid_total']:,} "
          f"(差 {summary['valid_diff_total']:,}, rate {summary['valid_rate']:.4f})")
    print(f'仅 raw 存在的文件: {len(raw_only)}, 仅 filtered 存在的文件: {len(filtered_only)}')
    print(f'统计失败文件: {len(errors)}')
    print(f'逐日 CSV: {csv_path}')
    print(f'Markdown 报告: {md_path}')


if __name__ == '__main__':
    main()
