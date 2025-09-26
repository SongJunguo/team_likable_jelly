#!/usr/bin/env python3
"""
修正版机场完整性分析 - 使用欧洲机场坐标
===========================================

基于数据实际地理覆盖（欧洲地区）重新分析轨迹完整性
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
from multiprocessing import Pool, cpu_count
import warnings
warnings.filterwarnings('ignore')

class EuropeanAirportAnalyzer:
    """基于欧洲机场的轨迹完整性分析"""
    
    def __init__(self, trajectory_dir: str, output_dir: str):
        self.trajectory_dir = Path(trajectory_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 欧洲主要机场坐标
        self.major_airports = {
            'LHR': {'name': 'London Heathrow', 'lat': 51.4700, 'lon': -0.4543},
            'CDG': {'name': 'Paris Charles de Gaulle', 'lat': 49.0097, 'lon': 2.5479},
            'FRA': {'name': 'Frankfurt am Main', 'lat': 50.0379, 'lon': 8.5622},
            'AMS': {'name': 'Amsterdam Schiphol', 'lat': 52.3105, 'lon': 4.7683},
            'MAD': {'name': 'Madrid Barajas', 'lat': 40.4839, 'lon': -3.5680},
            'FCO': {'name': 'Rome Fiumicino', 'lat': 41.8003, 'lon': 12.2389},
            'MUC': {'name': 'Munich', 'lat': 48.3537, 'lon': 11.7750},
            'ZUR': {'name': 'Zurich', 'lat': 47.4647, 'lon': 8.5492},
            'VIE': {'name': 'Vienna', 'lat': 48.1103, 'lon': 16.5697},
            'CPH': {'name': 'Copenhagen', 'lat': 55.6181, 'lon': 12.6561},
            'ARN': {'name': 'Stockholm Arlanda', 'lat': 59.6519, 'lon': 17.9186},
            'OSL': {'name': 'Oslo Gardermoen', 'lat': 60.1939, 'lon': 11.1004},
            'HEL': {'name': 'Helsinki Vantaa', 'lat': 60.3172, 'lon': 24.9633},
            'DUB': {'name': 'Dublin', 'lat': 53.4213, 'lon': -6.2701},
            'BRU': {'name': 'Brussels', 'lat': 50.9010, 'lon': 4.4856}
        }
        
    def haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """计算两点间的大圆距离"""
        R = 6371  # 地球半径（公里）
        
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        
        return R * c
    
    def find_nearest_airport(self, lat: float, lon: float):
        """找到最近的机场"""
        min_distance = float('inf')
        nearest_airport = None
        
        for code, info in self.major_airports.items():
            distance = self.haversine_distance(lat, lon, info['lat'], info['lon'])
            if distance < min_distance:
                min_distance = distance
                nearest_airport = code
                
        return nearest_airport, min_distance
    
    def analyze_single_file(self, file_path: str):
        """分析单个轨迹文件"""
        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                return []
                
            results = []
            
            for flight_id, flight_data in df.groupby('flight_id'):
                if len(flight_data) < 10:
                    continue
                    
                flight_data = flight_data.sort_values('timestamp')
                
                # 起点和终点
                start_lat, start_lon = flight_data.iloc[0]['latitude'], flight_data.iloc[0]['longitude']
                end_lat, end_lon = flight_data.iloc[-1]['latitude'], flight_data.iloc[-1]['longitude']
                
                # 找最近机场
                start_airport, start_dist = self.find_nearest_airport(start_lat, start_lon)
                end_airport, end_dist = self.find_nearest_airport(end_lat, end_lon)
                
                results.append({
                    'flight_id': flight_id,
                    'start_lat': start_lat,
                    'start_lon': start_lon,
                    'end_lat': end_lat,
                    'end_lon': end_lon,
                    'start_airport': start_airport,
                    'start_distance': start_dist,
                    'end_airport': end_airport,
                    'end_distance': end_dist,
                    'point_count': len(flight_data),
                    'duration_hours': (flight_data['timestamp'].max() - flight_data['timestamp'].min()).total_seconds() / 3600
                })
                
            return results
            
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {e}")
            return []
    
    def run_analysis(self, max_files: int = 10):
        """运行分析（限制文件数量以快速验证）"""
        files = list(self.trajectory_dir.glob('*.parquet'))[:max_files]
        print(f"分析 {len(files)} 个文件...")
        
        all_results = []
        for i, file in enumerate(files):
            print(f"处理文件 {i+1}/{len(files)}: {file.name}")
            results = self.analyze_single_file(file)
            all_results.extend(results)
            
        df = pd.DataFrame(all_results)
        
        # 生成快速报告
        self.generate_quick_report(df)
        
        return df
    
    def generate_quick_report(self, df: pd.DataFrame):
        """生成快速验证报告"""
        if df.empty:
            print("没有数据可分析")
            return
            
        print(f"\n=== 修正后的机场分析结果 ===")
        print(f"总轨迹数: {len(df):,}")
        print(f"平均起点到机场距离: {df['start_distance'].mean():.1f} km")
        print(f"平均终点到机场距离: {df['end_distance'].mean():.1f} km")
        
        # 50km内的轨迹
        near_start = (df['start_distance'] <= 50).sum()
        near_end = (df['end_distance'] <= 50).sum()
        
        print(f"起点在机场50km内: {near_start} ({near_start/len(df)*100:.1f}%)")
        print(f"终点在机场50km内: {near_end} ({near_end/len(df)*100:.1f}%)")
        
        # 最常用机场
        print(f"\n最常用起降机场:")
        print("起点机场:")
        print(df['start_airport'].value_counts().head())
        print("终点机场:")
        print(df['end_airport'].value_counts().head())
        
        # 保存结果
        report_file = self.output_dir / "corrected_airport_analysis.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("修正后的机场分析报告\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"总轨迹数: {len(df):,}\n")
            f.write(f"平均起点到机场距离: {df['start_distance'].mean():.1f} km\n")
            f.write(f"平均终点到机场距离: {df['end_distance'].mean():.1f} km\n")
            f.write(f"起点在机场50km内: {near_start} ({near_start/len(df)*100:.1f}%)\n")
            f.write(f"终点在机场50km内: {near_end} ({near_end/len(df)*100:.1f}%)\n")
            
        print(f"\n报告已保存到: {report_file}")

def main():
    trajectory_dir = "/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories"
    output_dir = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/corrected_analysis"
    
    analyzer = EuropeanAirportAnalyzer(trajectory_dir, output_dir)
    df = analyzer.run_analysis(max_files=5)  # 先分析5个文件验证
    
if __name__ == "__main__":
    main()