
"""
机场数据处理脚本
功能：将机场CSV文件转换为Parquet格式，过滤出实际使用的机场，并添加时区信息
输入csv文件 ourairports2024-10-21.csv
输出parquet文件 airports_tz.parquet
输入的航班信息文件：challenge_set.parquet final_submission_set.parquet
根据航班信息文件过滤机场csv信息
"""

# 导入必要的库
import pandas as pd              # 用于数据处理和分析
from timezonefinder import TimezoneFinder  # 用于根据经纬度查找时区
import numpy as np               # 用于数值计算
import argparse                  # 用于命令行参数解析
from tools.io import readers                   # 自定义的航班数据读取模块


def airports_to_dataframe(af, flightsnames):
    '''
    生成机场Parquet文件的主要函数
    功能：
    - 检查航班文件中提到的每个机场都会包含在生成的机场parquet文件中
    - 添加时区信息
    - 过滤出实际使用的机场
    
    参数：
    af: 机场数据DataFrame
    flightsnames: 航班文件名列表（以空格分隔的字符串）
    
    返回：
    处理后的机场DataFrame
    '''
    # 删除谢菲尔德市直升机场（EGSY），可能是因为数据质量问题
    af = af.query("ident!='EGSY'")  # drop shefield city heliport
    
    # 将指定列转换为字符串类型，确保数据类型一致性
    # 使用字典推导式创建类型转换映射：{列名: "string", 列名: "string", ...}
    # 等价于：column_types = {}; for x in [...]: column_types[x] = "string"
    string_columns = ['ident', 'type', 'name', 'continent', 'iso_country', 'iso_region', 
                     'municipality', 'scheduled_service', 'gps_code', 'iata_code', 
                     'local_code', 'home_link', 'wikipedia_link', 'keywords']
    af = af.astype({x: "string" for x in string_columns})
    
    # 将坐标和海拔数据转换为浮点数类型
    for x in ['latitude_deg', 'longitude_deg', 'elevation_ft']:
        af[x] = af[x].astype(np.float64)
    
    # 创建一个集合来存储实际使用的机场代码
    # 为什么使用set而不是list？
    # 1. 自动去重：避免重复的机场代码
    # 2. 快速查找：后面需要检查机场是否在集合中，set的查找速度是O(1)
    # 3. 集合运算：可以使用union()等操作合并多个文件的机场
    usedairports = set()
    
    # 遍历所有航班信息文件，收集实际使用的机场：challenge_set.parquet final_submission_set.parquet
    # flightsnames 是一个字符串，包含多个文件名，用空格分隔
    # 例如："file1.parquet file2.parquet file3.parquet"
    for fname in flightsnames.split():  # split()将字符串分割成文件名列表
        # fname 现在是单个文件名，如 "january_flights.parquet"
        f = readers.read_flights(fname)  # 读取这个航班文件的数据
        # f 是 DataFrame，包含航班数据，其中有：
        # - f.ades：目的地机场列（如 ['PEK', 'SHA', 'CAN', ...]）
        # - f.adep：出发地机场列（如 ['HKG', 'NRT', 'ICN', ...]）
        
        # 将目的地机场(ades)和出发地机场(adep)都加入到使用机场集合中
        # 使用union()进行集合合并，自动处理重复机场代码
        usedairports = usedairports.union(set(f.ades.values))  # 目的地机场
        usedairports = usedairports.union(set(f.adep.values))  # 出发地机场
    
    # 过滤机场数据，只保留实际使用的机场
    # 为什么要匹配 gps_code 或 ident 两个字段？关键原因：
    # 1. 数据不一致性：不同数据源可能使用不同的代码字段
    # 2. 机场类型差异：大型国际机场有ICAO代码，小型机场可能只有本地代码
    # 3. 数据完整性：某些机场可能缺少 gps_code 或 ident 字段
    # 4. 历史原因：ident 是原始标识符，gps_code 是后来标准化的
    # 
    # 查询条件解释：
    # - gps_code.isin(@usedairports)：检查GPS/ICAO代码是否在使用集合中
    # - ident.isin(@usedairports)：检查机场标识符是否在使用集合中
    # - or：逻辑或，满足任一条件即保留
    # - @usedairports：引用外部变量，即航班中实际使用的机场代码集合
    # 这行代码等价于问：
    # "这个机场的GPS代码或者标识符代码，是否出现在我们的航班数据中？如果是，就保留；如果不是，就删除。"
    af = af.query("gps_code.isin(@usedairports) or ident.isin(@usedairports)")
    
    # 创建统一的ICAO代码列：优先使用ident，如果ident不在使用列表中则使用gps_code
    icao_code = [i if i in usedairports else g for g, i in zip(af.gps_code.values, af.ident.values)]
    af = af.assign(icao_code=icao_code)  # 添加新的icao_code列
    af["icao_code"] = af["icao_code"].astype("string")  # 转换为字符串类型
    
    # 删除原始的ident列，因为已经有了统一的icao_code列
    af = af.drop(columns="ident")
    
    # 数据质量检查：确保所有使用的机场都被包含
    assert (len(usedairports) == af.shape[0])  # 检查机场数量是否匹配
    assert (af.icao_code.nunique() == af.shape[0])  # 检查icao_code是否唯一
    
    # 创建时区查找器对象
    tf = TimezoneFinder()
    ltz = []  # 存储时区信息的列表
    
    # 为每个机场查找对应的时区
    for i, line in af.iterrows():
        # print(i,line)  # 调试用的打印语句（已注释）
        # 根据经纬度查找时区
        tz = tf.timezone_at(lng=line.longitude_deg, lat=line.latitude_deg)
        ltz.append(str(tz))  # 将时区转换为字符串并添加到列表
    
    # 将时区信息添加到DataFrame
    af["time_zone"] = ltz
    af["time_zone"] = af["time_zone"].astype("string")  # 确保时区列为字符串类型
    
    return af

def main():
    """
    主函数：处理命令行参数并执行机场数据转换
    """
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(
        description='生成机场parquet文件，添加时区信息',  # 程序描述
    )
    # 添加命令行参数
    parser.add_argument("-a_in", help="输入的机场CSV文件路径")      # 输入机场文件
    parser.add_argument("-a_out", help="输出的机场Parquet文件路径")  # 输出机场文件  
    parser.add_argument("-flights", help="航班信息文件名列表（空格分隔）\n                         实际使用：根据Makefile，传入flights目录下的parquet文件\n                         例如：challenge_set.parquet final_submission_set.parquet") # 航班文件列表
    
    # 解析命令行参数
    args = parser.parse_args()
    
    # 读取输入的机场CSV文件 文件名是 ourairports2024-10-21.csv
    airportscsv = pd.read_csv(args.a_in)
    
    # 处理机场数据并保存为Parquet格式
    # 1. 调用airports_to_dataframe函数处理数据
    # 2. 保存为Parquet文件（index=False表示不保存行索引）
    airports_to_dataframe(airportscsv, args.flights).to_parquet(args.a_out, index=False)


if __name__ == '__main__':
    """
    脚本入口点：当直接运行此脚本时执行main函数
    """
    main()
