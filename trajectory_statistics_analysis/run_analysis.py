#!/usr/bin/env python3
"""
轨迹统计分析主程序
整合统计和可视化功能的一站式脚本
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

def run_command(command, description):
    """
    运行命令并处理结果
    
    Args:
        command: 要执行的命令
        description: 命令描述
    """
    print(f"🚀 {description}...")
    print(f"执行命令: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(f"✅ {description}完成")
        if result.stdout:
            print("输出:")
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description}失败")
        print(f"错误信息: {e.stderr}")
        return False

def find_available_data_directories():
    """
    查找可用的数据目录
    
    Returns:
        list: 可用目录列表
    """
    print("🔍 搜索可用的轨迹数据目录...")
    
    script_path = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/trajectory_statistics.py"
    command = ["python", script_path, "--list-dirs"]
    
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 搜索目录失败: {e.stderr}")
        return False

def run_trajectory_analysis(data_dir, max_workers=None):
    """
    运行轨迹统计分析
    
    Args:
        data_dir: 数据目录
        max_workers: 最大工作进程数
        
    Returns:
        bool: 是否成功
    """
    script_path = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/trajectory_statistics.py"
    output_dir = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output"
    
    command = ["python", script_path, "--data-dir", data_dir, "--output-dir", output_dir]
    
    if max_workers:
        command.extend(["--max-workers", str(max_workers)])
    
    return run_command(command, "轨迹统计分析")

def run_visualization(data_file=None):
    """
    运行可视化程序
    
    Args:
        data_file: 数据文件路径
        
    Returns:
        bool: 是否成功
    """
    script_path = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/visualize_trajectory_stats.py"
    output_dir = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output"
    
    if data_file:
        command = ["python", script_path, data_file, "--output-dir", output_dir]
    else:
        # 使用默认数据文件
        default_data_file = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output/trajectory_statistics.parquet"
        command = ["python", script_path, default_data_file, "--output-dir", output_dir]
    
    return run_command(command, "生成可视化图表")

def create_readme():
    """
    创建README文件
    """
    readme_path = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/README.md"
    
    readme_content = """# 轨迹统计分析工具

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
"""
    
    with open(readme_path, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    print(f"📄 README文件已创建: {readme_path}")

def main():
    parser = argparse.ArgumentParser(description='轨迹统计分析主程序')
    parser.add_argument('--data-dir', type=str, help='数据目录路径')
    parser.add_argument('--max-workers', type=int, help='最大工作进程数')
    parser.add_argument('--list-dirs', action='store_true', help='列出可用的数据目录')
    parser.add_argument('--full-analysis', action='store_true', help='运行完整分析（统计+可视化）')
    parser.add_argument('--stats-only', action='store_true', help='只运行统计分析')
    parser.add_argument('--viz-only', action='store_true', help='只运行可视化')
    
    args = parser.parse_args()
    
    # 创建输出目录
    output_dir = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/output"
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建README文件
    create_readme()
    
    if args.list_dirs:
        find_available_data_directories()
        return
    
    if not args.data_dir and not args.viz_only:
        print("❌ 请指定数据目录路径，或使用 --list-dirs 查看可用目录")
        print("💡 使用示例:")
        print("  python run_analysis.py --list-dirs")
        print("  python run_analysis.py --data-dir /path/to/data --full-analysis")
        return
    
    success = True
    
    # 运行统计分析
    if not args.viz_only:
        print("=" * 60)
        print("🔢 开始轨迹统计分析")
        print("=" * 60)
        
        if not run_trajectory_analysis(args.data_dir, args.max_workers):
            success = False
            print("❌ 统计分析失败，停止后续处理")
            return
    
    # 运行可视化
    if not args.stats_only and success:
        print("\n" + "=" * 60)
        print("🎨 开始生成可视化图表")
        print("=" * 60)
        
        data_file = os.path.join(output_dir, "trajectory_statistics.parquet")
        if os.path.exists(data_file) or args.viz_only:
            if not run_visualization(data_file if os.path.exists(data_file) else None):
                success = False
                print("❌ 可视化生成失败")
        else:
            print("⚠️ 统计数据文件不存在，跳过可视化")
    
    if success:
        print("\n" + "=" * 60)
        print("🎉 分析完成！")
        print("=" * 60)
        print(f"📁 输出目录: {output_dir}")
        print("📊 生成的文件:")
        
        # 列出生成的文件
        if os.path.exists(output_dir):
            for file in os.listdir(output_dir):
                file_path = os.path.join(output_dir, file)
                if os.path.isfile(file_path):
                    size_mb = os.path.getsize(file_path) / (1024 * 1024)
                    print(f"  - {file} ({size_mb:.2f} MB)")
    else:
        print("\n❌ 分析过程中出现错误，请检查日志")

if __name__ == "__main__":
    main()