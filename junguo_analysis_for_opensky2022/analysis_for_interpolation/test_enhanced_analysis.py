#!/usr/bin/env python3
"""
增强版轨迹分析程序测试脚本
用于验证程序功能和性能
"""

import os
import sys
import subprocess
import time
from pathlib import Path

def test_enhanced_analysis():
    """测试增强版分析程序"""
    
    # 检查数据目录是否存在
    data_dir = "../../opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories"
    if not os.path.exists(data_dir):
        print(f"警告: 数据目录不存在: {data_dir}")
        print("请确保数据目录路径正确")
        return False
    
    # 创建测试输出目录
    test_output_dir = "test_enhanced_analysis_output"
    os.makedirs(test_output_dir, exist_ok=True)
    
    # 测试参数
    test_configs = [
        {
            "name": "小规模抽样测试",
            "args": [
                "--data_dir", data_dir,
                "--output_dir", f"{test_output_dir}/small_sample",
                "--sample_percentage", "1",  # 1%抽样
                "--max_trajectories_per_file", "10",
                "--workers", "4"
            ]
        },
        {
            "name": "中等规模测试",
            "args": [
                "--data_dir", data_dir,
                "--output_dir", f"{test_output_dir}/medium_sample",
                "--sample_percentage", "5",  # 5%抽样
                "--workers", "8"
            ]
        }
    ]
    
    script_path = "enhanced_trajectory_analysis.py"
    
    for config in test_configs:
        print(f"\n{'='*60}")
        print(f"运行测试: {config['name']}")
        print(f"{'='*60}")
        
        # 构建命令
        cmd = ["python", script_path] + config["args"]
        print(f"执行命令: {' '.join(cmd)}")
        
        # 记录开始时间
        start_time = time.time()
        
        try:
            # 运行程序
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5分钟超时
            
            # 记录结束时间
            end_time = time.time()
            duration = end_time - start_time
            
            print(f"执行时间: {duration:.2f} 秒")
            
            if result.returncode == 0:
                print("✅ 测试成功完成")
                print("标准输出:")
                print(result.stdout)
                
                # 检查输出文件
                output_dir = config["args"][config["args"].index("--output_dir") + 1]
                expected_files = [
                    "enhanced_trajectory_analysis_report.txt",
                    "trajectory_statistics.json",
                    "trajectory_quality_analysis.txt"
                ]
                
                print("\n检查输出文件:")
                for file_name in expected_files:
                    file_path = os.path.join(output_dir, file_name)
                    if os.path.exists(file_path):
                        file_size = os.path.getsize(file_path)
                        print(f"  ✅ {file_name}: {file_size:,} 字节")
                    else:
                        print(f"  ❌ {file_name}: 文件不存在")
                
            else:
                print("❌ 测试失败")
                print("错误输出:")
                print(result.stderr)
                print("标准输出:")
                print(result.stdout)
                
        except subprocess.TimeoutExpired:
            print("❌ 测试超时 (5分钟)")
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    print(f"\n{'='*60}")
    print("测试完成")
    print(f"测试结果保存在: {test_output_dir}")
    print(f"{'='*60}")
    
    return True

def check_dependencies():
    """检查依赖包"""
    required_packages = [
        'pandas', 'numpy', 'psutil', 'pyarrow'
    ]
    
    print("检查依赖包:")
    missing_packages = []
    
    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} (缺失)")
            missing_packages.append(package)
    
    if missing_packages:
        print(f"\n请安装缺失的包: pip install {' '.join(missing_packages)}")
        return False
    
    return True

def main():
    print("增强版轨迹分析程序测试")
    print("="*60)
    
    # 检查依赖
    if not check_dependencies():
        return
    
    # 检查主程序文件
    script_path = "enhanced_trajectory_analysis.py"
    if not os.path.exists(script_path):
        print(f"错误: 主程序文件不存在: {script_path}")
        return
    
    # 运行测试
    test_enhanced_analysis()

if __name__ == "__main__":
    main()