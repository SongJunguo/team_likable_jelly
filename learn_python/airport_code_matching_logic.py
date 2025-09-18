"""
机场代码匹配逻辑详解
解释为什么需要同时匹配 gps_code 和 ident 字段
"""

import pandas as pd
import numpy as np

def explain_airport_code_logic():
    """解释机场代码的复杂性和匹配逻辑"""
    
    print("=" * 80)
    print("✈️  机场代码匹配逻辑详解")
    print("=" * 80)
    
    print("\n🏷️  机场代码的种类:")
    print("在机场数据中，存在多种不同的机场代码字段：")
    print("1. ident:     机场标识符（可能是ICAO代码或本地代码）")
    print("2. gps_code:  GPS/ICAO代码（国际民航组织标准代码）")
    print("3. iata_code: IATA代码（国际航空运输协会代码，3个字母）")
    print("4. local_code: 本地代码（各国自己的编码系统）")

def create_demo_airport_data():
    """创建演示用的机场数据"""
    
    print("\n📊 演示数据：机场数据表（ourairports.csv 的简化版本）")
    
    # 创建模拟的机场数据
    airports_data = pd.DataFrame({
        'ident': ['ZBAA', 'ZSSS', 'ZGGG', 'PHNL', 'K1G4', 'CN87'],
        'gps_code': ['ZBAA', 'ZSSS', 'ZGGG', 'PHNL', None, None],
        'iata_code': ['PEK', 'SHA', 'CAN', 'HNL', None, None],
        'name': ['Beijing Capital Intl', 'Shanghai Hongqiao Intl', 'Guangzhou Baiyun Intl', 
                'Honolulu Intl', 'Big Sandy Airfield', 'Small Local Airport'],
        'type': ['large_airport', 'large_airport', 'large_airport', 'large_airport', 
                'small_airport', 'small_airport'],
        'latitude_deg': [40.08, 31.20, 23.39, 21.32, 37.15, 35.42],
        'longitude_deg': [116.58, 121.34, 113.30, -157.92, -82.34, -119.56]
    })
    
    print(airports_data.to_string(index=False))
    
    print("\n🔍 关键观察:")
    print("1. 大型国际机场：ident 和 gps_code 通常相同（都是ICAO代码）")
    print("2. 小型机场：可能只有 ident，没有 gps_code")
    print("3. 本地机场：使用本地编码系统")
    
    return airports_data

def create_demo_flight_data():
    """创建演示用的航班数据"""
    
    print("\n📊 演示数据：航班信息表（challenge_set.parquet 的简化版本）")
    
    # 航班数据中的机场代码
    flights_data = pd.DataFrame({
        'flight_id': [12345, 12346, 12347, 12348, 12349],
        'adep': ['ZBAA', 'ZSSS', 'K1G4', 'CN87', 'PHNL'],  # 出发地
        'ades': ['ZSSS', 'ZGGG', 'ZBAA', 'ZGGG', 'ZBAA'],  # 目的地
        'aircraft_type': ['A320', 'B737', 'C172', 'C152', 'A350']
    })
    
    print(flights_data.to_string(index=False))
    
    print("\n📋 从航班数据提取的使用机场:")
    used_airports = set(flights_data['adep'].tolist() + flights_data['ades'].tolist())
    print(f"usedairports = {used_airports}")
    
    return flights_data, used_airports

def demonstrate_matching_logic():
    """演示匹配逻辑"""
    
    print("\n" + "=" * 80)
    print("🔄 匹配逻辑演示")
    print("=" * 80)
    
    # 获取演示数据
    airports_df = create_demo_airport_data()
    flights_df, used_airports = create_demo_flight_data()
    
    print(f"\n🎯 需要匹配的机场代码: {used_airports}")
    
    print("\n🔍 逐个检查机场数据的匹配情况:")
    print("=" * 60)
    
    for i, (idx, airport) in enumerate(airports_df.iterrows()):
        ident = airport['ident']
        gps_code = airport['gps_code'] if pd.notna(airport['gps_code']) else None
        name = airport['name']
        
        # 检查是否匹配
        ident_match = ident in used_airports
        gps_match = gps_code in used_airports if gps_code else False
        
        print(f"\n机场 {i+1}: {name}")
        print(f"  ident: {ident} -> {'✅ 匹配' if ident_match else '❌ 不匹配'}")
        print(f"  gps_code: {gps_code} -> {'✅ 匹配' if gps_match else '❌ 不匹配'}")
        
        # 判断是否保留
        keep = ident_match or gps_match
        print(f"  结果: {'✅ 保留' if keep else '❌ 过滤掉'}")

def explain_pandas_query():
    """解释 pandas query 语法"""
    
    print("\n" + "=" * 80)
    print("🐼 Pandas Query 语法详解")
    print("=" * 80)
    
    print("\n💻 原始代码:")
    print('af = af.query("gps_code.isin(@usedairports) or ident.isin(@usedairports)")')
    
    print("\n🔧 语法分解:")
    print("1. af.query(): pandas DataFrame 的查询方法")
    print("2. 查询条件: 'gps_code.isin(@usedairports) or ident.isin(@usedairports)'")
    print("3. @usedairports: 引用外部变量 usedairports")
    print("4. .isin(): 检查值是否在给定集合中")
    print("5. or: 逻辑或操作符")
    
    print("\n🔄 等价的传统写法:")
    print("mask1 = af['gps_code'].isin(usedairports)")
    print("mask2 = af['ident'].isin(usedairports)")
    print("af = af[mask1 | mask2]")
    
    print("\n📊 实际演示:")
    
    # 创建演示数据
    airports_df = create_demo_airport_data()
    used_airports = {'ZBAA', 'ZSSS', 'ZGGG', 'K1G4', 'CN87'}
    
    print(f"\n使用的机场: {used_airports}")
    
    # 方法1：使用 query
    print("\n方法1 - 使用 query:")
    result1 = airports_df.query("gps_code.isin(@used_airports) or ident.isin(@used_airports)")
    print(f"保留的机场数量: {len(result1)}")
    print("保留的机场:")
    for _, row in result1.iterrows():
        print(f"  {row['ident']} - {row['name']}")
    
    # 方法2：传统方法
    print("\n方法2 - 传统方法:")
    mask1 = airports_df['gps_code'].isin(used_airports)
    mask2 = airports_df['ident'].isin(used_airports)
    result2 = airports_df[mask1 | mask2]
    print(f"保留的机场数量: {len(result2)}")
    
    print(f"\n✅ 两种方法结果相同: {len(result1) == len(result2)}")

def explain_why_both_fields():
    """解释为什么需要检查两个字段"""
    
    print("\n" + "=" * 80)
    print("🤔 为什么需要检查 gps_code 和 ident 两个字段？")
    print("=" * 80)
    
    print("\n🏗️  机场数据的复杂性:")
    
    print("\n1️⃣ 数据不一致性:")
    print("   - 不同数据源可能使用不同的代码字段")
    print("   - 航班数据可能使用 ICAO 代码")
    print("   - 机场数据可能在不同字段存储这些代码")
    
    print("\n2️⃣ 历史原因:")
    print("   - ident: 最初的标识符，可能是 ICAO 或本地代码")
    print("   - gps_code: 后来添加的标准化 ICAO 代码")
    print("   - 数据迁移过程中可能存在不一致")
    
    print("\n3️⃣ 机场类型差异:")
    print("   - 大型国际机场: 通常有完整的 ICAO 代码")
    print("   - 小型本地机场: 可能只有本地代码")
    print("   - 军用机场: 可能有特殊编码")
    
    print("\n4️⃣ 数据完整性:")
    print("   - 某些机场可能缺少 gps_code")
    print("   - 某些机场可能缺少 ident")
    print("   - 通过检查两个字段确保不漏掉任何机场")

def show_real_world_example():
    """展示真实世界的例子"""
    
    print("\n" + "=" * 80)
    print("🌍 真实世界的例子")
    print("=" * 80)
    
    print("\n📋 可能遇到的情况:")
    
    examples = [
        {
            'scenario': '标准国际机场',
            'ident': 'ZBAA',
            'gps_code': 'ZBAA',
            'explanation': '两个字段相同，都是标准ICAO代码'
        },
        {
            'scenario': '美国小型机场',
            'ident': 'K1G4',
            'gps_code': None,
            'explanation': 'ident是美国本地代码，没有gps_code'
        },
        {
            'scenario': '历史数据迁移',
            'ident': 'PEK_OLD',
            'gps_code': 'ZBAA',
            'explanation': 'ident是旧代码，gps_code是新的标准代码'
        },
        {
            'scenario': '数据录入错误',
            'ident': 'ZBAA',
            'gps_code': 'ZBAAA',  # 多了一个A
            'explanation': 'gps_code有录入错误，ident是正确的'
        }
    ]
    
    for i, example in enumerate(examples, 1):
        print(f"\n{i}. {example['scenario']}:")
        print(f"   ident: {example['ident']}")
        print(f"   gps_code: {example['gps_code']}")
        print(f"   说明: {example['explanation']}")
        
        # 如果航班数据使用的是其中任何一个代码，我们都应该匹配到这个机场
        print(f"   如果航班使用 '{example['ident']}' 或 '{example['gps_code']}'")
        print(f"   都应该匹配到这个机场 ✅")

def provide_solution_summary():
    """提供解决方案总结"""
    
    print("\n" + "=" * 80)
    print("💡 解决方案总结")
    print("=" * 80)
    
    print("\n🎯 核心逻辑:")
    print("af.query('gps_code.isin(@usedairports) or ident.isin(@usedairports)')")
    
    print("\n📝 翻译成人话:")
    print("保留机场数据中满足以下任一条件的行：")
    print("1. gps_code 字段的值在使用的机场集合中")
    print("2. 或者 ident 字段的值在使用的机场集合中")
    
    print("\n✅ 这样做的好处:")
    print("1. 数据完整性: 不会因为字段不一致而漏掉机场")
    print("2. 容错性: 处理数据质量问题")
    print("3. 兼容性: 适应不同的编码标准")
    print("4. 灵活性: 适应历史数据和新数据")
    
    print("\n🚨 如果只检查一个字段会怎样:")
    print("❌ 只检查 gps_code: 可能漏掉没有标准ICAO代码的小机场")
    print("❌ 只检查 ident: 可能漏掉代码不一致的机场")
    
    print("\n🔧 最佳实践:")
    print("在处理真实世界的数据时，总是要考虑:")
    print("- 数据不一致性")
    print("- 历史遗留问题") 
    print("- 不同标准的混合使用")
    print("- 数据录入错误")

if __name__ == "__main__":
    explain_airport_code_logic()
    create_demo_airport_data()
    create_demo_flight_data()
    demonstrate_matching_logic()
    explain_pandas_query()
    explain_why_both_fields()
    show_real_world_example()
    provide_solution_summary()
    
    print("\n" + "=" * 80)
    print("🎓 学习要点")
    print("=" * 80)
    print("1. 真实数据往往不完美，需要容错处理")
    print("2. 机场代码有多种标准，需要灵活匹配")
    print("3. pandas.query() 是强大的数据筛选工具")
    print("4. 逻辑或(or)操作确保不遗漏数据")
    print("5. @variable 语法可以在query中引用外部变量")