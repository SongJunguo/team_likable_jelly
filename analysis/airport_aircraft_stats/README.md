# 机场/机型频率统计

本目录用于统计航班元数据中的热门机场与机型，并输出频率表格与 Top-N 直方图。

## 数据来源

默认仅使用：

- `opensky_2024_PRC_dataset/flights/challenge_set.parquet`

可选追加：

- `opensky_2024_PRC_dataset/flights/submission_set.parquet`
- `opensky_2024_PRC_dataset/flights/final_submission_set.parquet`

合并后按 `flight_id` 去重。

## 输出

默认输出目录：`reports/airport_aircraft_stats/`

- `airports_combined_counts.csv`（adep+ades 合并）
- `airports_adep_counts.csv`
- `airports_ades_counts.csv`
- `aircraft_type_counts.csv`
- `airports_combined_topN.png`
- `airports_adep_topN.png`
- `airports_ades_topN.png`
- `aircraft_type_topN.png`

## 用法

默认（仅 challenge_set）：

```bash
python analysis/airport_aircraft_stats/compute_meta_stats.py
```

追加 submission/final：

```bash
python analysis/airport_aircraft_stats/compute_meta_stats.py --include-submission --include-final
```

设置 Top-N 与输出目录：

```bash
python analysis/airport_aircraft_stats/compute_meta_stats.py --top-n 30 --out-dir reports/airport_aircraft_stats
```
