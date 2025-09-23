# 轨迹数据插值分析工具集

本目录包含用于分析OpenSky轨迹数据缺失率和质量的工具集，专门为轨迹插值预处理而设计。

## 🎯 核心功能

### 1. 快速轨迹缺失率分析 (quick_trajectory_analysis.py)
**主要程序** - 高效分析大规模轨迹数据的缺失情况

#### ✅ 成功运行命令
```bash
conda activate opensky && python quick_trajectory_analysis.py \
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

### 主要分析程序
1. **quick_trajectory_analysis.py** - 快速缺失率分析 (推荐使用)
2. **enhanced_trajectory_analysis.py** - 增强版分析 (功能更全面)
3. **analyze_missing_data_multiprocess.py** - 多进程缺失数据分析

### 辅助工具
4. **count_total_trajectories.py** - 统计轨迹总数
5. **count_total_trajectories_multiprocess.py** - 多进程版本
6. **analyze_time_gaps.py** - 时间间隔分析
7. **analyze_interpolation_logic.py** - 插值逻辑分析

### 测试程序
8. **test_enhanced_analysis.py** - 增强分析测试

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

## ⚠️ 注意事项

1. **进程数设置**: 推荐使用30个进程，避免"process pool terminated abruptly"错误
2. **内存使用**: 全年数据分析需要约2-3GB内存
3. **存储空间**: 输出文件约900MB，确保有足够磁盘空间
4. **运行时间**: 全年数据分析约需12-15分钟

## 📞 技术支持

如遇到问题，请检查：
1. conda环境是否正确激活 (`conda activate opensky`)
2. 数据目录路径是否正确
3. 系统资源是否充足
4. 进程数是否合理设置

---
*最后更新: 2025-09-22*
*数据版本: OpenSky 2024 PRC Dataset (classic__1e-2_interpolated_trajectories)*