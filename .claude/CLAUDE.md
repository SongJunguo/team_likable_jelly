# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

这是一个飞行轨迹数据分析和机器学习项目，目标是预测飞机起飞重量（TOW - Take Off Weight）。项目基于2022年OpenSky全年ADS-B轨迹数据（约60万航班，4.2亿轨迹点），使用LightGBM进行预测。

## 常用命令

### 环境激活
- **数据处理**: `conda activate opensky`
- **深度学习**: `conda activate Time-MoE`

### 完整数据处理流程
```bash
# 需先在CONFIG文件中设置FOLDER_DATA变量
make download          # 下载METAR天气数据
make cleantrajectories # 过滤和插值轨迹（使用-j4可并行4进程）
make features          # 提取特征（爬升、巡航、风、天气）
make submissions       # 训练模型并生成预测结果
```

### 单步执行
```bash
# 过滤轨迹（去重、去异常值）
python filter_trajs.py

# 插值轨迹（三次样条）
python interpolate.py

# 特征提取
python feature_climbing.py      # 爬升特征
python feature_cruise_infos.py  # 巡航特征
python feature_wind_effect.py   # 风效应特征
python feature_weather_from_metars.py  # 天气特征

# 训练模型
python regression.py --seed 0
```

## 核心架构

### 数据处理流程
```
原始轨迹 → 过滤(filter_trajs.py) → 插值(interpolate.py) → 特征提取(feature_*.py) → 模型训练(regression.py) → 预测结果
```

### 关键模块

1. **轨迹预处理**
   - `filter_trajs.py` + `filterclassic.py`: 去除重复数据和异常值，使用FilterDerivative和FilterIsolated
   - `interpolate.py`: 三次样条插值（基于csaps库），20秒以上间隔不插值

2. **特征提取**
   - `feature_climbing.py`: 按48个高度切片（每1000英尺）提取爬升性能特征（ROCD、能量率、估算质量等）
   - `feature_cruise_infos.py`: 按20个时间百分比切片提取巡航特征（马赫数、高度等）
   - `feature_wind_effect.py`: 计算沿航迹的平均风投影
   - `feature_weather_from_metars.py`: 从METAR提取起降机场天气特征
   - `feature_thunder_from_metars.py`: 检测时空半径内的雷暴/雾

3. **模型训练**
   - `regression.py`: LightGBM模型训练和预测（50,000棵树）
   - `features.py`: 特征组织和处理框架
   - `sklearnutils.py`: 自定义sklearn转换器（分组标准化、质量标准化等）
   - `optimparam.py`: 超参数随机搜索优化
   - `polynomial.py`: 基于OpenAP物理模型的二阶多项式计算

4. **分析模块**
   - `trajectory_statistics_analysis/`: 轨迹统计和完整性分析（多进程并行）
   - `trajectory_stitching/`: 跨日期轨迹拼接（处理跨越午夜的航班）
   - `junguo_analysis_for_opensky2022/`: 深度数据质量分析（1300+行文档）
   - `analysis/`: 数据质量分析（跳变检测、缺失数据、插值质量评估）

### 数据目录结构

- **rawtrajectories/**: 原始ADS-B轨迹（365个日度parquet文件）
- **perfect_trajectories/**: 清洗后的高质量轨迹（76GB，365个文件）
- **classic_filtered_trajectories/**: 过滤后未插值的轨迹
- **classic__1e-2_interpolated_trajectories/**: 插值后的轨迹
- **flights/**: 航班元数据（challenge_set.parquet, final_submission_set.parquet）
- 特征目录:
  - `classic__1e-2__5_500_40_daltitude_1_-0.5_1_masses/`: 爬升特征
  - `classic__1e-2__20_cruise/`: 巡航特征
  - `classic__1e-2_wind/`: 风效应特征
  - `weather/`: 天气特征
  - `thunder/`: 雷暴特征

### 关键技术要点

1. **数据质量**: 原始数据优秀（缺失率0.28%，99.9%为1秒采样），避免使用插值数据（缺失率恶化到25%+）
2. **跨日期处理**: 7.7%的航班跨越午夜，需要基于icao24和位置连续性进行拼接
3. **目标变量缩放**: (TOW-EOW)/(MTOW-EOW)标准化，训练时使用(MTOW-EOW)²作为样本权重
4. **特征工程**: 物理模型集成（OpenAP）、飞机类型分组标准化、多模态特征融合
5. **模型集成**: 平均10-20个不同随机种子的模型提升性能（单模型RMSE 1612kg → 20模型1562kg）

## 编程规则

### 环境配置
- **数据处理**: 使用conda虚拟环境 `conda activate opensky`
- **深度学习训练和测试**: 使用conda虚拟环境 `conda activate Time-MoE`
- **运行环境**: Ubuntu 18.04容器，无sudo权限，默认root用户
- **硬件资源**: 80核心CPU，512GB内存，8张32GB显存的V100显卡，机械硬盘（无固态硬盘）

### 代码规范
- **Python数据处理**: 必须考虑多进程优化（充分利用80核CPU）
- **文件组织**:
  - 不要在项目主目录创建py文件
  - Python文件放在相关的子目录下，如果没有则创建目录
  - 测试用途的Python文件放在 `test_python/` 目录下，可以创建子目录区分不同目的测试文件

### 数据路径
- **清洗好的数据**: `/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories`（Parquet格式，365个文件，raw数据的子集）
- **原始数据**: `/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories`
- **过滤未插值数据**: `/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories`

### 开发流程
- **文档更新**: 更新代码后，必须更新对应的markdown文件，保持更改的可追踪性和可记忆性
- **代码修改流程**: 不要轻易直接更改现有代码，请先给出详细方案，等待确认后再更改代码

### 沟通规范
- **语言**: 使用中文回答所有问题

---

**注意**: 这些规则适用于所有对话和代码修改，请严格遵守。
