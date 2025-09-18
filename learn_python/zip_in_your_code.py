#!/usr/bin/env python3
"""
你的代码中zip用法专题解析
针对 airports_to_parquet.py 中的具体应用
"""

import pandas as pd

print("🎯 你的代码中的zip用法解析")
print("=" * 40)
print()

# 模拟你的数据结构
demo_data = pd.DataFrame({
    'ident': ['ZBAA', 'PEK', 'ZSSS', 'SHA', 'ZGGG'],
    'gps_code': ['ZBAA', None, 'ZSSS', None, 'ZGGG'],
    'name': ['北京首都-ICAO', '北京首都-IATA', '上海虹桥-ICAO', '上海虹桥-IATA', '广州白云']
})

print("📊 DataFrame数据:")
print(demo_data)
print()

# 1. 提取.values
print("1️⃣ 从DataFrame提取数组")
print("-" * 25)

gps_values = demo_data.gps_code.values
ident_values = demo_data.ident.values

print(f"gps_code.values:  {gps_values}")
print(f"ident.values:     {ident_values}")
print(f"数据类型:         {type(gps_values)}")
print()

# 2. zip配对的具体过程
print("2️⃣ zip配对过程")
print("-" * 25)

print("zip(gps_code.values, ident.values) 创建的配对:")
zipped_pairs = list(zip(gps_values, ident_values))
for i, (g, ident) in enumerate(zipped_pairs):
    print(f"  索引{i}: (gps_code='{g}', ident='{ident}')")
print()

# 3. 在列表推导式中的解包
print("3️⃣ 在列表推导式中解包")
print("-" * 25)

print("for g, i in zip(af.gps_code.values, af.ident.values):")
print("  解释：每次循环时，zip返回一个元组 (g, i)")
print("  g 自动赋值为 gps_code 的值")
print("  i 自动赋值为 ident 的值")
print()

print("逐步演示:")
for g, i in zip(gps_values, ident_values):
    print(f"  本轮循环: g='{g}', i='{i}'")
print()

# 4. 为什么用zip而不是其他方法？
print("4️⃣ 为什么选择zip？")
print("-" * 25)

print("❌ 不好的方法1 - 分别循环:")
print("for i in range(len(gps_values)):")
print("    g = gps_values[i]")
print("    ident = ident_values[i]")
print("    # 处理逻辑...")
print("缺点: 需要管理索引，容易出错")
print()

print("❌ 不好的方法2 - 嵌套循环:")
print("for g in gps_values:")
print("    for ident in ident_values:")
print("        # 错误！这会产生笛卡尔积")
print("缺点: 逻辑错误，不是一一对应")
print()

print("✅ 好的方法 - 使用zip:")
print("for g, i in zip(gps_values, ident_values):")
print("    # 处理逻辑...")
print("优点: 简洁、安全、高效")
print()

# 5. 在你的具体场景中的应用
print("5️⃣ 你的具体应用场景")
print("-" * 25)

usedairports = {'ZBAA', 'SHA', 'ZGGG'}
print(f"使用的机场代码: {usedairports}")
print()

print("完整的处理逻辑:")
icao_codes = []
for g, i in zip(gps_values, ident_values):
    if i in usedairports:
        chosen = i
        reason = f"选择ident='{i}' (在使用列表中)"
    else:
        chosen = g
        reason = f"选择gps_code='{g}' (ident='{i}'不在使用列表中)"
    
    icao_codes.append(chosen)
    print(f"  {reason} → '{chosen}'")

print()
print(f"最终结果: {icao_codes}")
print()

# 6. 等价的列表推导式
print("6️⃣ 等价的列表推导式写法")
print("-" * 25)

# 你的原始代码的简化版
list_comp_result = [i if i in usedairports else g for g, i in zip(gps_values, ident_values)]

print("列表推导式:")
print("[i if i in usedairports else g for g, i in zip(gps_values, ident_values)]")
print()
print(f"结果: {list_comp_result}")
print(f"与循环结果相同: {icao_codes == list_comp_result}")
print()

# 7. zip的边界情况
print("7️⃣ 需要注意的边界情况")
print("-" * 25)

print("⚠️  长度不同的处理:")
short_list = [1, 2]
long_list = ['a', 'b', 'c', 'd']
print(f"短列表: {short_list}")
print(f"长列表: {long_list}")
print(f"zip结果: {list(zip(short_list, long_list))}")
print("在你的代码中，gps_code和ident长度应该相同（同一个DataFrame的列）")
print()

print("⚠️  处理None值:")
print("gps_code中的None值会直接参与zip配对")
print("在条件判断时需要特别处理None != 任何字符串")
print()

print("🎉 总结:")
print("zip在你的代码中的作用是将两列数据同步配对遍历，")
print("使得可以同时访问每一行的gps_code和ident值，")
print("然后根据业务逻辑选择合适的机场代码！")