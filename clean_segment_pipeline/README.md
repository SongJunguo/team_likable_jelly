# Clean-Segment-Interpolate 流程

## 🎯 设计理念

**核心思想**：过滤 → 切分 → 插值

**与旧流程的区别**：

| 维度 | 旧流程 | 新流程（Clean-Segment-Interp） |
|------|--------|-------------------------------|
| **流程顺序** | 过滤 → 插值 → 切分（带速度检查） | 过滤 → 切分 → 插值 |
| **速度检测** | 切分阶段再检查 | 过滤阶段一次性处理（投票机制） |
| **插值对象** | 完整轨迹（可能含大间隔） | 短小segment（内部连续） |
| **删除策略** | 单列或部分列 | 整行删除（位置+速度+天气） |
| **插值质量** | 可能跨异常段插值 | 仅在干净segment内插值 ✅ |

**优势**：
1. ✅ 速度异常在过滤阶段彻底处理（带投票机制，更稳健）
2. ✅ 位置异常时，天气参数联动删除（避免基于错误位置的数据）
3. ✅ 切分后的segment内部干净、时间连续，插值质量更高
4. ✅ 不对含异常段的数据插值，避免污染传播
5. ✅ 最终轨迹：0个NaN + 0个异常点 + 1Hz均匀采样

## 📂 目录结构

```
clean_segment_pipeline/
├── README.md                   # 本文档
├── config.sh                   # 统一配置
│
├── run_staged_pipeline.sh      # 【模式1】分阶段运行（便于调试）
├── run_fast_pipeline.sh        # 【模式2】一口气运行（快速，机械硬盘友好）
└── run_fast_pipeline_parallel.sh       # 新版（轨迹级并行）⭐
│
├── 01_filter_clean.sh          # 阶段1：过滤
├── 02_split_by_time.sh         # 阶段2：切分
├── 03_interpolate_segments.sh  # 阶段3：插值
├── 04_quality_check.sh         # 阶段4：质量检查
│
├── process_single_day_fast.py  # 快速模式核心脚本
├── process_single_day_fast_parallel.py # 新版（轨迹级并行）⭐
│
└── utils/
    ├── check_nan_in_final.py   # NaN检测
    └── batch_utils.sh          # 批量处理工具
```

## 🚀 使用方法

### 快速开始（推荐）

#### 方式1：轨迹级并行（单日测试推荐）
```bash
cd clean_segment_pipeline

# 单日数据测试（充分利用多核，速度快！）
bash run_fast_pipeline_parallel.sh --from 2022-01-01 --to 2022-01-01 --workers 24

# 全量运行（顺序处理文件，每个文件内并行）
bash run_fast_pipeline_parallel.sh --workers 40
```

**特点**：
- ✅ 文件级串行：一个parquet一个parquet处理
- ✅ 轨迹级并行：每个文件内按flight_id并行
- ✅ 单日测试时充分利用多核（不用等很久！）
- ✅ 机械硬盘友好（顺序读文件，避免I/O竞争）

#### 方式2：文件级并行（全量运行推荐）
```bash
cd clean_segment_pipeline

# 多个文件并行处理
bash run_fast_pipeline.sh --from 2022-01-01 --to 2022-01-10

# 全量运行
bash run_fast_pipeline.sh
```

**特点**：
- ✅ 文件级并行：同时处理多个parquet文件
- ✅ 全量运行时效率高（365个文件并行）
- ⚠️  单日测试时无法并行（只有1个文件）

**如何选择**：
- **测试单日数据**：用 `run_fast_pipeline_parallel.sh`（轨迹级并行）
- **全量处理**：用 `run_fast_pipeline.sh`（文件级并行）或 `run_fast_pipeline_parallel.sh`（看机械硬盘I/O是否饱和）

### 分阶段运行（调试用）

```bash
# 分阶段运行，每阶段都会存储中间结果
bash run_staged_pipeline.sh --from 2022-01-01 --to 2022-01-01

# 中间结果：
# - filtered_clean_v1/2022-01-01.parquet         （过滤后）
# - segmented_clean_v1/segmented_2022-01-01.parquet  （切分后）
# - interpolated_clean_v1/interpolated_2022-01-01.parquet  （最终）
```

### 单独运行某阶段

```bash
bash 01_filter_clean.sh --date 2022-01-01
bash 02_split_by_time.sh --date 2022-01-01
bash 03_interpolate_segments.sh --date 2022-01-01
bash 04_quality_check.sh  # 检查最终结果
```

## ⚙️ 参数配置

编辑 `config.sh`：

### 过滤参数
```bash
FILTER_STRATEGY="clean_segment_interp"  # 策略名
MAX_SPEED_MPS=550        # 速度阈值（550 m/s ≈ 1980 km/h）
MAX_ACCEL_MPS2=15.0      # 加速度阈值
VOTE_THRESHOLD=2         # 投票阈值（≥2票才删除）
```

### 切分参数
```bash
MAX_DT=20          # 最大时间间隔（秒）
MIN_POINTS=30      # 最小segment点数
MIN_DURATION=120   # 最小segment时长（秒）
```

### 插值参数
```bash
SMOOTH=1e-2        # csaps平滑系数
```

## 📊 质量检查

流程结束后自动运行质量检查（也可手动运行）：

```bash
bash 04_quality_check.sh

# 输出报告：
# 1. reports/quality_check_clean_v1/jump_detection/  (跳变检测)
# 2. reports/quality_check_clean_v1/nan_check_report.txt  (NaN检测)
```

**检查项**：
- ✅ 跳变检测：检测短时间内跨越超远距离的异常
- ✅ NaN检测：确保最终轨迹0个NaN
- ✅ 速度检测：确保无超速点（>550 m/s）

## 🔧 技术细节

### 过滤策略（clean_segment_interp）

```python
FilterCstLatLon()               # 删除经纬度重复点
| FilterCstPosition()           # 删除三维位置未更新点
| FilterCstSpeed()              # 删除速度指标未更新点
| FilterEdgeOutlier()           # 清理首尾离群点
| FilterMaxSpeedSkipNaNWithVoting(  # ★核心：跨NaN速度检测+投票
    max_speed_mps=550,
    max_accel_mps2=15.0,
    max_iterations=10,
    vote_threshold=2
  )
| FilterIsolated()              # 删除孤立点（>20s距离）
```

**投票机制**：
- 速度异常：前后两点各得1票
- 加速度异常：前中后三点各得1票
- 票数≥2才删除（更稳健）

**整行删除**：
- 位置列：latitude, longitude, altitude, geoaltitude
- 速度列：groundspeed, track, vertical_rate
- 天气列：u_component_of_wind, v_component_of_wind, temperature, specific_humidity
- 衍生列：gsx, gsy, tasx, tasy, tas, wind, track_unwrapped

理由：位置错误 → 基于位置的所有数据都不可信

### 两种运行模式

**模式1：分阶段模式**（便于调试）
- 每阶段存储中间结果
- 便于检查问题出在哪个阶段
- I/O较多（机械硬盘慢）

**模式2：快速模式**（生产推荐）
- 数据在内存中流转
- 只存储最终结果
- I/O最少（机械硬盘友好）✅

## 📈 性能优化

### 机械硬盘优化
- 使用快速模式（减少I/O）
- 并发度设置为24-40（避免磁盘饱和）
- 输出目录放在高速分区

### 并发配置
```bash
FILTER_PROCS=24      # 过滤阶段并发
SPLIT_PROCS=24       # 切分阶段并发
INTERP_PROCS=24      # 插值阶段并发（快速模式用）
```

## 🐛 故障排查

### 问题1：过滤后数据太少
**原因**：阈值过于严格

**解决**：
```bash
# config.sh中调整
MAX_SPEED_MPS=600    # 放宽到600 m/s
VOTE_THRESHOLD=3     # 提高投票阈值
```

### 问题2：最终轨迹仍有NaN
**原因**：插值阶段异常

**解决**：
```bash
# 检查插值日志
cat interpolated_clean_v1/.logs/2022-01-01.log

# 手动运行单日插值
bash 03_interpolate_segments.sh --date 2022-01-01 --force
```

### 问题3：质量检查发现跳变
**原因**：过滤阶段漏检

**解决**：
```bash
# 降低速度阈值
MAX_SPEED_MPS=500

# 或增加检测轮次
max_iterations=15
```

## 📝 与旧流程对比

### 旧流程入口
```bash
junguo_analysis_for_opensky2022/analysis_for_interpolation/run_full_pipeline_with_interpolate.sh
```

### 新流程入口
```bash
clean_segment_pipeline/run_fast_pipeline.sh
```

**两者完全独立**，可同时运行、对比评估！

## 💡 最佳实践

1. **首次使用**：先用单日数据测试（--from/--to）
2. **参数调优**：根据质量检查结果调整阈值
3. **生产运行**：使用快速模式（run_fast_pipeline.sh）
4. **定期检查**：运行quality_check.sh确保数据质量

## 📞 技术支持

- 配置问题：检查config.sh
- 代码问题：查看对应脚本的注释
- 质量问题：分析quality_check报告
