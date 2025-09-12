# OpenSky 2022 数据集分析工具包

本目录包含对OpenSky 2024 PRC Challenge数据集(2022年数据)的深度分析工具和报告。

## 📁 文件结构

```
junguo_analysis_for_opensky2022/
├── README.md                 # 📊 完整分析报告(主要文档)
├── PROJECT_INFO.md          # 📋 项目说明(本文件)
├── run_all_analysis.py      # 🚀 一键运行所有分析
├── analyze_data.py          # 📈 数据集基本信息分析
├── check_data_quality.py    # 🔍 数据质量深度检查
├── analyze_time_gaps.py     # ⏰ 时间间隔和缺失分析
└── analyze_flight_ids.py    # 🆔 航班标识系统分析
```

## 🚀 快速开始

### 环境要求
```bash
# 激活conda环境
conda activate opensky

# 确保已安装依赖
pandas, numpy, matplotlib, seaborn (通常环境中已有)
```

### 运行分析
```bash
# 进入分析目录
cd junguo_analysis_for_opensky2022/

# 运行所有分析(推荐)
python run_all_analysis.py

# 或者单独运行各个分析
python analyze_data.py
python check_data_quality.py
python analyze_time_gaps.py
python analyze_flight_ids.py
```

## 📊 主要发现

### 🎯 关键结论
1. **使用原始数据**: `rawtrajectories/` (✅推荐)
2. **避免插值数据**: `interpolated_trajectories/` (❌25%+缺失率)
3. **flight_id是完美标识**: 每航班唯一, 建议用作主键
4. **数据质量总体良好**: 99.9%时间连续性, 仅0.28%缺失

### ⚠️ 注意事项
- 插值处理引入了严重的数据质量问题
- 存在少量大时间间隔缺失(最长5+小时)
- 需要按间隔分割轨迹并过滤异常值
- 跨天航班需要特殊处理(132个/天)

## 🤖 模型训练建议

### 数据预处理流程
```python
1. 使用原始轨迹数据 (rawtrajectories/)
2. 按flight_id分组
3. 按大间隔(>60s)分割轨迹段  
4. 过滤短段(<5min)和异常值
5. 轻量插值小间隔(<5s)
```

### Decoder-only模型设计
```python
- 输入: 历史轨迹序列 (13维特征)
- 输出: 未来轨迹预测
- 编码: 相对时间位置编码
- 融合: 航班元数据(机型/航线)
- 处理: 变长序列, 分段训练
```

## 📈 数据统计摘要

| 指标 | 数值 | 说明 |
|------|------|------|
| 总航班数/天 | 1,708 | 基于2022-01-01 |
| 年度估计航班 | 62万+ | 365天 × 1,708 |
| 轨迹点/航班 | 6,000+ | 平均值, 约1-2小时飞行 |
| 采样频率 | 1秒 | 99.9%的数据点 |
| 数据完整率 | 99.72% | 原始数据 |
| 跨天航班比例 | 7.7% | 132/1,708 |

## 🔧 技术细节

### 数据源路径
```
相对于team_likable_jelly根目录:
../opensky_2024_PRC_dataset/rawtrajectories/2022-XX-XX.parquet
../opensky_2024_PRC_dataset/METARs.parquet
../opensky_2024_PRC_dataset/challenge_set.csv
```

### 关键字段
```python
# 轨迹数据(13维)
'flight_id', 'timestamp', 'latitude', 'longitude', 'altitude',
'groundspeed', 'track', 'vertical_rate', 'icao24',
'u_component_of_wind', 'v_component_of_wind', 
'temperature', 'specific_humidity'

# 元数据(18维)  
'flight_id', 'date', 'callsign', 'adep', 'ades',
'aircraft_type', 'airline', 'tow', ...
```

## 👨‍💻 作者信息

**分析者**: SongJunguo  
**创建时间**: 2025年9月11日  
**目的**: 为OpenSky数据集上的飞行轨迹预测模型开发提供数据洞察

## 📖 更多信息

- 完整分析报告: `README.md` 
- OpenSky官网: https://opensky-network.org/
- PRC Challenge: https://ansperformance.eu/study/data-challenge/

---

**使用提示**: 建议首先阅读`README.md`获取完整分析结果, 然后根据需要运行具体的分析脚本。
