import pandas as pd
import os

# ================= 配置区域 =================
META_DIR = 'Meta'

FILES_TO_MERGE = [
    os.path.join(META_DIR, 'challenge_set.csv'),
    os.path.join(META_DIR, 'final_submission_set.csv'),
    os.path.join(META_DIR, 'submission_set.csv')
]

OUTPUT_FILE = os.path.join(META_DIR, 'metadata_all.csv')

# 1. 日期截止 (只取一周)
CUTOFF_DATE = '2022-01-14' 

# 2. 热门机场筛选 (Top 8)
TOP_N_AIRPORTS = 10  

# 3. 【新增】热门机型筛选 (Top 5)
# 通常是 A320, B738, A321, B737 等
TOP_N_AIRCRAFT = 5

def process_metadata():
    print(f"🚀 开始处理，仅保留 {CUTOFF_DATE} 及其之前的数据...")
    print(f"📂 正在从 '{META_DIR}' 文件夹读取数据...")
    
    df_list = []
    
    # --- 1. 读取原始数据 ---
    for filepath in FILES_TO_MERGE:
        filename = os.path.basename(filepath)
        if os.path.exists(filepath):
            try:
                # 【修改点】增加读取 'aircraft_type'
                df = pd.read_csv(filepath, usecols=['flight_id', 'adep', 'ades', 'date', 'aircraft_type'])
                df['date'] = pd.to_datetime(df['date'])
                
                # 日期筛选
                df = df[df['date'] <= CUTOFF_DATE]
                
                # 简单清洗机型 (转大写，去空格)
                df['aircraft_type'] = df['aircraft_type'].astype(str).str.upper().str.strip()
                
                df['flight_id'] = df['flight_id'].astype(str)
                df_list.append(df)
                print(f"   -> 已读取 {filename} | 当前行数: {len(df)}")
            except Exception as e:
                print(f"   ⚠️ 读取 {filename} 失败: {e}")
        else:
            print(f"   ⚠️ 文件不存在: {filepath}")

    if not df_list: return

    # --- 2. 合并与初步处理 ---
    df_final = pd.concat(df_list, ignore_index=True)
    df_final.drop_duplicates(subset=['flight_id'], inplace=True)
    
    # 填充缺失值
    df_final.fillna({'adep': 'UNKNOWN', 'ades': 'UNKNOWN', 'aircraft_type': 'UNKNOWN'}, inplace=True)

    total_initial = len(df_final)
    print(f"\n🔄 初步合并完成，共 {total_initial} 条航班。")

    # ================= 核心筛选逻辑 (机场 & 机型) =================
    
    # --- A. 统计并筛选热门机场 ---
    print(f"\n🔍 正在筛选 Top {TOP_N_AIRPORTS} 热门机场...")
    airport_counts = pd.concat([df_final['adep'], df_final['ades']]).value_counts()
    top_airports = airport_counts.head(TOP_N_AIRPORTS).index.tolist()
    print(f"   -> 热门机场: {top_airports}")

    # --- B. 【新增】统计并筛选热门机型 ---
    print(f"\n✈️ 正在筛选 Top {TOP_N_AIRCRAFT} 热门机型...")
    aircraft_counts = df_final['aircraft_type'].value_counts()
    
    # 获取前 N 个机型
    top_aircraft_types = aircraft_counts.head(TOP_N_AIRCRAFT).index.tolist()
    
    print(f"   -> 热门机型分布:\n{aircraft_counts.head(TOP_N_AIRCRAFT)}")
    print(f"   -> 将只保留这些机型: {top_aircraft_types}")

    # --- C. 执行联合筛选 (交集) ---
    # 逻辑：起飞在热门机场 AND 降落在热门机场 AND 机型是热门机型
    mask = (
        df_final['adep'].isin(top_airports) & 
        df_final['ades'].isin(top_airports) & 
        df_final['aircraft_type'].isin(top_aircraft_types)
    )
    
    df_filtered = df_final[mask].copy()
    
    # 打印结果
    filtered_count = len(df_filtered)
    print(f"\n✂️ 筛选结果: {total_initial} -> {filtered_count} 条航班")
    
    if filtered_count == 0:
        print("❌ 警告: 筛选后数据为0！可能是条件太苛刻，请尝试调大 TOP_N 或放宽日期。")
        return

    # 预估 Parquet 大小
    est_min = filtered_count * 4000
    est_max = filtered_count * 6000
    print(f"   📊 【预估】最终行数: {est_min/10000:.1f}万 - {est_max/10000:.1f}万 行")

    # ================= ID 映射 (Mapping) =================
    print("\n🔄 正在生成 ID 映射...")
    
    # 1. 机场 ID
    all_airports = pd.concat([df_filtered['adep'], df_filtered['ades']]).unique()
    airport_to_id = {code: i for i, code in enumerate(all_airports)}
    df_filtered['adep_id'] = df_filtered['adep'].map(airport_to_id)
    df_filtered['ades_id'] = df_filtered['ades'].map(airport_to_id)
    
    # 2. 【新增】机型 ID (用于 Embedding)
    # 我们只对保留下来的这 Top N 机型进行编号
    unique_aircraft = df_filtered['aircraft_type'].unique()
    type_to_id = {code: i for i, code in enumerate(unique_aircraft)}
    df_filtered['aircraft_type_id'] = df_filtered['aircraft_type'].map(type_to_id)
    
    print(f"   -> 机型映射关系: {type_to_id}")

    # --- 保存 ---
    # 删除日期列 (如果不需要)，保留 flight_id, adep_id, ades_id, aircraft_type_id
    df_filtered.drop(columns=['date'], inplace=True)
    
    df_filtered.to_csv(OUTPUT_FILE, index=False)
    
    print("-" * 30)
    print(f"🎉 处理完成！文件保存为: {OUTPUT_FILE}")
    print(f"包含字段: {list(df_filtered.columns)}")
    print(df_filtered.head())

if __name__ == "__main__":
    process_metadata()