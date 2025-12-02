"""
演示 airports_to_parquet.py 的命令行参数使用
"""

def demonstrate_command_line_usage():
    """演示命令行参数的实际含义"""
    
    print("=" * 60)
    print("📋 airports_to_parquet.py 命令行参数详解")
    print("=" * 60)
    
    print("\n🎯 命令行参数说明:")
    print("-a_in:   输入的机场CSV文件路径")
    print("-a_out:  输出的机场Parquet文件路径") 
    print("-flights: 航班文件名列表（用空格分隔）")
    
    print("\n📁 假设您的文件结构:")
    print("opensky_2024_PRC_dataset/")
    print("├── ourairports2024-10-21.csv        # 机场数据")
    print("├── flights/")
    print("│   ├── january_2024.parquet         # 1月航班数据")
    print("│   ├── february_2024.parquet        # 2月航班数据")
    print("│   └── march_2024.parquet           # 3月航班数据")
    print("└── output/")
    print("    └── filtered_airports.parquet    # 输出文件")
    
    print("\n💻 实际命令行调用:")
    command = '''python airports_to_parquet.py \\
  -a_in "opensky_2024_PRC_dataset/ourairports2024-10-21.csv" \\
  -a_out "opensky_2024_PRC_dataset/output/filtered_airports.parquet" \\
  -flights "opensky_2024_PRC_dataset/flights/january_2024.parquet opensky_2024_PRC_dataset/flights/february_2024.parquet opensky_2024_PRC_dataset/flights/march_2024.parquet"'''
    
    print(command)
    
    print("\n🔍 参数解析过程:")
    print("1. -a_in 参数:")
    print("   值: 'opensky_2024_PRC_dataset/ourairports2024-10-21.csv'")
    print("   含义: 输入的机场CSV文件路径")
    
    print("\n2. -a_out 参数:")
    print("   值: 'opensky_2024_PRC_dataset/output/filtered_airports.parquet'")
    print("   含义: 输出的过滤后机场文件路径")
    
    print("\n3. -flights 参数:")
    flights_string = "opensky_2024_PRC_dataset/flights/january_2024.parquet opensky_2024_PRC_dataset/flights/february_2024.parquet opensky_2024_PRC_dataset/flights/march_2024.parquet"
    print(f"   值: '{flights_string}'")
    print("   含义: 多个航班文件的路径，用空格分隔")
    
    print("\n🔧 代码中的处理:")
    print("flightsnames.split() 会将字符串分割成列表:")
    file_list = flights_string.split()
    for i, fname in enumerate(file_list, 1):
        print(f"   文件{i}: {fname}")

def demonstrate_data_flow():
    """演示数据处理流程"""
    
    print("\n" + "=" * 60)
    print("🌊 数据处理流程演示")
    print("=" * 60)
    
    # 模拟航班数据
    print("\n📊 模拟航班文件内容:")
    
    # 文件1的数据
    print("\n📁 january_2024.parquet 内容:")
    print("flight_id | adep | ades | ...")
    print("----------|------|------|-----")
    print("   12345  | PEK  | SHA  | ...")
    print("   12346  | CAN  | HKG  | ...")
    print("   12347  | CTU  | PEK  | ...")
    
    # 文件2的数据
    print("\n📁 february_2024.parquet 内容:")
    print("flight_id | adep | ades | ...")
    print("----------|------|------|-----")
    print("   22345  | SHA  | NRT  | ...")
    print("   22346  | HKG  | ICN  | ...")
    print("   22347  | PEK  | TPE  | ...")
    
    print("\n🔄 处理过程:")
    print("1. 从 january_2024.parquet 提取机场:")
    print("   adep: {PEK, CAN, CTU}")
    print("   ades: {SHA, HKG, PEK}")
    print("   合并: {PEK, CAN, CTU, SHA, HKG}")
    
    print("\n2. 从 february_2024.parquet 提取机场:")
    print("   adep: {SHA, HKG, PEK}")
    print("   ades: {NRT, ICN, TPE}")
    print("   合并: {SHA, HKG, PEK, NRT, ICN, TPE}")
    
    print("\n3. 最终合并所有使用的机场:")
    print("   usedairports = {PEK, CAN, CTU, SHA, HKG, NRT, ICN, TPE}")
    
    print("\n4. 过滤机场数据:")
    print("   - 从 ourairports2024-10-21.csv 中")
    print("   - 只保留在 usedairports 集合中的机场")
    print("   - 添加时区信息")
    print("   - 保存为 filtered_airports.parquet")

def show_file_vs_column_difference():
    """展示文件名 vs 列名的区别"""
    
    print("\n" + "=" * 60)
    print("🆚 文件名 vs 列名 对比")
    print("=" * 60)
    
    print("\n❌ 错误理解（列名）:")
    print("-flights 参数如果是列名的话，会是这样:")
    print("  -flights \"adep ades flight_id callsign\"")
    print("  但这是错误的！")
    
    print("\n✅ 正确理解（文件名）:")
    print("-flights 参数实际上是文件名:")
    print("  -flights \"file1.parquet file2.parquet file3.parquet\"")
    
    print("\n🔍 为什么需要多个文件？")
    print("- 航班数据通常按时间分割存储")
    print("- 例如：按月份、按季度、按年份")
    print("- 需要分析多个时间段的数据来确定所有使用的机场")
    
    print("\n📋 每个文件内部的结构:")
    print("所有航班文件都有相同的列结构:")
    print("- adep: 出发地机场代码（列名）")
    print("- ades: 目的地机场代码（列名）") 
    print("- flight_id: 航班ID（列名）")
    print("- 其他航班信息...")

if __name__ == "__main__":
    demonstrate_command_line_usage()
    demonstrate_data_flow()
    show_file_vs_column_difference()
    
    print("\n" + "=" * 60)
    print("📝 总结")
    print("=" * 60)
    print("✅ -flights 参数是：多个航班文件的文件名")
    print("❌ -flights 参数不是：CSV文件内部的列名")
    print("\n🎯 目的：")
    print("- 读取多个航班文件")
    print("- 从每个文件中提取使用的机场代码")
    print("- 合并所有机场代码（去重）")
    print("- 用这个列表过滤机场数据")