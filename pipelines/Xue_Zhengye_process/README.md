# 薛正烨轨迹处理方案（rawtrajectories 按天版）

本目录是从 `legacy/薛正烨的处理方案/` 迁移出的**独立可运行**版本，用于在本仓库数据结构下处理 `opensky_2024_PRC_dataset/rawtrajectories/` 按天 Parquet。

## 输入

- 轨迹：`opensky_2024_PRC_dataset/rawtrajectories/<date>.parquet`
- 航班元数据（仅 challenge_set）：`opensky_2024_PRC_dataset/flights/challenge_set.parquet`
- 机场信息：`opensky_2024_PRC_dataset/airports_tz.parquet`（用于补充 `adep/ades` 的经纬度）

## 输出

- 按天落盘：`opensky_2024_PRC_dataset/xue_processed_raw__v1/xue_<date>.parquet`
- 字段（默认）：`timestamp, flight_id, latitude, longitude, altitude, TAS, track, adep, ades, aircraft_type, adep_latitude_deg, adep_longitude_deg, ades_latitude_deg, ades_longitude_deg`

## 运行

推荐使用一键脚本（默认并发 14；优先激活 `data`，失败回退 `opensky`）：

```bash
bash pipelines/Xue_Zhengye_process/run_xue_process_raw.sh --from 2022-01-01 --to 2022-01-31
```

测试小样本（只跑 1 天、只处理前 10 条航迹）：

```bash
bash pipelines/Xue_Zhengye_process/run_xue_process_raw.sh --from 2022-01-01 --to 2022-01-01 --limit-flights 10
```

