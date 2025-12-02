#!/usr/bin/env python3
"""
为什么选择 assign() 而不是直接赋值？
深入分析两种添加列方法的区别和应用场景
"""

import pandas as pd
import numpy as np

print("🤔 为什么用 assign() 而不是直接添加列？")
print("=" * 50)
print()

# 创建示例数据
demo_df = pd.DataFrame({
    'name': ['北京首都', '上海虹桥', '广州白云'],
    'code': ['ZBAA', 'ZSSS', 'ZGGG']
})

new_data = ['PEK', 'SHA', 'CAN']

print("📊 示例数据:")
print(demo_df)
print(f"要添加的数据: {new_data}")
print()

# 1. 结果对比 - 两种方法效果相同
print("1️⃣ 结果对比 - 效果确实相同")
print("-" * 30)

# 方法1: assign()
df1 = demo_df.copy()
df1 = df1.assign(iata_code=new_data)

# 方法2: 直接赋值
df2 = demo_df.copy()
df2['iata_code'] = new_data

print("方法1 (assign):")
print(df1)
print()
print("方法2 (直接赋值):")
print(df2)
print()
print(f"两种结果相同: {df1.equals(df2)}")
print("✅ 你说得对，结果确实等效！")
print()

# 2. 为什么还要用assign？深层原因分析
print("2️⃣ 为什么还要用assign？深层原因")
print("-" * 30)

print("🎯 原因1: 编程风格和设计哲学")
print()
print("📝 函数式编程 vs 命令式编程:")
print()

print("命令式风格 (直接修改):")
print("df['new_col'] = data")
print("# 特点: 直接修改现有对象")
print()

print("函数式风格 (创建新对象):")
print("df = df.assign(new_col=data)")
print("# 特点: 不修改原对象，创建新对象")
print()

print("💡 函数式风格的优势:")
print("   ✅ 更安全: 不会意外修改原数据")
print("   ✅ 更可预测: 函数的输入输出明确")
print("   ✅ 更易调试: 每一步都产生新的中间结果")
print("   ✅ 更易测试: 纯函数更容易单元测试")
print()

# 3. 链式调用的优势
print("🎯 原因2: 支持链式调用")
print()

print("❌ 直接赋值不支持链式调用:")
print("df['col1'] = data1")
print("df['col2'] = data2")
print("df = df.drop(columns='old_col')")
print("df = df.query('col1 > 0')")
print("# 需要多行，不够优雅")
print()

print("✅ assign支持链式调用:")
print("df = (df.assign(col1=data1)")
print("        .assign(col2=data2)")
print("        .drop(columns='old_col')")
print("        .query('col1 > 0'))")
print("# 一个流畅的处理管道")
print()

# 实际演示链式调用
print("📝 链式调用实际演示:")
result = (demo_df
          .assign(iata_code=['PEK', 'SHA', 'CAN'])
          .assign(region=['华北', '华东', '华南'])
          .query('region != "华北"'))

print("链式调用结果:")
print(result)
print()

# 4. 在你的代码中的具体考虑
print("🎯 原因3: 你的代码中的具体考虑")
print()

print("📝 你的代码上下文:")
print("af = af.query(...)")
print("icao_code = [...]")
print("af = af.assign(icao_code=icao_code)")
print("af['icao_code'] = af['icao_code'].astype('string')")
print("af = af.drop(columns='ident')")
print()

print("🔍 分析:")
print("1. 整个函数都在使用函数式风格")
print("2. 每一步都是 af = af.方法(...)")
print("3. 保持代码风格的一致性")
print("4. 便于理解数据流转过程")
print()

# 5. 性能对比
print("🎯 原因4: 性能考虑")
print()

print("⚡ 性能测试 (小数据集):")

import time

# 创建测试数据
test_df = pd.DataFrame({
    'a': range(1000),
    'b': range(1000, 2000)
})
test_data = list(range(2000, 3000))

# 测试assign性能
start_time = time.time()
for _ in range(100):
    result1 = test_df.assign(c=test_data)
assign_time = time.time() - start_time

# 测试直接赋值性能
start_time = time.time()
for _ in range(100):
    temp_df = test_df.copy()
    temp_df['c'] = test_data
direct_time = time.time() - start_time

print(f"assign方法耗时: {assign_time:.4f}秒")
print(f"直接赋值耗时: {direct_time:.4f}秒")
print(f"性能差异: {abs(assign_time - direct_time):.4f}秒")
print("📊 结论: 性能差异很小，可以忽略")
print()

# 6. 实际项目中的最佳实践
print("🎯 原因5: 实际项目中的最佳实践")
print()

print("📝 不同场景的选择:")
print()

print("🔸 选择 assign() 的场景:")
print("   • 数据处理管道中")
print("   • 需要链式调用时")
print("   • 函数式编程风格项目")
print("   • 需要保持原数据不变时")
print()

print("🔸 选择直接赋值的场景:")
print("   • 简单的数据探索")
print("   • 交互式分析")
print("   • 性能极度敏感的场景")
print("   • 确定要修改原DataFrame时")
print()

# 7. 你的代码的另一种写法
print("📝 你的代码的另一种写法对比:")
print()

print("当前写法 (assign):")
print("icao_code = [i if i in usedairports else g for g, i in zip(af.gps_code.values, af.ident.values)]")
print("af = af.assign(icao_code=icao_code)")
print("af['icao_code'] = af['icao_code'].astype('string')")
print()

print("等价写法 (直接赋值):")
print("icao_code = [i if i in usedairports else g for g, i in zip(af.gps_code.values, af.ident.values)]")
print("af['icao_code'] = icao_code")
print("af['icao_code'] = af['icao_code'].astype('string')")
print()

print("📊 两种写法的比较:")
print("相同点:")
print("   ✅ 最终结果完全相同")
print("   ✅ 性能差异可以忽略")
print("   ✅ 都能正确完成任务")
print()

print("不同点:")
print("   📝 assign: 符合函数式编程理念")
print("   📝 直接赋值: 更直观，更常见")
print("   📝 assign: 便于链式调用")
print("   📝 直接赋值: 代码更简洁")
print()

# 8. 总结
print("🎯 总结")
print("-" * 20)

print("💡 你的观察是正确的:")
print("   两种方法在功能上完全等效！")
print()

print("🤔 选择assign的原因:")
print("   1️⃣ 保持代码风格一致性")
print("   2️⃣ 支持函数式编程理念")
print("   3️⃣ 便于链式调用")
print("   4️⃣ 在数据处理管道中更自然")
print()

print("📝 实际建议:")
print("   • 在数据处理管道中: 使用assign")
print("   • 在简单脚本中: 直接赋值也完全可以")
print("   • 关键是保持项目内的一致性")
print()

print("🎉 这不是对错问题，而是风格选择问题！")