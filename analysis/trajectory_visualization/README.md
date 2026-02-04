# Trajectory Visualization

用于可视化某个完整航班轨迹的所有数值列与相邻点差分，输出 PDF（每列一页，上图原始值，下图差分）。

## 运行

```bash
conda activate opensky
bash analysis/trajectory_visualization/run_trajectory_viz.sh \
  --flight-id 123456789 \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean_eu_v5 \
  --date-from 2022-01-01 \
  --date-to 2022-02-28
```

默认差分仅统计 dt=1 秒的相邻点，差分模式为 `signed`。可选参数：

```bash
bash analysis/trajectory_visualization/run_trajectory_viz.sh \
  --flight-id 123456789 \
  --delta-required-dt-seconds 1.0 \
  --delta-diff-mode signed \
  --columns latitude,longitude,altitude,groundspeed,track
```

输出默认路径：`reports/trajectory_visualization/flight_<id>_<range>.pdf`。
