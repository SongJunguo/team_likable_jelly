#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
航班数据格式转换脚本：CSV转Parquet
=====================================

脚本功能：
---------
将航班CSV文件转换为Parquet格式，主要解决以下问题：
1. 统一数据类型(dtype)：确保数值、字符串、时间等字段类型一致
2. 统一时区处理：将时间字段转换为UTC时区格式
3. 加速IO操作：Parquet格式比CSV读写速度更快，存储更紧凑

主要特点：
---------
- 自动处理机场代码、航班号、飞机型号等字符串字段
- 正确处理飞行时长、距离、重量等数值字段
- 统一时间字段为UTC时区的datetime格式
- 支持命令行参数，便于批处理

使用方法：
---------
python flights_to_parquet.py -f_in input.csv -f_out output.parquet

数据字段说明：
-----------
- adep/ades: 起飞/降落机场代码
- callsign: 航班呼号
- airline: 航空公司
- wtc: 飞机重量类别
- aircraft_type: 飞机型号
- flight_duration: 飞行时长
- tow: 起飞重量
- date/actual_offblock_time/arrival_time: 各类时间字段
"""

# 导入必要的库
import pandas as pd  # 用于数据处理和操作
import argparse     # 用于解析命令行参数
import numpy as np   # 用于数值计算和数据类型定义

def read_flights(f):
    '''
    将航班CSV文件转换为Parquet格式，并统一数据类型
    目的：
    1. 加速文件读写速度（Parquet比CSV更高效）
    2. 确保数据类型一致性，避免后续处理中的类型错误
    
    参数：
    f: 输入的CSV文件路径
    
    返回：
    处理后的DataFrame，包含正确的数据类型

    challenge_set.csv的所有列名:
    flight_id,date,callsign,adep,name_adep,country_code_adep,ades,name_ades,country_code_ades,actual_offblock_time,arrival_time,aircraft_type,wtc,airline,flight_duration,taxiout_time,flown_distance,tow
    '''
    # 定义时间相关的列名
    # 这些列需要被转换为UTC时区的datetime格式
    dates = ["date","actual_offblock_time","arrival_time"]
    
    # 定义各列的数据类型映射
    # 【数据结构层次分析】
    # ltypes是一个列表，包含多个元组(tuple)
    # 每个元组的结构：(数据类型, [列名列表])
    # 这样设计的目的：把相同数据类型的列分组处理，提高代码复用性
    #
    # 数据结构层次：
    # ltypes = [                           ← 最外层：LIST列表，用中括号[]
    #     (数据类型, [列名1, 列名2, ...]),    ← 第1层：TUPLE元组，用小括号()
    #     (数据类型, [列名3, 列名4, ...]),    ← 第1层：TUPLE元组，用小括号()
    # ]
    # 其中每个元组包含：
    # - 第1个元素：数据类型（字符串或numpy类型）
    # - 第2个元素：列名列表，用中括号[]
    ltypes = [
        # 第1组：机场代码类 - 字符串类型
        # 元组结构：("string", ["adep","ades"])
        #           ↑字符串    ↑列表[字符串,字符串]
        ("string", ["adep","ades"]),
        
        # 第2组：航班标识类 - 字符串类型
        # 元组结构：("string", ["callsign","airline"])
        #           ↑字符串    ↑列表[字符串,字符串]
        ("string", ["callsign","airline"]),
        
        # 第3组：飞机重量类别 - 字符串类型
        # 元组结构：("string", ["wtc"])
        #           ↑字符串    ↑列表[字符串]
        ("string",["wtc"]),
        
        # 第4组：机场详细信息 - 字符串类型
        # 元组结构：("string", ["country_code_ades","country_code_adep","name_ades","name_adep"])
        #           ↑字符串    ↑列表[字符串,字符串,字符串,字符串]
        ("string",["country_code_ades","country_code_adep","name_ades","name_adep"]),
        
        # 第5组：飞机型号 - 字符串类型
        # 元组结构：("string", ["aircraft_type"])
        #           ↑字符串    ↑列表[字符串]
        ("string",["aircraft_type"]),
        
        # 第6组：数值型数据 - 64位浮点数
        # 元组结构：(np.float64, ["flight_duration","taxiout_time","flown_distance","tow"])
        #           ↑numpy类型  ↑列表[字符串,字符串,字符串,字符串]
        (np.float64, ["flight_duration","taxiout_time","flown_distance","tow"]),
        
        # 第7组：航班ID - 64位整数
        # 元组结构：(np.int64, ["flight_id"])
        #           ↑numpy类型  ↑列表[字符串]
        (np.int64, ["flight_id"]),
        
        # 第8组：时间数据 - UTC时区的datetime格式（纳秒精度）
        # 元组结构：("datetime64[ns, UTC]", ["date","actual_offblock_time","arrival_time"])
        #           ↑字符串                 ↑列表[字符串,字符串,字符串]
        ("datetime64[ns, UTC]", dates),
    ]
    
    # 读取CSV文件到DataFrame
    df = pd.read_csv(f)
    
    # 【双重循环详解】
    # 外层循环：遍历每种数据类型组
    # 内层循环：遍历该组内的每个列名
    
    # 外层循环：for dtype, lvar in ltypes
    # 【元组解包详解】
    # Python的"元组解包"(tuple unpacking)机制：
    # 
    # 原理：
    # - for循环每次取出ltypes中的一个元组，如 ("string", ["adep","ades"])
    # - Python自动把这个元组"拆开"成两个独立的变量
    # - dtype = 元组的第1个元素（数据类型）
    # - lvar = 元组的第2个元素（列名列表）
    #
    # 触发条件：
    # - 左边变量数量 = 右边元组元素数量（这里都是2个）
    # - 自动触发，无需特殊语法
    #
    # 解包层数：
    # - 只解包1层（最外层的元组）
    # - lvar仍然是列表，不会进一步自动解包
    #
    # 等价写法：
    # for item in ltypes:
    #     dtype = item[0]  # 手动取第1个元素
    #     lvar = item[1]   # 手动取第2个元素
    for dtype, lvar in ltypes:
        print(f"当前处理数据类型：{dtype}")  # 调试用，显示当前处理的数据类型
        print(f"该类型包含的列：{lvar}")      # 调试用，显示该类型的所有列名
        
        # 内层循环：遍历当前数据类型组中的每个列名
        # v = 当前列名
        for v in lvar:
            print(f"  正在转换列：{v} -> {dtype}")  # 调试用，显示具体转换过程
            # 将该列转换为指定的数据类型
            df[v] = df[v].astype(dtype)
    
    # 返回类型转换后的DataFrame
    return df
def main():
    '''
    主函数：处理命令行参数并执行CSV到Parquet的转换
    
    使用方法：
    python flights_to_parquet.py -f_in input.csv -f_out output.parquet
    '''
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser()
    
    # 添加输入文件参数：-f_in 指定要转换的CSV文件路径
    parser.add_argument("-f_in")
    
    # 添加输出文件参数：-f_out 指定输出的Parquet文件路径
    parser.add_argument("-f_out")
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 执行转换流程：
    # 1. 调用read_flights函数读取并处理CSV文件
    # 2. 将结果保存为Parquet格式，不保存行索引
    read_flights(args.f_in).to_parquet(args.f_out, index=False)

# 如果直接运行此脚本（而非被导入），则执行主函数
if __name__ == "__main__":
    main()

"""
【ltypes和双重循环的详细解释】
===============================

1. ltypes的数据结构：
   ltypes = [
       ("string", ["adep","ades"]),           # 第1个元组
       ("string", ["callsign","airline"]),    # 第2个元组
       (np.float64, ["flight_duration","tow"]), # 第3个元组
       ...
   ]

2. 双重循环的执行过程示例：

   第1轮外层循环：
   dtype = "string"
   lvar = ["adep","ades"]
   
   内层循环：
   v = "adep"  -> df["adep"] = df["adep"].astype("string")
   v = "ades"  -> df["ades"] = df["ades"].astype("string")

   第2轮外层循环：
   dtype = "string" 
   lvar = ["callsign","airline"]
   
   内层循环：
   v = "callsign"  -> df["callsign"] = df["callsign"].astype("string")
   v = "airline"   -> df["airline"] = df["airline"].astype("string")

   第3轮外层循环：
   dtype = np.float64
   lvar = ["flight_duration","taxiout_time","flown_distance","tow"]
   
   内层循环：
   v = "flight_duration"  -> df["flight_duration"] = df["flight_duration"].astype(np.float64)
   v = "taxiout_time"     -> df["taxiout_time"] = df["taxiout_time"].astype(np.float64)
   v = "flown_distance"   -> df["flown_distance"] = df["flown_distance"].astype(np.float64)
   v = "tow"              -> df["tow"] = df["tow"].astype(np.float64)

3. 为什么这样设计？
   - 避免重复代码：相同类型的列可以批量处理
   - 易于维护：新增字段只需在对应组中添加列名
   - 逻辑清晰：按数据类型分组，便于理解和修改
   - 减少错误：统一的类型转换逻辑，减少手工错误

4. 元组解包语法：
   for dtype, lvar in ltypes:
   等价于：
   for item in ltypes:
       dtype = item[0]  # 元组的第1个元素
       lvar = item[1]   # 元组的第2个元素
"""
