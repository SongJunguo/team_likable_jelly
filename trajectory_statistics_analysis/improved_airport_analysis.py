#!/usr/bin/env python3
"""
改进的机场完整性分析脚本
使用官方机场数据和轨迹起降机场信息进行精确分析
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import multiprocessing as mp
from functools import partial
import warnings
warnings.filterwarnings('ignore')

class ImprovedAirportAnalyzer:
    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.trajectory_dir = self.base_dir / "perfect_trajectories"
        self.output_dir = self.base_dir / "trajectory_statistics_analysis" / "improved_analysis"
        self.output_dir.mkdir(exist_ok=True)
        
        # 数据文件路径
        self.airport_data_file = self.base_dir / "ourairports2024-10-21.csv"
        self.challenge_set_file = self.base_dir / "opensky_2024_PRC_dataset" / "challenge_set.csv"
        self.final_submission_file = self.base_dir / "opensky_2024_PRC_dataset" / "final_submission_set.csv"
        self.submission_file = self.base_dir / "opensky_2024_PRC_dataset" / "submission_set.csv"
        
        # 加载数据
        self.load_airport_data()
        self.load_official_trajectory_data()
        
    def load_airport_data(self):
        """加载机场数据"""
        print("加载机场数据...")
        self.airports_df = pd.read_csv(self.airport_data_file)
        
        # 过滤出有效的机场（有ICAO代码和坐标）
        self.airports_df = self.airports_df[
            (self.airports_df['ident'].notna()) & 
            (self.airports_df['latitude_deg'].notna()) & 
            (self.airports_df['longitude_deg'].notna())
        ].copy()
        
        # 创建ICAO代码到机场信息的映射
        self.airport_dict = {}
        for _, row in self.airports_df.iterrows():
            icao = row['ident']
            self.airport_dict[icao] = {
                'name': row['name'],
                'latitude': row['latitude_deg'],
                'longitude': row['longitude_deg'],
                'elevation': row['elevation_ft'],
                'country': row['iso_country'],
                'type': row['type']
            }
        
        print(f"加载了 {len(self.airport_dict)} 个机场的数据")
        
    def load_official_trajectory_data(self):
        """加载官方轨迹数据"""
        print("加载官方轨迹数据...")
        
        # 合并三个数据集
        datasets = []
        
        if self.challenge_set_file.exists():
            df_challenge = pd.read_csv(self.challenge_set_file)
            df_challenge['dataset'] = 'challenge'
            datasets.append(df_challenge)
            
        if self.final_submission_file.exists():
            df_final = pd.read_csv(self.final_submission_file)
            df_final['dataset'] = 'final_submission'
            datasets.append(df_final)
            
        if self.submission_file.exists():
            df_submission = pd.read_csv(self.submission_file)
            df_submission['dataset'] = 'submission'
            datasets.append(df_submission)
        
        if datasets:
            self.official_trajectories = pd.concat(datasets, ignore_index=True)
            # 去重（基于flight_id）
            self.official_trajectories = self.official_trajectories.drop_duplicates(subset=['flight_id'])
            print(f"加载了 {len(self.official_trajectories)} 条官方轨迹记录")
        else:
            self.official_trajectories = pd.DataFrame()
            print("未找到官方轨迹数据文件")
    
    def haversine_distance(self, lat1, lon1, lat2, lon2):
        """计算两点间的距离（公里）"""
        R = 6371  # 地球半径（公里）
        
        lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
        c = 2 * np.arcsin(np.sqrt(a))
        
        return R * c
    
    def find_nearest_airport(self, lat, lon, airport_type_filter=None):
        """找到最近的机场"""
        min_distance = float('inf')
        nearest_airport = None
        
        for icao, airport_info in self.airport_dict.items():
            # 如果指定了机场类型过滤
            if airport_type_filter and airport_info['type'] not in airport_type_filter:
                continue
                
            distance = self.haversine_distance(
                lat, lon, 
                airport_info['latitude'], 
                airport_info['longitude']
            )
            
            if distance < min_distance:
                min_distance = distance
                nearest_airport = {
                    'icao': icao,
                    'distance': distance,
                    **airport_info
                }
        
        return nearest_airport
    
    def analyze_trajectory_file(self, file_path):
        """分析单个轨迹文件"""
        try:
            df = pd.read_parquet(file_path)
            if df.empty:
                return []
            
            results = []
            
            # 按flight_id分组
            for flight_id, group in df.groupby('flight_id'):
                if len(group) < 2:
                    continue
                
                # 获取起点和终点
                start_point = group.iloc[0]
                end_point = group.iloc[-1]
                
                # 查找官方数据中的起降机场信息
                official_info = self.official_trajectories[
                    self.official_trajectories['flight_id'] == flight_id
                ]
                
                result = {
                    'flight_id': flight_id,
                    'file': file_path.name,
                    'start_lat': start_point['latitude'],
                    'start_lon': start_point['longitude'],
                    'end_lat': end_point['latitude'],
                    'end_lon': end_point['longitude'],
                    'trajectory_points': len(group),
                    'duration_minutes': (group['timestamp'].max() - group['timestamp'].min()) / 60
                }
                
                # 添加官方起降机场信息
                if not official_info.empty:
                    official_row = official_info.iloc[0]
                    result.update({
                        'official_adep': official_row['adep'],
                        'official_ades': official_row['ades'],
                        'official_adep_name': official_row['name_adep'],
                        'official_ades_name': official_row['name_ades'],
                        'official_adep_country': official_row['country_code_adep'],
                        'official_ades_country': official_row['country_code_ades']
                    })
                    
                    # 计算到官方起降机场的距离
                    if official_row['adep'] in self.airport_dict:
                        adep_info = self.airport_dict[official_row['adep']]
                        result['distance_to_official_adep'] = self.haversine_distance(
                            start_point['latitude'], start_point['longitude'],
                            adep_info['latitude'], adep_info['longitude']
                        )
                    else:
                        result['distance_to_official_adep'] = None
                        
                    if official_row['ades'] in self.airport_dict:
                        ades_info = self.airport_dict[official_row['ades']]
                        result['distance_to_official_ades'] = self.haversine_distance(
                            end_point['latitude'], end_point['longitude'],
                            ades_info['latitude'], ades_info['longitude']
                        )
                    else:
                        result['distance_to_official_ades'] = None
                else:
                    # 没有官方数据，查找最近的机场
                    result.update({
                        'official_adep': None,
                        'official_ades': None,
                        'official_adep_name': None,
                        'official_ades_name': None,
                        'official_adep_country': None,
                        'official_ades_country': None,
                        'distance_to_official_adep': None,
                        'distance_to_official_ades': None
                    })
                
                # 查找最近的机场（所有类型）
                nearest_start = self.find_nearest_airport(
                    start_point['latitude'], start_point['longitude']
                )
                nearest_end = self.find_nearest_airport(
                    end_point['latitude'], end_point['longitude']
                )
                
                if nearest_start:
                    result.update({
                        'nearest_start_airport': nearest_start['icao'],
                        'nearest_start_airport_name': nearest_start['name'],
                        'distance_to_nearest_start': nearest_start['distance']
                    })
                
                if nearest_end:
                    result.update({
                        'nearest_end_airport': nearest_end['icao'],
                        'nearest_end_airport_name': nearest_end['name'],
                        'distance_to_nearest_end': nearest_end['distance']
                    })
                
                results.append(result)
                
            return results
            
        except Exception as e:
            print(f"处理文件 {file_path} 时出错: {e}")
            return []
    
    def run_analysis(self, max_files=None):
        """运行完整分析"""
        print("开始改进的机场完整性分析...")
        
        # 获取所有轨迹文件
        trajectory_files = list(self.trajectory_dir.glob("*.parquet"))
        if max_files:
            trajectory_files = trajectory_files[:max_files]
        
        print(f"找到 {len(trajectory_files)} 个轨迹文件")
        
        # 多进程处理
        with mp.Pool(processes=min(mp.cpu_count(), len(trajectory_files))) as pool:
            results_list = pool.map(self.analyze_trajectory_file, trajectory_files)
        
        # 合并结果
        all_results = []
        for results in results_list:
            all_results.extend(results)
        
        if not all_results:
            print("没有找到有效的轨迹数据")
            return
        
        # 转换为DataFrame
        self.results_df = pd.DataFrame(all_results)
        print(f"分析了 {len(self.results_df)} 条轨迹")
        
        # 生成报告
        self.generate_comprehensive_report()
        self.create_visualizations()
        
    def generate_comprehensive_report(self):
        """生成综合报告"""
        report_file = self.output_dir / "improved_airport_analysis_report.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("改进的机场完整性分析报告\n")
            f.write("=" * 80 + "\n")
            f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"分析轨迹数量: {len(self.results_df)}\n\n")
            
            # 基本统计
            f.write("1. 基本统计信息\n")
            f.write("-" * 40 + "\n")
            f.write(f"总轨迹数: {len(self.results_df)}\n")
            f.write(f"平均轨迹点数: {self.results_df['trajectory_points'].mean():.1f}\n")
            f.write(f"平均飞行时长: {self.results_df['duration_minutes'].mean():.1f} 分钟\n\n")
            
            # 官方数据匹配情况
            has_official_data = self.results_df['official_adep'].notna()
            f.write("2. 官方数据匹配情况\n")
            f.write("-" * 40 + "\n")
            f.write(f"有官方起降机场数据的轨迹: {has_official_data.sum()} ({has_official_data.mean()*100:.1f}%)\n")
            f.write(f"无官方起降机场数据的轨迹: {(~has_official_data).sum()} ({(~has_official_data).mean()*100:.1f}%)\n\n")
            
            # 距离分析（有官方数据的轨迹）
            if has_official_data.any():
                official_subset = self.results_df[has_official_data]
                
                f.write("3. 到官方起降机场的距离分析\n")
                f.write("-" * 40 + "\n")
                
                # 起点到官方起飞机场的距离
                valid_adep_distances = official_subset['distance_to_official_adep'].dropna()
                if not valid_adep_distances.empty:
                    f.write(f"起点到官方起飞机场平均距离: {valid_adep_distances.mean():.1f} km\n")
                    f.write(f"起点到官方起飞机场中位数距离: {valid_adep_distances.median():.1f} km\n")
                    
                    # 距离阈值分析
                    thresholds = [5, 10, 20, 50, 100]
                    for threshold in thresholds:
                        within_threshold = (valid_adep_distances <= threshold).sum()
                        percentage = within_threshold / len(valid_adep_distances) * 100
                        f.write(f"起点在官方起飞机场 {threshold}km 内: {within_threshold} ({percentage:.1f}%)\n")
                
                f.write("\n")
                
                # 终点到官方降落机场的距离
                valid_ades_distances = official_subset['distance_to_official_ades'].dropna()
                if not valid_ades_distances.empty:
                    f.write(f"终点到官方降落机场平均距离: {valid_ades_distances.mean():.1f} km\n")
                    f.write(f"终点到官方降落机场中位数距离: {valid_ades_distances.median():.1f} km\n")
                    
                    # 距离阈值分析
                    for threshold in thresholds:
                        within_threshold = (valid_ades_distances <= threshold).sum()
                        percentage = within_threshold / len(valid_ades_distances) * 100
                        f.write(f"终点在官方降落机场 {threshold}km 内: {within_threshold} ({percentage:.1f}%)\n")
                
                f.write("\n")
            
            # 最近机场分析
            f.write("4. 最近机场分析\n")
            f.write("-" * 40 + "\n")
            
            valid_start_distances = self.results_df['distance_to_nearest_start'].dropna()
            valid_end_distances = self.results_df['distance_to_nearest_end'].dropna()
            
            if not valid_start_distances.empty:
                f.write(f"起点到最近机场平均距离: {valid_start_distances.mean():.1f} km\n")
                f.write(f"起点到最近机场中位数距离: {valid_start_distances.median():.1f} km\n")
            
            if not valid_end_distances.empty:
                f.write(f"终点到最近机场平均距离: {valid_end_distances.mean():.1f} km\n")
                f.write(f"终点到最近机场中位数距离: {valid_end_distances.median():.1f} km\n")
            
            f.write("\n")
            
            # 热门机场统计
            if has_official_data.any():
                f.write("5. 热门起降机场\n")
                f.write("-" * 40 + "\n")
                
                # 起飞机场
                adep_counts = self.results_df['official_adep'].value_counts().head(10)
                f.write("热门起飞机场:\n")
                for airport, count in adep_counts.items():
                    airport_name = self.results_df[self.results_df['official_adep'] == airport]['official_adep_name'].iloc[0]
                    f.write(f"  {airport} ({airport_name}): {count} 次\n")
                
                f.write("\n")
                
                # 降落机场
                ades_counts = self.results_df['official_ades'].value_counts().head(10)
                f.write("热门降落机场:\n")
                for airport, count in ades_counts.items():
                    airport_name = self.results_df[self.results_df['official_ades'] == airport]['official_ades_name'].iloc[0]
                    f.write(f"  {airport} ({airport_name}): {count} 次\n")
            
            f.write("\n")
            
            # 完整性评估
            f.write("6. 轨迹完整性评估\n")
            f.write("-" * 40 + "\n")
            
            if has_official_data.any():
                # 基于官方数据的完整性评估
                official_subset = self.results_df[has_official_data]
                
                # 定义完整性标准
                excellent_adep = (official_subset['distance_to_official_adep'] <= 10).fillna(False)
                excellent_ades = (official_subset['distance_to_official_ades'] <= 10).fillna(False)
                excellent_both = excellent_adep & excellent_ades
                
                good_adep = (official_subset['distance_to_official_adep'] <= 50).fillna(False)
                good_ades = (official_subset['distance_to_official_ades'] <= 50).fillna(False)
                good_both = good_adep & good_ades
                
                f.write("基于官方起降机场的完整性评估:\n")
                f.write(f"优秀级别 (起降点均在10km内): {excellent_both.sum()} ({excellent_both.mean()*100:.1f}%)\n")
                f.write(f"良好级别 (起降点均在50km内): {good_both.sum()} ({good_both.mean()*100:.1f}%)\n")
                f.write(f"起点完整 (在官方起飞机场10km内): {excellent_adep.sum()} ({excellent_adep.mean()*100:.1f}%)\n")
                f.write(f"终点完整 (在官方降落机场10km内): {excellent_ades.sum()} ({excellent_ades.mean()*100:.1f}%)\n")
        
        print(f"报告已保存到: {report_file}")
        
        # 保存详细数据
        data_file = self.output_dir / "improved_airport_analysis_data.csv"
        self.results_df.to_csv(data_file, index=False, encoding='utf-8')
        print(f"详细数据已保存到: {data_file}")
    
    def create_visualizations(self):
        """创建可视化图表"""
        plt.style.use('default')
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('改进的机场完整性分析', fontsize=16, fontweight='bold')
        
        # 1. 距离分布（有官方数据的轨迹）
        has_official = self.results_df['official_adep'].notna()
        if has_official.any():
            official_subset = self.results_df[has_official]
            
            ax1 = axes[0, 0]
            distances_adep = official_subset['distance_to_official_adep'].dropna()
            distances_ades = official_subset['distance_to_official_ades'].dropna()
            
            if not distances_adep.empty and not distances_ades.empty:
                ax1.hist([distances_adep, distances_ades], bins=50, alpha=0.7, 
                        label=['到起飞机场', '到降落机场'], color=['blue', 'red'])
                ax1.set_xlabel('距离 (km)')
                ax1.set_ylabel('轨迹数量')
                ax1.set_title('到官方起降机场的距离分布')
                ax1.legend()
                ax1.set_xlim(0, 200)  # 限制显示范围以便观察
        
        # 2. 完整性分类饼图
        ax2 = axes[0, 1]
        if has_official.any():
            official_subset = self.results_df[has_official]
            
            excellent_both = ((official_subset['distance_to_official_adep'] <= 10) & 
                            (official_subset['distance_to_official_ades'] <= 10)).fillna(False)
            good_both = ((official_subset['distance_to_official_adep'] <= 50) & 
                        (official_subset['distance_to_official_ades'] <= 50)).fillna(False)
            
            excellent_count = excellent_both.sum()
            good_count = good_both.sum() - excellent_count
            poor_count = len(official_subset) - good_both.sum()
            
            labels = ['优秀 (≤10km)', '良好 (≤50km)', '较差 (>50km)']
            sizes = [excellent_count, good_count, poor_count]
            colors = ['green', 'yellow', 'red']
            
            ax2.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
            ax2.set_title('轨迹完整性分类\n(基于官方起降机场)')
        
        # 3. 热门机场
        ax3 = axes[1, 0]
        if has_official.any():
            top_airports = pd.concat([
                self.results_df['official_adep'].value_counts().head(5),
                self.results_df['official_ades'].value_counts().head(5)
            ]).groupby(level=0).sum().sort_values(ascending=True).tail(10)
            
            top_airports.plot(kind='barh', ax=ax3)
            ax3.set_xlabel('航班数量')
            ax3.set_title('热门机场 (起降总数)')
        
        # 4. 轨迹长度vs完整性
        ax4 = axes[1, 1]
        if has_official.any():
            official_subset = self.results_df[has_official]
            
            complete_mask = ((official_subset['distance_to_official_adep'] <= 50) & 
                           (official_subset['distance_to_official_ades'] <= 50)).fillna(False)
            
            complete_points = official_subset[complete_mask]['trajectory_points']
            incomplete_points = official_subset[~complete_mask]['trajectory_points']
            
            ax4.hist([complete_points, incomplete_points], bins=30, alpha=0.7,
                    label=['完整轨迹', '不完整轨迹'], color=['green', 'red'])
            ax4.set_xlabel('轨迹点数')
            ax4.set_ylabel('轨迹数量')
            ax4.set_title('轨迹点数分布 (按完整性分类)')
            ax4.legend()
        
        plt.tight_layout()
        
        # 保存图表
        plot_file = self.output_dir / "improved_airport_analysis_plots.png"
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"可视化图表已保存到: {plot_file}")

def main():
    """主函数"""
    base_dir = "/workspace/aircraft_trajectory/team_likable_jelly"
    
    analyzer = ImprovedAirportAnalyzer(base_dir)
    analyzer.run_analysis(max_files=5)  # 先测试5个文件
    
    print("\n改进的机场完整性分析完成！")

if __name__ == "__main__":
    main()