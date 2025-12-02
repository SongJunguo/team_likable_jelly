#!/usr/bin/env python3
"""
使用筛选过的机场数据进行优化的机场完整性分析
使用 opensky_2024_PRC_dataset/airports_tz.parquet 文件，该文件只包含实际使用过的机场
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import multiprocessing as mp
from functools import partial
import time
import warnings
warnings.filterwarnings('ignore')

class OptimizedAirportAnalyzer:
    def __init__(self, data_dir, output_dir):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 数据存储
        self.airports_df = None
        self.official_flights_df = None
        self.flight_to_airports = {}
        self.analysis_results = []
        
    def load_filtered_airports(self):
        """加载筛选过的机场数据"""
        airports_file = self.data_dir / "opensky_2024_PRC_dataset" / "airports_tz.parquet"
        
        print(f"正在加载筛选过的机场数据: {airports_file}")
        self.airports_df = pd.read_parquet(airports_file)
        
        print(f"已加载 {len(self.airports_df)} 个机场")
        print(f"机场类型分布:")
        print(self.airports_df['type'].value_counts())
        
        # 创建IATA和ICAO代码映射
        self.iata_to_coords = {}
        self.icao_to_coords = {}
        
        for _, row in self.airports_df.iterrows():
            lat, lon = row['latitude_deg'], row['longitude_deg']
            
            # IATA代码映射
            if pd.notna(row['iata_code']):
                self.iata_to_coords[row['iata_code']] = (lat, lon)
            
            # ICAO代码映射 (使用icao_code列)
            if pd.notna(row['icao_code']):
                self.icao_to_coords[row['icao_code']] = (lat, lon)
        
        print(f"IATA代码映射: {len(self.iata_to_coords)} 个")
        print(f"ICAO代码映射: {len(self.icao_to_coords)} 个")
        
    def load_official_flights(self):
        """加载官方航班数据"""
        print("正在加载官方航班数据...")
        
        # 定义官方航班数据文件路径
        flight_files = [
            self.data_dir / "opensky_2024_PRC_dataset" / "challenge_set.csv",
            self.data_dir / "opensky_2024_PRC_dataset" / "final_submission_set.csv", 
            self.data_dir / "opensky_2024_PRC_dataset" / "submission_set.csv"
        ]
        
        all_flights = []
        
        for file_path in flight_files:
            if file_path.exists():
                print(f"加载文件: {file_path}")
                try:
                    df = pd.read_csv(file_path)
                    print(f"  - 加载了 {len(df):,} 条记录")
                    all_flights.append(df)
                except Exception as e:
                    print(f"  - 加载失败: {e}")
            else:
                print(f"文件不存在: {file_path}")
        
        if all_flights:
            # 合并所有航班数据
            self.official_flights_df = pd.concat(all_flights, ignore_index=True)
            print(f"总共加载了 {len(self.official_flights_df):,} 条官方航班记录")
            
            # 创建flight_id到机场的映射
            self.flight_to_airports = {}
            for _, row in self.official_flights_df.iterrows():
                flight_id = row['flight_id']
                self.flight_to_airports[flight_id] = {
                    'departure': row['adep'],
                    'arrival': row['ades']
                }
            
            print(f"创建了 {len(self.flight_to_airports):,} 个航班ID到机场的映射")
        else:
            print("警告: 未能加载任何官方航班数据")
            self.official_flights_df = pd.DataFrame()
            self.flight_to_airports = {}
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """计算两点间的距离（公里）"""
        R = 6371  # 地球半径（公里）
        
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        
        return R * c
    
    def get_airport_coordinates(self, airport_code):
        """获取机场坐标，优先使用IATA代码，然后ICAO代码"""
        if airport_code in self.iata_to_coords:
            return self.iata_to_coords[airport_code]
        elif airport_code in self.icao_to_coords:
            return self.icao_to_coords[airport_code]
        else:
            return None
    
    def analyze_trajectory_file(self, file_path):
        """分析单个轨迹文件"""
        try:
            df = pd.read_parquet(file_path)
            
            if df.empty:
                return {
                    'file': file_path.name,
                    'total_trajectories': 0,
                    'trajectories_with_official_airports': 0,
                    'start_distances': [],
                    'end_distances': [],
                    'start_within_50km': 0,
                    'end_within_50km': 0,
                    'error': None
                }
            
            # 获取所有唯一的flight_id
            flight_ids = df['flight_id'].unique()
            
            start_distances = []
            end_distances = []
            start_within_50km = 0
            end_within_50km = 0
            trajectories_with_official_airports = 0
            
            for flight_id in flight_ids:
                # 查找官方机场信息
                if flight_id not in self.flight_to_airports:
                    continue
                
                official_airports = self.flight_to_airports[flight_id]
                
                trajectories_with_official_airports += 1
                
                # 获取轨迹的起点和终点
                flight_data = df[df['flight_id'] == flight_id].sort_values('timestamp')
                if len(flight_data) < 2:
                    continue
                
                start_point = flight_data.iloc[0]
                end_point = flight_data.iloc[-1]
                
                # 获取官方起降机场坐标
                dep_coords = self.get_airport_coordinates(official_airports['departure'])
                arr_coords = self.get_airport_coordinates(official_airports['arrival'])
                
                # 计算起点到起飞机场的距离
                if dep_coords:
                    start_dist = self.haversine_distance(
                        start_point['latitude'], start_point['longitude'],
                        dep_coords[0], dep_coords[1]
                    )
                    start_distances.append(start_dist)
                    if start_dist <= 50:
                        start_within_50km += 1
                
                # 计算终点到降落机场的距离
                if arr_coords:
                    end_dist = self.haversine_distance(
                        end_point['latitude'], end_point['longitude'],
                        arr_coords[0], arr_coords[1]
                    )
                    end_distances.append(end_dist)
                    if end_dist <= 50:
                        end_within_50km += 1
            
            return {
                'file': file_path.name,
                'total_trajectories': len(flight_ids),
                'trajectories_with_official_airports': trajectories_with_official_airports,
                'start_distances': start_distances,
                'end_distances': end_distances,
                'start_within_50km': start_within_50km,
                'end_within_50km': end_within_50km,
                'error': None
            }
            
        except Exception as e:
            return {
                'file': file_path.name,
                'total_trajectories': 0,
                'trajectories_with_official_airports': 0,
                'start_distances': [],
                'end_distances': [],
                'start_within_50km': 0,
                'end_within_50km': 0,
                'error': str(e)
            }
    
    def _create_test_data(self):
        """创建测试数据用于演示"""
        print("创建测试数据进行演示...")
        
        # 创建一些测试轨迹数据
        test_data = {
            'icao24': ['test001', 'test002', 'test003'],
            'callsign': ['TEST001', 'TEST002', 'TEST003'],
            'origin_airport': ['ZBAA', 'ZSSS', 'ZSPD'],
            'destination_airport': ['ZSSS', 'ZSPD', 'ZBAA'],
            'first_seen': [1640995200, 1640998800, 1641002400],
            'last_seen': [1641002400, 1641006000, 1641009600],
            'day': [1, 1, 1],
            'latitude': [39.9042, 31.1979, 31.1434],
            'longitude': [116.4074, 121.3364, 121.8052],
            'altitude': [10000, 11000, 9500],
            'velocity': [250, 280, 260],
            'heading': [90, 180, 270],
            'vertrate': [0, -5, 2],
            'onground': [False, False, False]
        }
        
        # 模拟分析结果
        self.analysis_results = {
            'test_file.parquet': {
                'total_trajectories': 3,
                'with_official_airports': 3,
                'start_distances': [2.1, 1.8, 3.2],
                'end_distances': [1.5, 2.3, 1.9],
                'within_50km_start': 3,
                'within_50km_end': 3
            }
        }
        
        print("测试数据创建完成")

    def run_analysis(self, max_files=None):
        """运行完整的机场完整性分析"""
        print("开始优化的机场完整性分析...")
        
        # 加载数据
        self.load_filtered_airports()
        self.load_official_flights()
        
        # 获取轨迹文件列表 - 尝试多个可能的目录
        possible_dirs = [
            "flightlist_20240101_20241201",
            "opensky_2024_PRC_dataset/rawtrajectories", 
            "opensky_2024_PRC_dataset/classic_filtered_trajectories",
            "opensky_2024_PRC_dataset/high_quality_interpolated_trajectories"
        ]
        
        parquet_files = []
        for dir_name in possible_dirs:
            trajectory_dir = self.data_dir / dir_name
            if trajectory_dir.exists():
                files = list(trajectory_dir.glob("*.parquet"))
                if files:
                    parquet_files = files
                    print(f"使用轨迹目录: {trajectory_dir}")
                    break
        
        if not parquet_files:
            print("警告: 未找到轨迹文件，将使用测试数据进行演示")
            # 创建测试数据
            self._create_test_data()
            return
        
        if max_files:
            parquet_files = parquet_files[:max_files]
            print(f"限制分析文件数量为: {max_files}")
        
        print(f"找到 {len(parquet_files)} 个轨迹文件")
        
        # 使用多进程分析
        print("开始多进程分析...")
        start_time = time.time()
        
        with mp.Pool(processes=mp.cpu_count()) as pool:
            self.analysis_results = pool.map(self.analyze_trajectory_file, parquet_files)
        
        end_time = time.time()
        print(f"分析完成，耗时: {end_time - start_time:.2f} 秒")
        
        # 生成报告
        self.generate_comprehensive_report()
        self.create_visualizations()
    
    def generate_comprehensive_report(self):
        """生成综合分析报告"""
        # 统计总体结果
        total_trajectories = sum(r['total_trajectories'] for r in self.analysis_results)
        total_with_official = sum(r['trajectories_with_official_airports'] for r in self.analysis_results)
        
        all_start_distances = []
        all_end_distances = []
        total_start_within_50km = 0
        total_end_within_50km = 0
        
        for result in self.analysis_results:
            all_start_distances.extend(result['start_distances'])
            all_end_distances.extend(result['end_distances'])
            total_start_within_50km += result['start_within_50km']
            total_end_within_50km += result['end_within_50km']
        
        # 生成报告
        report_file = self.output_dir / "optimized_airport_analysis_report.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=== 优化的机场完整性分析报告 ===\n")
            f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"使用筛选过的机场数据: {len(self.airports_df)} 个机场\n\n")
            
            f.write("=== 总体统计 ===\n")
            f.write(f"分析文件数量: {len(self.analysis_results)}\n")
            f.write(f"总轨迹数量: {total_trajectories:,}\n")
            percentage = total_with_official/total_trajectories*100 if total_trajectories > 0 else 0.0
            f.write(f"有官方机场信息的轨迹: {total_with_official:,} ({percentage:.1f}%)\n\n")
            
            if all_start_distances:
                f.write("=== 起点到起飞机场距离分析 ===\n")
                f.write(f"分析轨迹数量: {len(all_start_distances):,}\n")
                f.write(f"平均距离: {np.mean(all_start_distances):.2f} 公里\n")
                f.write(f"中位数距离: {np.median(all_start_distances):.2f} 公里\n")
                f.write(f"最小距离: {np.min(all_start_distances):.2f} 公里\n")
                f.write(f"最大距离: {np.max(all_start_distances):.2f} 公里\n")
                f.write(f"50公里内轨迹: {total_start_within_50km:,} ({total_start_within_50km/len(all_start_distances)*100:.1f}%)\n\n")
            
            if all_end_distances:
                f.write("=== 终点到降落机场距离分析 ===\n")
                f.write(f"分析轨迹数量: {len(all_end_distances):,}\n")
                f.write(f"平均距离: {np.mean(all_end_distances):.2f} 公里\n")
                f.write(f"中位数距离: {np.median(all_end_distances):.2f} 公里\n")
                f.write(f"最小距离: {np.min(all_end_distances):.2f} 公里\n")
                f.write(f"最大距离: {np.max(all_end_distances):.2f} 公里\n")
                f.write(f"50公里内轨迹: {total_end_within_50km:,} ({total_end_within_50km/len(all_end_distances)*100:.1f}%)\n\n")
            
            f.write("=== 机场数据统计 ===\n")
            f.write(f"筛选过的机场总数: {len(self.airports_df)}\n")
            f.write("机场类型分布:\n")
            for airport_type, count in self.airports_df['type'].value_counts().items():
                f.write(f"  {airport_type}: {count}\n")
            
            f.write(f"\nIATA代码覆盖: {len(self.iata_to_coords)} 个机场\n")
            f.write(f"ICAO代码覆盖: {len(self.icao_to_coords)} 个机场\n\n")
            
            f.write("=== 官方航班数据统计 ===\n")
            if hasattr(self, 'official_flights_df') and self.official_flights_df is not None:
                f.write(f"官方航班记录总数: {len(self.official_flights_df):,}\n")
                f.write(f"有效航班映射: {len(self.flight_to_airports):,}\n")
            else:
                f.write("未加载官方航班数据\n")
            
            # 错误统计
            errors = [r for r in self.analysis_results if r['error']]
            if errors:
                f.write(f"\n=== 处理错误 ===\n")
                f.write(f"出错文件数量: {len(errors)}\n")
                for error in errors[:10]:  # 只显示前10个错误
                    f.write(f"  {error['file']}: {error['error']}\n")
        
        print(f"报告已保存到: {report_file}")
        
        # 打印关键统计信息
        print(f"\n=== 关键结果 ===")
        print(f"总轨迹数量: {total_trajectories:,}")
        print(f"有官方机场信息的轨迹: {total_with_official:,} ({percentage:.1f}%)")
        
        if all_start_distances:
            print(f"起点平均距离: {np.mean(all_start_distances):.2f} 公里")
            print(f"起点50公里内: {total_start_within_50km/len(all_start_distances)*100:.1f}%")
        
        if all_end_distances:
            print(f"终点平均距离: {np.mean(all_end_distances):.2f} 公里")
            print(f"终点50公里内: {total_end_within_50km/len(all_end_distances)*100:.1f}%")
    
    def create_visualizations(self):
        """创建可视化图表"""
        # 收集所有距离数据
        all_start_distances = []
        all_end_distances = []
        
        for result in self.analysis_results:
            all_start_distances.extend(result['start_distances'])
            all_end_distances.extend(result['end_distances'])
        
        if not all_start_distances and not all_end_distances:
            print("没有距离数据，跳过可视化")
            return
        
        # 创建图表
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('优化的机场完整性分析结果', fontsize=16, fontweight='bold')
        
        # 起点距离分布
        if all_start_distances:
            axes[0, 0].hist(all_start_distances, bins=50, alpha=0.7, color='blue', edgecolor='black')
            axes[0, 0].axvline(50, color='red', linestyle='--', label='50公里阈值')
            axes[0, 0].set_title(f'起点到起飞机场距离分布\n(平均: {np.mean(all_start_distances):.1f}km)')
            axes[0, 0].set_xlabel('距离 (公里)')
            axes[0, 0].set_ylabel('轨迹数量')
            axes[0, 0].legend()
            axes[0, 0].grid(True, alpha=0.3)
        
        # 终点距离分布
        if all_end_distances:
            axes[0, 1].hist(all_end_distances, bins=50, alpha=0.7, color='green', edgecolor='black')
            axes[0, 1].axvline(50, color='red', linestyle='--', label='50公里阈值')
            axes[0, 1].set_title(f'终点到降落机场距离分布\n(平均: {np.mean(all_end_distances):.1f}km)')
            axes[0, 1].set_xlabel('距离 (公里)')
            axes[0, 1].set_ylabel('轨迹数量')
            axes[0, 1].legend()
            axes[0, 1].grid(True, alpha=0.3)
        
        # 机场类型分布
        airport_types = self.airports_df['type'].value_counts()
        axes[1, 0].pie(airport_types.values, labels=airport_types.index, autopct='%1.1f%%')
        axes[1, 0].set_title(f'筛选机场类型分布\n(总计: {len(self.airports_df)} 个)')
        
        # 完整性统计
        if all_start_distances and all_end_distances:
            start_within_50 = sum(1 for d in all_start_distances if d <= 50)
            end_within_50 = sum(1 for d in all_end_distances if d <= 50)
            
            categories = ['起点50km内', '起点50km外', '终点50km内', '终点50km外']
            values = [
                start_within_50,
                len(all_start_distances) - start_within_50,
                end_within_50,
                len(all_end_distances) - end_within_50
            ]
            colors = ['lightgreen', 'lightcoral', 'lightblue', 'lightyellow']
            
            bars = axes[1, 1].bar(categories, values, color=colors, edgecolor='black')
            axes[1, 1].set_title('机场邻近度统计')
            axes[1, 1].set_ylabel('轨迹数量')
            axes[1, 1].tick_params(axis='x', rotation=45)
            
            # 添加数值标签
            for bar, value in zip(bars, values):
                height = bar.get_height()
                axes[1, 1].text(bar.get_x() + bar.get_width()/2., height + height*0.01,
                               f'{value:,}', ha='center', va='bottom')
        
        plt.tight_layout()
        
        # 保存图表
        chart_file = self.output_dir / "optimized_airport_analysis_dashboard.png"
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"可视化图表已保存到: {chart_file}")

def main():
    """主函数"""
    data_dir = "/workspace/aircraft_trajectory/team_likable_jelly"
    output_dir = "/workspace/aircraft_trajectory/team_likable_jelly/trajectory_statistics_analysis/optimized_analysis"
    
    analyzer = OptimizedAirportAnalyzer(data_dir, output_dir)
    
    # 先用5个文件测试
    print("开始优化的机场完整性分析（测试模式：5个文件）...")
    analyzer.run_analysis(max_files=5)

if __name__ == "__main__":
    main()