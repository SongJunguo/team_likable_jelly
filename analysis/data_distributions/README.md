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

## Notes
- Heatmap background prefers 10m data: analysis/data_distributions/ne_10m_admin_0_countries.zip
  or analysis/data_distributions/ne_10m_admin_0_countries/ne_10m_admin_0_countries.shp.
- If missing, it falls back to 110m local data, then geopandas naturalearth_lowres, then a built-in simplified outline.
- Disable background with --heatmap-background none; adjust opacity with --heatmap-background-alpha.
- Country labels are enabled by default; disable with --no-heatmap-country-labels (requires vector data).
- Delta 直方图默认使用绝对差值（非负）；使用 --delta-diff-mode signed 可保留正负差值。
- Delta 默认对所有数值列统计（排除 timestamp/flight_id/original_flight_id/icao24/segment_index）。
- 若显式指定 --delta-columns（含 all），需要为每个列提供 --delta-bin-width 与 --delta-max。
- 若默认列中缺少 bin/max 配置，则该列会被自动跳过。

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
