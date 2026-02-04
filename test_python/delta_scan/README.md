# Delta Interval Scan

用途：扫描相邻点（dt=1s、同一 flight）差分的最小/最大间隔，用于估计 delta bin/max。

## 运行

```bash
conda activate opensky
python test_python/delta_scan/scan_delta_intervals.py \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --date-from 2022-01-01 \
  --date-to 2022-02-28
```

默认会扫描所有数值列（排除 `timestamp/flight_id/original_flight_id/icao24/segment_index`）。
默认会输出：
- `test_python/delta_scan/delta_interval_stats.csv`（min/max 统计）
- `test_python/delta_scan/delta_quantiles.csv`（|delta| 分位数）

如需指定列：

```bash
python test_python/delta_scan/scan_delta_intervals.py \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --columns latitude,longitude,altitude,groundspeed,track
```

输出 CSV 默认路径：`test_python/delta_scan/delta_interval_stats.csv`。

生成 |delta| 分布 PDF（多页，每列一页）：

```bash
python test_python/delta_scan/scan_delta_intervals.py \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --plot-pdf
```

注意：`--workers > 1` 时分位数/可视化使用**近似抽样**（每进程抽样后合并），速度更快但为近似结果。

一键脚本：

```bash
bash test_python/delta_scan/run_delta_scan.sh \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --date-from 2022-01-01 \
  --date-to 2022-02-28 \
  --plot-pdf
```
