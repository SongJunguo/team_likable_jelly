# raw vs filtered 轨迹数量对比报告

- 生成时间：2025-11-10 12:11 UTC
- 原始目录：/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories
- 过滤目录：/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v8
- 输出 CSV：`raw_vs_filtered_stats/raw_vs_filtered_counts.csv`

## 总体统计

| 指标 | Raw | Filtered | 差值 (Raw-Filtered) | Filtered/Raw |
| --- | ---: | ---: | ---: | ---: |
| 轨迹点数 | 291,997,964 | 291,997,964 | 0 | 1.0000 |
| 航班数量 | 45,460 | 45,460 | 0 | 1.0000 |
| 有效点数 (lat/lon/alt 均非 NaN) | 291,997,964 | 206,637,342 | 85,360,622 | 0.7077 |

- 配对文件数：24
- raw 目录缺失的文件：0
- filtered 目录缺失的文件：0
- 统计失败的文件：0
- 有效点定义：latitude/longitude/altitude 三列均非 NaN 的行

### 仅在 raw 目录存在的文件 (0)
- 无

### 仅在 filtered 目录存在的文件 (0)
- 无
