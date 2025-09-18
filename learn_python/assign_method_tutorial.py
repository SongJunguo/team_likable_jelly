#!/usr/bin/env python3
"""
pandas DataFrame.assign() 方法详解
解答你关于 af.assign(icao_code=icao_code) 的疑问
"""

import pandas as pd
import numpy as np

print("🔍 pandas DataFrame.assign() 方法详解")
print("=" * 50)
print()

# 1. 创建示例DataFrame
print("1️⃣ 创建示例DataFrame")
print("-" * 30)

original_df = pd.DataFrame({
    'name': ['北京首都', '上海虹桥', '广州白云'],
    'code': ['ZBAA', 'ZSSS', 'ZGGG'],
    'type': ['国际', '国际', '国际']
})

print("原始DataFrame:")
print(original_df)
print(f"原始DataFrame的ID: {id(original_df)}")
print()

# 2. assign() 的核心特性：返回新的DataFrame
print("2️⃣ assign() 的核心特性")
print("-" * 30)

# 准备要添加的新列数据
new_column_data = ['PEK', 'SHA', 'CAN']  # 这是一个list
print(f"要添加的新列数据: {new_column_data}")
print(f"数据类型: {type(new_column_data)}")
print()

# 使用assign添加新列
new_df = original_df.assign(iata_code=new_column_data)

print("✅ 使用assign后:")
print("new_df = original_df.assign(iata_code=new_column_data)")
print()
print("新的DataFrame:")
print(new_df)
print(f"新DataFrame的ID: {id(new_df)}")
print()

print("原始DataFrame:")
print(original_df)
print(f"原始DataFrame的ID: {id(original_df)}")
print()

print("🔍 关键发现:")
print(f"   - 原始DataFrame是否改变: {original_df.equals(pd.DataFrame({'name': ['北京首都', '上海虹桥', '广州白云'], 'code': ['ZBAA', 'ZSSS', 'ZGGG'], 'type': ['国际', '国际', '国际']}))}")
print(f"   - 两个DataFrame是同一个对象: {original_df is new_df}")
print(f"   - 新DataFrame有新列: {'iata_code' in new_df.columns}")
print(f"   - 原DataFrame有新列: {'iata_code' in original_df.columns}")
print()

# 3. assign() vs 直接赋值的区别
print("3️⃣ assign() vs 直接赋值的区别")
print("-" * 30)

# 方法1：直接赋值（修改原DataFrame）
test_df1 = original_df.copy()
print("方法1 - 直接赋值:")
print("test_df1['new_col'] = [1, 2, 3]")
test_df1['new_col'] = [1, 2, 3]
print("结果: 修改了原DataFrame")
print(test_df1)
print()

# 方法2：使用assign（返回新DataFrame）
print("方法2 - 使用assign:")
print("test_df2 = original_df.assign(new_col=[1, 2, 3])")
test_df2 = original_df.assign(new_col=[1, 2, 3])
print("结果: 返回新的DataFrame，原DataFrame不变")
print("新DataFrame:")
print(test_df2)
print("原DataFrame:")
print(original_df)
print()

# 4. 你的代码中的具体情况
print("4️⃣ 你的代码中的具体情况")
print("-" * 30)

print("🎯 你的代码:")
print("icao_code = [i if i in usedairports else g for g, i in zip(af.gps_code.values, af.ident.values)]")
print("af = af.assign(icao_code=icao_code)")
print()

print("📝 详细解析:")
print("   icao_code=icao_code 这个语法中:")
print("   - 等号左边的 'icao_code': 新列的名字（字符串）")
print("   - 等号右边的 'icao_code': 变量名，指向一个list")
print()

# 模拟你的情况
demo_af = pd.DataFrame({
    'ident': ['ZBAA', 'PEK', 'ZSSS'],
    'gps_code': ['ZBAA', None, 'ZSSS'],
    'name': ['北京首都-ICAO', '北京首都-IATA', '上海虹桥']
})

usedairports = {'ZBAA', 'ZSSS'}
icao_code_list = [i if i in usedairports else g for g, i in zip(demo_af.gps_code.values, demo_af.ident.values)]

print("模拟数据:")
print(f"原始DataFrame af:")
print(demo_af)
print()
print(f"icao_code变量 (list): {icao_code_list}")
print(f"类型: {type(icao_code_list)}")
print()

# 执行assign
print("执行 af = af.assign(icao_code=icao_code):")
old_id = id(demo_af)
demo_af = demo_af.assign(icao_code=icao_code_list)
new_id = id(demo_af)

print("结果:")
print(demo_af)
print()
print(f"DataFrame ID 变化: {old_id} → {new_id}")
print("说明: assign() 创建了新的DataFrame对象")
print()

# 5. 为什么使用 af = af.assign() 这种写法？
print("5️⃣ 为什么使用 af = af.assign() 写法？")
print("-" * 30)

print("🤔 既然assign()返回新DataFrame，为什么要写 af = af.assign()？")
print()
print("✅ 原因:")
print("   1. 函数式编程风格: 不修改原数据，而是创建新数据")
print("   2. 链式调用友好: 可以连续调用多个方法")
print("   3. 代码清晰: 明确表示'创建新的带有额外列的DataFrame'")
print("   4. 避免意外修改: 原始数据保持不变（在重新赋值前）")
print()

print("📝 等价写法对比:")
print()
print("写法1 (你的代码):")
print("af = af.assign(icao_code=icao_code)")
print()
print("写法2 (直接赋值):")
print("af['icao_code'] = icao_code")
print()
print("区别:")
print("- 写法1: 创建新DataFrame，然后赋值给af变量")
print("- 写法2: 直接修改现有的af DataFrame")
print("- 结果相同，但过程不同")
print()

# 6. 链式调用示例
print("6️⃣ assign() 支持链式调用")
print("-" * 30)

example_df = pd.DataFrame({'a': [1, 2, 3]})
print("原始数据:")
print(example_df)
print()

print("链式调用示例:")
print("result = (example_df")
print("          .assign(b=[4, 5, 6])")
print("          .assign(c=[7, 8, 9])")
print("          .assign(sum_col=lambda x: x['a'] + x['b'] + x['c']))")

result = (example_df
          .assign(b=[4, 5, 6])
          .assign(c=[7, 8, 9])
          .assign(sum_col=lambda x: x['a'] + x['b'] + x['c']))

print("结果:")
print(result)
print()

print("💡 这种写法在数据处理管道中很常见！")
print()

# 7. 总结
print("7️⃣ 总结")
print("-" * 30)

print("🎯 回答你的问题:")
print()
print("Q1: assign是在原DataFrame上加列，还是新建DataFrame？")
print("A1: 新建DataFrame！assign()总是返回新的DataFrame对象")
print()
print("Q2: icao_code=icao_code中，前一个是列名，后一个是list？")
print("A2: 完全正确！")
print("    - 前一个icao_code: 新列的名字")
print("    - 后一个icao_code: 变量名，指向包含列数据的list")
print()
print("Q3: 为什么写 af = af.assign()？")
print("A3: 因为assign()返回新DataFrame，需要重新赋值给af变量")
print("    才能让af指向包含新列的DataFrame")
print()

print("🎉 现在你完全理解assign()方法了！")