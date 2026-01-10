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

**日期范围**: 2022-01-01 ~ 2022-02-28 (59天)

---

# 📌 目录

1. **数据格式概览** - Parquet格式与字段说明
2. **流程总览** - 三阶段清洗架构
3. **阶段1: 过滤清洗** - 异常点检测与删除
4. **阶段2: 时间切分** - 航段分割与筛选
5. **阶段3: 插值平滑** - 均匀采样生成
6. **数据量变化** - 各阶段统计指标
7. **最终数据质量** - 质量验证结果
8. **数据分布特征** - 关键变量统计

---

# � 数据格式概览

## Parquet 文件组织

| 属性 | 说明 |
|------|------|
| **文件格式** | Apache Parquet (列式存储) |
| **文件命名** | `interpolated_<yyyy-mm-dd>.parquet` |
| **分片方式** | 按 **UTC 日期** 分片 |
| **采样频率** | 原始: 不均匀 (~0.5-5s) → 最终: **1 Hz** |
| **时间戳精度** | `datetime64[ns, UTC]` |

### 数据规模 (59天)
- **文件数**: 59 个 Parquet 文件
- **总数据点**: 1.06 亿
- **总航班数**: 20,130
- **存储大小**: 14.24 GB

---

# 📋 基础字段说明 (1/2)

## 轨迹核心字段

| 字段 | 含义 | 单位 | 精度/分辨率 |
|------|------|------|-------------|
| `timestamp` | 轨迹点时间戳 (UTC) | datetime64[ns] | 1 秒 |
| `latitude` | 纬度 | ° (十进制度) | ~0.001° |
| `longitude` | 经度 | ° (十进制度) | ~0.001° |
| `altitude` | ADS-B 报告高度 | **ft** | 25 ft |
| `groundspeed` | 对地速度 | **kt** | 1 kt |
| `track` | 航迹角 (地面航向) | ° | 0.01° |
| `vertical_rate` | 爬升/下降率 | **ft/min** | 16 ft/min |

> **注意**: 高度 `altitude` 原始精度为 25 ft，主巡航高度层: 37000/36000/38000 ft

---

# 📋 基础字段说明 (2/2)

## 气象字段

| 字段 | 含义 | 单位 | 说明 |
|------|------|------|------|
| `u_component_of_wind` | 风 U 分量 | **m/s** | 向东为正 |
| `v_component_of_wind` | 风 V 分量 | **m/s** | 向北为正 |
| `temperature` | 环境温度 | **K** | 开尔文 |
| `specific_humidity` | 比湿 | **kg/kg** | 质量比 |

## 标识字段

| 字段 | 含义 | 类型 |
|------|------|------|
| `flight_id` | 航段 ID | int64 |
| `original_flight_id` | 原始航班 ID | int64 |
| `icao24` | ICAO24 地址 (混淆) | int64 |
| `segment_index` | 航段序号 | int32 |

---

# 🔢 插值后派生字段

## 速度分量与真空速

| 字段 | 含义 | 单位 | 计算公式 |
|------|------|------|----------|
| `gsx` | 对地速度东向分量 | kt | `groundspeed × sin(track)` |
| `gsy` | 对地速度北向分量 | kt | `groundspeed × cos(track)` |
| `tasx` | 真空速东向分量 | kt | `gsx - u_wind` |
| `tasy` | 真空速北向分量 | kt | `gsy - v_wind` |
| `tas` | 真空速大小 | kt | `√(tasx² + tasy²)` |
| `wind` | 风速大小 | m/s | `√(u² + v²)` |
| `daltitude` | 高度变化率 (平滑) | ft/min | 高度样条一阶导 × 60 |

> **方向约定**: x = 东, y = 北

---

# ⏱️ 采样率与时间处理

## 原始数据 vs 最终数据

| 属性 | 原始 (Raw) | 最终 (Interpolated) |
|------|-----------|---------------------|
| **采样频率** | 不均匀 (~0.5-5 秒) | **1 Hz** (均匀) |
| **时间间隔** | 可能存在大间隔 | 连续无间隔 |
| **缺失处理** | 存在 NaN | **0% NaN** |

## 1 Hz 重建过程

1. **时间网格生成**: 按秒级 `reindex` 生成均匀时间点
2. **保留原观测点**: 原始数据点保持不变
3. **缺失秒填充**: 通过样条插值填充
4. **限洞控制**: 缺口 > MAX_HOLE_SIZE 保持 NaN

---

# 🔄 flight_id 语义变化

## 切分前后 ID 的区别

| 阶段 | `flight_id` 含义 | 示例 |
|------|-----------------|------|
| **Raw / Filtered** | 原始航班 ID | `2489916420218` |
| **Segmented / Interpolated** | **航段 ID** | `24899164202180001` |

### 航段 ID 构造规则
```
flight_id = original_flight_id × 10000 + segment_index
```

### 追溯字段
| 字段 | 说明 |
|------|------|
| `original_flight_id` | 切分前的原始航班 ID |
| `segment_index` | 航段序号 (0, 1, 2, ...) |
| `flight_seg_info` | 描述串: `{orig}_s{idx}_{t0}Z_{t1}` |

---

# �🔄 流程总览

## 三阶段清洗架构

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  原始数据    │───▶│  阶段1:过滤  │───▶│  阶段2:切分  │───▶│  阶段3:插值  │
│  (Raw)      │    │  (Filter)   │    │  (Segment)  │    │  (Interp)   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
     6.89亿              1.50亿            4097万             1.06亿
     30.94GB             6.41GB            2.15GB            14.24GB
                    ↑                 ↑
               元数据筛选          机场邻近过滤
```

### ✅ 设计优势
- **先过滤后插值**: 避免在异常数据上插值
- **投票机制**: 多检测器综合判断，减少误删
- **整行删除**: 位置错误时，关联数据联动清除

---

# 🎯 元数据筛选 (阶段1开始时)

## 航班筛选条件

在异常点检测**之前**，先按元数据筛选航班：

| 筛选条件 | 配置参数 | 说明 |
|----------|----------|------|
| **欧洲航班** | `META_EUROPE_ONLY=1` | 起降机场 continent = EU |
| **Top 机场** | `META_TOP_AIRPORTS=64` | adep+ades 合并统计前64 |
| **Top 机型** | `META_TOP_AIRCRAFT=25` | 按出现频次前25 |
| **数据来源** | `challenge_set.parquet` | 仅匹配挑战赛航班 |

### 筛选流程
```
challenge_set.parquet  ──┐
                         ├──▶ 生成 allowed_flight_ids ──▶ 过滤原始轨迹
airports_tz.parquet    ──┘
```

> **注意**: 不在 `challenge_set.parquet` 中的航班直接丢弃

---

# 📊 阶段1: 过滤清洗 (Filter)

## 阶段1执行顺序

```
1️⃣ 元数据筛选 ──▶ 2️⃣ 异常点检测链
   (航班级)           (点级)
```

## 多层级异常检测策略

| 检测器 | 功能 | 参数 |
|--------|------|------|
| `FilterCstLatLon` | 删除经纬度重复点 | - |
| `FilterCstPosition` | 删除三维位置未更新点 | - |
| `FilterCstSpeed` | 删除速度指标未更新点 | - |
| `FilterEdgeOutlier` | 清理首尾离群点 | - |
| `FilterMaxSpeedSkipNaNWithVoting` | ⭐跨NaN速度检测+投票 | 见下页 |
| `MyFilterDerivative` | 高度三点投票 | first=201 ft/s, second=51 ft/s² |
| `FilterSpatialPCAOutlier` | PCA主轴残差检测 | MAD×6 |
| `FilterIsolated` | 删除孤立点 | >20s |

---

# 🎯 核心检测参数

## FilterMaxSpeedSkipNaNWithVoting (投票机制)

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_SPEED_MPS` | 600 m/s | 速度阈值 (~2160 km/h) |
| `MAX_ACCEL_MPS2` | 450 m/s² | 加速度阈值 |
| `VOTE_THRESHOLD` | ≥2票 | 至少2个检测器标记才删除 |
| `max_iterations` | 10 | 迭代次数 |

### 投票规则
- **速度异常**: 前后两点各得1票
- **加速度异常**: 前中后三点各得1票
- **删除条件**: 累计票数 ≥ 2

---

# 🔍 PCA 空间异常检测

## FilterSpatialPCAOutlier

**原理**: 对 (latitude, longitude) 做PCA，计算每点到主轴的重建残差

| 参数 | 值 | 说明 |
|------|-----|------|
| `PCA_MIN_POINTS` | 40 | 最少有效点数 |
| `PCA_MAD_SCALE` | 6.0 | 阈值倍数 |
| `PCA_WINDOW_SIZE` | 256 | 滑动窗口大小 |

**阈值计算**: 
$$threshold = median(residual) + 6.0 \times 1.4826 \times MAD$$

**作用**: 自动剔除偏离主航迹的孤立段（如GPS漂移）

---

# ✂️ 整行删除策略

## 位置异常时联动删除的列

当检测到位置异常，以下所有列整行置为NaN：

| 类别 | 列名 |
|------|------|
| **位置列** | latitude, longitude, altitude, geoaltitude |
| **速度列** | groundspeed, track, vertical_rate |
| **天气列** | u_component_of_wind, v_component_of_wind, temperature, specific_humidity |
| **衍生列** | gsx, gsy, tasx, tasy, tas, wind, track_unwrapped |

**理由**: 位置错误 → 基于位置计算的所有数据都不可信

---

# 🔪 阶段2: 时间切分 (Segment)

## 阶段2执行顺序

```
1️⃣ 机场邻近过滤 ──▶ 2️⃣ 时间切分 ──▶ 3️⃣ 航段筛选
   (航班级)           (点级)          (航段级)
```

---

# ✈️ 机场邻近过滤 (阶段2开始时)

## 起降点距离验证

在时间切分**之前**，验证轨迹首尾点与机场的距离：

| 参数 | 值 | 说明 |
|------|-----|------|
| `AIRPORT_PROXIMITY_ENABLE` | 1 | 启用过滤 |
| `AIRPORT_PROXIMITY_THRESHOLD_KM` | 10 km | 距离阈值 |

### 过滤逻辑
```
轨迹首点 ←→ adep机场坐标  < 10 km  ✅ 保留
轨迹尾点 ←→ ades机场坐标  < 10 km  ✅ 保留
任一条件不满足 → ❌ 丢弃整条轨迹
```

### 数据来源
- 机场坐标: `airports_tz.parquet`
- 起降机场: `challenge_set.parquet` 中的 adep/ades

---

# 🔪 时间切分参数

## 航段分割与筛选

| 参数 | 值 | 说明 |
|------|-----|------|
| `MAX_DT` | 1200秒 (20分钟) | 时间间隔阈值 |
| `GAP_HANDLING` | drop | 存在>MAX_DT则丢弃整条轨迹 |
| `MIN_POINTS` | 300 | 最小航段点数 |
| `MIN_DURATION` | 600秒 (10分钟) | 最小航段时长 |

### 必需列 (全部非NaN才保留)
```
latitude, longitude, altitude, groundspeed, track, vertical_rate
```

---

# 📈 阶段3: 插值平滑 (Interpolate)

## 三次平滑样条 (CSAPS)

| 参数 | 值 | 说明 |
|------|-----|------|
| `SMOOTH` | 1e-2 | 平滑参数 p |
| `MAX_HOLE_SIZE` | 1200秒 | 最大插值间隔 |
| 输出频率 | **1 Hz** | 均匀采样 |

### 插值列
- latitude, longitude, altitude
- groundspeed, track, vertical_rate
- u_component_of_wind, v_component_of_wind
- temperature, specific_humidity

### 衍生计算
- TAS (真空速)、daltitude (高度变化率) 等

---

# 📐 CSAPS 数学原理

## 三次平滑样条 (Cubic Smoothing Spline)

**核心思想**: 在整个航段上找一条"尽量贴近数据、同时尽量不弯"的曲线

### 目标函数

$$\min_f \left[ p \sum_{i} w_i (y_i - f(x_i))^2 + (1-p) \int (f''(x))^2 dx \right]$$

| 项 | 含义 |
|----|------|
| $\sum (y_i - f(x_i))^2$ | 拟合误差（数据保真度） |
| $\int (f''(x))^2 dx$ | 曲线弯曲度（平滑度） |
| $p$ | 平滑参数 (0~1) |

---

# ⚖️ 平滑参数 p 的含义

## smooth 参数与 λ 的等价关系

若写成传统正则化形式：
$$\min_f \left[ \sum (y_i - f(x_i))^2 + \lambda \int (f''(x))^2 dx \right]$$

则等价关系为：
$$\lambda = \frac{1-p}{p}, \quad p = \frac{1}{1+\lambda}$$

### 实际配置效果

| 配置 | p 值 | λ 值 | 效果 |
|------|------|------|------|
| `smooth=1e-2` | 0.01 | **99** | 强平滑，追随趋势 |
| `smooth*0.1` (速度/风) | 0.001 | **999** | 更平滑，滤除高频噪声 |
| `smooth=1` | 1.0 | 0 | 严格插值，穿过所有点 |

> **注意**: p 越小 → λ 越大 → 曲线越平滑、越不追随局部波动

---

# 🔧 插值技术细节

## Track 航向角处理

**问题**: 航向角在 0°/360° 处不连续

**解决方案**:
1. `track` 前后填充
2. `unwrap(period=360)` 解包得到 `track_unwrapped`
3. 对解包后的值做平滑插值
4. 输出时转回: `track = track_unwrapped % 360`

## 限洞插值策略

| 条件 | 处理方式 |
|------|----------|
| 缺口 ≤ MAX_HOLE_SIZE | 样条插值填充 |
| 缺口 > MAX_HOLE_SIZE | 保持 NaN |

## 为什么不是滑窗插值？

- 三次样条是**分段多项式**，局部影响更大，视觉上像"局部处理"
- 但系数是用**全段数据一起求解**的，不是滑动窗口逐段拟合
- 实现流程：重采样到1Hz → csaps拟合 → 在1Hz网格求值

> 本流程通过**先切分**保证 segment 内时间连续，最终达到 **0 NaN**

---

# 📉 数据量变化统计

## 各阶段数据点数对比

| 阶段 | 数据点数 | 占原始比例 | 存储大小 | 缺失值率 |
|------|----------|-----------|---------|---------|
| **Raw (原始)** | 689,634,097 | 100.0% | 30.94 GB | 0% |
| **Filtered (过滤后)** | 150,166,028 | 21.8% | 6.41 GB | 14.4% |
| **Segmented (切分后)** | 40,965,669 | 5.9% | 2.15 GB | 0% |
| **Interpolated (最终)** | 106,339,053 | 15.4% | 14.24 GB | 0% |

### 关键指标
- **过滤阶段去除**: 78.2% 异常/冗余数据
- **切分后点数增长**: 通过1Hz插值从4097万→1.06亿

---

# 📊 数据保留率可视化

```
原始数据    ████████████████████████████████████████ 100%
            │
            ▼  去除欧洲以外航迹、异常点 (-78.2%)
过滤后      ████████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  21.8%
            │
            ▼  仅保留距离机场<10km航迹、切分筛选 (仅保留高质量连续段)
切分后      ██▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒   5.9%
            │
            ▼  1Hz插值填充
最终数据    ██████▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒  15.4%
```

---

# ✅ 最终数据质量

## 质量验证报告

| 指标 | 值 |
|------|-----|
| 总文件数 | **59** |
| 总航班数 | **20,130** |
| 总数据点 | **106,339,053** |
| 每航班平均segment数 | **1.00** |

### 缺失值检测 (关键列)

| 列名 | 缺失数 | 缺失率 |
|------|--------|--------|
| LATITUDE | 0 | 0.0000% |
| LONGITUDE | 0 | 0.0000% |
| ALTITUDE | 0 | 0.0000% |
| GROUNDSPEED | 0 | 0.0000% |
| TRACK | 0 | 0.0000% |
| VERTICAL_RATE | 0 | 0.0000% |

---

# 📊 数据分布特征 (1/2)

## 位置与运动变量

| 变量 | 均值 | 标准差 | 范围 | 单位 |
|------|------|--------|------|------|
| **纬度** | 49.996 | 5.22 | 36.4 ~ 67.3 | deg |
| **经度** | 10.48 | 8.46 | -9.5 ~ 29.5 | deg |
| **高度** | 26,675 | 12,457 | -5,039 ~ 44,100 | ft |
| **地速** | 375.4 | 94.9 | -204 ~ 953 | kt |
| **真空速** | 384.5 | 87.5 | -4 ~ 806 | kt |
| **航向** | 194.5 | 105.7 | 0 ~ 360 | deg |
| **垂直速率** | -31.7 | 3,713 | -277,824 ~ 467,926 | ft/min |

---

# 📊 数据分布特征 (2/2)

## 气象变量

| 变量 | 均值 | 标准差 | 范围 | 单位 |
|------|------|--------|------|------|
| **温度** | 232.2 | 22.9 | 199.9 ~ 295.0 | K |
| **风速** | 26.2 | 15.7 | -0.3 ~ 96.4 | m/s |
| **U风分量** | 15.2 | 16.8 | -56.8 ~ 91.9 | m/s |
| **V风分量** | -9.6 | 18.1 | -94.9 ~ 59.8 | m/s |
| **比湿** | 0.00057 | 0.00118 | -0.0001 ~ 0.0103 | kg/kg |

---

# 📈 时间连续性检验

## 相邻点变化量 (Δt = 1秒)

| 变量 | 均值变化 | 标准差 | 单位 |
|------|----------|--------|------|
| **Δlatitude** | 0.00108 | 0.00060 | deg |
| **Δlongitude** | 0.00181 | 0.00090 | deg |
| **Δtrack** | 0.076 | 0.298 | deg |
| **Δvertical_rate** | 12.2 | 53.8 | ft/min |
| **Δtemperature** | 0.024 | 0.038 | K |
| **Δwind_u** | 0.015 | 0.025 | m/s |
| **Δwind_v** | 0.017 | 0.027 | m/s |

✅ 变化量符合物理约束，无异常跳变

---

# 🗺️ 空间覆盖范围

## 欧洲航空网络

- **纬度范围**: 36.4°N ~ 67.3°N
- **经度范围**: 9.5°W ~ 29.5°E
- **覆盖区域**: 欧洲大陆及周边

### 数据筛选条件 (详见"元数据筛选"页)
- 仅保留**欧洲区域**航班 → 阶段1开始时执行
- 机场邻近过滤 (<10km) → 阶段2开始时执行

---

# 📂 输出文件结构

## 中间与最终结果

```
opensky_2024_PRC_dataset/
├── rawtrajectories/                    # 原始数据 (365天)
├── filtered_clean_eu_v5/               # 过滤后 (59天)
├── segmented_clean_eu_v5/              # 切分后 (59天)
└── interpolated_clean_eu_v5/           # 最终数据 (59天)

reports/
├── quality_check_clean_eu_v5/          # 质量报告
│   ├── basic_statistics.txt
│   ├── nan_check_report.txt
│   ├── raw_vs_filtered_point_stats_summary.txt
│   └── jump_detection/
└── data_distributions/                 # 分布统计 & 图表
    └── interpolated_clean_eu_v5_eu_meta/
```

---

# 📊 可视化图表

## 报告中包含的图表

| 图表类型 | 文件名 |
|----------|--------|
| 经纬度热力图 | `heatmap_lat_lon.png` |
| 高度热力图 | `heatmap_lat_lon_mean_altitude.png` |
| 各变量直方图 (对数) | `hist_y_log/hist_*.png` |
| 各变量直方图 (线性) | `hist_y_linear/hist_*.png` |
| 变化量分布图 | `hist_delta_*.png` |

### 图表路径
```
reports/data_distributions/interpolated_clean_eu_v5_eu_meta/2022-01-01__2022-02-28/
```

---

# 🏗️ 运行流程

## 一键执行命令

```bash
# 激活环境
conda activate opensky

# 进入目录
cd pipelines/clean_segment

# 分阶段运行 (便于调试)
bash run_staged_pipeline.sh --from 2022-01-01 --to 2022-02-28

# 或: 快速运行 (生产推荐)
bash run_fast_pipeline.sh --from 2022-01-01 --to 2022-02-28
```

### 运行时间参考
- 59天数据 (6.89亿点)
- 24核并行 + SSD
- 总耗时: 约 2-4 小时

---

<!-- _class: lead -->

# 🎯 总结

## 清洗流程特点

| 特点 | 说明 |
|------|------|
| ✅ **多层检测** | 7种检测器串联，覆盖各类异常 |
| ✅ **投票机制** | 减少误删，提高稳健性 |
| ✅ **PCA检测** | 自动识别GPS漂移 |
| ✅ **先切后插** | 仅在干净段内插值 |
| ✅ **完整验证** | 0缺失值、0跳变 |

### 最终成果
**20,130** 条高质量航班轨迹，**1.06亿** 数据点，**1Hz** 均匀采样

---

<!-- _class: lead -->

# 谢谢！

## 问题与讨论

---

# 附录: 配置参数汇总

```bash
# === 过滤参数 ===
MAX_SPEED_MPS=600.0          # 速度阈值 (m/s)
MAX_ACCEL_MPS2=450.0         # 加速度阈值 (m/s²)
ALT_DERIV_FIRST_FTPS=201     # 高度一阶导 (ft/s)
ALT_DERIV_SECOND_FTPS2=51    # 高度二阶导 (ft/s²)
VOTE_THRESHOLD=2             # 投票阈值

# === 切分参数 ===
MAX_DT=1200                  # 最大时间间隔 (秒)
MIN_POINTS=300               # 最小点数
MIN_DURATION=600             # 最小时长 (秒)
AIRPORT_PROXIMITY_THRESHOLD_KM=10  # 机场邻近阈值

# === 插值参数 ===
SMOOTH=1e-2                  # 平滑系数
```

---

# 附录: 完整字段单位参照表

## 轨迹与气象字段

| 字段 | 单位 | 精度 | 数值范围 |
|------|------|------|----------|
| `timestamp` | datetime64[ns, UTC] | 1 s | - |
| `latitude` | ° (十进制度) | ~0.001° | 36.4 ~ 67.3 |
| `longitude` | ° (十进制度) | ~0.001° | -9.5 ~ 29.5 |
| `altitude` | ft | 25 ft | -5,039 ~ 44,100 |
| `groundspeed` | kt | 1 kt | -204 ~ 953 |
| `track` | ° | 0.01° | 0 ~ 360 |
| `vertical_rate` | ft/min | 16 ft/min | -277,824 ~ 467,926 |
| `u_component_of_wind` | m/s | - | -56.8 ~ 91.9 |
| `v_component_of_wind` | m/s | - | -94.9 ~ 59.8 |
| `temperature` | K | - | 199.9 ~ 295.0 |
| `specific_humidity` | kg/kg | - | -0.0001 ~ 0.0103 |

---

# 附录: 派生字段与单位换算

## 派生速度字段

| 字段 | 单位 | 计算方式 |
|------|------|----------|
| `gsx` | kt | `groundspeed × sin(track)` |
| `gsy` | kt | `groundspeed × cos(track)` |
| `tasx` | kt | `gsx - u_wind × 1.94384` |
| `tasy` | kt | `gsy - v_wind × 1.94384` |
| `tas` | kt | `√(tasx² + tasy²)` |
| `wind` | m/s | `√(u² + v²)` |
| `daltitude` | ft/min | `d(altitude)/dt × 60` |

## 常用单位换算

| 换算关系 | 数值 |
|----------|------|
| 1 kt → m/s | × 0.514444 |
| 1 m/s → kt | × 1.94384 |
| 1 ft → m | × 0.3048 |
| 1 m → ft | × 3.28084 |
| K → °C | - 273.15 |