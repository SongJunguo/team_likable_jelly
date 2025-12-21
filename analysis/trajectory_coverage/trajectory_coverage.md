# 航迹完整率与大圆吻合度分析

本说明对应脚本：`analysis/trajectory_coverage/coverage_metrics.py`。

## 1. 功能概述

给定轨迹点与起降机场，计算：
- 大圆（great-circle）吻合度：每点到大圆的横向偏差（cross-track error）统计与比例
- 地理覆盖率：沿大圆路径的覆盖缺口与覆盖率
- 仅以 `flight_id` 关联机场信息（不依赖数据集自身是否包含 `adep/ades`）

## 2. 数据来源与关联

- 航班信息：`opensky_2024_PRC_dataset/flights/challenge_set.parquet`
  - 通过 `flight_id -> adep/ades` 关联机场
- 机场信息：`opensky_2024_PRC_dataset/airports_tz.parquet`
  - 通过 `icao_code` 获取机场经纬度与 `continent`
- 数据集轨迹点可选：
  - `opensky_2024_PRC_dataset/rawtrajectories`
  - `opensky_2024_PRC_dataset/interpolated_clean__PCA_v6`
  - `opensky_2024_PRC_dataset/xue_processed_raw__v1`

欧洲判定规则：`continent == 'EU'` 且起降机场都满足。

## 3. 指标定义

### 3.1 大圆吻合度（cross‑track error）

对每个轨迹点计算其到大圆航线的横向偏差（km），输出：
- `xt_mean_km` / `xt_std_km` / `xt_median_km` / `xt_p95_km`
- `ratio_xt_le_20km` / `ratio_xt_le_30km`：偏差不超过阈值的点比例

### 3.2 地理覆盖率

将点投影到大圆路径的沿程距离 `s`（0~L），排序后计算相邻点间隔：
- gap 阈值：`max(50km, 0.05 * L)`
- 若 `gap > threshold`，视为覆盖缺口
- 覆盖率：`coverage_ratio = 1 - (sum(gap_km) / L)`
- 最大缺口：`max_gap_km`

## 4. 输出文件

输出目录：`reports/trajectory_coverage/<label>/<date_from__date_to>/`

- `flight_metrics.csv`：逐航班指标
- `summary.csv`：整体与欧洲内起降汇总
- `plots/coverage_ratio_hist.png`：覆盖率直方图
- `plots/coverage_ratio_cdf.png`：覆盖率 CDF
- `plots/max_gap_km_hist.png`：最大缺口分布
- `plots/ratio_xt_hist.png`：大圆吻合度比例分布
- `plots/coverage_vs_distance_hexbin.png`：覆盖率 vs 航程
- `plots/sample_flights/*.png`：样例航迹 vs 大圆
- `meta.json`：运行参数记录

## 5. 常用命令

建议在数据处理环境中运行：

```bash
conda activate opensky
```

统计 `rawtrajectories`（示例：2022-01-01 到 2022-02-28）：

```bash
python analysis/trajectory_coverage/coverage_metrics.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-02-28
```

统计 `interpolated_clean__PCA_v6`：

```bash
python analysis/trajectory_coverage/coverage_metrics.py \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean__PCA_v6 \
  --date-from 2022-01-01 --date-to 2022-02-28
```

默认会优先使用 `original_flight_id` 作为分组 id（如果列存在），否则使用 `flight_id`。

统计 `xue_processed_raw__v1`：

```bash
python analysis/trajectory_coverage/coverage_metrics.py \
  --data-dir opensky_2024_PRC_dataset/xue_processed_raw__v1 \
  --date-from 2022-01-01 --date-to 2022-02-28
```

只输出指标 CSV（不画图）：

```bash
python analysis/trajectory_coverage/coverage_metrics.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-02-28 \
  --no-plots
```

## 6. 欧洲+Meta 汇总（轨迹数与点数）

基于 `flight_metrics.csv` 汇总“欧洲且有 meta 信息”的轨迹数与轨迹点数，并输出 CSV + 图：

```bash
python analysis/trajectory_coverage/summarize_eu_meta.py \
  --metrics-csv reports/trajectory_coverage/rawtrajectories/2022-01-01__2022-02-28/flight_metrics.csv
```

输出：
- `eu_meta_summary.csv`
- `plots/eu_meta_summary.png`

## 7. 备注

- 计算假设 `flight_id` 在每天分片中唯一（已抽样验证相邻两天无重叠）。
- 若机场经纬度缺失，则该航班的覆盖率与大圆吻合度指标为空值。
