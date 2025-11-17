# 分析脚本：经纬未变但高度变化（多进程）

本目录提供针对 ADS-B 原始/清洗数据的并行统计脚本，用于量化如下事件的出现频率：

- 相邻采样对中，经纬度均未变化，但高度发生变化（可能源自字段不同步、量化/重复广播等）。
- 统计同时区分地面与空中阶段（以相邻两点 `groundspeed` 的平均值与阈值比较）。

脚本路径：`test_python/analysis/latlon_static_alt_change_stats.py`

## 环境
- 建议在数据处理环境运行：`conda activate opensky`
- 运行平台：Ubuntu 18.04 容器（无 sudo）；HDD 磁盘，注意合理并发（建议先小样本验证）。

## 用法
```
conda activate opensky
python test_python/analysis/latlon_static_alt_change_stats.py \
  --data_dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories \
  --out_csv  test_python/analysis/reports/latlon_static_alt_change_summary.csv \
  --n_workers 32 \
  --max_files 50 \
  --gs_threshold 60
```

参数说明：
- `--data_dir`：输入 Parquet 日文件目录。可选择 `rawtrajectories`（原始）或 `classic_filtered_trajectories`（已过滤未插值）。
- `--out_csv`：输出 CSV 路径；会额外生成 `*.per_file.csv` 的逐文件明细。
- `--n_workers`：并行进程数（默认 min(32, CPU)）。机械硬盘建议适当减小，避免 IO 抖动。
- `--max_files`：最多处理多少个文件（0 表示全部）。建议先用 10–50 做抽样验证，再全量跑。
- `--gs_threshold`：地面/空中分界的 `groundspeed` 阈值（单位 kt，默认 60）。

## 统计口径
- 与 `filterclassic.isvar` 一致：仅在相邻两端均非 NaN 时比较是否变化；否则该对样本不计入“有效对”。
- 事件定义：相邻对满足 `(~(lat 变化或 lon 变化) 且 alt 变化)`，并且四个经纬点与两个高度点均非 NaN。
- 地面/空中划分：取相邻两点 `groundspeed` 平均值与阈值比较，无法计算时不参与相位统计。

## 结果
- `*.csv`：汇总（总有效对、事件数与比例；地面/空中分开统计）。
- `*.per_file.csv`：逐文件明细，包含 OK/失败状态与各项计数。

## 备注
- 与主流程保持一致：读入后会按 `flight_id,timestamp` 去重并排序。
- 若数据集中 `groundspeed` 缺失，仍会输出总体统计，但无法区分地面/空中。
- 如需扩展到“按小时/机场/机型”的切片，可在当前脚本基础上添加分组维度。

## 单航班过滤 + Raw/Filter 出图

脚本：`pipelines/clean_segment/run_single_flight_plot.sh`。用于快速验证某条航班在指定策略（由 `pipelines/clean_segment/config.sh` 中的 `FILTER_STRATEGY` 决定，例如 `clean_segment_interp`）下的过滤效果，自动输出 Raw vs Filter PDF，同时打印过滤前/后有效点数、保留比例及按类别（位置 / 高度 / 速度）统计的“失效原因”，并默认保存过滤结果 Parquet。

### 基本用法

```
conda activate opensky
bash pipelines/clean_segment/run_single_flight_plot.sh 2022-01-01 248750611
```

- PDF 默认输出到 `reports/single_flight/plot_<date>_<flight>_<strategy>.pdf`。
- 通过 `OUT_DIR=/tmp/plots ...` 自定义 PDF 目录。
- 过滤后的单航班 Parquet 默认保存在同一个目录（文件名 `filtered_<date>_<flight>_<strategy>.parquet`），并附带四列速度/加速度指标：过滤后 `speed_mps`、`accel_mps2` 以及 Raw 侧 `raw_speed_mps`、`raw_accel_mps2`（全部使用与 `FilterMaxSpeedSkipNaNWithVoting` 相同的跨 NaN 水平速度推导，只依赖经纬度）。
- 自动生成速度/加速度图：`plot_<date>_<flight>_<strategy>_metrics.pdf`（单位 m/s 与 m/s²，使用与过滤器一致的水平速度/加速度计算逻辑；速度子图范围约定为 [-100, 1000]，加速度子图固定 ±500，便于聚焦常规航迹）。
- 终端会额外输出：
  - 原始 / 过滤后有效点数及比例（以 lat/lon/alt 同时非 NaN 为“有效”）。
  - “经纬约束”“高度约束”两类失效点数，基于被置 NaN 的经纬度/高度列做统计，用于快速判断主要删除来源（同一点可同时计入两类）。

### 自定义或关闭 Parquet 输出

```
OUT_PARQUET_DIR=reports/single_flight/parquet \
  bash pipelines/clean_segment/run_single_flight_plot.sh 2022-01-01 248750611
```

- `OUT_PARQUET_DIR` 用于覆盖默认目录（默认与 PDF 相同）。
- 若暂时不需要保存过滤结果，可在运行前设置 `SAVE_PARQUET=0`。
- `OUT_METRICS_PDF` 可自定义速度/加速度 PDF 路径；不设定时与轨迹 PDF 放在同一目录、文件名自动带 `_metrics`。
- 底层由 `filter_and_plot_single_flight.py --out-parquet/--metrics-pdf` 实现，也可直接调用该脚本并手动指定输出路径；Parquet 输出在原始列的基础上追加 Filter/Raw 两套 `*_speed_mps`、`*_accel_mps2`，速度/加速度计算严格遵循 `FilterMaxSpeedSkipNaNWithVoting` 的跨 NaN 水平逻辑，便于对照过滤策略。

> 若需测试不同过滤策略，请修改 `pipelines/clean_segment/config.sh` 中的 `FILTER_STRATEGY`（或在运行命令前临时导出新的 `FILTER_STRATEGY=xxx`）。脚本会自动加载并使用该配置，无需额外传参。
