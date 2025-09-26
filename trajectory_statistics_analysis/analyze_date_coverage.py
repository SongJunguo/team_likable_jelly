#!/usr/bin/env python3
"""
分析日期覆盖范围和数据集关系
理解为什么轨迹文件中的flight_id在官方CSV中找不到
"""

import pandas as pd
import numpy as np
from pathlib import Path
import os
from datetime import datetime, date
import re

def analyze_csv_date_coverage():
    """分析官方CSV文件的日期覆盖范围"""
    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
    
    csv_files = [
        "challenge_set.csv",
        "final_submission_set.csv", 
        "submission_set.csv"
    ]
    
    print("=" * 60)
    print("官方CSV文件日期覆盖分析")
    print("=" * 60)
    
    for csv_file in csv_files:
        file_path = base_dir / csv_file
        if file_path.exists():
            df = pd.read_csv(file_path)
            print(f"\n{csv_file}:")
            print(f"  总记录数: {len(df)}")
            print(f"  唯一flight_id数: {df['flight_id'].nunique()}")
            
            if 'date' in df.columns:
                dates = pd.to_datetime(df['date'])
                print(f"  日期范围: {dates.min().date()} 到 {dates.max().date()}")
                print(f"  覆盖天数: {(dates.max() - dates.min()).days + 1}")
                
                # 统计每个日期的航班数
                date_counts = dates.dt.date.value_counts().sort_index()
                print(f"  平均每天航班数: {date_counts.mean():.0f}")
                print(f"  最多一天航班数: {date_counts.max()}")
                print(f"  最少一天航班数: {date_counts.min()}")
                
                # 显示前几个日期的数据
                print("  前5个日期的航班数:")
                for date_val, count in date_counts.head().items():
                    print(f"    {date_val}: {count}")
            else:
                print("  没有date列")

def analyze_trajectory_date_coverage():
    """分析轨迹文件的日期覆盖范围"""
    traj_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories")
    
    if not traj_dir.exists():
        print(f"轨迹目录不存在: {traj_dir}")
        return
    
    parquet_files = list(traj_dir.glob("*.parquet"))
    print(f"\n=" * 60)
    print("轨迹文件日期覆盖分析")
    print("=" * 60)
    print(f"找到 {len(parquet_files)} 个轨迹文件")
    
    # 从文件名提取日期
    file_dates = []
    for file_path in parquet_files:
        # 假设文件名格式为 YYYY-MM-DD.parquet
        match = re.search(r'(\d{4}-\d{2}-\d{2})', file_path.name)
        if match:
            try:
                file_date = datetime.strptime(match.group(1), '%Y-%m-%d').date()
                file_dates.append(file_date)
            except ValueError:
                pass
    
    if file_dates:
        file_dates.sort()
        print(f"轨迹文件日期范围: {min(file_dates)} 到 {max(file_dates)}")
        print(f"覆盖天数: {(max(file_dates) - min(file_dates)).days + 1}")
        print(f"实际文件数: {len(file_dates)}")
        
        # 检查缺失的日期
        all_dates = pd.date_range(min(file_dates), max(file_dates), freq='D').date
        missing_dates = set(all_dates) - set(file_dates)
        if missing_dates:
            print(f"缺失的日期数: {len(missing_dates)}")
            if len(missing_dates) <= 10:
                print("缺失的日期:", sorted(missing_dates))
    
    return file_dates

def analyze_specific_date_matching():
    """分析特定日期的匹配情况"""
    print(f"\n=" * 60)
    print("特定日期匹配分析")
    print("=" * 60)
    
    # 选择一个轨迹文件进行详细分析
    traj_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories")
    sample_file = traj_dir / "2022-01-01.parquet"
    
    if not sample_file.exists():
        # 找第一个可用的文件
        parquet_files = list(traj_dir.glob("*.parquet"))
        if parquet_files:
            sample_file = parquet_files[0]
        else:
            print("没有找到轨迹文件")
            return
    
    print(f"分析文件: {sample_file.name}")
    
    try:
        # 读取轨迹文件
        traj_df = pd.read_parquet(sample_file)
        traj_flight_ids = set(traj_df['flight_id'].astype(str))
        print(f"轨迹文件中的flight_id数量: {len(traj_flight_ids)}")
        
        # 从文件名提取日期
        match = re.search(r'(\d{4}-\d{2}-\d{2})', sample_file.name)
        if match:
            file_date = match.group(1)
            print(f"文件日期: {file_date}")
            
            # 检查官方CSV中该日期的数据
            base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
            csv_files = ["challenge_set.csv", "final_submission_set.csv", "submission_set.csv"]
            
            for csv_file in csv_files:
                file_path = base_dir / csv_file
                if file_path.exists():
                    df = pd.read_csv(file_path)
                    if 'date' in df.columns:
                        # 筛选该日期的数据
                        date_df = df[df['date'] == file_date]
                        if len(date_df) > 0:
                            csv_flight_ids = set(date_df['flight_id'].astype(str))
                            matched = traj_flight_ids.intersection(csv_flight_ids)
                            match_rate = len(matched) / len(traj_flight_ids) * 100 if traj_flight_ids else 0
                            print(f"  {csv_file} ({file_date}): {len(date_df)} 条记录, 匹配 {len(matched)}/{len(traj_flight_ids)} ({match_rate:.1f}%)")
                        else:
                            print(f"  {csv_file}: 该日期无数据")
    
    except Exception as e:
        print(f"分析文件时出错: {e}")

def main():
    """主函数"""
    analyze_csv_date_coverage()
    trajectory_dates = analyze_trajectory_date_coverage()
    analyze_specific_date_matching()
    
    print(f"\n=" * 60)
    print("总结")
    print("=" * 60)
    print("可能的原因:")
    print("1. 官方CSV文件可能只包含特定类型的航班（如比赛用的航班）")
    print("2. 轨迹文件包含所有航班，而CSV文件是筛选后的子集")
    print("3. 数据集的时间范围可能不完全重叠")
    print("4. 某些flight_id可能在数据处理过程中被过滤掉了")

if __name__ == "__main__":
    main()