#!/usr/bin/env python3
"""
测试 data_wrangler 环境的数据处理能力
测试核心包：pandas、numpy、pyarrow、scipy、matplotlib、geopandas 等
"""
import sys
import time
from pathlib import Path

def test_basic_imports():
    """测试基本包导入"""
    print("=" * 80)
    print("测试 1: 基本包导入")
    print("=" * 80)
    
    packages = [
        'numpy', 'pandas', 'pyarrow', 'scipy', 'matplotlib',
        'seaborn', 'sklearn', 'polars', 'shapely', 'geopandas',
        'cartopy', 'tqdm', 'joblib'
    ]
    
    results = {}
    for pkg in packages:
        try:
            if pkg == 'sklearn':
                __import__('sklearn')
                import sklearn
                version = sklearn.__version__
            else:
                module = __import__(pkg)
                version = getattr(module, '__version__', 'unknown')
            results[pkg] = ('✓', version)
            print(f"  ✓ {pkg:20s} {version}")
        except ImportError as e:
            results[pkg] = ('✗', str(e))
            print(f"  ✗ {pkg:20s} 导入失败: {e}")
    
    return results

def test_parquet_reading():
    """测试 parquet 文件读取"""
    print("\n" + "=" * 80)
    print("测试 2: Parquet 文件读取（使用 perfect_trajectories）")
    print("=" * 80)
    
    import pandas as pd
    import pyarrow.parquet as pq
    from pathlib import Path
    
    data_dir = Path('/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories')
    
    if not data_dir.exists():
        print(f"  ⚠ 数据目录不存在: {data_dir}")
        return False
    
    # 读取第一个文件
    parquet_files = list(data_dir.glob('*.parquet'))
    if not parquet_files:
        print(f"  ⚠ 未找到 parquet 文件")
        return False
    
    test_file = parquet_files[0]
    print(f"  读取测试文件: {test_file.name}")
    
    start = time.time()
    df = pd.read_parquet(test_file)
    elapsed = time.time() - start
    
    print(f"  ✓ 读取成功!")
    print(f"    - 耗时: {elapsed:.3f} 秒")
    print(f"    - 行数: {len(df):,}")
    print(f"    - 列数: {len(df.columns)}")
    print(f"    - 列名: {list(df.columns)[:5]}...")
    print(f"    - 内存占用: {df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    
    return True

def _compute_task(n):
    """简单计算任务（顶层函数，可被 pickle）"""
    import numpy as np
    arr = np.random.rand(1000, 1000)
    return np.sum(arr ** 2)

def test_multiprocessing():
    """测试多进程能力"""
    print("\n" + "=" * 80)
    print("测试 3: 多进程计算")
    print("=" * 80)
    
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing
    
    cpu_count = multiprocessing.cpu_count()
    print(f"  可用 CPU 核心数: {cpu_count}")
    
    # 测试 8 个并行任务
    n_tasks = 8
    print(f"  测试 {n_tasks} 个并行计算任务...")
    
    start = time.time()
    with ProcessPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(_compute_task, range(n_tasks)))
    elapsed = time.time() - start
    
    print(f"  ✓ 多进程计算成功!")
    print(f"    - 耗时: {elapsed:.3f} 秒")
    print(f"    - 完成任务数: {len(results)}")
    
    return True

def test_geopandas():
    """测试地理数据处理"""
    print("\n" + "=" * 80)
    print("测试 4: 地理数据处理 (geopandas)")
    print("=" * 80)
    
    import geopandas as gpd
    from shapely.geometry import Point
    import pandas as pd
    
    # 创建简单的地理数据
    data = {
        'name': ['北京', '上海', '广州'],
        'lon': [116.4074, 121.4737, 113.2644],
        'lat': [39.9042, 31.2304, 23.1291]
    }
    df = pd.DataFrame(data)
    
    # 转换为 GeoDataFrame
    geometry = [Point(lon, lat) for lon, lat in zip(df['lon'], df['lat'])]
    gdf = gpd.GeoDataFrame(df, geometry=geometry, crs='EPSG:4326')
    
    print(f"  ✓ GeoDataFrame 创建成功!")
    print(f"    - 行数: {len(gdf)}")
    print(f"    - CRS: {gdf.crs}")
    print(f"    - 几何类型: {gdf.geometry.type.unique()}")
    
    # 计算点之间的距离
    gdf_utm = gdf.to_crs('EPSG:32650')  # 转换到 UTM
    print(f"  ✓ 坐标转换成功 (WGS84 -> UTM)")
    
    return True

def main():
    print("\n" + "=" * 80)
    print("data_wrangler 环境测试")
    print(f"Python 版本: {sys.version}")
    print("=" * 80)
    
    # 运行所有测试
    test_basic_imports()
    test_parquet_reading()
    test_multiprocessing()
    test_geopandas()
    
    print("\n" + "=" * 80)
    print("✓ 所有测试完成!")
    print("=" * 80)

if __name__ == '__main__':
    main()
