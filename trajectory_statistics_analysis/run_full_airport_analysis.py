#!/usr/bin/env python3
"""
运行完整的机场完整性分析
使用所有可用的轨迹文件进行分析
"""

import sys
from pathlib import Path
from optimized_airport_analysis import OptimizedAirportAnalyzer

def main():
    """运行完整的机场完整性分析"""
    print("=" * 60)
    print("开始完整的机场完整性分析")
    print("=" * 60)
    
    # 设置数据和输出目录
    data_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly")
    output_dir = Path("optimized_analysis")
    
    # 创建分析器实例
    analyzer = OptimizedAirportAnalyzer(data_dir, output_dir)
    
    # 运行完整分析（不限制文件数量）
    analyzer.run_analysis(max_files=None)
    
    print("\n" + "=" * 60)
    print("完整的机场完整性分析已完成")
    print("=" * 60)

if __name__ == "__main__":
    main()