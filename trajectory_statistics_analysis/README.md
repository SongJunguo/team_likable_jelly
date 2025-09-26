# 轨迹统计分析工具

这个工具包用于分析飞行轨迹数据，统计轨迹点数和时长，并生成可视化图表。

## 功能特性

- 🚀 多进程并行处理，充分利用服务器资源
- 📊 统计轨迹点数和飞行时长
- 💾 结果保存为parquet格式，便于后续分析
- 📈 生成多种可视化图表
- 🔍 自动搜索可用的数据目录

## 文件结构

```
trajectory_statistics_analysis/
├── trajectory_statistics.py      # 主统计程序
├── visualize_trajectory_stats.py # 可视化程序
├── run_analysis.py              # 一站式运行脚本
├── README.md                    # 说明文档
└── output/                      # 输出目录
    ├── trajectory_statistics.parquet    # 轨迹统计数据
    ├── summary_statistics.txt           # 汇总统计报告
    ├── trajectory_duration_distribution.png  # 时长分布图
    ├── trajectory_points_distribution.png    # 点数分布图
    ├── duration_points_correlation.png       # 相关性图
    └── visualization_report.txt              # 可视化报告
```

## 使用方法

### 1. 查看可用数据目录

```bash
python run_analysis.py --list-dirs
```

### 2. 运行完整分析（推荐）

```bash
python run_analysis.py --data-dir /path/to/trajectory/data --full-analysis
```

### 3. 只运行统计分析

```bash
python trajectory_statistics.py --data-dir /path/to/trajectory/data
```

### 4. 只生成可视化图表

```bash
python visualize_trajectory_stats.py --data-file output/trajectory_statistics.parquet
```

## 参数说明

- `--data-dir`: 轨迹数据目录路径
- `--max-workers`: 最大工作进程数（默认自动检测）
- `--output-dir`: 输出目录路径
- `--full-analysis`: 运行完整分析（统计+可视化）
- `--list-dirs`: 列出可用的数据目录

## 输出说明

### 统计结果
- 总轨迹数和数据点数
- 轨迹点数分布统计
- 飞行时长分布统计
- 处理性能信息

### 可视化图表
- **时长分布图**: 直方图、累积分布、箱线图、区间分布
- **点数分布图**: 直方图、对数尺度图、箱线图、区间分布
- **相关性图**: 时长与点数的相关性分析

## 性能优化

- 使用多进程并行处理，充分利用80核CPU
- 支持大规模数据处理（GB级别）
- 内存优化，避免数据溢出
- 进度显示，实时监控处理状态

## 注意事项

1. 确保在conda虚拟环境中运行：`conda activate opensky`
2. 数据目录应包含parquet格式的轨迹文件
3. 轨迹文件应包含`flight_id`列用于分组
4. 时间列可以是`timestamp`、`time`或`datetime`
5. 大数据集处理可能需要较长时间，请耐心等待

## 示例输出

```
📊 统计结果:
  处理文件数: 365
  总轨迹数: 238,215
  总数据点: 1,497,169,274
  平均每轨迹点数: 6287.5
  处理时间: 128.6 秒
  数据大小: 280.45 GB

📈 轨迹点数分布:
  最小值: 18
  最大值: 36871
  平均值: 6287.5
  中位数: 4735.0
  标准差: 4521.2

⏱️ 轨迹时长分布 (小时):
  最小值: 0.01
  最大值: 24.58
  平均值: 2.45
  中位数: 1.87
  标准差: 2.12
```
