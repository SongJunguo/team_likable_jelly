#!/usr/bin/env python3
"""
重新深入分析可疑的跨日航班案例
Critical Case Re-analysis for Cross-Date Flight Detection
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz
import math

def calculate_distance(lat1, lon1, lat2, lon2):
    """计算两点间的大圆距离（公里）"""
    R = 6371  # 地球半径（公里）
    
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c

def analyze_flight_trajectory_pattern(df, flight_id, label):
    """分析单个航班的轨迹模式"""
    print(f"\n=== {label} 航班 {flight_id} 轨迹分析 ===")
    
    # 基本统计
    print(f"记录数: {len(df)}")
    print(f"时间跨度: {df['timestamp'].min()} 到 {df['timestamp'].max()}")
    print(f"持续时间: {(df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60:.1f} 分钟")
    
    # 高度分析
    print(f"\n高度分析:")
    print(f"  最低高度: {df['altitude'].min():.0f} ft")
    print(f"  最高高度: {df['altitude'].max():.0f} ft")
    print(f"  平均高度: {df['altitude'].mean():.0f} ft")
    print(f"  高度变化: {df['altitude'].max() - df['altitude'].min():.0f} ft")
    
    # 速度分析
    print(f"\n速度分析:")
    print(f"  最低速度: {df['groundspeed'].min():.1f} m/s")
    print(f"  最高速度: {df['groundspeed'].max():.1f} m/s")
    print(f"  平均速度: {df['groundspeed'].mean():.1f} m/s")
    
    # 轨迹模式分析
    df_sorted = df.sort_values('timestamp')
    
    # 高度变化趋势
    altitude_trend = "上升" if df_sorted['altitude'].iloc[-1] > df_sorted['altitude'].iloc[0] else "下降"
    altitude_change = df_sorted['altitude'].iloc[-1] - df_sorted['altitude'].iloc[0]
    print(f"\n轨迹模式:")
    print(f"  高度趋势: {altitude_trend} ({altitude_change:+.0f} ft)")
    
    # 速度变化趋势
    speed_change = df_sorted['groundspeed'].iloc[-1] - df_sorted['groundspeed'].iloc[0]
    speed_trend = "加速" if speed_change > 0 else "减速"
    print(f"  速度趋势: {speed_trend} ({speed_change:+.1f} m/s)")
    
    # 位置变化
    start_pos = (df_sorted['latitude'].iloc[0], df_sorted['longitude'].iloc[0])
    end_pos = (df_sorted['latitude'].iloc[-1], df_sorted['longitude'].iloc[-1])
    distance = calculate_distance(start_pos[0], start_pos[1], end_pos[0], end_pos[1])
    print(f"  位置变化: {distance:.1f} 公里")
    print(f"  起始位置: ({start_pos[0]:.4f}, {start_pos[1]:.4f})")
    print(f"  结束位置: ({end_pos[0]:.4f}, {end_pos[1]:.4f})")
    
    return {
        'flight_id': flight_id,
        'duration_minutes': (df['timestamp'].max() - df['timestamp'].min()).total_seconds() / 60,
        'altitude_range': (df['altitude'].min(), df['altitude'].max()),
        'altitude_trend': altitude_trend,
        'altitude_change': altitude_change,
        'speed_range': (df['groundspeed'].min(), df['groundspeed'].max()),
        'speed_trend': speed_trend,
        'speed_change': speed_change,
        'distance_traveled': distance,
        'start_position': start_pos,
        'end_position': end_pos
    }

def analyze_flight_phase(trajectory_stats):
    """分析航班所处的飞行阶段"""
    altitude_change = trajectory_stats['altitude_change']
    speed_change = trajectory_stats['speed_change']
    duration = trajectory_stats['duration_minutes']
    altitude_range = trajectory_stats['altitude_range']
    
    print(f"\n🔍 飞行阶段分析:")
    
    # 判断飞行阶段
    if altitude_change < -1000 and speed_change < -50:
        phase = "降落阶段"
        confidence = "高"
    elif altitude_change > 1000 and speed_change > 50:
        phase = "起飞/爬升阶段"
        confidence = "高"
    elif abs(altitude_change) < 500 and altitude_range[0] > 20000:
        phase = "巡航阶段"
        confidence = "中"
    elif altitude_range[1] < 5000:
        phase = "地面/低空阶段"
        confidence = "中"
    else:
        phase = "不确定"
        confidence = "低"
    
    print(f"  判断结果: {phase} (置信度: {confidence})")
    print(f"  判断依据:")
    print(f"    - 高度变化: {altitude_change:+.0f} ft")
    print(f"    - 速度变化: {speed_change:+.1f} m/s")
    print(f"    - 高度范围: {altitude_range[0]:.0f} - {altitude_range[1]:.0f} ft")
    
    return phase, confidence

def check_same_aircraft_possibility(stats1, stats2, time_gap_minutes, distance_km):
    """检查是否可能是同一架飞机"""
    print(f"\n🤔 同一架飞机可能性分析:")
    
    # 分析两个轨迹的飞行阶段
    phase1, conf1 = analyze_flight_phase(stats1)
    phase2, conf2 = analyze_flight_phase(stats2)
    
    print(f"\n航班1阶段: {phase1}")
    print(f"航班2阶段: {phase2}")
    
    # 检查连续性的合理性
    print(f"\n连续性检查:")
    print(f"  时间间隔: {time_gap_minutes:.1f} 分钟")
    print(f"  位置距离: {distance_km:.1f} 公里")
    
    # 高度和速度变化的合理性
    altitude_gap = stats2['start_position'] != stats1['end_position']  # 这里需要修正
    altitude_diff = abs(stats2['altitude_range'][0] - stats1['altitude_range'][1])
    speed_diff = abs(stats2['speed_range'][0] - stats1['speed_range'][1])
    
    print(f"  高度差异: {altitude_diff:.0f} ft")
    print(f"  速度差异: {speed_diff:.1f} m/s")
    
    # 判断逻辑
    reasons_against = []
    reasons_for = []
    
    # 反对理由
    if "降落" in phase1 and "起飞" in phase2:
        reasons_against.append("第一段是降落，第二段是起飞 - 更像是不同飞机")
    
    if altitude_diff > 3000:
        reasons_against.append(f"高度差异过大 ({altitude_diff:.0f} ft)")
    
    if speed_diff > 100:
        reasons_against.append(f"速度差异过大 ({speed_diff:.1f} m/s)")
    
    if time_gap_minutes > 60:
        reasons_against.append(f"时间间隔过长 ({time_gap_minutes:.1f} 分钟)")
    
    if distance_km > 50:
        reasons_against.append(f"位置距离过远 ({distance_km:.1f} 公里)")
    
    # 支持理由
    if time_gap_minutes < 30:
        reasons_for.append(f"时间间隔合理 ({time_gap_minutes:.1f} 分钟)")
    
    if distance_km < 30:
        reasons_for.append(f"位置距离合理 ({distance_km:.1f} 公里)")
    
    print(f"\n❌ 反对理由:")
    for reason in reasons_against:
        print(f"    - {reason}")
    
    print(f"\n✅ 支持理由:")
    for reason in reasons_for:
        print(f"    - {reason}")
    
    # 最终判断
    if len(reasons_against) > len(reasons_for):
        conclusion = "不太可能是同一架飞机"
        confidence = "高" if len(reasons_against) >= 3 else "中"
    else:
        conclusion = "可能是同一架飞机"
        confidence = "低"
    
    print(f"\n🎯 最终判断: {conclusion} (置信度: {confidence})")
    
    return conclusion, confidence, reasons_against, reasons_for

def main():
    """主函数"""
    print("=" * 80)
    print("重新深入分析可疑的跨日航班案例")
    print("=" * 80)
    
    # 数据文件路径
    data_dir = "/workspace/aircraft_trajectory/opensky_2024_PRC_dataset_jelly/rawtrajectories"
    file1 = f"{data_dir}/2022-01-01.parquet"
    file2 = f"{data_dir}/2022-01-02.parquet"
    
    print(f"加载数据文件...")
    print(f"文件1: {file1}")
    print(f"文件2: {file2}")
    
    try:
        df1 = pd.read_parquet(file1)
        df2 = pd.read_parquet(file2)
        
        # 转换时间戳
        df1['timestamp'] = pd.to_datetime(df1['timestamp'], utc=True)
        df2['timestamp'] = pd.to_datetime(df2['timestamp'], utc=True)
        
        print(f"✅ 数据加载成功")
        print(f"文件1记录数: {len(df1):,}")
        print(f"文件2记录数: {len(df2):,}")
        
        # 分析可疑案例
        flight_id1 = 248757373
        flight_id2 = 248777023
        
        # 提取航班数据
        flight1_data = df1[df1['icao24'] == flight_id1].copy()
        flight2_data = df2[df2['icao24'] == flight_id2].copy()
        
        if len(flight1_data) == 0:
            print(f"❌ 未找到航班 {flight_id1} 的数据")
            return
        
        if len(flight2_data) == 0:
            print(f"❌ 未找到航班 {flight_id2} 的数据")
            return
        
        # 分析两个航班的轨迹模式
        stats1 = analyze_flight_trajectory_pattern(flight1_data, flight_id1, "晚间")
        stats2 = analyze_flight_trajectory_pattern(flight2_data, flight_id2, "凌晨")
        
        # 计算时间和距离间隔
        time_gap = (flight2_data['timestamp'].min() - flight1_data['timestamp'].max()).total_seconds() / 60
        distance = calculate_distance(
            stats1['end_position'][0], stats1['end_position'][1],
            stats2['start_position'][0], stats2['start_position'][1]
        )
        
        # 检查是否可能是同一架飞机
        conclusion, confidence, reasons_against, reasons_for = check_same_aircraft_possibility(
            stats1, stats2, time_gap, distance
        )
        
        print(f"\n" + "=" * 80)
        print("🔍 重新分析结论")
        print("=" * 80)
        print(f"原始分析结论: 可能是同一架飞机的跨日轨迹")
        print(f"重新分析结论: {conclusion} (置信度: {confidence})")
        
        if len(reasons_against) > 0:
            print(f"\n⚠️  主要问题:")
            for reason in reasons_against:
                print(f"   • {reason}")
        
        print(f"\n💡 建议:")
        if "不太可能" in conclusion:
            print("   • 该案例很可能是两架不同的飞机（一架降落，一架起飞）")
            print("   • 需要寻找更强的证据来证明跨日轨迹分割问题")
            print("   • 建议分析更多案例或使用其他方法验证")
        else:
            print("   • 需要更多证据来确认是否为同一架飞机")
            print("   • 建议检查航班号、机型等其他标识符")
        
    except Exception as e:
        print(f"❌ 分析过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()