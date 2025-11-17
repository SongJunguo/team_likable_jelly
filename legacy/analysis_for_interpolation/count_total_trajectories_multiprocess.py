#!/usr/bin/env python3
"""
多进程统计整个插值后数据集的总轨迹数量
针对280GB数据和80核心CPU优化
"""

import pandas as pd
import os
import glob
from datetime import datetime
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
import time
import psutil

def count_trajectories_in_file(file_path):
    """统计单个文件中的轨迹数量"""
    try:
        # 使用更高效的读取方式
        df = pd.read_parquet(file_path, columns=['flight_id'])  # 只读取需要的列
        unique_flights = df.flight_id.nunique()
        
        # 获取总行数而不加载整个数据
        df_full = pd.read_parquet(file_path)
        total_points = len(df_full)
        
        filename = os.path.basename(file_path)
        return {
            'filename': filename,
            'flights': unique_flights,
            'points': total_points,
            'file_size_mb': os.path.getsize(file_path) / (1024*1024)
        }
    except Exception as e:
        filename = os.path.basename(file_path)
        print(f"处理文件 {filename} 时出错: {e}")
        return {
            'filename': filename,
            'flights': 0,
            'points': 0,
            'file_size_mb': 0,
            'error': str(e)
        }

def process_file_batch(file_batch):
    """处理一批文件"""
    results = []
    for file_path in file_batch:
        result = count_trajectories_in_file(file_path)
        results.append(result)
    return results

def get_optimal_workers():
    """根据系统资源确定最优工作进程数"""
    cpu_count = psutil.cpu_count(logical=True)
    memory_gb = psutil.virtual_memory().total / (1024**3)
    
    # 考虑到每个进程可能需要处理大文件，限制并发数
    # 假设每个进程最多使用4GB内存
    max_workers_by_memory = int(memory_gb / 4)
    
    # 使用CPU核心数的75%，留一些资源给系统
    max_workers_by_cpu = int(cpu_count * 0.75)
    
    # 取较小值，但至少4个进程
    optimal_workers = max(4, min(max_workers_by_memory, max_workers_by_cpu, 60))
    
    print(f"系统信息:")
    print(f"  CPU核心数: {cpu_count}")
    print(f"  内存: {memory_gb:.1f} GB")
    print(f"  建议工作进程数: {optimal_workers}")
    
    return optimal_workers

def create_file_batches(files, num_batches):
    """将文件列表分成批次"""
    batch_size = len(files) // num_batches
    if batch_size == 0:
        batch_size = 1
    
    batches = []
    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        if batch:
            batches.append(batch)
    
    return batches

def main():
    """主函数"""
    start_time = time.time()
    
    os.chdir('/workspace/aircraft_trajectory/team_likable_jelly')
    
    # 插值后数据目录
    interp_dir = 'opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories/'
    
    if not os.path.exists(interp_dir):
        print(f"目录不存在: {interp_dir}")
        return
    
    # 获取所有parquet文件
    parquet_files = glob.glob(os.path.join(interp_dir, '*.parquet'))
    parquet_files.sort()
    
    if not parquet_files:
        print(f"在 {interp_dir} 中没有找到parquet文件")
        return
    
    print(f"找到 {len(parquet_files)} 个parquet文件")
    
    # 计算总文件大小
    total_size_gb = sum(os.path.getsize(f) for f in parquet_files) / (1024**3)
    print(f"总数据大小: {total_size_gb:.1f} GB")
    
    # 确定最优工作进程数
    num_workers = get_optimal_workers()
    
    print(f"\n开始多进程统计轨迹数量...")
    print(f"使用 {num_workers} 个工作进程")
    
    # 使用ProcessPoolExecutor进行多进程处理
    all_results = []
    completed_files = 0
    
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # 提交所有文件处理任务
        future_to_file = {
            executor.submit(count_trajectories_in_file, file_path): file_path 
            for file_path in parquet_files
        }
        
        # 收集结果
        for future in as_completed(future_to_file):
            file_path = future_to_file[future]
            try:
                result = future.result()
                all_results.append(result)
                completed_files += 1
                
                if completed_files % 10 == 0 or completed_files == len(parquet_files):
                    elapsed = time.time() - start_time
                    progress = completed_files / len(parquet_files) * 100
                    eta = elapsed / completed_files * (len(parquet_files) - completed_files)
                    print(f"进度: {completed_files}/{len(parquet_files)} ({progress:.1f}%) "
                          f"已用时: {elapsed/60:.1f}分钟, 预计剩余: {eta/60:.1f}分钟")
                
            except Exception as e:
                print(f"处理文件 {os.path.basename(file_path)} 时出错: {e}")
    
    # 统计结果
    total_flights = sum(r['flights'] for r in all_results)
    total_points = sum(r['points'] for r in all_results)
    total_size_mb = sum(r['file_size_mb'] for r in all_results)
    
    # 统计错误文件
    error_files = [r for r in all_results if 'error' in r]
    
    elapsed_time = time.time() - start_time
    
    print("\n" + "="*80)
    print("多进程统计结果:")
    print("="*80)
    print(f"处理时间: {elapsed_time/60:.1f} 分钟")
    print(f"总文件数: {len(parquet_files)}")
    print(f"成功处理: {len(all_results) - len(error_files)}")
    print(f"错误文件: {len(error_files)}")
    print(f"总数据大小: {total_size_mb/1024:.1f} GB")
    print(f"总航班数: {total_flights:,}")
    print(f"总轨迹点数: {total_points:,}")
    print(f"平均每个文件的航班数: {total_flights/len(parquet_files):.0f}")
    print(f"平均每个航班的轨迹点数: {total_points/total_flights:.0f}")
    print(f"处理速度: {total_size_mb/1024/elapsed_time*60:.1f} GB/分钟")
    
    # 保存详细统计
    stats_df = pd.DataFrame(all_results)
    stats_df.to_csv('trajectory_count_stats_multiprocess.csv', index=False)
    print(f"\n详细统计已保存到: trajectory_count_stats_multiprocess.csv")
    
    # 计算建议的抽样数量
    print("\n建议的抽样方案:")
    for pct in [10, 20, 30]:
        sample_flights = int(total_flights * pct / 100)
        print(f"  {pct}% 抽样: {sample_flights:,} 个航班")
    
    # 如果有错误文件，列出它们
    if error_files:
        print(f"\n错误文件列表:")
        for error_file in error_files:
            print(f"  {error_file['filename']}: {error_file.get('error', 'Unknown error')}")

if __name__ == "__main__":
    # 设置多进程启动方法
    mp.set_start_method('spawn', force=True)
    main()