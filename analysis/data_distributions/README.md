# Data Distributions

This folder contains scripts for computing ADS-B parquet field distributions and plots.

## Files
- plot_adsb_parquet_distributions.py: compute histogram counts and plots using columns present in source files.
- run_distributions.sh: wrapper to run the python script with an explicit --data-dir.

## Environment
- conda activate opensky

## Inputs
- Example data dirs:
  - opensky_2024_PRC_dataset/rawtrajectories (365 parquet files)
  - opensky_2024_PRC_dataset/xue_processed_eu_v1

## Outputs
- Default out root: reports/data_distributions
- Layout: reports/data_distributions/<label>/<date_from__date_to>/
- 关键文件：
  - `hist_meta.json`：完整配置与生效参数（含 `xlims_effective`、`delta_config_effective`）
  - `summary.csv`：原始列统计
  - `delta_summary.csv`：delta 统计（含 `out_of_range_ratio`、`p99/p99.9`、`recommended_delta_max`）
  - `delta_recommendations.csv`：按截断率排序的 delta 阈值建议
  - `hist_counts.csv`：全部直方图计数

## One-Click Mode Switch
- `analysis/data_distributions/run_distributions.sh` 顶部可配置：
  - `INTERVAL_MODE_DEFAULT="1s"` 或 `INTERVAL_MODE_DEFAULT="20s"`
  - `DELTA_DIFF_MODE_DEFAULT="signed"`：默认输出带符号 delta 图（可改为 `abs`）
  - `AUTO_LABEL_WITH_MODE="true"`：自动给 label 增加 `mode1s/mode20s` 后缀，避免覆盖
  - `AUTO_20S_PLOT_XLIM="true"`：20s 模式自动设置保守 xlim（signed 默认会使用对称区间）
- 设置好后可直接一键运行：
  - `bash analysis/data_distributions/run_distributions.sh`
- 也支持临时覆盖模式（不改文件）：
  - `INTERVAL_MODE=1s bash analysis/data_distributions/run_distributions.sh`
  - `INTERVAL_MODE=20s bash analysis/data_distributions/run_distributions.sh`

## Notes
- Heatmap background prefers 10m data: analysis/data_distributions/ne_10m_admin_0_countries.zip
  or analysis/data_distributions/ne_10m_admin_0_countries/ne_10m_admin_0_countries.shp.
- If missing, it falls back to 110m local data, then geopandas naturalearth_lowres, then a built-in simplified outline.
- Disable background with --heatmap-background none; adjust opacity with --heatmap-background-alpha.
- Country labels are enabled by default; disable with --no-heatmap-country-labels (requires vector data).
- Delta 直方图默认使用绝对差值（非负）；使用 --delta-diff-mode signed 可保留正负差值。
- 注意：Python 脚本默认 `abs`，但 `run_distributions.sh` 默认会传 `--delta-diff-mode signed`。
- Delta 默认对所有数值列统计（排除 timestamp/flight_id/original_flight_id/icao24/segment_index）。
- 若显式指定 --delta-columns（含 all），需要为每个列提供 --delta-bin-width 与 --delta-max。
- 若默认列中缺少 bin/max 配置，则该列会被自动跳过。
- 可使用 `--sample-step-seconds` 开启时间抽样（默认 `1` 不抽样；例如 `20` 表示保留 `timestamp` 落在 20 秒网格上的点）。
- 当开启时间抽样且 `--delta-required-dt-seconds` 保持默认 `1` 时，会自动使用与抽样步长相同的 delta dt，避免 delta 配对为空。
- `run_distributions.sh` 的 20s 模式会自动注入一组保守 delta 参数（减少 out_of_range）及可选的 delta 绘图 xlim。
- `run_distributions.sh` 会对 `--delta-max` 与 `--plot-xlim` 按列去重（同列后出现的值覆盖先前值），并在日志打印最终生效配置。
- Python 脚本会输出 delta 截断率与分位统计（P99/P99.9、|delta| 的 P99/P99.9）以及建议阈值，便于回调 `--delta-max`。
- 1D 直方图 PNG 会按类别输出到子目录：
- `motion/hist_y_linear/` 与 `motion/hist_y_log/`
- `weather/hist_y_linear/` 与 `weather/hist_y_log/`
- delta 列直方图命名为 `delta_hist_<src>.png`（例如 `delta_hist_latitude.png`）。

## Examples
python analysis/data_distributions/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 \
  --date-to 2022-02-28

bash analysis/data_distributions/run_distributions.sh \
  --data-dir opensky_2024_PRC_dataset/xue_processed_eu_v1 \
  --filter eu_meta \
  --date-from 2022-01-01 \
  --date-to 2022-02-28

Signed delta example:
python analysis/data_distributions/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 \
  --date-to 2022-01-01 \
  --delta-diff-mode signed

20 秒抽样示例（建议加 label 避免覆盖历史结果）：
bash analysis/data_distributions/run_distributions.sh \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --filter eu_meta \
  --date-from 2022-01-01 \
  --date-to 2022-02-28 \
  --label interpolated_clean_eu_v5_eu_meta_sample20 \
  --sample-step-seconds 20
