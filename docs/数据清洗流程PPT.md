---
marp: true
theme: default
paginate: true
size: 16:9
style: |
  section {
    font-family: 'Microsoft YaHei', 'SimHei', sans-serif;
  }
  table {
    font-size: 0.8em;
  }
  h1 {
    color: #2563eb;
  }
  h2 {
    color: #1e40af;
  }
---

<!-- _class: lead -->

# ADS-B 轨迹数据清洗流程
## OpenSky 2024 PRC Data Challenge

**日期范围**: 2022-01-01 ~ 2022-02-28 (59 天 / 59 文件)  
**版本**: clean_eu_v5

---

# 📌 目录

1. **范围与输入输出**
2. **流程总览与脚本入口**
3. **阶段0: 元数据筛选**
4. **阶段1: 过滤清洗**
5. **阶段2: 时间切分**
6. **阶段3: 插值平滑**
7. **质量检查与统计**
8. **数据量变化与缺失**
9. **分布特征与连续性检验**
10. **图表索引与输出结构**

---

# 🎯 范围与输入输出

- 原始数据: `opensky_2024_PRC_dataset/rawtrajectories`（2022-*.parquet，全年 365 天）
- 本次处理: 2022-01-01 ~ 2022-02-28，共 59 天文件
- 输出目录:
  - `opensky_2024_PRC_dataset/filtered_clean_eu_v5`
  - `opensky_2024_PRC_dataset/segmented_clean_eu_v5`
  - `opensky_2024_PRC_dataset/interpolated_clean_eu_v5`
- 报告目录:
  - `reports/quality_check_clean_eu_v5`
  - `reports/data_distributions/interpolated_clean_eu_v5_eu_meta/2022-01-01__2022-02-28`

---

# 🔄 流程总览

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  原始数据    │───▶│  阶段1:过滤  │───▶│  阶段2:切分  │───▶│  阶段3:插值  │
│  (Raw)      │    │  (Filter)   │    │  (Segment)  │    │  (Interp)   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
    6.896 亿            1.502 亿           0.410 亿            1.063 亿
    30.94 GB            6.41 GB           2.15 GB            14.24 GB
```

### ✅ 设计原则
- **先过滤再插值**，避免异常点传播
- **多检测器 + 投票机制**，降低误删风险
- **分段约束**确保插值可靠性

---

# 🧭 流程入口与阶段脚本

- 入口脚本: `pipelines/clean_segment/run_staged_pipeline.sh`
- 阶段脚本与输出:
  1. `01_filter_clean.sh` → `filtered_clean_eu_v5`
  2. `02_split_by_time.sh` → `segmented_clean_eu_v5`
  3. `03_interpolate_segments.sh` → `interpolated_clean_eu_v5`
  4. `04_quality_check.sh` → `reports/quality_check_clean_eu_v5`
  5. `run_raw_filtered_point_stats.sh` → raw vs filtered 统计
- 核心配置: `pipelines/clean_segment/config.sh`

---

# 🧩 阶段0: 元数据筛选（在过滤阶段执行）

- 仅保留欧洲航班: `META_EUROPE_ONLY=1`，continent=EU
- Top 机场/机型筛选: `META_TOP_AIRPORTS=64`，`META_TOP_AIRCRAFT=25`
- 元数据来源:
  - `opensky_2024_PRC_dataset/flights/challenge_set.parquet`
  - `opensky_2024_PRC_dataset/airports_tz.parquet`
- submission/final 集合默认关闭（`META_INCLUDE_SUBMISSION=0`，`META_INCLUDE_FINAL=0`）

---

# 📊 阶段1: 过滤清洗（clean_segment_interp）

过滤链路（`pipelines/clean_segment/filter_trajs.py`）:

```
FilterCstLatLon
→ FilterCstPosition
→ FilterCstSpeed
→ FilterEdgeOutlier
→ FilterMaxSpeedSkipNaNWithVoting
→ MyFilterDerivative (altitude)
→ FilterSpatialPCAOutlier (可选)
→ FilterMaxSpeedSkipNaN (post PCA)
→ FilterIsolated
```

- 读入后 **按 (flight_id, timestamp) 去重并排序**，保证时间序列严格递增

---

# 🎯 阶段1: 关键阈值

## 速度 / 高度检测
- `MAX_SPEED_MPS=600` (m/s)
- `MAX_ACCEL_MPS2=450` (m/s²)
- `VOTE_THRESHOLD=2`，`max_iterations=10`
- `ALT_DERIV_FIRST_FTPS=201`，`ALT_DERIV_SECOND_FTPS2=51`

## PCA 与后置 SkipNaN
- `ENABLE_SPATIAL_PCA=1`
- `PCA_MIN_POINTS=40`，`PCA_MAD_SCALE=6.0`，`PCA_WINDOW_SIZE=256`
- `ENABLE_SKIPNAN_POST_PCA=1`，`POST_PCA_SKIPNAN_MAX_ITER=30`

---

# 🧷 阶段1: 联动屏蔽与 NaN 流

- 过滤阶段允许 NaN 留存（为后续切分做准备）
- 当 **latitude 或 altitude 为 NaN** 时联动屏蔽:
  - `u_component_of_wind`
  - `v_component_of_wind`
  - `temperature`
- 进入切分前，对必需列执行 `dropna(REQ_COLS)`

---

# 🔪 阶段2: 时间切分（Segment）

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_DT` | 1200 秒 | 最大时间间隔 |
| `GAP_HANDLING` | drop | 有超大间隔则丢弃整条轨迹 |
| `MIN_POINTS` | 300 | 每段最小点数 |
| `MIN_DURATION` | 600 秒 | 每段最小时长 |
| `REQ_COLS` | 6 列 | 经纬高 + 速度/航向/升降率 |

必需列：
```
latitude, longitude, altitude, groundspeed, track, vertical_rate
```

---

# ✈️ 阶段2: 机场邻近过滤

- `AIRPORT_PROXIMITY_ENABLE=1`
- `AIRPORT_PROXIMITY_THRESHOLD_KM=10`
- 使用航班元数据与机场坐标判定起降点邻近性

---

# 📈 阶段3: 插值平滑（Interpolate）

- 每个 segment 独立插值
- **1 Hz 重采样**
- `SMOOTH=1e-2`（CSAPS 平滑系数）
- `MAX_HOLE_SIZE=1200` 秒

主要插值列：
- latitude, longitude, altitude
- groundspeed, track, vertical_rate
- u_component_of_wind, v_component_of_wind
- temperature, specific_humidity

衍生变量：
- tas, gsx/gsy, tasx/tasy, wind, daltitude

---

# ✅ 质量检查流程

1. **跳变检测**（`run_detect_jumps_all.sh`）
2. **NaN 检测**（`check_nan_values.py`）
3. **基础统计**（文件数 / 点数 / segment 数）
4. **raw vs filtered 点数统计**（`run_raw_filtered_point_stats.sh`）

---

# ✅ 质量检查结果

| 指标 | 值 |
|------|-----|
| 文件数 | 59 |
| 总数据点 | 106,339,053 |
| 总 segment 数 | 20,130 |
| 原始航班数 | 20,130 |
| 平均每航班 segment 数 | 1.00 |
| NaN 检测 | 0 缺失（59/59） |
| 跳变检测 | 1 航班 / 15 事件 |

跳变检测最大值（2022-01-13）：
- 最大速度: **2361.75 km/h**
- 最大距离: **0.656 km**

---

# 📉 数据量变化统计

| 阶段 | 数据点数 | 占原始比例 | 存储大小 |
|------|----------|-----------|---------|
| Raw | 689,634,097 | 100.000% | 30.94 GB |
| Filtered | 150,166,028 | 21.775% | 6.41 GB |
| Segmented | 40,965,669 | 5.940% | 2.15 GB |
| Interpolated | 106,339,053 | 15.420% | 14.24 GB |

**过滤阶段去除比例**: 78.225%

---

# 🧮 缺失值变化（关键列）

| 数据集 | 纬度缺失 | 经度缺失 | 高度缺失 | any_nan |
|--------|----------|----------|----------|---------|
| Raw | 0.000% | 0.000% | 0.000% | 0.000% |
| Filtered | 13.656% | 13.656% | 12.456% | 14.429% |
| Segmented | 0.000% | 0.000% | 0.000% | 0.000% |
| Interpolated | 0.000% | 0.000% | 0.000% | 0.000% |

---

# 🧪 PCA 检测统计（过滤阶段）

基于 `pca_flags.csv`：
- 覆盖航班数: **25,748**
- PCA 评估点数: **131,669,529**
- 标记异常点: **1,932,970**
- 标记比例: **约 1.47%**

> 统计仅覆盖满足 `PCA_MIN_POINTS` 的航班

---

# 📊 数据分布特征（位置/运动）

| 变量 | 均值 | 标准差 | 范围 | 单位 |
|------|------|--------|------|------|
| 纬度 | 49.996 | 5.219 | 36.392 ~ 67.314 | deg |
| 经度 | 10.483 | 8.464 | -9.475 ~ 29.511 | deg |
| 高度 | 26675.238 | 12457.216 | -5038.973 ~ 44099.850 | ft |
| 地速 | 375.399 | 94.916 | -203.665 ~ 953.244 | kt |
| 真空速 | 384.475 | 87.530 | -3.702 ~ 805.613 | kt |
| 航向 | 194.506 | 105.694 | 0.000 ~ 360.000 | deg |
| 垂直速率 | -31.703 | 3712.674 | -277823.950 ~ 467926.470 | ft/min |

---

# 📊 数据分布特征（气象）

| 变量 | 均值 | 标准差 | 范围 | 单位 |
|------|------|--------|------|------|
| 温度 | 232.213 | 22.907 | 199.898 ~ 294.971 | K |
| 风速 | 26.244 | 15.670 | -0.283 ~ 96.385 | m/s |
| U 风分量 | 15.182 | 16.838 | -56.807 ~ 91.877 | m/s |
| V 风分量 | -9.599 | 18.113 | -94.911 ~ 59.806 | m/s |
| 比湿 | 0.000573 | 0.001180 | -0.000127 ~ 0.010335 | kg/kg |

---

# 📈 时间连续性检验（Δt = 1s）

| 变量 | 均值变化 | 标准差 | out_of_range | 单位 |
|------|----------|--------|--------------|------|
| Δlatitude | 0.001082 | 0.000599 | 0 | deg |
| Δlongitude | 0.001806 | 0.000903 | 0 | deg |
| Δtrack | 0.075597 | 0.297565 | 105 | deg |
| Δvertical_rate | 12.170 | 53.752 | 38494 | ft/min |
| Δtemperature | 0.024061 | 0.037563 | 45 | K |
| Δwind_u | 0.015401 | 0.025447 | 0 | m/s |
| Δwind_v | 0.016753 | 0.026518 | 0 | m/s |

> out_of_range 为超出直方图区间的计数

---

# 🗺️ 空间覆盖范围

- **纬度范围**: 36.392°N ~ 67.314°N  
- **经度范围**: 9.475°W ~ 29.511°E
- 覆盖欧洲大陆及周边区域
- 元数据筛选: EU 航班 + Top 64 机场 + Top 25 机型

---

# 🖼️ 图表索引

数据路径：
```
reports/data_distributions/interpolated_clean_eu_v5_eu_meta/2022-01-01__2022-02-28/
```

主要图表：
- `heatmap_lat_lon.png`
- `heatmap_lat_lon_mean_altitude.png`
- `hist_y_linear/hist_*.png`
- `hist_y_log/hist_*.png`
- `delta_hist_*.png`

---

# 📂 输出文件结构

```
opensky_2024_PRC_dataset/
├── rawtrajectories/                    # 原始数据 (365 天)
├── filtered_clean_eu_v5/               # 过滤后 (59 天)
├── segmented_clean_eu_v5/              # 切分后 (59 天)
└── interpolated_clean_eu_v5/           # 最终数据 (59 天)

reports/
├── quality_check_clean_eu_v5/          # 质量报告
│   ├── basic_statistics.txt
│   ├── nan_check_report.txt
│   ├── raw_vs_filtered_point_stats_summary.txt
│   ├── pca_flags.csv
│   └── jump_detection/
└── data_distributions/                 # 分布统计 & 图表
    └── interpolated_clean_eu_v5_eu_meta/
```

---

# 🏗️ 运行方式

```bash
conda activate opensky
cd pipelines/clean_segment

# 分阶段运行（可调试）
bash run_staged_pipeline.sh --from 2022-01-01 --to 2022-02-28

# 可选参数示例
# --skip-filter / --skip-split / --skip-interp / --skip-quality / --skip-stats
# --limit N  (仅处理前 N 天)
```

---

<!-- _class: lead -->

# 🎯 总结

## 清洗流程特点

| 特点 | 说明 |
|------|------|
| ✅ 多层检测 | 速度/高度/空间异常协同过滤 |
| ✅ 投票机制 | 减少单指标误判 |
| ✅ 分段约束 | 只在高质量段内插值 |
| ✅ 全流程验证 | NaN + 跳变 + 统计全覆盖 |

### 最终成果
**20,130** 条高质量航班轨迹，**1.063 亿** 数据点，**1 Hz** 均匀采样

---

<!-- _class: lead -->

# 谢谢！

## 问题与讨论

---

# 附录: 关键配置（节选）

```bash
# === 元数据筛选 ===
META_EUROPE_ONLY=1
META_TOP_AIRPORTS=64
META_TOP_AIRCRAFT=25

# === 过滤参数 ===
MAX_SPEED_MPS=600.0
MAX_ACCEL_MPS2=450.0
ALT_DERIV_FIRST_FTPS=201
ALT_DERIV_SECOND_FTPS2=51
VOTE_THRESHOLD=2
ENABLE_SPATIAL_PCA=1
PCA_MIN_POINTS=40
PCA_MAD_SCALE=6.0
PCA_WINDOW_SIZE=256
ENABLE_SKIPNAN_POST_PCA=1
POST_PCA_SKIPNAN_MAX_ITER=30

# === 切分参数 ===
MAX_DT=1200
MIN_POINTS=300
MIN_DURATION=600
GAP_HANDLING=drop
AIRPORT_PROXIMITY_THRESHOLD_KM=10

# === 插值参数 ===
SMOOTH=1e-2
MAX_HOLE_SIZE=1200
```
