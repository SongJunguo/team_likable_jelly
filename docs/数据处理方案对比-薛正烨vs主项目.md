# 数据处理方案对比：薛正烨 vs 主项目 Clean-Segment-Interpolate

## 一、方案概览

| 维度 | 薛正烨方案 | 主项目方案（Clean-Segment-Interpolate v6） |
|------|-----------|----------------------------------------|
| **文件位置** | `pipelines/Xue_Zhengye_process/`（`legacy/薛正烨的处理方案/` 仍保留对照） | `pipelines/clean_segment/` |
| **核心脚本** | `process_rawtrajectories_by_day.py` + `run_xue_process_raw.sh` | `run_fast_pipeline.sh` + `process_single_day_fast.py` |
| **处理流程** | 过滤 → 重采样 → 平滑 → 重构 → 互补滤波 | 过滤 → 切分 → 插值 |
| **输出目录** | `opensky_2024_PRC_dataset/xue_processed_raw__v1/xue_<date>.parquet` | `interpolated_clean__PCA_v6/` |

---

## 二、核心算法对比

### 2.1 数据过滤策略

#### 薛正烨方案
```python
# 1. 地速硬阈值过滤（50~600 kt）
mask = (df['groundspeed'] >= 50) & (df['groundspeed'] <= 600)
df = df[mask]

# 2. 去除静态数据（经纬度不变）
is_static = (lat_diff == 0) & (lon_diff == 0)
df = df[~is_static]

# 3. 时间间隔切分（>5s切段，<60点废弃）
segment_ids = (df['dt'] > 5.0).cumsum()
```

**特点**：
- ✅ 简单直接，物理删除异常行
- ✅ 去除静态数据（地面悬停）
- ❌ 硬阈值可能误删边缘正常数据
- ❌ 无基于导数的异常检测

#### 主项目方案（clean_segment_interp 策略）
```python
# 过滤链：
FilterCstLatLon()                        # 经纬度范围检查
| FilterCstPosition()                    # 位置常量检查
| FilterCstSpeed()                       # 速度常量检查
| FilterMaxSpeedSkipNaNWithVoting()      # 跨NaN速度检测（带投票）
| FilterSpatialPCAOutlier()              # PCA空间异常检测（可选）
| MyFilterDerivative(altitude)           # 高度导数检测
| FilterIsolated()                       # 孤立点剔除
```

**特点**：
- ✅ 多级过滤链，异常点置 NaN（非删除）
- ✅ 基于导数的物理约束检测
- ✅ PCA空间异常检测（检测3D轨迹偏离）
- ✅ 投票机制（≥2票才删除，降低误杀）
- ⚠️ 复杂度高，参数调优成本大

---

### 2.2 插值方法

#### 薛正烨方案
```python
# 线性插值（Pandas resample）
df_resampled = df[numeric_cols].resample('1S').mean()
df_resampled = df_resampled.interpolate(method='linear', limit_direction='both')
```

**特点**：
- ✅ 实现简单，计算快
- ❌ 线性插值对加速度突变不友好
- ❌ 无缺口限制（即使60s缺失也会插值）

#### 主项目方案
```python
# 三次平滑样条插值（csaps库）
for col in cols:
    sp = csaps.csaps(t_seconds, values, t_grid, smooth=1e-2)

# 限洞插值（max_hole_size=120s）
if hole_size <= max_hole_size:
    interpolate(col)
else:
    keep_nan(col)
```

**特点**：
- ✅ 三次样条更平滑，符合飞机动力学
- ✅ 限洞插值（大缺口保持NaN）
- ✅ 可调平滑系数（smooth=1e-2）
- ⚠️ 计算成本高（csaps库）

---

### 2.3 高度处理

#### 薛正烨方案：**互补滤波 + 形态学滤波**
```python
# 步骤1：垂直速率积分 + 气压高度融合
alt_fused = α × (alt_prev + vr×dt) + (1-α) × alt_raw

# 步骤2：形态学滤波（Opening + Closing）
alt_final = morphological_filter(alt_fused, window_size=20)
```

**优势**：
- ✅ 互补滤波融合多源数据（气压高度 + 垂直速率）
- ✅ 形态学滤波去除尖刺（抗噪声强）
- ✅ 动态权重调整（大爬升率时降低积分权重）
- ⚠️ 垂直速率数据质量影响大

#### 主项目方案：**样条平滑 + 导数计算**
```python
# 高度样条平滑
alt_smooth = csaps.csaps(t, altitude, t_grid, smooth=1e-2)

# 派生daltitude（ft/min）
daltitude = derivative(alt_smooth) * 60
```

**优势**：
- ✅ 样条平滑效果好
- ✅ daltitude来自高度曲线导数（比原始vertical_rate更平滑）
- ❌ 未融合垂直速率数据（信息利用不充分）

---

### 2.4 经纬度重构

#### 薛正烨方案：**动力学约束 + 航位推算（Dead Reckoning）**
```python
# 核心思想：检测GPS跳变并用DR修复
limit_dist = v × dt × 2.0 + 50m
meas_dist = haversine(lat_prev, lon_prev, lat, lon)

if meas_dist > limit_dist:
    # GPS跳变！用航向+地速推算位置
    vn = v × cos(track)
    ve = v × sin(track)
    lat_new = lat_prev + vn × dt / R
    lon_new = lon_prev + ve × dt / (R × cos(lat))
else:
    # 信任GPS测量值
    lat_new = lat
```

**优势**：
- ✅ **创新算法**：基于物理约束检测并修复GPS跳变
- ✅ 保留真实轨迹特征（未超限时信任GPS）
- ✅ Numba加速（高性能）
- ⚠️ 依赖平滑后的地速和航向（误差传播风险）

#### 主项目方案：**样条平滑**
```python
# 仅对经纬度做样条平滑
lat_smooth = csaps.csaps(t, latitude, t_grid, smooth=1e-2)
lon_smooth = csaps.csaps(t, longitude, t_grid, smooth=1e-2)
```

**特点**：
- ✅ 简单直接
- ❌ **未检测GPS跳变**（可能平滑掉跳变，引入虚假轨迹）

---

### 2.5 航向角处理

#### 薛正烨方案：**sin/cos分量平滑**
```python
# 处理0/360°环绕问题
trk_sin = sin(track)
trk_cos = cos(track)
trk_sin_smooth = gaussian_filter1d(trk_sin, sigma=2.0)
trk_cos_smooth = gaussian_filter1d(trk_cos, sigma=2.0)
track_smooth = arctan2(trk_sin_smooth, trk_cos_smooth)
```

#### 主项目方案：**unwrap + 样条**
```python
# unwrap解环绕（0→360变成连续）
track_unwrapped = np.unwrap(track, period=360)
track_smooth = csaps.csaps(t, track_unwrapped, t_grid)
track_final = track_smooth % 360
```

**两者效果类似**，主项目方案更符合数学习惯。

---

## 三、关于 challenge_set.parquet 过滤（flight_id 白名单）

### 当前状态
- ✅ 薛正烨方案（新目录 `pipelines/Xue_Zhengye_process/`）已实现：按天读取 raw 后第一时间用 `challenge_set.parquet` 做 `flight_id` 白名单过滤，并将 `adep/ades/aircraft_type` 合并回输出。
- ⚠️ 主项目 `pipelines/clean_segment/` 目前仍未做 challenge_set 白名单过滤（会处理 raw 中的非挑战航班，浪费算力）。

### 数据路径分析
- **原始数据**：`opensky_2024_PRC_dataset/rawtrajectories/2022-*.parquet`（包含所有航班）
- **目标航班**：`opensky_2024_PRC_dataset/flights/challenge_set.parquet`
- **问题**：原始数据包含非目标航班，处理时浪费资源

### 解决方案
需要在 **过滤阶段最开始** 添加 flight_id 白名单过滤：

```python
# 在 filter_trajs.py 或 raw 处理脚本开头添加
challenge_ids = pd.read_parquet(
    "opensky_2024_PRC_dataset/flights/challenge_set.parquet",
    columns=["flight_id"],
)["flight_id"].values
df = df[df['flight_id'].isin(challenge_ids)]  # 仅保留目标航班
```

---

## 四、融合建议：吸收薛正烨方案优点

### 4.1 可融合的优秀算法

| 算法 | 优先级 | 融合难度 | 收益 |
|------|-------|---------|------|
| **经纬度动力学约束重构** | ⭐⭐⭐⭐⭐ | 中 | 检测并修复GPS跳变（重要！） |
| **高度互补滤波** | ⭐⭐⭐⭐ | 低 | 融合垂直速率，提升高度精度 |
| **形态学滤波** | ⭐⭐⭐ | 低 | 去除高度尖刺 |
| **去除静态数据** | ⭐⭐⭐ | 低 | 去除地面悬停数据 |
| **challenge_set过滤** | ⭐⭐⭐⭐⭐ | 低 | 减少无用数据处理 |

### 4.2 具体融合方案

#### 方案A：在主项目中增强（推荐）
```bash
# 修改 pipelines/clean_segment/filter_trajs.py
1. 添加 challenge_set 白名单过滤
2. 在过滤链后添加去除静态数据模块
3. 在插值阶段后添加经纬度动力学检测（可选）
4. 在高度插值后添加互补滤波优化（可选）
```

**优势**：
- 保留主项目的严格过滤链
- 增强GPS跳变检测能力
- 提升高度精度

**实施步骤**：
1. 在 `filter_trajs.py` 开头添加 `FilterChallengeSet()` 过滤器
2. 在 `FilterIsolated()` 后添加 `FilterStaticPoints()` 过滤器
3. 在 `interpolate.py` 中添加后处理步骤：
   - `postprocess_latlon_kinematic_check()`
   - `postprocess_altitude_complementary_filter()`

#### 方案B：将薛正烨方案改造为主项目插件
```bash
# 创建 pipelines/clean_segment/postprocessors.py
def kinematic_latlon_reconstruct(df, config):
    """动力学约束经纬度重构（薛正烨算法）"""
    # 复用 numba_kinematic_reconstruction()
    pass

def complementary_altitude_filter(df, config):
    """互补滤波高度优化（薛正烨算法）"""
    # 复用 numba_complementary_filter()
    pass

# 在 process_single_day_fast.py 中调用
df = interpolate_in_memory(df, ...)
df = kinematic_latlon_reconstruct(df, config)  # 新增
df = complementary_altitude_filter(df, config)  # 新增
```

---

## 五、性能对比

| 维度 | 薛正烨方案 | 主项目方案 |
|------|-----------|-----------|
| **单日处理速度** | 快（线性插值） | 中等（样条插值） |
| **内存占用** | 中等 | 中等 |
| **并行效率** | 高（ProcessPoolExecutor） | 高（xargs并行） |
| **代码复杂度** | 低（单文件550行） | 高（模块化） |
| **可维护性** | 低（耦合紧密） | 高（解耦模块） |

---

## 六、推荐行动计划

### 短期（优先级⭐⭐⭐⭐⭐）
1. **添加 challenge_set.parquet 过滤**
   - 薛正烨方案（`pipelines/Xue_Zhengye_process/`）已完成
   - 主项目方案建议补齐
   - 减少无效数据处理（节省50%+时间）

2. **在主项目中添加去除静态数据**
   - 创建 `FilterStaticPoints()` 过滤器
   - 去除地面悬停数据

### 中期（优先级⭐⭐⭐⭐）
3. **集成经纬度动力学检测**
   - 将 `numba_kinematic_reconstruction()` 移植到主项目
   - 作为插值后的后处理步骤

4. **集成高度互补滤波**
   - 将 `numba_complementary_filter()` 移植到主项目
   - 融合垂直速率和气压高度

### 长期（优先级⭐⭐⭐）
5. **统一方案评估**
   - 在相同数据集上对比两个方案的TOW预测RMSE
   - 选择最优方案或混合使用

---

## 七、关键代码位置索引

### 薛正烨方案
- 主脚本：[pipelines/Xue_Zhengye_process/process_rawtrajectories_by_day.py](../pipelines/Xue_Zhengye_process/process_rawtrajectories_by_day.py)
- 运行脚本：[pipelines/Xue_Zhengye_process/run_xue_process_raw.sh](../pipelines/Xue_Zhengye_process/run_xue_process_raw.sh)
- 核心算法：[pipelines/Xue_Zhengye_process/flight_processor_core.py](../pipelines/Xue_Zhengye_process/flight_processor_core.py)
- 核心算法：
  - 动力学重构：`flight_processor_core.py:78`
  - 互补滤波：`flight_processor_core.py:129`
  - 形态学滤波：`flight_processor_core.py:21`

### 主项目方案
- 运行脚本：[pipelines/clean_segment/run_fast_pipeline.sh](../pipelines/clean_segment/run_fast_pipeline.sh)
- 配置文件：[pipelines/clean_segment/config.sh](../pipelines/clean_segment/config.sh)
- 过滤模块：[pipelines/clean_segment/filter_trajs.py](../pipelines/clean_segment/filter_trajs.py)
- 插值模块：[pipelines/clean_segment/interpolate.py](../pipelines/clean_segment/interpolate.py)
- 过滤器实现：[pipelines/classic_filters/filterclassic.py](../pipelines/classic_filters/filterclassic.py)

---

## 八、总结

| 方案 | 优势 | 劣势 | 适用场景 |
|------|------|------|---------|
| **薛正烨** | GPS跳变检测、互补滤波、代码简洁 | 硬阈值过滤、无导数检测、线性插值 | 快速实验、GPS质量差的数据 |
| **主项目** | 严格过滤链、样条插值、PCA异常检测 | 未检测GPS跳变、未融合垂直速率 | 生产环境、高质量数据要求 |

**最佳实践**：将薛正烨方案的 **动力学检测** 和 **互补滤波** 集成到主项目，结合两者优势。
