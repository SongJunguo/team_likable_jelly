# raw vs filtered 轨迹数量对比工具

`compare_raw_vs_filtered_counts.py` 用于一次性统计 `rawtrajectories` 与
`classic_filtered_trajectories_doublepass_loop_v8`（或任意两套日粒度 parquet 目录）之间的轨迹点数、
有效点数（lat/lon/alt 均非 NaN）与航班总量的差异，支持多进程并行，默认输出逐日 CSV 与 Markdown 汇总，
方便追踪过滤前后数据损失情况，同时避免“行数未变但经纬高缺失”造成的误判。

## 环境要求

- 建议在 `conda activate opensky` 环境中运行，确保 `pandas`、`pyarrow`、`psutil` 可用。
- 运行脚本前确认两个目录均包含 `YYYY-MM-DD.parquet` 命名的日文件。

## 运行示例

```bash
conda activate opensky
cd /workspace/aircraft_trajectory/team_likable_jelly/junguo_analysis_for_opensky2022/analysis_for_interpolation
python compare_raw_vs_filtered_counts.py \
  --raw-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories \
  --filtered-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v8 \
  --output-dir raw_vs_filtered_stats \
  --limit 24
```

常用参数：

- `--max-workers`: 手动设置并行进程数，默认按 CPU/内存自动计算（约 4GB/进程，最多 48 个）。
- `--limit`: 仅处理前 N 个共有日期，便于调试。

## 输出内容

输出目录默认位于 `analysis_for_interpolation/raw_vs_filtered_stats/`，包含：

- `raw_vs_filtered_counts.csv`：逐日统计，列出 raw/filtered 的点数、航班数及差值、比例。
- `raw_vs_filtered_summary.md`：汇总报告，记录总量对比、缺失文件列表、运行配置等。

CSV 字段说明：

| 列名 | 描述 |
| --- | --- |
| `file` | 日期文件名，例如 `2022-01-01.parquet` |
| `raw_points`, `filtered_points` | 当日轨迹点总行数（Parquet metadata） |
| `points_diff` | `raw_points - filtered_points` |
| `raw_valid_points`, `filtered_valid_points` | 有效点（lat/lon/alt 全部非 NaN）的数量 |
| `valid_points_diff` | 有效点差值 |
| `raw_flights`, `filtered_flights` | 当日 `flight_id` 唯一数 |
| `flights_diff` | `raw_flights - filtered_flights` |
| `filtered_points_rate`, `filtered_valid_points_rate`, `filtered_flights_rate` | 过滤后相对 raw 的比例 |

## 工作流程概述

1. 枚举两个目录的日文件，按文件名匹配配对列表并记录缺失项。
2. 通过 `ProcessPoolExecutor` 并行处理，每个进程仅读取 `flight_id` 列并使用 Parquet metadata 获取总行数，减少 IO。
3. 汇总多日结果，计算总体差异与比例，输出 CSV + Markdown。

若需对其他版本的过滤结果进行对比，只需替换 `--filtered-dir`（或 `--raw-dir`）。
