# 轨迹统计分析工具

这个工具包用于分析飞行轨迹数据的完整性和质量，包括轨迹统计、机场匹配分析和综合报告生成。

## 功能特性

- 🚀 多进程并行处理，充分利用服务器资源
- 📊 统计轨迹点数和飞行时长
- ✈️ 机场完整性分析，匹配起降机场信息
- 🎯 官方航班数据匹配分析
- 📈 生成多种可视化图表和综合报告
- 💾 结果保存为多种格式，便于后续分析

## 文件结构

```
trajectory_statistics_analysis/
├── trajectory_statistics.py           # 基础轨迹统计程序
├── visualize_trajectory_stats.py      # 轨迹统计可视化
├── optimized_airport_analysis.py      # 优化的机场完整性分析（主要）
├── run_full_airport_analysis.py       # 运行完整机场分析
├── analyze_trajectory_completeness.py # 轨迹完整性分析
├── match_official_flight_data.py      # 官方航班数据匹配
├── generate_comprehensive_report.py   # 综合报告生成器
├── FINAL_ANALYSIS_SUMMARY.md          # 最终分析总结
├── README.md                          # 说明文档
└── 分析结果目录/
    ├── output/                        # 基础统计输出
    ├── optimized_analysis/            # 机场分析结果
    ├── completeness_analysis/         # 完整性分析结果
    ├── matching_analysis/             # 匹配分析结果
    ├── comprehensive_analysis/        # 综合分析结果
    └── airport_completeness_analysis/ # 机场完整性分析结果
```

## 使用方法

### 1. 基础轨迹统计分析

```bash
# 运行基础轨迹统计
python trajectory_statistics.py --data-dir /path/to/trajectory/data

# 生成可视化图表
python visualize_trajectory_stats.py --data-file output/trajectory_statistics.parquet
```

### 2. 机场完整性分析（推荐）

```bash
# 运行优化的机场完整性分析
python run_full_airport_analysis.py

# 或者直接使用主分析脚本
python optimized_airport_analysis.py
```

### 3. 轨迹完整性分析

```bash
# 分析轨迹完整性
python analyze_trajectory_completeness.py --data-dir /path/to/trajectory/data
```

### 4. 官方航班数据匹配

```bash
# 匹配官方航班数据
python match_official_flight_data.py --data-dir /path/to/data
```

### 5. 生成综合报告

```bash
# 生成综合分析报告
python generate_comprehensive_report.py
```

## 主要脚本说明

### optimized_airport_analysis.py
- **功能**: 最新的机场完整性分析脚本
- **特点**: 使用筛选过的机场数据，支持多进程处理
- **输出**: 机场匹配报告、可视化图表、完整性统计

### trajectory_statistics.py
- **功能**: 基础轨迹统计分析
- **特点**: 统计轨迹点数、飞行时长等基本信息
- **输出**: 轨迹统计数据和汇总报告

### analyze_trajectory_completeness.py
- **功能**: 轨迹完整性深度分析
- **特点**: 基于高度模式识别不完整轨迹
- **输出**: 完整性分类和质量评估

### match_official_flight_data.py
- **功能**: 官方航班数据匹配
- **特点**: 匹配轨迹ID与官方航班信息
- **输出**: 匹配结果和一致性分析

### generate_comprehensive_report.py
- **功能**: 综合报告生成器
- **特点**: 整合所有分析结果
- **输出**: 综合质量评估和推荐

## 数据要求

- 轨迹数据: Parquet格式，包含经纬度、高度、时间戳等字段
- 机场数据: `opensky_2024_PRC_dataset/airports_tz.parquet`
- 官方航班数据: `challenge_set.csv`, `final_submission_set.csv`, `submission_set.csv`

## 输出说明

各分析脚本会在对应的输出目录中生成：
- 统计报告 (`.txt`)
- 可视化图表 (`.png`)
- 数据文件 (`.parquet`, `.txt`)
- 轨迹ID列表 (用于后续筛选)

## 注意事项

1. 确保在conda虚拟环境中运行: `conda activate opensky`
2. 脚本支持多进程处理，会自动利用服务器的多核CPU
3. 大数据集分析可能需要较长时间，建议使用`nohup`后台运行
4. 输出文件较大，注意磁盘空间

## 示例输出

### 机场完整性分析结果
```
=== 机场完整性分析报告 ===
分析文件数: 365
总轨迹数: 238,215
有官方机场信息的轨迹: 133,456 (56.0%)

起点机场匹配情况:
- 50公里内: 98.3%
- 100公里内: 99.1%
- 平均距离: 12.5公里

终点机场匹配情况:
- 50公里内: 99.3%
- 100公里内: 99.8%
- 平均距离: 8.7公里
```

### 轨迹完整性分析结果
```
=== 轨迹完整性分析 ===
总轨迹数: 238,215

完整性分类:
- 完整轨迹: 156,789 (65.8%)
- 可能完整: 45,123 (18.9%)
- 不完整轨迹: 36,303 (15.3%)

质量评估:
- 优秀质量: 89,456 (37.6%)
- 良好质量: 78,234 (32.8%)
- 一般质量: 70,525 (29.6%)
```

## 版本历史

- **v3.0** (当前): 优化的机场完整性分析，支持官方航班数据匹配
- **v2.0**: 添加轨迹完整性分析和综合报告功能
- **v1.0**: 基础轨迹统计和可视化功能

## 相关文档

- `FINAL_ANALYSIS_SUMMARY.md`: 最终分析结果总结
- 各输出目录中的报告文件: 详细分析结果
