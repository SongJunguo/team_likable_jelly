# OpenSky 2022 数据集深度分析报告

**分析时间**: 2025年9月11日  
**分析者**: SongJunguo  
**数据集**: OpenSky 2024 PRC Challenge Dataset (2022年数据)

## 📋 目录

1. [数据集概览](#数据集概览)
2. [数据质量分析](#数据质量分析)
3. [航班标识系统](#航班标识系统)
4. [时间分布特征](#时间分布特征)
5. [插值处理问题](#插值处理问题)
6. [模型训练建议](#模型训练建议)
7. [结论与建议](#结论与建议)

---

## 📊 数据集概览

### 基本规模
- **时间跨度**: 2022年全年 (365个文件)
- **数据量**: 每天约### 分析工具列表

- `analyze_data.py` - 数据集基本信息分析
- `check_data_quality.py` - 数据质量深度检查  
- `check_data_quality_polars.py` - **高性能数据质量检测** ⭐ 新增
- `run_quality_check.sh` - **高性能检测便捷脚本** ⭐ 新增
- `analyze_time_gaps.py` - 时间间隔和缺失分析
- `analyze_flight_ids.py` - 航班标识系统分析
- `QnA_groundspeed_weather_TAS.md` - 飞行轨迹字段与天气/TAS问题答疑（保留对话记忆）
- `verify_metadata_sources.py` - **数据来源验证工具** ⭐ 新增
- `check_trajectory_feasibility.py` - **轨迹预测可行性分析** ⭐ 新增
- `run_all_analysis.py` - 一键运行所有分析
- `PERFORMANCE_GUIDE.md` - **高性能工具使用指南** ⭐ 新增轨迹点
- **航班数**: 每天约1,700个航班
- **总航班数**: 估计超过60万个航班/年

### 📁 数据来源详解

#### ✈️ **航班元数据** (`challenge_set.csv`)
- **字段数**: 18个
- **数据量**: 约1万条记录
- **主要内容**: 航班基本信息、机场信息、时间信息、飞机信息、性能数据
- **预测目标**: `tow` (起飞重量) - 这是比赛的核心预测任务

| 类别 | 字段 | 描述 |
|------|------|------|
| 航班基本 | `flight_id`, `date`, `callsign` | 唯一标识、日期、加密呼号 |
| 起降机场 | `adep`, `ades`, `name_adep`, `name_ades` | 起飞/到达机场代码和名称 |
| 地理信息 | `country_code_adep`, `country_code_ades` | 起降机场国家代码 |
| 时间信息 | `actual_offblock_time`, `arrival_time`, `flight_duration`, `taxiout_time` | 起飞、到达、飞行、滑行时间 |
| 飞机信息 | `aircraft_type`, `wtc`, `airline` | 机型、尾流类别、航空公司 |
| 性能数据 | `flown_distance`, **`tow`** | 飞行距离、**起飞重量(预测目标)** |

#### 🌤️ **机场天气数据** (`METARs.parquet`)
- **字段数**: 33个  
- **数据量**: 4,261万条记录
- **气象站**: 5,976个 (主要是机场和地面观测站)
- **时间范围**: 2021-12-31 到 2023-01-01 (覆盖2022全年)
- **地理覆盖**: 全球主要机场 (美国、欧洲、亚洲等)

| 类别 | 主要字段 | 描述 |
|------|----------|------|
| 基本信息 | `station`, `valid`, `lat`, `lon`, `elevation` | 气象站、时间、位置、海拔 |
| 温度湿度 | `tmpf`, `dwpf`, `relh`, `feel` | 温度、露点、相对湿度、体感温度 |
| 风力信息 | `drct`, `sknt`, `gust`, `peak_wind_gust` | 风向、风速、阵风、最大阵风 |
| 气压能见度 | `alti`, `mslp`, `vsby` | 气压、海平面气压、能见度 |
| 云层信息 | `skyc1-4`, `skyl1-4` | 云层类型和高度 |
| 天气现象 | `wxcodes`, `p01i`, `snowdepth` | 天气代码、降水、雪深 |
| 结冰信息 | `ice_accretion_1hr/3hr/6hr` | 1/3/6小时结冰量 |

**重要特点**: 这是**固定地面气象站数据**，主要用于**起降阶段天气分析**，不是飞行路径沿线的天气。

#### 🛰️ **轨迹天气数据** (在 `rawtrajectories/*.parquet` 中)
- **字段数**: 4个天气字段
- **覆盖**: 每个轨迹点都有对应天气数据
- **数据性质**: 沿飞行路径的**插值气象数据** (可能来自数值天气模式)

| 字段 | 单位 | 描述 | 数据范围 |
|------|------|------|----------|
| `u_component_of_wind` | m/s | 风速东西分量 | -43.62 到 103.33 |
| `v_component_of_wind` | m/s | 风速南北分量 | -68.43 到 59.89 |
| `temperature` | K | 环境温度 | 171.70 到 305.47 |
| `specific_humidity` | kg/kg | 比湿 | 0 到 0.02 |

**重要特点**: 这是**飞行路径级天气数据**，用于**巡航阶段轨迹预测**和**风场影响分析**。

#### 🛬 **机场信息** (`airports_tz.parquet`)
- **字段数**: 19个
- **机场数**: 502个
- **主要内容**: 机场位置、类型、时区等基础信息

| 类别 | 字段 | 描述 |
|------|------|------|
| 标识信息 | `icao_code`, `iata_code`, `gps_code` | ICAO代码、IATA代码、GPS代码 |
| 基本信息 | `name`, `type`, `municipality` | 机场名称、类型、城市 |
| 地理信息 | `latitude_deg`, `longitude_deg`, `elevation_ft` | 纬度、经度、海拔 |
| 行政信息 | `iso_country`, `iso_region`, `continent` | 国家、地区、大洲 |
| 运营信息 | `scheduled_service`, `time_zone` | 定期航班服务、时区 |

### 数据文件结构
```
opensky_2024_PRC_dataset/
├── rawtrajectories/           # 原始ADS-B轨迹数据 (365个parquet文件)
├── classic__1e-2_interpolated_trajectories/  # 插值处理后轨迹
├── METARs.parquet            # 机场天气数据 (4,261万条记录, 5,976个气象站)
├── airports_tz.parquet       # 机场信息 (502个机场, 19个字段)
├── challenge_set.csv         # 航班元数据 (18个字段, 包含TOW预测目标)
├── final_submission_set.csv  # 最终提交集 (TOW为NaN, 需要预测)
└── submission_set.csv        # 提交集样本
```

### 轨迹数据字段 (13维)
| 字段名 | 类型 | 描述 | 数据范围 |
|--------|------|------|----------|
| `flight_id` | int64 | 航班唯一标识 | 248750611 - 248772010 |
| `timestamp` | datetime64[ns] | 时间戳 | 2022-01-01 到 2022-12-31 |
| `latitude` | float64 | 纬度 | -34.07° 到 68.51° |
| `longitude` | float64 | 经度 | -122.76° 到 140.42° |
| `altitude` | float64 | 高度(英尺) | -1200 到 126800 |
| `groundspeed` | float64 | 地面速度(节) | 0 到 1445 |
| `track` | float64 | 航向角(度) | 0 到 359.89 |
| `vertical_rate` | float64 | 垂直速度(英尺/分) | -30848 到 32640 |
| `icao24` | int64 | 飞机标识(=flight_id) | 同flight_id |
| `u_component_of_wind` | float64 | 风速U分量 | -43.62 到 103.33 |
| `v_component_of_wind` | float64 | 风速V分量 | -68.43 到 59.89 |
| `temperature` | float64 | 温度(K) | 171.70 到 305.47 |
| `specific_humidity` | float64 | 比湿 | 0 到 0.02 |

---

## 🔍 数据质量分析

### ✅ 原始数据质量 (良好)
- **缺失率**: 仅0.28% (groundspeed, track, vertical_rate)
- **时间采样**: 99.9%的点间隔为1秒
- **轨迹完整性**: 平均99.9%完整度

### ❌ 插值数据质量 (严重问题)
| 字段 | 缺失率 | 问题描述 |
|------|--------|----------|
| `latitude/longitude` | 15.26% | 位置信息大量缺失 |
| `groundspeed` | 25.84% | 速度信息严重缺失 |
| `tasx/tasy/tas` | 33.03% | 真空速度完全不可用 |
| **总体影响** | 15% | 178万行数据大部分字段为空 |

### 数据异常情况
1. **超高高度**: 126,800英尺 (正常商航<45,000英尺)
2. **超高速度**: 1,445节 (接近音速)
3. **极端垂直速度**: ±30,000英尺/分钟
4. **时间间隔异常**: 最大间隔23,984秒 (6.6小时)

---

## 🆔 航班标识系统

### 主要标识符
- **`flight_id`**: 🏆 **主键**, 每航班唯一 (248750611-248772010)
- **`icao24`**: ⚠️ **等同于flight_id** (非传统飞机标识)
- **`callsign`**: 🔐 **哈希加密** (非真实呼号, 如"3840d84f25d3f5fcc0a1be3076bb4039")

### 重要发现 🚨
```
发现: icao24 === flight_id
原因: 数据脱敏处理，每航班分配虚拟飞机ID
影响: 无法分析同一架飞机的多个航班
```

### 航班分布特征
- **单天数据**: 1,708个唯一航班
- **跨天航班**: 132个 (7.7%)
- **最长航班**: 12.5小时 (洲际航线)
- **callsign重用**: 115个呼号对应多个航班

---

## ⏰ 时间分布特征

### 采样频率分析
| 时间间隔 | 占比 | 数量 | 说明 |
|----------|------|------|------|
| 1秒 | 99.9% | 342,477 | 标准采样 |
| 2-5秒 | 0.1% | 217 | 小间隔 |
| 6-30秒 | 0.02% | 76 | 中等间隔 |
| 31-60秒 | 0.003% | 10 | 大间隔 |
| >60秒 | 0.014% | 49 | 数据缺失 |

### 缺失时间段统计
- **总缺失段**: 17个 (前20航班中)
- **平均缺失**: 85.3分钟
- **最长缺失**: 311.1分钟 (5.2小时)
- **>1小时缺失**: 6个航班

### 轨迹覆盖率
- **平均覆盖率**: 85.2%
- **<50%覆盖**: 4个航班 (2.3%)
- **<80%覆盖**: 7个航班 (4.1%)
- **多段轨迹**: 12个航班 (平均1.9段/航班)

---

## 🔧 插值处理问题

### 插值目的 (理论)
1. ✅ 统一时间网格 (1秒间隔)
2. ✅ 填补小间隔缺失
3. ✅ 便于机器学习处理

### 实际效果 (问题)
1. ❌ **引入大量NaN值** (25-33%缺失率)
2. ❌ **未解决大间隔** (>60秒间隔仍存在)
3. ❌ **数据质量下降** (从0.28%恶化到25%+)

### 对比结果
```
原始数据: 0.28% 缺失率, 99.9% 时间连续性
插值数据: 25%+ 缺失率, 178万行严重缺失
结论: 插值处理适得其反！
```

---

## 🤖 模型训练建议

### 数据选择策略
```python
# 推荐使用原始数据
data_source = "rawtrajectories/"  # ✅ 推荐
# data_source = "interpolated_trajectories/"  # ❌ 不推荐
```

### 预处理流程
```python
def preprocess_trajectory(flight_id, df):
    """推荐的预处理流程"""
    
    # 1. 按flight_id筛选
    flight_data = df[df.flight_id == flight_id].sort_values('timestamp')
    
    # 2. 按大间隔分割轨迹段
    time_diffs = flight_data['timestamp'].diff().dt.total_seconds()
    break_points = time_diffs > 60  # 超过1分钟分割
    segments = split_by_breakpoints(flight_data, break_points)
    
    # 3. 过滤短段轨迹
    valid_segments = [seg for seg in segments if len(seg) > 300]  # >5分钟
    
    # 4. 简单线性插值小间隔
    for seg in valid_segments:
        seg = interpolate_small_gaps(seg, max_gap=5)  # 最多插5秒
    
    # 5. 异常值过滤
    seg = filter_outliers(seg, altitude_range=(-2000, 50000))
    
    return valid_segments
```

### 模型架构考虑
```python
class TOWPredictor(nn.Module):
    def __init__(self):
        # 1. 轨迹编码器: 处理时序轨迹数据
        self.trajectory_encoder = TrajectoryEncoder(input_dim=13)
        
        # 2. 元数据编码器: 处理航班静态信息
        self.metadata_encoder = MetadataEncoder()
        
        # 3. 天气融合器: 整合起降和路径天气
        self.weather_fusion = WeatherFusion()
        
        # 4. 多模态融合: 结合轨迹、元数据、天气
        self.multimodal_fusion = MultiModalFusion()
        
        # 5. TOW预测器: 输出起飞重量
        self.tow_predictor = nn.Linear(hidden_dim, 1)
    
    def forward(self, trajectory, metadata, weather):
        """
        trajectory: [batch, seq_len, 13] 轨迹序列
        metadata: [batch, meta_dim] 航班元数据  
        weather: [batch, weather_dim] 天气信息
        return: [batch, 1] 预测的起飞重量
        """
        traj_features = self.trajectory_encoder(trajectory)
        meta_features = self.metadata_encoder(metadata)
        weather_features = self.weather_fusion(weather)
        
        combined = self.multimodal_fusion([traj_features, meta_features, weather_features])
        tow_pred = self.tow_predictor(combined)
        
        return tow_pred
```

### 训练数据组织
```python
# 每个训练样本 - 起飞重量预测任务
sample = {
    'flight_id': 248763775,
    'trajectory_sequence': trajectory_points,  # 完整轨迹数据
    'flight_metadata': {
        'aircraft_type': 'A320',
        'departure_airport': 'EGLL', 
        'arrival_airport': 'EICK',
        'flight_duration': 105,  # 分钟
        'flown_distance': 686,   # 海里
        'actual_offblock_time': '2022-01-01T13:46:00Z',
    },
    'weather_data': {
        'departure_weather': departure_metars,  # 起飞机场天气
        'arrival_weather': arrival_metars,      # 到达机场天气  
        'enroute_weather': trajectory_weather,  # 飞行路径天气
    },
    'target': {
        'tow': 54748.0  # 起飞重量 (预测目标)
    }
}
```

---

## 📈 结论与建议

### ✅ 数据集优势
1. **大规模真实数据**: 60万+航班, 高分辨率轨迹
2. **多维特征丰富**: 13维轨迹 + 天气 + 元数据
3. **标识清晰**: flight_id提供完美的航班边界
4. **时间连续性好**: 99.9%为1秒间隔

### ⚠️ 主要挑战
1. **时间间隔不均**: 少量大间隔缺失 (>1小时)
2. **插值数据损坏**: 不要使用插值后的数据
3. **异常值存在**: 需要合理的范围过滤
4. **跨天航班**: 需要特殊处理逻辑

### 🎯 最佳实践
1. **数据源**: 使用`rawtrajectories/`原始数据
2. **预处理**: 按大间隔分割, 过滤短段和异常值
3. **模型**: Transformer Decoder with relative position encoding
4. **训练**: 变长序列, 元数据融合, 分段处理

### 🔮 模型应用前景
- ✈️ **起飞重量预测**: 核心任务，基于航班信息和轨迹数据预测TOW
- 🛬 **着陆时间估计**: ETA准确性提升 
- 🌤️ **天气影响建模**: 风场对轨迹和燃油消耗的影响
- 🚦 **空管优化**: 冲突检测和路径规划
- ⛽ **燃油规划**: 基于TOW预测优化燃油装载
- 📊 **运营分析**: 航班性能评估和优化

### 🎯 **比赛任务说明**
**主要目标**: 预测航班的起飞重量 (`tow`)
- **输入数据**: 航班元数据 + 完整轨迹数据 + 天气数据
- **预测目标**: `challenge_set.csv` 中的 `tow` 字段
- **评估数据**: `final_submission_set.csv` (TOW为NaN，需要预测)
- **应用价值**: 燃油优化、载重规划、安全分析

---

## 📁 相关文件

本分析涉及的代码文件已保存在 `junguo_analysis_for_opensky2022/` 目录:

- `analyze_data.py` - 数据集基本信息分析
- `check_data_quality.py` - 数据质量深度检查  
- `analyze_time_gaps.py` - 时间间隔和缺失分析
- `analyze_flight_ids.py` - 航班标识系统分析
\n+- `QnA_groundspeed_weather_TAS.md` - 飞行轨迹字段与天气/TAS问题答疑（保留对话记忆）
- `verify_metadata_sources.py` - **数据来源验证工具** ⭐ 新增
- `run_all_analysis.py` - 一键运行所有分析

### 🔍 数据来源验证

运行 `verify_metadata_sources.py` 可以详细验证本报告中提到的所有数据来源：

```bash
cd junguo_analysis_for_opensky2022/
python verify_metadata_sources.py
```

该脚本会验证：
- ✅ 航班元数据的18个字段详情
- ✅ METAR天气数据的33个字段和5,976个气象站分布  
- ✅ 机场信息的19个字段和502个机场详情
- ✅ 轨迹数据中的4个天气字段特征
- ✅ 提交集格式和预测目标确认

### ⚡ 高性能数据质量检测

**新增工具**: `check_data_quality_polars.py` - 基于Polars的高性能分析工具

**特性**:
- 🚀 充分利用80核CPU和512GB内存
- 📊 支持全量365天数据分析（~280GB）
- ⏱️ 极速处理：2天数据仅需2-5秒
- 🎯 可配置日期范围和文件数量限制

**快速开始**:
```bash
# 测试模式 - 处理前5天
python check_data_quality_polars.py --limit 5

# 便捷脚本
chmod +x run_quality_check.sh
./run_quality_check.sh -l 5

# 全量分析（需10-20分钟）
./run_quality_check.sh
```

**核心发现**:
- ✅ 原始数据质量优秀：缺失值仅0.326%
- ⚠️ 插值数据质量下降：缺失值14-31%
- 💡 推荐使用原始轨迹数据进行机器学习

详细说明见：[PERFORMANCE_GUIDE.md](PERFORMANCE_GUIDE.md)

### 地区分布统计（欧洲 vs 美国）

新增脚本：`analyze_regions.py`

用途：
- 统计原始飞行轨迹主要分布在哪个地区（欧洲、美国、其他）。
- 统计全年总轨迹数（按 `flight_id` 唯一计）。

方法：
- 使用 Polars 懒加载与流式 groupby，分两步执行：
  1) 对每日 parquet 做 per-file 聚合，输出小表至 `tmp_region_counts/`
  2) 汇总所有小表得到全局结果（航班级、点级双口径）
- 地理范围采用经纬度近似边界（US=本土+阿拉斯加+夏威夷，EU=纬度[35,72] 经度[-25,45]）

安装依赖：
```
pip install polars pyarrow
```

运行示例：
```
python junguo_analysis_for_opensky2022/analyze_regions.py \
  --raw-dir opensky_2024_PRC_dataset/rawtrajectories \
  --tmp-dir junguo_analysis_for_opensky2022/tmp_region_counts \
  --out junguo_analysis_for_opensky2022/region_summary \
  --majority-threshold 0.0
```

输出：
- `region_summary_per_flight.csv`：每个 flight_id 的地区分类和计数
- `region_summary_summary.csv` / `.json`：总览统计（按航班/按点）与主区域结论

### 一键运行脚本

为了后续复用，提供了一个便捷脚本：

- 脚本：`junguo_analysis_for_opensky2022/run_region_analysis.sh`
- 作用：激活 conda 环境、配置线程数，并运行 `analyze_regions.py`

使用示例：

```bash
# 快速试跑前 2 天
bash junguo_analysis_for_opensky2022/run_region_analysis.sh -l 2

# 全量运行，按 60% 多数判定地区
bash junguo_analysis_for_opensky2022/run_region_analysis.sh -m 0.6

# 覆盖默认路径与线程数
bash junguo_analysis_for_opensky2022/run_region_analysis.sh \
  -r opensky_2024_PRC_dataset/rawtrajectories \
  -t junguo_analysis_for_opensky2022/tmp_region_counts \
  -o junguo_analysis_for_opensky2022/region_summary \
  -j 80
```

可选参数：
- `-r <raw_dir>`：原始 parquet 目录（默认 `opensky_2024_PRC_dataset/rawtrajectories`）
- `-t <tmp_dir>`：中间 per-file 小表目录（默认 `junguo_analysis_for_opensky2022/tmp_region_counts`）
- `-o <out_prefix>`：输出前缀（默认 `junguo_analysis_for_opensky2022/region_summary`）
- `-m <threshold>`：多数阈值（0~1，默认 `0.0`）
- `-l <limit>`：仅处理前 N 天（默认全量）
- `-j <threads>`：`POLARS_MAX_THREADS`（默认 `80`）
- `-e <conda_env>`：Conda 环境名（默认 `opensky`）

仅汇总（不重算 daily partials）

已有逐日小表后，可仅重算汇总（修改阈值或格式时很方便）：

```bash
bash junguo_analysis_for_opensky2022/summarize_region_analysis.sh

# 或指定参数，例如阈值与输出前缀
bash junguo_analysis_for_opensky2022/summarize_region_analysis.sh -m 0.6 -o junguo_analysis_for_opensky2022/region_summary
```

## 🚀 轨迹预测任务可行性分析

基于可行性分析脚本 `check_trajectory_feasibility.py` 的结果，本数据集可以用于**多种轨迹预测任务**：

### 核心发现

✅ **TOW数据完整性**: 挑战集中所有369,013个航班都有完整的TOW（起飞重量）数据  
✅ **轨迹数据覆盖**: 每日轨迹文件包含数万航班，如2022-01-01有531个航班  
✅ **多模态特征**: 轨迹+天气+元数据三重特征组合，适合复杂预测模型  

### 可行的预测任务

#### 1. 条件轨迹生成
- **输入**: TOW + 起降机场 + 航班类型 + 天气条件
- **输出**: 完整飞行轨迹序列 (lat, lon, altitude, groundspeed)
- **优势**: 高质量特征组合，天气数据增强泛化能力

#### 2. 序列到序列预测
- **输入**: 部分轨迹序列 + TOW + 天气
- **输出**: 后续轨迹点预测
- **应用**: 实时飞行路径预测和优化

#### 3. 多任务学习
- **主任务**: 轨迹预测
- **辅助任务**: TOW估计、天气影响建模
- **优势**: 共享表示学习，提升模型鲁棒性

### 数据集成策略

```python
# 推荐的数据加载流程
import pandas as pd

# 1. 加载目标航班的TOW数据
tow_data = pd.read_csv('opensky_2024_PRC_dataset/challenge_set.csv')

# 2. 加载对应日期的轨迹数据
trajectory_data = pd.read_parquet('opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet')

# 3. 基于flight_id关联数据
merged_data = pd.merge(trajectory_data, tow_data, on='flight_id', how='inner')

# 4. 添加天气特征
# trajectory_data中已包含4个天气字段: u_component_of_wind, v_component_of_wind, 
# temperature, specific_humidity
```

### 模型架构建议

🔄 **Transformer架构**:
- 编码器: 处理多模态输入 (TOW + 天气 + 机场信息)
- 解码器: 生成轨迹序列，注意力机制捕获时空依赖

🧠 **混合模型**:
- CNN: 提取天气空间特征
- LSTM/GRU: 建模轨迹时序动态  
- MLP: 融合TOW等标量特征

### 验证建议

运行可行性分析脚本查看详细统计：

```bash
cd junguo_analysis_for_opensky2022/
python check_trajectory_feasibility.py
```

该脚本提供：
- TOW数据完整性检查
- 轨迹数据可用性统计  
- 特征维度和质量评估
- 具体的数据集成指导

---

**作者**: SongJunguo  
**最后更新**: 2025年1月23日  
**版本**: v1.2 - 新增轨迹预测任务可行性分析
