# 轨迹数据插值分析工具集

本目录包含用于分析OpenSky轨迹数据缺失率和质量的工具集，专门为轨迹插值预处理而设计。

## 🎯 核心功能

### 1. 快速轨迹缺失率分析 (All_trajectory_NaN_analysis.py)
**主要程序** - 高效分析大规模轨迹数据的缺失情况

#### ✅ 成功运行命令
```bash
conda activate opensky && python All_trajectory_NaN_analysis.py \
  --data_dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories \
  --sample_percentage 1.0 \
  --max_workers 30 \
  --max_files 365 \
  --output_dir full_365_analysis_output_v2
```

#### 📊 分析结果 (2025-09-22)
- **总轨迹数**: 979,680条 (全年365天完整数据)
- **处理时间**: 727.6秒 (约12分钟)
- **数据质量分布**:
  - Good: 443,104 (45.2%)
  - Excellent: 430,342 (43.9%)
  - Fair: 88,536 (9.0%)
  - Poor: 17,698 (1.8%)

#### 🔧 命令参数说明
- `--data_dir`: 轨迹数据目录路径
- `--sample_percentage`: 抽样比例 (1.0 = 100%完整数据)
- `--max_workers`: 并行进程数 (推荐30，避免进程池错误)
- `--max_files`: 最大处理文件数 (365 = 全年数据)
- `--output_dir`: 输出结果目录

## 📁 输出文件说明

### 1. trajectory_analysis.csv (653MB)
轨迹汇总数据，便于Excel打开和分析

### 2. trajectory_analysis.parquet (252MB)
高效存储格式，推荐用于大数据分析

### 3. analysis_summary.txt
简要分析报告，包含数据概览和质量分布

## 📋 CSV/Parquet 文件列说明

### 基本信息
- `flight_id`: 航班轨迹唯一标识符
- `total_points`: 轨迹总点数
- `duration_minutes`: 轨迹持续时间(分钟)

### 关键字段缺失率统计
对每个关键字段 (`latitude`, `longitude`, `altitude`, `groundspeed`, `track`, `vertical_rate`)，包含以下列：

#### 缺失率指标
- `{field}_missing_rate`: 缺失率百分比
- `{field}_missing_count`: 缺失点数量
- `{field}_valid_count`: 有效点数量

#### 缺失模式分析
- `{field}_max_window`: 最大连续缺失窗口大小
- `{field}_num_windows`: 缺失窗口数量
- `{field}_head_missing`: 轨迹开头是否缺失 (True/False)
- `{field}_tail_missing`: 轨迹结尾是否缺失 (True/False)

#### 数据范围统计
- `{field}_min_value`: 最小值
- `{field}_max_value`: 最大值
- `{field}_mean_value`: 平均值
- `{field}_std_value`: 标准差

### 质量评估
- `quality_score`: 综合质量分数 (0-100)
- `quality_level`: 质量等级 (Excellent/Good/Fair/Poor)

## 🛠️ 程序文件说明

### 核心分析程序
1. **All_trajectory_NaN_analysis.py** - 快速缺失率分析 (推荐使用，生成CSV/Parquet结果)
2. **get_high_quality_trajectories_id.py** - 核心分析工具，生成高质量轨迹ID列表
3. **regenerate_complete_dataset.py** - 高质量数据集重新生成工具
4. **generate_final_dataset.py** - 最终训练数据集生成工具 检测插值后的轨迹是否还有NaN值，如有则移除整条轨迹
5. **review_trajectory_selection_and_interpolation.py** - 综合分析报告，问题诊断和解决方案

### 辅助工具
4. **count_total_trajectories.py** - 统计轨迹总数
5. **count_total_trajectories_multiprocess.py** - 多进程版本

## 完整数据处理流程

本项目采用以下完整的数据处理流程来生成高质量的轨迹训练数据集：

### 1. 轨迹质量分析 (All_trajectory_NaN_analysis.py)
- **功能**: 分析所有轨迹的NaN值分布和数据质量
- **输出**: `trajectory_analysis.parquet` - 包含每条轨迹的质量评估指标
- **运行**: `python All_trajectory_NaN_analysis.py`

### 2. 高质量轨迹ID提取 (get_high_quality_trajectories_id.py)
- **功能**: 基于质量分析结果，筛选出高质量轨迹的ID列表
- **输入**: `trajectory_analysis.parquet`
- **输出**: `high_quality_flight_ids.txt` - 高质量轨迹ID列表
- **运行**: `python get_high_quality_trajectories_id.py`

### 3. 高质量数据集重新生成 (regenerate_complete_dataset.py)
- **功能**: 根据高质量轨迹ID，从原始滤波数据中提取轨迹，进行掐头去尾和插值处理
- **输入**: `high_quality_flight_ids.txt` 和原始滤波轨迹数据
- **处理步骤**:
  - 提取指定ID的轨迹数据
  - 移除头尾的NaN值（基于经纬度有效性）
  - 对所有字段进行线性插值（track字段特殊处理角度连续性）
- **输出**: `complete_high_quality_trajectories/` 目录下的插值处理后数据
- **运行**: `python regenerate_complete_dataset.py`

### 4. 最终数据集生成 (generate_final_dataset.py)
- **功能**: 合并所有插值后的高质量轨迹，生成最终训练数据集
- **输入**: `complete_high_quality_trajectories/` 目录下的所有插值数据
- **质量检查**: 检测插值后的轨迹是否还有NaN值，如有则移除整条轨迹（因为有两个轨迹，经纬高完全没有NaN值，但是垂直速度列完全都是nan值，无法插值，所以增加此功能）
- **输出**: `final_training_dataset.parquet` - 最终无NaN值的训练数据集
- **运行**: `python generate_final_dataset.py`

### 流程总结
```
原始数据 → 质量分析 → 高质量ID筛选 → 数据重新生成(掐头去尾+插值) → 最终数据集(NaN检查+合并)
```

### 验证工具
6. **check_nan_values.py** - 验证插值数据是否包含NaN值
   - 检查插值处理后数据的质量
   - 统计各列的缺失值数量
   - 生成详细的验证报告
   
7. **validate_trajectory_count.py** - 验证轨迹数量是否足够
   - 统计最终数据集的轨迹数量
   - 计算数据处理的达成率
   - 评估数据集完整性

### 已弃用程序 (功能重复，不推荐使用)
- ~~**enhanced_trajectory_analysis.py**~~ - 功能与quick_trajectory_analysis.py重复
- ~~**analyze_missing_data_multiprocess.py**~~ - 功能与quick_trajectory_analysis.py重复  
- ~~**analyze_time_gaps.py**~~ - 功能与quick_trajectory_analysis.py重复
- ~~**analyze_interpolation_logic.py**~~ - 理论分析，实际价值有限

## 📈 关键发现

### 数据质量概况
- **优秀数据占比**: 89.1% (Excellent + Good)
- **需要插值数据**: 10.9% (Fair + Poor)
- **关键字段缺失率**:
  - 位置信息 (lat/lon/alt): ~14.8%
  - 速度信息 (groundspeed/vertical_rate): ~21.6%
  - 航向信息 (track): 100% (完全缺失)

### 插值建议
1. **优先插值字段**: latitude, longitude, altitude
2. **次要插值字段**: groundspeed, vertical_rate
3. **需要重建字段**: track (可从位置变化计算)

## 🚀 使用建议

### 1. 快速分析 (推荐)
```bash
# 分析全年数据
python quick_trajectory_analysis.py --data_dir [数据目录] --max_files 365 --max_workers 30

# 测试分析 (50个文件)
python quick_trajectory_analysis.py --data_dir [数据目录] --max_files 50 --max_workers 20
```

### 2. 结果分析
```python
import pandas as pd

# 读取分析结果
df = pd.read_parquet('full_365_analysis_output_v2/trajectory_analysis.parquet')

# 查看质量分布
print(df['quality_level'].value_counts())

# 分析缺失率分布
print(df[['latitude_missing_rate', 'longitude_missing_rate', 'altitude_missing_rate']].describe())
```

### 3. 数据验证
```bash
# 验证插值数据质量 (检查NaN值)
python check_nan_values.py --data_dir [插值数据目录]

# 验证插值好的轨迹数量是否足够 高质量轨迹ID的txt文件 的轨迹数量
python validate_trajectory_count.py --data_dir [最终数据集目录] --target_count [预期轨迹数]
```

## ⚠️ 注意事项

1. **进程数设置**: 推荐使用30个进程，避免"process pool terminated abruptly"错误
2. **内存使用**: 全年数据分析需要约2-3GB内存
3. **存储空间**: 输出文件约900MB，确保有足够磁盘空间
4. **运行时间**: 全年数据分析约需12-15分钟

## 🎯 Perfect Trajectories统计工具 (count_perfect_trajectories.py)
**新增功能** - 专门统计perfect_trajectories目录下的轨迹数量和数据点

### ✅ 使用方法
```bash
conda activate opensky
cd /workspace/aircraft_trajectory/team_likable_jelly/junguo_analysis_for_opensky2022/analysis_for_interpolation
python count_perfect_trajectories.py
```

### 📊 统计结果 (2025-09-25)
- **总轨迹数**: 238,215条 (100%无缺失值的完美轨迹)
- **总数据点**: 1,497,169,274个
- **数据质量**: ✅ 100%无缺失值
- **文件大小**: 75.7 GB (365个parquet文件)
- **处理时间**: ~33秒 (16进程并行)

### 🔧 功能特性
- 🚀 多进程并行处理，充分利用80核心CPU
- 📊 全面统计：轨迹数量、数据点、文件大小
- 🎯 质量检查：各列缺失值统计
- 📏 轨迹分析：长度分布统计
- 📄 详细报告：生成时间戳报告文件
- ✅ 结果验证：与预期结果自动对比

### 📋 输出信息
- 文件处理统计（成功/失败文件数）
- 轨迹总数和数据点总数
- 数据质量评估（缺失值情况）
- 各列缺失值详细统计
- 轨迹长度分布（最短/最长/平均）
- 与预期结果的对比验证
- 生成详细的统计报告文件

## 📞 技术支持

如遇到问题，请检查：
1. conda环境是否正确激活 (`conda activate opensky`)
2. 数据目录路径是否正确
3. 系统资源是否充足
4. 进程数是否合理设置

---
*最后更新: 2025-09-25*
*数据版本: OpenSky 2024 PRC Dataset (perfect_trajectories)*