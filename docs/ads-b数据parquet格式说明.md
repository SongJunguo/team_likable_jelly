# ADS-B 数据 Parquet 格式说明（OpenSky PRC 2024 / Clean-Segment-Interpolate v6）

本说明面向本仓库内 OpenSky ADS‑B 轨迹数据（`.parquet`）的**字段含义、单位、以及本目录（`interpolated_clean__PCA_v6`）产物与上游目录的差异**，便于后续特征工程/建模/量化编码对齐口径。

---

## 1. 数据文件组织（按天分片）

- 数据以 **UTC 日期**分片：`<yyyy-mm-dd>.parquet` 或 `interpolated_<yyyy-mm-dd>.parquet`。
- 同一个 `original_flight_id`（= 原始航班 ID）**可能跨 UTC 零点**出现在相邻两个日文件中（这是数据集特性，而非本流程引入）。

本仓库相关目录（`opensky_2024_PRC_dataset/`）：

- `rawtrajectories/`：原始轨迹（官方提供日文件）。
- `filtered_clean__PCA_v6/`：过滤后轨迹（异常点置 NaN；不插值）。
- `segmented_clean__PCA_v6/`：按时间间隔切分后的 segment（去除关键列 NaN 的行）。
- `interpolated_clean__PCA_v6/`：对每个 segment **重建 1Hz 网格 + 平滑样条 + 限洞插值**后的最终轨迹（本目录）。
- `xue_processed_raw__v1/`：薛正烨方案对 `rawtrajectories/` 的按天处理产物（`xue_<date>.parquet`，仅保留 challenge_set 航班，并合并 `adep/ades/aircraft_type` 与机场经纬度）。

---

## 2. 字段与单位（通用规则）

### 2.1 轨迹基础字段（raw / filtered / segmented / interpolated 均存在）

| 字段 | 含义 | 单位 | 分辨率 |
|---|---|---|---|
| `timestamp` | 轨迹点时间戳（UTC） | `datetime64[ns, UTC]` | 1 s|
| `latitude` | 纬度 | °（十进制度） |  |
| `longitude` | 经度 | °（十进制度） | |
| `altitude` | ADS‑B 报告高度 | ft | 25 ft |
| `groundspeed` | 对地速度 | kt | 1 kt |
| `track` | 航迹角（地面航向） | °（十进制度） | 
| `vertical_rate` | 爬升/下降率 | ft/min | 16 ft/min |
| `u_component_of_wind` | 风 U 分量（向东为正） | m/s | |
| `v_component_of_wind` | 风 V 分量（向北为正） | m/s | |
| `temperature` | 环境温度 | K | |
| `specific_humidity` | 比湿 | kg/kg | |

注意: altitude 精度为 25ft。
主要巡航尖峰（1–2 月合并 Top）：37000/36000/38000/35000/39000/34000/40000/33000/32000/41000 ft，主间隔约 1000ft，并伴随 ±25ft 的次峰（如 36975/37000/37025）


### 2.2 标识字段（注意 `flight_id` 的语义会在切分后变化）

| 字段 | raw / filtered 语义 | segmented / interpolated 语义 |
|---|---|---|
| `flight_id` | 原始航班 ID | **segment ID**（由 `original_flight_id*10000 + segment_index` 构造） |
| `icao24` | 数据集提供的（混淆）ICAO24 地址；在该挑战数据中与原始 `flight_id` 相同 | 仍保留原值（因此在切分后通常满足 `icao24 == original_flight_id`） |

---

## 3. 分段（segmented）新增字段

`segmented_clean__PCA_v6/segmented_<date>.parquet` 在基础字段外新增：

| 字段 | 含义 | 单位/类型 |
|---|---|---|
| `original_flight_id` | 切分前的原始航班 ID | int64 |
| `segment_index` | segment 序号（单日内递增） | int32 |
| `flight_seg_info` | 便于追踪的 segment 描述串：`{original}_s{idx}_{t0}Z_{t1}` | string |

并且：

- `flight_id` 被重写为 segment ID：`flight_id = original_flight_id * 10000 + segment_index`。
- 切分前会丢弃关键列缺失的行：默认要求 `latitude/longitude/altitude` 非 NaN。

---

## 4. 插值（interpolated）新增字段（本目录重点）

`interpolated_clean__PCA_v6/interpolated_<date>.parquet` 在 segmented 的字段基础上，新增/派生：

| 字段 | 含义 | 单位 |
|---|---|---|
| `gsx` | 对地速度东向分量（x=east） | kt |
| `gsy` | 对地速度北向分量（y=north） | kt |
| `tasx` | 真空速东向分量（TAS x） | kt |
| `tasy` | 真空速北向分量（TAS y） | kt |
| `tas` | 真空速大小（`hypot(tasx, tasy)`） | kt |
| `wind` | 风速大小（`hypot(u_component_of_wind, v_component_of_wind)`） | m/s |
| `daltitude` | 由平滑高度曲线的一阶导得到的爬升率（更平滑） | ft/min |

同时插值过程会做：

- **1Hz 重建**：对每个 segment 用秒级时间网格 `reindex`（保持原观测点，缺失秒产生 NaN）。
- **track 解包**：先将 `track` 前后填充后做 `unwrap(period=360)` 得到中间列 `track_unwrapped`，再平滑；最终输出再转回 `track = track_unwrapped % 360`。
- **限洞插值**：对每个变量计算“缺口长度”，仅在缺口 `<= max_hole_size` 时才允许插值；大缺口保持 NaN（本流程通过先切分保证 segment 内时间连续，从而尽量达到 0 NaN）。

### 4.1 派生速度分量的计算口径

派生列定义（方向约定：x=东、y=北）：

- `gsx = groundspeed * sin(track)`，`gsy = groundspeed * cos(track)`
- `tasx = gsx - u_component_of_wind`，`tasy = gsy - v_component_of_wind`
- `tas = hypot(tasx, tasy)`
- `wind = hypot(u_component_of_wind, v_component_of_wind)`

实现时会先把角度/速度转换到 SI（rad、m/s）做计算，再转换回数据集常用单位；因此最终落盘的 `gsx/gsy/tasx/tasy/tas` 单位与 `groundspeed` 一致（kt），而 `wind` 保持 m/s。

### 4.2 `daltitude` 的定义

- 插值中对 `altitude` 生成平滑样条并取一阶导（单位：ft/s），再乘以 60 转为 ft/min：`daltitude = d(altitude)/dt * 60`。
- 该列与原始/平滑后的 `vertical_rate` 不是同一个量：前者来自高度曲线导数，通常更平滑、对噪声更鲁棒。

---

## 5. 本目录辅助统计文件说明

### 5.1 `quantization_stats.json`

该文件记录了基于本目录数据计算得到的**量化/差分统计**（用于把连续变量映射到离散整数或 token），包含：

- `_meta.physical_units`：统计时采用的物理单位（例如 `alt=m`、`spdx=m/s`）。
- `_meta.raw_units`：量化到整数时的“原始单位定义”（例如 `alt = meter/10` 表示以 0.1m 为 1 个整数单位）。
- `_meta.split_meta`：按天划分的 `train/val/test` 日期范围。
- `splits.*.step_1.attrs.*`：以 `max_delta=1` 为裁剪策略时的差分分布（绝对差分分位数、裁剪率等）。

注意：该文件描述的是**建模量化口径**（如 `alt/lat/lon/spdx/spdy/spdz`），不等同于 Parquet 原始字段单位；使用时应以其 `_meta` 中的单位声明为准。

### 5.2 `norm_stats_{train,val,test,all}.npz`

该组文件保存了 z-score 归一化统计（`method=zscore`），包含：

- `mean`：均值向量
- `std`：标准差向量
- `count`：统计样本数

向量维度为 6（与量化口径中的 6 个连续属性一致，顺序以生成脚本约定为准）。

---

## 6. 依据（本仓库可追溯来源）

- 单位口径（经纬高/速度/风/温度/时间戳）：`docs/数据清理流程.md`
- 比湿单位：`junguo_analysis_for_opensky2022/README.md`
- segment 字段与 `flight_id` 构造：`pipelines/clean_segment/split_single_day.py`
- 1Hz 重建、track unwrap、限洞插值、`daltitude` 生成：`pipelines/clean_segment/interpolate.py`
- `track_unwrapped -> track` 的回写：`pipelines/clean_segment/interpolate_single_day.py`
- 派生速度/风特征定义与单位换算：`tools/io/readers.py`

---

## 7. 薛正烨方案按天输出（`xue_processed_raw__v1/`）

该目录由 `pipelines/Xue_Zhengye_process/` 产出，文件命名：`xue_<yyyy-mm-dd>.parquet`。

字段（默认输出）：

| 字段 | 含义 | 单位 |
|---|---|---|
| `timestamp` | 轨迹点时间戳（UTC） | `datetime64[ns, UTC]` |
| `flight_id` | 原始航班 ID（与 raw 一致） | int64 |
| `latitude`,`longitude` | 经纬度 | ° |
| `altitude` | 高度 | ft |
| `track` | 航迹角 | ° |
| `TAS` | 合成真空速（由地速+风估计） | kt |
| `adep`,`ades` | 起降机场 ICAO | string |
| `aircraft_type` | 机型 | string |
| `adep_latitude_deg`,`adep_longitude_deg` | 起飞机场经纬度（来自 `airports_tz.parquet`） | ° |
| `ades_latitude_deg`,`ades_longitude_deg` | 到达机场经纬度（来自 `airports_tz.parquet`） | ° |

---

## 8. 分布统计与可视化（直方图 / 经纬热力图）

仓库提供脚本 `analysis/plot_adsb_parquet_distributions.py` 用于统计字段分布并绘图，**只统计源数据中已落盘的列**（不会为缺失列做派生计算，因此 raw 目录里不会额外计算/绘制 `gsx/tas/wind` 等）。

### 8.1 输出内容

脚本会在 `reports/data_distributions/<label>/<date_from__date_to>/` 下输出：

- `hist_counts.csv`：所有字段（含 delta_* 派生字段）的 1D 直方图计数（长表；包含 count=0 的 bin，便于观察尖峰/间隔）
- `hist_meta.json`：直方图配置（bin 宽度、起点、bins 数）与元数据 min/max
- `summary.csv`：每列的 valid/missing/mean/std 等汇总
- `delta_summary.csv`：delta 直方图的 pairs/mean/std 等汇总（仅当开启 delta-hist 且数据中存在 `flight_id/timestamp` 时输出）
- `hist_y_linear/hist_<col>.png`：每列 1D 直方图（y 轴线性）
- `hist_y_log/hist_<col>.png`：每列 1D 直方图（y 轴对数）
- `hist_<col>.png`：线性版（兼容旧路径；通常为指向 `hist_y_linear/` 的链接）
- `heatmap_lat_lon.png`：`latitude/longitude` 2D 热力图（点密度）
- `heatmap_lat_lon_mean_altitude.png`：经纬-平均高度热力图（若存在 `altitude` 且未禁用）

### 8.2 默认 bin / 网格分辨率（可按需用 CLI 参数覆盖）

- `altitude`：25 ft
- `vertical_rate`：32 ft/min
- `track`：0.01°
- `u_component_of_wind` / `v_component_of_wind` / `wind`：0.05 m/s（仅当列存在时统计）
- `temperature`：0.05 K
- `latitude` / `longitude`（1D）：0.001°
- `latitude/longitude`（2D heatmap）：0.005°（若像素数过大，会自动增大 step 以满足 `--heatmap-max-cells` 上限）
- 直方图 y 轴：默认同时输出线性与对数（`--hist-yscales linear,log`）
- 直方图绘图默认 x 轴裁剪（不影响 `hist_counts.csv` 统计本身，可用 `--plot-xlim` 覆盖）：
  - `groundspeed`：[0, 700] kt
  - `altitude`：[-1000, 45000] ft
  - `vertical_rate` / `daltitude`：[-5000, 5000] ft/min
- delta（相邻点差值）直方图：默认开启（`--delta-hist`），只在同一 `flight_id` 内且 `timestamp` 差值**严格为 1 秒**的相邻点上计算（可用 `--delta-required-dt-seconds` 覆盖）

### 8.3 常用命令示例

建议在数据处理环境中运行：

```bash
conda activate opensky
```

统计 raw（建议先跑一天做 sanity check）：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-01-01
```

统计插值目录（会自动统计已落盘的 `gsx/gsy/tasx/tasy/tas/wind` 等列）：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/interpolated_clean__PCA_v6 \
  --date-from 2022-01-01 --date-to 2022-01-01
```

热力图范围控制（默认 `--heatmap-range-mode full` 使用数据 min/max；如只看中国附近可用 `bbox`；如希望超大时自动回退可用 `auto`。另外若像素数过大，脚本会自动增大 step 以满足 `--heatmap-max-cells` 上限，默认 16,000,000）：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-01-01 \
  --heatmap-range-mode full
```

仅输出线性 y 轴直方图，且把 `vertical_rate` 绘图范围收紧到 [-6000,6000]：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-01-01 \
  --hist-yscales linear \
  --plot-xlim vertical_rate:-6000:6000
```

只为 `altitude` 临时尝试更细的 bin（例如 1 ft），避免修改默认配置：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-01-01 \
  --bin-width altitude:1
```

只为 `vertical_rate` 临时尝试更细的 bin（例如 1 ft/min）：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-01-01 \
  --bin-width vertical_rate:1
```

关闭 delta 直方图（只输出原始列的分布）：

```bash
python analysis/plot_adsb_parquet_distributions.py \
  --data-dir opensky_2024_PRC_dataset/rawtrajectories \
  --date-from 2022-01-01 --date-to 2022-01-01 \
  --no-delta-hist
```
