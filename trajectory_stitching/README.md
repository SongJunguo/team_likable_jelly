# 跨日期轨迹拼接项目

## 项目概述

本项目旨在解决OpenSky 2024 PRC数据集中跨日期轨迹被切分的问题。当航班轨迹跨越0点时，原始数据会被分割到两个不同日期的文件中，本项目通过智能算法识别并拼接这些被分割的轨迹。

## 🔍 数据跨日存储特性分析

### 重要发现
经过深入分析OpenSky 2022数据集，发现了关键的数据存储特性：

#### 📊 flight_id独立性
- **每日独立范围**: 每个日期文件的flight_id完全独立，无重叠
- **示例分析**:
  ```
  2022-01-05: flight_id范围 248750611-248752318 (1,708个)
  2022-01-06: flight_id范围 248752319-248754026 (1,708个)  
  2022-01-07: flight_id范围 248754027-248755734 (1,708个)
  2022-01-08: flight_id范围 248755735-248757442 (1,708个)
  ```

#### 🚨 关键影响
- **传统方法失效**: 无法直接通过flight_id匹配跨日期轨迹
- **数据分割**: 跨越午夜的航班被强制分割为两个独立的flight_id
- **icao24等同性**: icao24字段与flight_id完全相同（数据脱敏结果）

#### 💡 解决策略
本项目针对这一特性设计了多模式检测算法：
1. **icao24_only模式**: 基于飞机标识符匹配（推荐用于传统分析）
2. **flight_id_only模式**: 基于航班标识符匹配（适用于特殊场景）
3. **both模式**: 结合两种方法（最全面，推荐使用）

## 问题背景

在OpenSky数据集的`rawtrajectories`目录中，轨迹数据按日期分割存储（如`2022-01-01.parquet`）。当航班在UTC时间0点前后飞行时，其轨迹会被分割到相邻两天的文件中，导致：

1. 同一航班的轨迹被人为分割
2. 轨迹连续性被破坏  
3. 影响后续的轨迹分析和建模
4. **flight_id无法跨文件关联**（重要发现）

## 解决方案

### 核心策略

1. **多模式跨日期航班识别**：支持不同的检测模式切换
2. **智能连续性验证**：通过时间、空间、飞行参数验证轨迹连续性
3. **灵活拼接策略**：将验证通过的轨迹片段合并为完整轨迹
4. **全面质量控制**：对拼接结果进行多维度验证

### 技术特点

- **🔄 多检测模式**: 支持flight_id、icao24、both三种检测模式
- **📍 多维度匹配**：结合标识符、时间、位置、高度等多个维度
- **🔍 渐进式验证**：从粗粒度到细粒度的多层验证机制
- **⚙️ 可配置参数**：支持灵活的阈值和策略配置
- **📊 完整验证**：提供详细的拼接质量报告

## 项目结构

```
trajectory_stitching/
├── config/                     # 配置文件
│   └── stitching_config.yaml  # 主配置文件（支持检测模式切换）
├── analysis/                   # 分析模块
│   ├── detect_cross_date_flights.py  # 跨日期航班检测（多模式支持）
│   └── validate_stitching.py         # 拼接结果验证
├── processing/                 # 处理模块
│   ├── utils.py               # 工具函数
│   └── stitch_trajectories.py # 轨迹拼接核心逻辑
├── output/                    # 输出目录
│   ├── stitched_trajectories/ # 拼接后的轨迹文件
│   └── reports/              # 分析报告和图表
├── run_stitching_pipeline.py # 主执行脚本
├── test_detection.py         # 检测功能测试脚本
├── test_different_modes.py   # 多模式效果对比测试
└── README.md                 # 项目说明
```

## 使用方法

### 环境准备

```bash
# 激活conda环境
conda activate opensky

# 安装依赖包
pip install pandas numpy pyyaml matplotlib seaborn
```

### 配置设置

编辑 `config/stitching_config.yaml` 文件，设置数据路径和处理参数：

```yaml
data_paths:
  raw_trajectories: "/path/to/opensky_2024_PRC_dataset/rawtrajectories"
  output_dir: "./output/stitched_trajectories"
  reports_dir: "./output/reports"
```

### 运行流水线

#### 1. 完整流水线

```bash
# 运行完整的拼接流水线
python run_stitching_pipeline.py

# 指定日期范围
python run_stitching_pipeline.py --start-date 2022-01-01 --end-date 2022-01-31
```

#### 2. 分阶段运行

```bash
# 仅检测跨日期航班
python run_stitching_pipeline.py --detection-only

# 仅执行轨迹拼接
python run_stitching_pipeline.py --stitching-only

# 仅验证结果
python run_stitching_pipeline.py --validation-only
```

#### 3. 跳过特定阶段

```bash
# 跳过检测阶段（使用已有检测结果）
python run_stitching_pipeline.py --skip-detection

# 跳过验证阶段
python run_stitching_pipeline.py --skip-validation
```

### 单独运行模块

#### 跨日期航班检测

```bash
cd analysis
python detect_cross_date_flights.py
```

#### 多模式效果测试

```bash
# 测试不同检测模式的效果对比
python test_different_modes.py

# 输出示例:
# flight_id_only模式: 290个跨日期航班
# icao24_only模式: 290个跨日期航班  
# both模式: 580个跨日期航班
```

#### 轨迹拼接

```bash
cd processing
python stitch_trajectories.py
```

#### 结果验证

```bash
cd analysis
python validate_stitching.py
```

## 输出结果

### 拼接后的轨迹文件

- 位置：`output/stitched_trajectories/`
- 格式：`YYYY-MM-DD_stitched.parquet`
- 内容：包含拼接后完整轨迹的数据文件

### 分析报告

- 位置：`output/reports/`
- 包含：
  - `cross_date_detection_report.yaml`：跨日期航班检测报告
  - `stitching_report.yaml`：拼接处理报告
  - `stitching_validation_report.yaml`：验证结果报告
  - `validation_plots/`：验证图表目录

## 配置参数说明

### 🔄 检测模式配置（新增）

```yaml
cross_date_detection:
  detection_mode: "both"        # 检测模式选择
  # 可选值:
  # - "flight_id_only": 仅使用flight_id匹配
  # - "icao24_only": 仅使用icao24匹配（推荐）
  # - "both": 同时使用两种方法（最全面）
```

#### 模式效果对比
基于实际测试数据（2022-01-05至2022-01-08）：

| 检测模式 | 发现航班数 | 优势 | 适用场景 |
|----------|------------|------|----------|
| `flight_id_only` | 290个 | 基于航班标识，精确匹配 | 特殊分析需求 |
| `icao24_only` | 290个 | 基于飞机标识，传统方法 | 常规轨迹分析 |
| `both` | 580个 | 覆盖面最广，结果最全 | **推荐使用** |

### 跨日期检测参数

```yaml
cross_date_detection:
  time_window_minutes: 60        # 边界时间窗口
  identifier_priority:           # 匹配标识符优先级（仅当detection_mode为both时使用）
    - flight_id                  # 优先使用flight_id
    - icao24                     # 备选icao24
  position_matching:
    max_distance_km: 100         # 最大匹配距离
    max_altitude_diff: 5000      # 最大高度差
  time_matching:
    max_time_gap_minutes: 30     # 最大时间间隔
    min_confidence_score: 0.7    # 最小置信度
```

### 连续性验证参数

```yaml
continuity_validation:
  max_time_gap_minutes: 30      # 最大时间间隔
  max_distance_km: 100          # 最大空间距离
  max_altitude_diff: 5000       # 最大高度差
  max_speed_diff: 100           # 最大速度差
```

### 拼接处理参数

```yaml
stitching_processing:
  merge_strategy: "append"       # 拼接策略
  time_sort: true               # 时间排序
  remove_duplicates: true       # 去重处理
  interpolate_gaps: false       # 间隔插值
```

## 算法原理

### 1. 多模式跨日期航班检测

#### 检测模式选择
```python
# 根据配置选择匹配标识符
if detection_mode == 'flight_id_only':
    identifiers = ['flight_id']
elif detection_mode == 'icao24_only':
    identifiers = ['icao24']  
elif detection_mode == 'both':
    identifiers = ['flight_id', 'icao24']
```

#### 检测流程
1. **边界提取**：提取每日文件的最后60分钟和次日文件的前60分钟轨迹
2. **标识符匹配**：
   - **flight_id模式**: 基于航班标识符进行匹配
   - **icao24模式**: 基于飞机标识符进行匹配  
   - **both模式**: 同时使用两种标识符，结果合并
3. **多维验证**：
   - 时间连续性：检查时间间隔是否合理
   - 空间连续性：计算位置距离
   - 飞行参数：验证高度、速度等参数连续性
4. **置信度评分**：综合各维度得分计算匹配置信度

#### 关键算法改进
- **智能标识符选择**: 根据数据特性自动选择最优匹配策略
- **位置连续性检测**: 当直接标识符匹配失败时，基于位置和时间连续性进行匹配
- **多重验证机制**: 结合多个维度确保匹配准确性

### 2. 轨迹拼接

1. **数据加载**：加载检测到的航班对数据
2. **连续性验证**：再次验证轨迹连续性
3. **数据合并**：
   - 按时间排序合并轨迹点
   - 生成新的统一flight_id
   - 处理重复点和异常值
4. **质量控制**：验证拼接后轨迹的完整性

### 3. 结果验证

1. **时间连续性**：统计时间间隔分布
2. **空间连续性**：分析位置跳跃情况
3. **参数合理性**：检查飞行参数范围
4. **数据对比**：与原始数据进行统计对比
5. **模式效果对比**：分析不同检测模式的效果差异

## 性能优化

- **批量处理**：支持多日期并行处理
- **内存管理**：分块加载大文件
- **缓存机制**：缓存中间结果避免重复计算
- **进度监控**：提供详细的处理进度信息

## 注意事项

1. **数据完整性**：确保原始数据文件完整且可读
2. **内存需求**：大数据集处理可能需要较大内存
3. **时区处理**：所有时间均为UTC时间
4. **参数调优**：根据数据特点调整匹配阈值
5. **结果验证**：建议仔细检查验证报告
6. **🔄 检测模式选择**：
   - 对于常规分析，推荐使用`both`模式获得最全面的结果
   - 对于性能敏感场景，可选择`icao24_only`模式
   - 对于特殊需求，可使用`flight_id_only`模式
7. **数据特性理解**：
   - flight_id在不同日期文件中完全独立
   - icao24与flight_id在此数据集中等同
   - 跨日期航班需要通过位置和时间连续性识别

## 故障排除

### 常见问题

1. **文件不存在**：检查数据路径配置
2. **内存不足**：减少批处理大小或增加系统内存
3. **匹配结果少**：
   - 检查detection_mode配置是否合适
   - 调整检测阈值参数
   - 尝试使用`both`模式获得更全面的结果
4. **拼接质量差**：检查连续性验证参数
5. **模式选择困惑**：
   - 默认使用`both`模式
   - 查看测试脚本输出了解不同模式效果
   - 根据具体需求选择合适模式

### 日志分析

查看详细日志信息：
```bash
tail -f trajectory_stitching.log
```

## 扩展功能

- 支持其他数据格式（CSV、JSON等）
- 添加更多验证维度
- 实现实时处理模式
- 集成机器学习匹配算法

## 贡献指南

欢迎提交问题报告和改进建议。请确保：

1. 详细描述问题或改进点
2. 提供复现步骤
3. 包含相关日志信息
4. 遵循代码规范

## 许可证

本项目遵循项目根目录的LICENSE文件。