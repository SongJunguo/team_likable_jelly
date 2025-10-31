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
