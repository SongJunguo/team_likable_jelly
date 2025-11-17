#!/usr/bin/env python3
"""
回顾优质轨迹选择标准和插值方法，分析速度缺失问题
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
import multiprocessing as mp
from functools import partial
from datetime import datetime

def analyze_trajectory_selection_criteria():
    """分析优质轨迹选择标准"""
    print("=" * 80)
    print("优质轨迹选择标准回顾")
    print("=" * 80)
    
    print("\n📊 基于 legacy/analysis_for_interpolation/full_365_analysis_output_v2/")
    print("   trajectory_analysis.parquet 的分析结果:")
    
    print("\n🎯 选择标准:")
    print("1. 质量评分计算方法:")
    print("   - 核心字段权重70%: latitude, longitude, altitude")
    print("   - 次要字段权重30%: groundspeed, track, vertical_rate")
    print("   - 基础分数: 100分")
    print("   - 缺失率惩罚: 每1%缺失率扣1分")
    print("   - 头尾缺失额外惩罚: 最多扣10分")
    print("   - 大缺失窗口惩罚: 超过50个点的窗口最多扣15分")
    
    print("\n2. 质量等级分类:")
    print("   - Excellent (≥90分): 430,342条 (43.9%)")
    print("   - Good (70-89分): 443,104条 (45.2%)")
    print("   - Fair (50-69分): 88,536条 (9.0%)")
    print("   - Poor (<50分): 17,698条 (1.8%)")
    
    print("\n3. 最终选择结果:")
    print("   - 选择了 Excellent + Good 等级的轨迹")
    print("   - 总计: 873,446条轨迹")
    print("   - 但实际保存到 high_quality_flight_ids.txt 的只有 238,217条")
    print("   - 说明还有额外的筛选条件")
    
    print("\n❓ 关键发现:")
    print("   - track列平均缺失率100%，中位数100%")
    print("   - 这意味着当时分析的数据中track列完全缺失")
    print("   - 但仍然选择了这些轨迹，说明track缺失被认为是可接受的")

def analyze_interpolation_method():
    """分析插值方法和标准"""
    print("\n" + "=" * 80)
    print("插值方法和标准回顾")
    print("=" * 80)
    
    print("\n🔧 插值算法 (interpolate.py):")
    print("1. 核心参数:")
    print("   - MAX_HOLE_SIZE = 20秒 (最大插值间隔)")
    print("   - 使用样条插值 (csaps.csaps)")
    print("   - 不同字段使用不同的平滑因子")
    
    print("\n2. 插值流程:")
    print("   Step 1: 计算时间间隔 compute_holes()")
    print("   Step 2: 对各字段应用样条插值 spline()")
    print("   Step 3: 屏蔽超过20秒间隔的插值结果")
    print("   Step 4: 保留原始NaN值在大间隔处")
    
    print("\n3. 字段特殊处理:")
    print("   - track: 先展开角度 (unwrap)，再插值，最后重新包装")
    print("   - altitude: 同时计算导数 (垂直速度)")
    print("   - 不同平滑因子:")
    print("     * 位置 (lat/lon): smooth")
    print("     * 高度: smooth")
    print("     * 速度类: smooth * 0.1")
    print("     * 垂直速度: smooth * 0.1")
    
    print("\n4. 高质量轨迹定制插值 (high_quality_interpolation.py):")
    print("   - MAX_HOLE_SIZE = 10秒 (更保守)")
    print("   - 增加头尾NaN截断逻辑")
    print("   - 质量验证: 确保缺失率 < 1%")
    
    print("\n📊 插值效果:")
    print("   - 根据 interpolation_quality_report_20250923_152202.txt:")
    print("   - 处理了4,469条轨迹，32,329,882个数据点")
    print("   - 最终缺失值: 0个 (100%完整)")
    print("   - 所有关键列缺失率: 0.0000%")

def analyze_speed_missing_problem():
    """分析速度完全缺失的问题"""
    print("\n" + "=" * 80)
    print("速度完全缺失问题分析")
    print("=" * 80)
    
    print("\n🔍 问题发现:")
    print("根据最新的 comprehensive_missing_rate_analysis.py 分析:")
    print("- groundspeed: 5,167个缺失值 (0.0003%)")
    print("- track: 5,167个缺失值 (0.0003%)")
    print("- vertical_rate: 5,167个缺失值 (0.0003%)")
    print("- 所有缺失值都集中在 complete_2022-02-10.parquet 文件中")
    print("- 涉及2条轨迹: flight_id 249452195, 249466605")
    
    print("\n❓ 为什么当时没有发现这个问题？")
    print("1. 当时的分析基于插值前的数据 (classic_filtered_trajectories)")
    print("2. 那时track列显示100%缺失，被认为是正常现象")
    print("3. groundspeed和vertical_rate的缺失率相对较低")
    print("4. 选择标准主要关注位置数据 (lat/lon/alt) 的完整性")
    
    print("\n🎯 问题的根本原因:")
    print("1. 原始数据质量问题:")
    print("   - 某些轨迹的运动参数 (groundspeed, track, vertical_rate) 完全缺失")
    print("   - 但位置数据 (lat/lon/alt) 完整")
    
    print("\n2. 插值算法的局限性:")
    print("   - 样条插值需要至少3个有效数据点")
    print("   - 完全缺失的列无法进行插值")
    print("   - 插值算法无法从位置数据推导运动参数")
    
    print("\n3. 选择标准的盲点:")
    print("   - 当时的质量评分虽然考虑了运动参数")
    print("   - 但权重较低 (30% vs 70%)")
    print("   - 完全缺失的情况可能被其他因素掩盖")

def check_problematic_trajectories():
    """检查问题轨迹的详细情况"""
    print("\n" + "=" * 80)
    print("问题轨迹详细检查")
    print("=" * 80)
    
    # 检查问题轨迹是否在高质量ID列表中
    high_quality_ids_file = "/workspace/aircraft_trajectory/team_likable_jelly/high_quality_flight_ids.txt"
    
    if os.path.exists(high_quality_ids_file):
        with open(high_quality_ids_file, 'r') as f:
            high_quality_ids = set(int(line.strip()) for line in f)
        
        problematic_ids = {249452195, 249466605}
        
        print(f"📋 高质量轨迹ID总数: {len(high_quality_ids):,}")
        print(f"🔍 问题轨迹ID: {problematic_ids}")
        
        in_high_quality = problematic_ids.intersection(high_quality_ids)
        not_in_high_quality = problematic_ids - high_quality_ids
        
        if in_high_quality:
            print(f"⚠️ 在高质量列表中的问题轨迹: {in_high_quality}")
            print("   这说明当时的选择标准确实存在盲点")
        
        if not_in_high_quality:
            print(f"✅ 不在高质量列表中的问题轨迹: {not_in_high_quality}")
            print("   这些轨迹已经被正确排除")
        
        # 计算影响比例
        impact_ratio = len(in_high_quality) / len(high_quality_ids) * 100
        print(f"📊 问题轨迹占高质量轨迹的比例: {impact_ratio:.4f}%")
    
    else:
        print("❌ 未找到高质量轨迹ID文件")

def recommend_solutions():
    """推荐解决方案"""
    print("\n" + "=" * 80)
    print("解决方案推荐")
    print("=" * 80)
    
    print("\n🎯 短期解决方案 (立即可行):")
    print("1. 直接移除问题轨迹:")
    print("   - 从 complete_high_quality_trajectories 中移除包含这2条轨迹的文件")
    print("   - 或者在读取时过滤掉这些flight_id")
    print("   - 数据损失极小: 2/238,217 = 0.0008%")
    
    print("\n2. 基于位置计算运动参数:")
    print("   - 从 lat/lon 计算 groundspeed 和 track")
    print("   - 从 altitude 计算 vertical_rate")
    print("   - 但计算精度可能不如原始传感器数据")
    
    print("\n🔧 中期解决方案 (优化选择标准):")
    print("1. 增强质量评分算法:")
    print("   - 对完全缺失的运动参数给予更严厉的惩罚")
    print("   - 设置运动参数缺失率阈值 (如 >50% 直接排除)")
    
    print("\n2. 多阶段筛选:")
    print("   - 第一阶段: 基于位置数据质量筛选")
    print("   - 第二阶段: 基于运动参数完整性筛选")
    print("   - 第三阶段: 综合质量评分")
    
    print("\n🚀 长期解决方案 (数据处理流程优化):")
    print("1. 预处理阶段增加运动参数检查:")
    print("   - 在插值前检查关键运动参数的完整性")
    print("   - 建立运动参数质量档案")
    
    print("\n2. 智能插值策略:")
    print("   - 对于位置完整但运动参数缺失的轨迹")
    print("   - 实现基于物理模型的运动参数推导")
    print("   - 结合航空器性能数据和气象数据")
    
    print("\n💡 推荐实施顺序:")
    print("1. 立即: 移除2条问题轨迹，确保数据集100%完整")
    print("2. 短期: 实现基于位置的运动参数计算作为备选方案")
    print("3. 中期: 优化轨迹选择标准，防止类似问题")
    print("4. 长期: 建立完整的数据质量保证体系")

def main():
    """主函数"""
    print("🔍 优质轨迹选择和插值方法回顾分析")
    print("生成时间:", datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # 1. 回顾优质轨迹选择标准
    analyze_trajectory_selection_criteria()
    
    # 2. 回顾插值方法和标准
    analyze_interpolation_method()
    
    # 3. 分析速度缺失问题
    analyze_speed_missing_problem()
    
    # 4. 检查问题轨迹
    check_problematic_trajectories()
    
    # 5. 推荐解决方案
    recommend_solutions()
    
    print("\n" + "=" * 80)
    print("✅ 分析完成")
    print("=" * 80)
    
    print("\n📋 总结:")
    print("1. 优质轨迹选择基于质量评分，主要关注位置数据完整性")
    print("2. 插值使用样条插值，最大间隔20秒，对高质量轨迹优化为10秒")
    print("3. 速度缺失问题源于原始数据质量和选择标准的盲点")
    print("4. 推荐立即移除2条问题轨迹，确保数据集100%完整")
    print("5. 长期需要优化选择标准和数据质量保证体系")

if __name__ == "__main__":
    main()