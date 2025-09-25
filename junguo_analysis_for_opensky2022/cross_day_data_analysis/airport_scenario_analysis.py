#!/usr/bin/env python3
"""
机场起降场景分析
Airport Landing/Takeoff Scenario Analysis
"""

import pandas as pd
import numpy as np
import math
from datetime import datetime, timedelta
import pytz

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

def analyze_airport_operations():
    """分析机场起降操作的特征"""
    print("=" * 80)
    print("机场起降操作特征分析")
    print("=" * 80)
    
    print("🛬 典型降落过程特征:")
    print("-" * 40)
    print("   • 高度变化: 从巡航高度(30000-40000ft)逐渐下降到地面(0-1000ft)")
    print("   • 速度变化: 从巡航速度(400-500m/s)减速到着陆速度(60-80m/s)")
    print("   • 时间持续: 通常15-30分钟")
    print("   • 轨迹模式: 连续下降，可能包含盘旋等待")
    
    print("\n🛫 典型起飞过程特征:")
    print("-" * 40)
    print("   • 高度变化: 从地面(0-1000ft)爬升到巡航高度(30000-40000ft)")
    print("   • 速度变化: 从起飞速度(80-120m/s)加速到巡航速度(400-500m/s)")
    print("   • 时间持续: 通常10-20分钟到达初始巡航高度")
    print("   • 轨迹模式: 连续爬升，遵循标准离场程序")
    
    print("\n⏰ 机场起降间隔:")
    print("-" * 40)
    print("   • 最小间隔: 2-3分钟（繁忙机场）")
    print("   • 典型间隔: 5-15分钟")
    print("   • 跑道切换: 可能需要更长间隔")
    print("   • 夜间操作: 间隔可能更长")

def analyze_case_against_airport_pattern():
    """分析案例是否符合机场起降模式"""
    print("\n" + "=" * 80)
    print("案例与机场起降模式对比分析")
    print("=" * 80)
    
    # 案例数据
    case_data = {
        'flight1': {
            'id': 248757373,
            'label': '晚间航班',
            'duration': 189.1,  # 分钟
            'altitude_range': (50, 40350),  # ft
            'altitude_change': 900,  # ft (上升)
            'speed_range': (None, None),  # 需要修正
            'start_pos': (41.2191, 28.7285),
            'end_pos': (41.2191, 28.7285)  # 需要从实际数据获取
        },
        'flight2': {
            'id': 248777023,
            'label': '凌晨航班',
            'duration': 43.5,  # 分钟
            'altitude_range': (5900, 35025),  # ft
            'altitude_change': 29100,  # ft (上升)
            'speed_range': (263, 473),  # m/s
            'start_pos': (41.3810, 28.6196),
            'end_pos': (39.7343, 34.0343)
        }
    }
    
    time_gap = 37.5  # 分钟
    distance_gap = 20.2  # 公里
    
    print("📊 案例数据总结:")
    print("-" * 50)
    for key, flight in case_data.items():
        print(f"\n{flight['label']} ({flight['id']}):")
        print(f"   • 持续时间: {flight['duration']:.1f} 分钟")
        print(f"   • 高度范围: {flight['altitude_range'][0]} - {flight['altitude_range'][1]} ft")
        print(f"   • 高度变化: {flight['altitude_change']:+} ft")
        if flight['speed_range'][0] is not None:
            print(f"   • 速度范围: {flight['speed_range'][0]} - {flight['speed_range'][1]} m/s")
        else:
            print(f"   • 速度范围: 数据异常")
    
    print(f"\n⏰ 时间间隔: {time_gap} 分钟")
    print(f"📍 位置距离: {distance_gap} 公里")
    
    print("\n🔍 模式匹配分析:")
    print("-" * 50)
    
    # 分析第一个航班是否像降落
    print("1️⃣ 晚间航班 - 降落模式匹配:")
    flight1 = case_data['flight1']
    
    # 检查高度模式
    if flight1['altitude_change'] < -10000:
        landing_altitude_match = "✅ 高度大幅下降，符合降落模式"
        altitude_score = 1.0
    elif flight1['altitude_change'] < -1000:
        landing_altitude_match = "⚠️ 高度有所下降，部分符合降落模式"
        altitude_score = 0.5
    else:
        landing_altitude_match = "❌ 高度上升，不符合降落模式"
        altitude_score = 0.0
    
    print(f"   • {landing_altitude_match}")
    
    # 检查持续时间
    if 15 <= flight1['duration'] <= 45:
        landing_duration_match = "✅ 持续时间符合降落过程"
        duration_score1 = 1.0
    elif flight1['duration'] <= 60:
        landing_duration_match = "⚠️ 持续时间偏长，但可能包含等待"
        duration_score1 = 0.7
    else:
        landing_duration_match = "❌ 持续时间过长，不太像单次降落"
        duration_score1 = 0.3
    
    print(f"   • {landing_duration_match} ({flight1['duration']:.1f}分钟)")
    
    # 分析第二个航班是否像起飞
    print("\n2️⃣ 凌晨航班 - 起飞模式匹配:")
    flight2 = case_data['flight2']
    
    # 检查高度模式
    if flight2['altitude_change'] > 20000:
        takeoff_altitude_match = "✅ 高度大幅上升，符合起飞爬升模式"
        altitude_score2 = 1.0
    elif flight2['altitude_change'] > 5000:
        takeoff_altitude_match = "⚠️ 高度上升，部分符合起飞模式"
        altitude_score2 = 0.7
    else:
        takeoff_altitude_match = "❌ 高度变化不符合起飞模式"
        altitude_score2 = 0.0
    
    print(f"   • {takeoff_altitude_match}")
    
    # 检查持续时间
    if 10 <= flight2['duration'] <= 30:
        takeoff_duration_match = "✅ 持续时间符合起飞爬升过程"
        duration_score2 = 1.0
    elif flight2['duration'] <= 60:
        takeoff_duration_match = "⚠️ 持续时间合理"
        duration_score2 = 0.8
    else:
        takeoff_duration_match = "❌ 持续时间异常"
        duration_score2 = 0.3
    
    print(f"   • {takeoff_duration_match} ({flight2['duration']:.1f}分钟)")
    
    # 检查速度模式
    if flight2['speed_range'][0] is not None:
        speed_change = flight2['speed_range'][1] - flight2['speed_range'][0]
        if speed_change > 100:
            takeoff_speed_match = "✅ 速度大幅增加，符合起飞加速模式"
            speed_score2 = 1.0
        elif speed_change > 50:
            takeoff_speed_match = "⚠️ 速度增加，部分符合起飞模式"
            speed_score2 = 0.7
        else:
            takeoff_speed_match = "❌ 速度变化不符合起飞模式"
            speed_score2 = 0.0
        
        print(f"   • {takeoff_speed_match} ({speed_change:+.0f} m/s)")
    else:
        speed_score2 = 0.0
        print("   • ❌ 速度数据异常，无法判断")
    
    # 分析时间和位置间隔
    print("\n3️⃣ 时间和位置间隔分析:")
    
    if time_gap <= 60:
        time_match = "✅ 时间间隔合理，符合机场起降间隔"
        time_score = 1.0
    elif time_gap <= 120:
        time_match = "⚠️ 时间间隔偏长，但仍可能"
        time_score = 0.6
    else:
        time_match = "❌ 时间间隔过长"
        time_score = 0.0
    
    print(f"   • {time_match} ({time_gap}分钟)")
    
    if distance_gap <= 30:
        distance_match = "✅ 位置距离合理，可能是同一机场或附近机场"
        distance_score = 1.0
    elif distance_gap <= 100:
        distance_match = "⚠️ 位置距离较远，可能是不同机场"
        distance_score = 0.6
    else:
        distance_match = "❌ 位置距离过远"
        distance_score = 0.0
    
    print(f"   • {distance_match} ({distance_gap}公里)")
    
    # 计算总体匹配度
    print("\n📊 机场起降模式匹配度评分:")
    print("-" * 50)
    
    # 注意：第一个航班的高度是上升的，不符合降落模式
    print(f"   • 晚间航班降落模式: {altitude_score:.1f}/1.0 (高度) + {duration_score1:.1f}/1.0 (时间)")
    print(f"   • 凌晨航班起飞模式: {altitude_score2:.1f}/1.0 (高度) + {duration_score2:.1f}/1.0 (时间) + {speed_score2:.1f}/1.0 (速度)")
    print(f"   • 时间间隔匹配: {time_score:.1f}/1.0")
    print(f"   • 位置间隔匹配: {distance_score:.1f}/1.0")
    
    total_score = (altitude_score + duration_score1 + altitude_score2 + duration_score2 + speed_score2 + time_score + distance_score) / 7
    
    print(f"\n🎯 总体匹配度: {total_score:.2f}/1.00 ({total_score*100:.1f}%)")
    
    if total_score >= 0.8:
        conclusion = "高度匹配机场起降模式"
    elif total_score >= 0.6:
        conclusion = "较好匹配机场起降模式"
    elif total_score >= 0.4:
        conclusion = "部分匹配机场起降模式"
    else:
        conclusion = "不太匹配机场起降模式"
    
    print(f"🎯 结论: {conclusion}")
    
    return total_score, conclusion

def main():
    """主函数"""
    # 分析机场操作特征
    analyze_airport_operations()
    
    # 分析案例匹配度
    score, conclusion = analyze_case_against_airport_pattern()
    
    print("\n" + "=" * 80)
    print("🔍 最终分析结论")
    print("=" * 80)
    
    print("📋 关键发现:")
    print("   1. 晚间航班显示高度上升模式，不符合典型降落特征")
    print("   2. 凌晨航班显示明显的起飞爬升特征")
    print("   3. 时间和位置间隔符合机场操作范围")
    
    print(f"\n🎯 机场起降模式匹配度: {score:.2f} ({conclusion})")
    
    print("\n💡 修正后的判断:")
    print("   ❌ 不是典型的'降落+起飞'组合")
    print("   ✅ 更可能是两个独立的飞行操作")
    print("   🤔 第一个航班可能是:")
    print("      - 正在爬升的起飞航班")
    print("      - 正在进行复飞(go-around)操作")
    print("      - 其他类型的飞行操作")
    
    print("\n🎯 最终结论:")
    print("   • 这两个记录很可能来自两架不同的飞机")
    print("   • 不能作为跨日轨迹分割的有效证据")
    print("   • 需要寻找更强的证据来证明跨日轨迹问题")

if __name__ == "__main__":
    main()