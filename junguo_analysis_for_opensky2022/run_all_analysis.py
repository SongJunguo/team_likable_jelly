#!/usr/bin/env python3
"""
OpenSky 2022 数据集完整分析脚本
运行所有分析并生成报告

使用方法:
    python run_all_analysis.py
"""

import os
import sys
import subprocess
from datetime import datetime

def run_script(script_name, description):
    """运行分析脚本并捕获输出"""
    print(f"\n{'='*60}")
    print(f"🔍 {description}")
    print(f"脚本: {script_name}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run([sys.executable, script_name], 
                              capture_output=True, text=True, 
                              cwd=os.path.dirname(os.path.abspath(__file__)))
        
        if result.returncode == 0:
            print(result.stdout)
            if result.stderr:
                print(f"警告: {result.stderr}")
            return True, result.stdout
        else:
            print(f"❌ 脚本执行失败:")
            print(result.stderr)
            return False, result.stderr
    except Exception as e:
        print(f"❌ 执行错误: {e}")
        return False, str(e)

def main():
    """主函数"""
    print("🚀 OpenSky 2022 数据集深度分析")
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 确保在正确的目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # 检查数据目录
    data_dir = "../opensky_2024_PRC_dataset"
    if not os.path.exists(data_dir):
        print(f"❌ 数据目录不存在: {data_dir}")
        print("请确保在正确的目录运行此脚本")
        return
    
    # 分析脚本列表
    analyses = [
        ("analyze_data.py", "数据集基本信息分析"),
        ("check_data_quality.py", "数据质量深度检查"),
        ("analyze_time_gaps.py", "时间间隔和缺失分析"),
        ("analyze_flight_ids.py", "航班标识系统分析"),
        ("verify_metadata_sources.py", "数据来源验证"),
    ]
    
    results = {}
    success_count = 0
    
    # 运行所有分析
    for script, description in analyses:
        if os.path.exists(script):
            success, output = run_script(script, description)
            results[script] = {'success': success, 'output': output}
            if success:
                success_count += 1
        else:
            print(f"⚠️  脚本不存在: {script}")
            results[script] = {'success': False, 'output': f"文件不存在: {script}"}
    
    # 生成总结报告
    print(f"\n{'='*60}")
    print("📊 分析完成总结")
    print(f"{'='*60}")
    print(f"总分析脚本: {len(analyses)}")
    print(f"成功执行: {success_count}")
    print(f"失败执行: {len(analyses) - success_count}")
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 显示各脚本状态
    print(f"\n📋 各脚本执行状态:")
    for script, description in analyses:
        status = "✅" if results.get(script, {}).get('success', False) else "❌"
        print(f"  {status} {script}: {description}")
    
    print(f"\n📚 详细分析报告请查看: README.md")
    print(f"🔧 分析代码位于当前目录: {script_dir}")

if __name__ == "__main__":
    main()
