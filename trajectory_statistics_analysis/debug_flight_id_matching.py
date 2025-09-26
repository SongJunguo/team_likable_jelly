#!/usr/bin/env python3
"""
调试flight_id匹配问题
分析为什么有些轨迹文件中的flight_id在官方CSV文件中找不到
"""

import pandas as pd
import numpy as np
from pathlib import Path
import os
from collections import defaultdict
import re

def load_official_flights():
    """加载所有官方航班数据"""
    base_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset")
    
    csv_files = [
        "challenge_set.csv",
        "final_submission_set.csv", 
        "submission_set.csv"
    ]
    
    all_flights = []
    flight_counts = {}
    
    for csv_file in csv_files:
        file_path = base_dir / csv_file
        if file_path.exists():
            df = pd.read_csv(file_path)
            print(f"加载 {csv_file}: {len(df)} 条记录")
            all_flights.append(df)
            flight_counts[csv_file] = set(df['flight_id'].astype(str))
        else:
            print(f"文件不存在: {file_path}")
    
    if all_flights:
        combined_df = pd.concat(all_flights, ignore_index=True)
        print(f"合并后总记录数: {len(combined_df)}")
        
        # 去重
        unique_df = combined_df.drop_duplicates(subset=['flight_id'])
        print(f"去重后记录数: {len(unique_df)}")
        
        # 分析重复情况
        flight_id_counts = combined_df['flight_id'].value_counts()
        duplicates = flight_id_counts[flight_id_counts > 1]
        if len(duplicates) > 0:
            print(f"发现 {len(duplicates)} 个重复的flight_id")
            print("前10个重复的flight_id:")
            print(duplicates.head(10))
        
        return set(unique_df['flight_id'].astype(str)), flight_counts
    
    return set(), {}

def analyze_trajectory_files(max_files=10):
    """分析轨迹文件中的flight_id"""
    traj_dir = Path("/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories")
    
    if not traj_dir.exists():
        print(f"轨迹目录不存在: {traj_dir}")
        return
    
    parquet_files = list(traj_dir.glob("*.parquet"))
    print(f"找到 {len(parquet_files)} 个轨迹文件")
    
    if max_files:
        parquet_files = parquet_files[:max_files]
        print(f"分析前 {max_files} 个文件")
    
    trajectory_flight_ids = set()
    file_flight_ids = {}
    
    for i, file_path in enumerate(parquet_files):
        try:
            df = pd.read_parquet(file_path)
            if 'flight_id' in df.columns:
                file_ids = set(df['flight_id'].astype(str).unique())
                trajectory_flight_ids.update(file_ids)
                file_flight_ids[file_path.name] = file_ids
                print(f"文件 {i+1}/{len(parquet_files)}: {file_path.name} - {len(file_ids)} 个唯一flight_id")
            else:
                print(f"文件 {file_path.name} 没有flight_id列")
        except Exception as e:
            print(f"处理文件 {file_path.name} 时出错: {e}")
    
    print(f"轨迹文件中总共有 {len(trajectory_flight_ids)} 个唯一flight_id")
    return trajectory_flight_ids, file_flight_ids

def compare_flight_ids():
    """比较官方CSV和轨迹文件中的flight_id"""
    print("=" * 60)
    print("开始flight_id匹配分析")
    print("=" * 60)
    
    # 加载官方航班数据
    print("\n1. 加载官方航班数据...")
    official_flight_ids, flight_counts = load_official_flights()
    print(f"官方CSV文件中有 {len(official_flight_ids)} 个唯一flight_id")
    
    # 分析轨迹文件
    print("\n2. 分析轨迹文件...")
    trajectory_flight_ids, file_flight_ids = analyze_trajectory_files(max_files=10)
    
    if not trajectory_flight_ids:
        print("没有找到轨迹文件中的flight_id")
        return
    
    # 比较匹配情况
    print("\n3. 匹配分析...")
    matched_ids = official_flight_ids.intersection(trajectory_flight_ids)
    unmatched_in_traj = trajectory_flight_ids - official_flight_ids
    unmatched_in_official = official_flight_ids - trajectory_flight_ids
    
    print(f"匹配的flight_id: {len(matched_ids)}")
    print(f"轨迹中有但官方CSV中没有的: {len(unmatched_in_traj)}")
    print(f"官方CSV中有但轨迹中没有的: {len(unmatched_in_official)}")
    
    match_rate = len(matched_ids) / len(trajectory_flight_ids) * 100 if trajectory_flight_ids else 0
    print(f"匹配率: {match_rate:.1f}%")
    
    # 分析未匹配的flight_id
    if unmatched_in_traj:
        print(f"\n4. 分析轨迹中未匹配的flight_id (前20个):")
        sample_unmatched = list(unmatched_in_traj)[:20]
        for flight_id in sample_unmatched:
            print(f"  {flight_id}")
            
        # 检查是否是格式问题
        print("\n5. 检查flight_id格式...")
        sample_official = list(official_flight_ids)[:10]
        sample_traj = list(trajectory_flight_ids)[:10]
        
        print("官方CSV中的flight_id样例:")
        for fid in sample_official:
            print(f"  '{fid}' (类型: {type(fid)}, 长度: {len(str(fid))})")
            
        print("轨迹文件中的flight_id样例:")
        for fid in sample_traj:
            print(f"  '{fid}' (类型: {type(fid)}, 长度: {len(str(fid))})")
    
    # 分析每个CSV文件的匹配情况
    print("\n6. 各CSV文件匹配情况:")
    for csv_name, csv_ids in flight_counts.items():
        matched_with_csv = csv_ids.intersection(trajectory_flight_ids)
        match_rate_csv = len(matched_with_csv) / len(trajectory_flight_ids) * 100 if trajectory_flight_ids else 0
        print(f"  {csv_name}: {len(matched_with_csv)}/{len(trajectory_flight_ids)} ({match_rate_csv:.1f}%)")

if __name__ == "__main__":
    compare_flight_ids()