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

机场统计 CSV 新增字段：

- `country`：国家全称（基于 ISO 3166-1 两字母码映射）
- `continent`：大洲全称（基于 continent 代码映射）

默认读取 `/usr/share/iso-codes/json/iso_3166-1.json` 作为国家全称映射；若文件缺失或条目不完整，会回退为国家两字母码或 `UNKNOWN`。

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

指定机场元数据与国家映射文件：

```bash
python analysis/airport_aircraft_stats/compute_meta_stats.py \
  --airports-path opensky_2024_PRC_dataset/airports_tz.parquet \
  --iso3166-path /usr/share/iso-codes/json/iso_3166-1.json
```
