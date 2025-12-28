import pandas as pd
import numpy as np
import os
import glob
import time
import pyarrow as pa
import pyarrow.parquet as pq

# ================= 配置路径 =================
ADS_B_FOLDER = 'ADS-B'       # ADS-B 数据文件夹名称
META_FOLDER = 'Meta'         # 元数据文件夹名称
OUTPUT_FOLDER = 'ProcessedData' # 输出结果保存的文件夹

# 输入的元数据文件名 (根据你的截图应该是这个)
META_FILE_NAME = 'metadata_all.csv' 

# 最终输出的单一文件名
FINAL_OUTPUT_FILE = 'combined_adsb_data.parquet'

# ================= 📅 新增：日期范围限制 =================
# 根据你的运行结果，15号之后都没匹配上，所以我们把截止日期设为 14 号
# 只要文件名里的日期 > END_DATE，程序直接跳过，看都不看
START_DATE = '2022-01-01' 
END_DATE   = '2022-01-14'

# 最终结果文件中需要保留的列
COLS_TO_KEEP = [
    'flight_id', 
    'timestamp', 
    'latitude', 
    'longitude', 
    'altitude', 
    'vertical_rate',
    'track', 
    'groundspeed',          # 保留：地速
    'u_component_of_wind',  # 保留：风速 U 分量
    'v_component_of_wind',  # 保留：风速 V 分量
    'adep_id',              # 起飞机场
    'ades_id',              # 降落机场
    'aircraft_type_id'      # 机型
]

ROW_GROUP_SIZE = 100000

def load_metadata():
    """读取单一元数据文件"""
    file_path = os.path.join(META_FOLDER, META_FILE_NAME)
    print(f"🔄 [步骤1] 正在加载元数据: {file_path} ...")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"❌ 找不到文件: {file_path}")

    try:
        # 读取必要的列
        df = pd.read_csv(file_path, usecols=['flight_id', 'adep_id', 'ades_id', 'aircraft_type_id'])
        df['flight_id'] = df['flight_id'].astype(str)
        
        # 去重，确保 flight_id 唯一
        df.drop_duplicates(subset=['flight_id'], inplace=True)
        print(f"✅ 元数据加载完毕，包含 {len(df)} 条航班索引。")
        return df
    except Exception as e:
        print(f"❌ 元数据读取失败: {e}")
        return pd.DataFrame()

def process_and_combine():
    # 1. 准备输出
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    output_path = os.path.join(OUTPUT_FOLDER, FINAL_OUTPUT_FILE)
    
    # 如果目标文件已存在，先删除，防止追加到旧数据后面
    if os.path.exists(output_path):
        os.remove(output_path)
        print(f"🧹 已清理旧文件: {output_path}")

    # 2. 加载元数据
    df_meta = load_metadata()
    if df_meta.empty: return

    # 3. 获取文件列表
    adsb_files = glob.glob(os.path.join(ADS_B_FOLDER, "*.parquet"))
    adsb_files.sort()
    print(f"🔄 [步骤2] 准备合并 {len(adsb_files)} 个文件到 -> {FINAL_OUTPUT_FILE}")

    # 初始化 ParquetWriter
    writer = None
    total_rows = 0
    total_start_time = time.time()

    # 4. 循环处理并写入
    for i, adsb_path in enumerate(adsb_files):
        file_name = os.path.basename(adsb_path)

        # === 新增逻辑：提取文件名日期并过滤 ===
        # 假设文件名格式为 "2022-01-14.parquet"
        file_date_str = file_name.replace('.parquet', '') # 拿到 "2022-01-14"
        
        # 字符串比较：如果日期在范围之外，直接跳过
        if file_date_str < START_DATE or file_date_str > END_DATE:
            print(f"   [{i+1}/{len(adsb_files)}] 跳过: {file_name} (不在日期范围内)")
            continue
        # ========================================

        print(f"   [{i+1}/{len(adsb_files)}] 处理: {file_name} ...", end="", flush=True)

        try:
            # --- A. 读取 ADS-B 数据 ---
            df_adsb = pd.read_parquet(adsb_path)
            df_adsb['flight_id'] = df_adsb['flight_id'].astype(str)
            
            # 清洗：确保必要的列没有缺失值（虽然不计算TAS了，但如果没风速或地速，数据可能也不完整，根据需要可调整）
            df_adsb.dropna(subset=['latitude', 'longitude', 'groundspeed', 'track', 
                                   'u_component_of_wind', 'v_component_of_wind'], inplace=True)
            
            if df_adsb.empty:
                print(" ⚠️ 空数据 (跳过)")
                continue

            # --- B. 合并元数据 (核心任务) ---
            # 仅做 inner join，把机场和机型拼上去
            df_merged = pd.merge(df_adsb, df_meta, on='flight_id', how='inner')
            
            if df_merged.empty:
                print(" ⚠️ 无匹配航班 (跳过)")
                continue

            # --- C. 筛选列 ---
            # 此时不再进行计算，直接筛选需要的列
            df_final = df_merged[COLS_TO_KEEP]
            
            # --- D. 分块写入 (Chunked Writing) ---
            # 第一次写入时初始化 writer
            if writer is None:
                temp_schema = pa.Table.from_pandas(df_final.head(1)).schema
                writer = pq.ParquetWriter(output_path, temp_schema, compression='snappy')

            rows_written_this_file = 0
            
            # 循环切片写入
            for start_idx in range(0, len(df_final), ROW_GROUP_SIZE):
                sub_df = df_final.iloc[start_idx : start_idx + ROW_GROUP_SIZE]
                table_chunk = pa.Table.from_pandas(sub_df)
                writer.write_table(table_chunk)
                rows_written_this_file += len(sub_df)

            total_rows += rows_written_this_file
            print(f" ✅ 追加 {rows_written_this_file} 行")

            # 释放内存
            del df_adsb, df_merged, df_final, table_chunk

        except Exception as e:
            print(f" ❌ 出错: {e}")

    # 5. 关闭 Writer
    if writer:
        writer.close()
        print(f"\n🎉 全部完成！")
        print(f"📂 最终文件: {output_path}")
        print(f"📊 总数据量: {total_rows} 行")
        print(f"⏳ 总耗时: {time.time() - total_start_time:.2f} 秒")
    else:
        print("\n⚠️ 警告: 没有写入任何数据 (可能是所有文件都匹配失败)。")

if __name__ == "__main__":
    process_and_combine()