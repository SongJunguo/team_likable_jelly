# 轨迹运动量对比（interpolated_clean_eu_v5）

目的：基于经纬度/高度/时间差反算地速、航向角、垂直速度，并与数据中原始字段进行对比，观察偏差与可能的迟滞。

## 计算口径

- 仅使用 **相邻点 dt==1s** 的样本对（可通过参数调整）。
- 地速与航向角：
  - 默认使用 `pyproj.Geod` (WGS84) 计算两点间测地距离与方位角。
  - 可切换为 `haversine`（近似球面）。
- 垂直速度：
  - `vrate = (alt[i] - alt[i-1]) / dt * 60`，单位 ft/min。
- 对齐方式：派生量对应 **当前点 i**（由 i-1 → i 计算），与 `groundspeed/track/vertical_rate` 同时刻对比。
- 航向角误差为环绕差：`(a - b + 180) % 360 - 180`（范围 [-180, 180]）。
- 迟滞 shift 定义：对比 `derived[t]` 与 `obs[t+shift]`（shift>0 表示观测量向后移动）。

## 输出

输出目录默认：`reports/spd_compare/`

- `summary_all.csv`：全局统计（count/bias/MAE/RMSE/min/max）
- `summary_filtered.csv`：过滤后统计（默认 `groundspeed>=30 kt` 且 `altitude>=1000 ft`）
- `summary_by_speed_bin.csv`：按地速区间统计
- `lag_best_shift.csv`：迟滞搜索（每个 shift 的 MAE，以及最佳 shift）
- `hist_speed_diff.csv` / `hist_track_diff.csv` / `hist_vrate_diff.csv` / `hist_vrate_diff_ms.csv`
- `hist_*.png`：直方图可视化（可关闭）
- `bin_hists/`：按地速分箱的直方图（每箱包含 `ft/min` 与 `m/s` 的 `vrate` 图和 CSV）
- `run_meta.json`：运行参数与统计元信息

分箱图标题说明：
- 标题中的分箱会同时显示 `kt` 与 `m/s`，例如：`speed bin 300-500 kt / 154.3-257.2 m/s`。

## 运行方式（建议在 opensky 环境）

```bash
conda activate opensky
python analysis/spd_compare/compare_interpolated_motion.py \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --date-from 2022-01-01 \
  --date-to 2022-01-31 \
  --geo-method pyproj \
  --processes 8
```

## 常用参数

- `--dt-seconds 1`：只使用 dt==1s
- `--lag-min -5 --lag-max 5`：迟滞搜索范围（秒）
- `--speed-diff-min/-max/-bin`：地速差直方图范围与 bin
- `--track-diff-min/-max/-bin`：航向角差直方图范围与 bin
- `--vrate-diff-min/-max/-bin`：垂直速度差直方图范围与 bin
- `--min-groundspeed`：过滤统计最低地速（kt）
- `--min-altitude`：过滤统计最低高度（ft）
- `--speed-bins`：按地速分箱边界（kt，逗号分隔）
- `--bin-hist-yscale`：分箱直方图 y 轴刻度（linear/log/both）
- `--no-plot`：不输出 PNG

## 备注

- 数据按天文件并行处理（多进程）。
- 若需要更高精度或不同航迹计算口径，可调整 `--geo-method` 或直方图参数。
- 2026-02-05：修复文件名日期解析正则。
- 2026-02-05：新增过滤统计与地速分箱统计。
- 2026-02-05：新增分箱直方图输出。
- 2026-02-05：`vrate_diff` 默认同时输出 `ft/min` 与 `m/s` 两套图和 CSV（`1 ft/min = 0.00508 m/s`）。
- 2026-02-05：分箱图标题改为同时显示 `kt` 与 `m/s`。
