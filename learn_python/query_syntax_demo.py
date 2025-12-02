#!/usr/bin/env python3
"""
pandas.query() 语法详解演示
第一次接触query语法的完整讲解
"""

import pandas as pd
import numpy as np

print("🎯 pandas.query() 语法完整讲解")
print("=" * 50)

# 创建示例数据
data = {
    'name': ['北京首都', '上海虹桥', '广州白云', '深圳宝安', '成都双流'],
    'code': ['ZBAA', 'ZSSS', 'ZGGG', 'ZGSZ', 'ZUUU'],
    'type': ['国际', '国际', '国际', '国际', '国内'],
    'passengers': [95000000, 40000000, 70000000, 50000000, 55000000]
}
df = pd.DataFrame(data)
print("📊 示例数据：")
print(df)
print()

# 1. 最基本的query语法
print("1️⃣ 基本query语法：")
print("代码：df.query('passengers > 60000000')")
result1 = df.query('passengers > 60000000')
print("结果：")
print(result1)
print()

# 2. 字符串匹配
print("2️⃣ 字符串匹配：")
print("代码：df.query('type == \"国际\"')")
result2 = df.query('type == "国际"')
print("结果：")
print(result2)
print()

# 3. isin()方法 - 这是关键！
print("3️⃣ isin()方法 - 检查值是否在列表中：")
target_codes = ['ZBAA', 'ZSSS', 'ZUUU']
print(f"目标代码列表：{target_codes}")

# 传统写法
print("\n🔸 传统写法：")
print("traditional = df[df['code'].isin(target_codes)]")
traditional = df[df['code'].isin(target_codes)]
print(traditional)

# query写法 - 关键来了！
print("\n🔸 query写法（使用@引用外部变量）：")
print("query_result = df.query('code.isin(@target_codes)')")
query_result = df.query('code.isin(@target_codes)')
print(query_result)
print()

# 4. @ 符号的作用
print("4️⃣ @ 符号的神奇作用：")
print("   - @变量名：在query字符串中引用Python变量")
print("   - 没有@：query会把它当作DataFrame的列名")
print("   - 有了@：query知道这是外部定义的Python变量")
print()

# 5. 逻辑运算符
print("5️⃣ 逻辑运算符：")
big_airports = ['ZBAA', 'ZGGG']
print(f"大型机场代码：{big_airports}")
print("代码：df.query('code.isin(@big_airports) or passengers > 50000000')")
result5 = df.query('code.isin(@big_airports) or passengers > 50000000')
print("结果：")
print(result5)
print()

# 6. 你的代码等价演示
print("6️⃣ 你的代码的等价形式：")
print()

# 模拟你的情况
usedairports = {'ZBAA', 'ZSSS', 'UNKNOWN_CODE'}  # 模拟航班中用到的机场代码
df_airports = pd.DataFrame({
    'ident': ['ZBAA', 'PEK', 'ZSSS', 'SHA', 'ZGGG'],
    'gps_code': ['ZBAA', None, 'ZSSS', None, 'ZGGG'],
    'name': ['北京首都-ident', '北京首都-iata', '上海虹桥-ident', '上海虹桥-iata', '广州白云']
})

print("🏢 机场数据表：")
print(df_airports)
print()
print(f"✈️ 航班中使用的机场代码：{usedairports}")
print()

# 你的原始代码
print("🎯 你的原始代码：")
print('af.query("gps_code.isin(@usedairports) or ident.isin(@usedairports)")')
your_result = df_airports.query("gps_code.isin(@usedairports) or ident.isin(@usedairports)")
print("匹配结果：")
print(your_result)
print()

# 等价的传统写法
print("📝 等价的传统写法：")
print("condition1 = df_airports['gps_code'].isin(usedairports)")
print("condition2 = df_airports['ident'].isin(usedairports)")
print("traditional_result = df_airports[condition1 | condition2]")

condition1 = df_airports['gps_code'].isin(usedairports)
condition2 = df_airports['ident'].isin(usedairports)
traditional_result = df_airports[condition1 | condition2]
print("结果：")
print(traditional_result)
print()

# 验证结果相同
print(f"🔍 两种方法结果相同：{your_result.equals(traditional_result)}")
print()

# 7. 为什么用query？
print("7️⃣ 为什么使用query语法？")
print("✅ 优点：")
print("   - 代码更简洁，接近SQL语法")
print("   - 复杂条件时更易读")
print("   - 支持@引用外部变量")
print("   - 性能在某些情况下更好")
print()
print("❌ 缺点：")
print("   - 学习成本，第一次见会懵")
print("   - 字符串形式，IDE支持有限")
print("   - 调试相对困难")
print()

print("🎉 现在你应该完全理解query语法了！")