#!/usr/bin/env python3
"""
Python zip() 函数完全详解
从基础到高级用法的全面教程
"""

print("🔗 Python zip() 函数完全详解")
print("=" * 50)
print()

# 1. 基本概念
print("1️⃣ 基本概念")
print("-" * 20)
print("zip() 的作用：将多个可迭代对象（列表、元组等）逐个配对")
print("返回：zip对象（迭代器）")
print()

# 2. 最简单的例子
print("2️⃣ 最简单的例子")
print("-" * 20)

list1 = [1, 2, 3]
list2 = ['a', 'b', 'c']

print(f"列表1: {list1}")
print(f"列表2: {list2}")

# zip配对
zipped = zip(list1, list2)
print(f"zip(list1, list2): {zipped}")  # 这是一个zip对象
print(f"转换为列表: {list(zip(list1, list2))}")
print()

# 3. 详细展示配对过程
print("3️⃣ 配对过程详解")
print("-" * 20)
for i, (num, letter) in enumerate(zip(list1, list2)):
    print(f"索引{i}: {num} 配对 {letter}")
print()

# 4. 三个列表的配对
print("4️⃣ 多个列表配对")
print("-" * 20)

names = ['张三', '李四', '王五']
ages = [25, 30, 28]
cities = ['北京', '上海', '广州']

print(f"姓名: {names}")
print(f"年龄: {ages}")
print(f"城市: {cities}")
print()

print("三元组配对结果:")
for name, age, city in zip(names, ages, cities):
    print(f"  {name}, {age}岁, 住在{city}")
print()

# 5. 长度不同的列表
print("5️⃣ 长度不同时的行为")
print("-" * 20)

short_list = [1, 2]
long_list = ['a', 'b', 'c', 'd', 'e']

print(f"短列表: {short_list}")
print(f"长列表: {long_list}")
print(f"zip结果: {list(zip(short_list, long_list))}")
print("⚠️  注意：以最短的列表长度为准！")
print()

# 6. 实际应用场景
print("6️⃣ 实际应用场景")
print("-" * 20)

# 场景1：创建字典
keys = ['name', 'age', 'city']
values = ['小明', 22, '深圳']
person_dict = dict(zip(keys, values))
print(f"创建字典: {person_dict}")
print()

# 场景2：并行处理两个列表
scores_math = [85, 92, 78, 96]
scores_english = [88, 89, 85, 94]
print("计算总分:")
for i, (math, english) in enumerate(zip(scores_math, scores_english)):
    total = math + english
    print(f"  学生{i+1}: 数学{math} + 英语{english} = 总分{total}")
print()

# 7. zip的逆操作：解包
print("7️⃣ zip的逆操作：解包")
print("-" * 20)

paired_data = [(1, 'a'), (2, 'b'), (3, 'c')]
print(f"配对数据: {paired_data}")

# 使用 * 解包
numbers, letters = zip(*paired_data)
print(f"解包后的数字: {numbers}")
print(f"解包后的字母: {letters}")
print()

# 8. 高级用法：zip_longest
print("8️⃣ 高级用法：itertools.zip_longest")
print("-" * 20)

from itertools import zip_longest

short = [1, 2]
long = ['a', 'b', 'c', 'd']

print(f"短列表: {short}")
print(f"长列表: {long}")
print(f"普通zip: {list(zip(short, long))}")
print(f"zip_longest: {list(zip_longest(short, long, fillvalue='X'))}")
print("💡 zip_longest 会用指定值填充短列表")
print()

# 9. 在pandas/数据处理中的应用
print("9️⃣ 数据处理中的应用")
print("-" * 20)

# 模拟机场数据场景
airport_codes = ['ZBAA', 'ZSSS', 'ZGGG']
airport_names = ['北京首都', '上海虹桥', '广州白云']

print("机场代码和名称配对:")
for code, name in zip(airport_codes, airport_names):
    print(f"  {code} → {name}")
print()

# 10. 性能和内存效率
print("🔟 性能特点")
print("-" * 20)
print("✅ zip返回迭代器，内存高效")
print("✅ 延迟计算，只在需要时生成配对")
print("✅ 适合处理大数据集")
print("⚠️  zip对象只能遍历一次！")
print()

# 演示zip对象只能遍历一次
demo_zip = zip([1, 2, 3], ['a', 'b', 'c'])
print("第一次遍历zip对象:")
for item in demo_zip:
    print(f"  {item}")

print("第二次遍历同一个zip对象:")
for item in demo_zip:
    print(f"  {item}")
print("结果：空的！因为迭代器已经耗尽")
print()

# 11. 总结
print("📝 总结")
print("-" * 20)
print("🎯 zip()函数的核心价值：")
print("  • 将多个序列元素一一配对")
print("  • 支持同时遍历多个数据源")
print("  • 内存高效的迭代器设计")
print("  • 广泛应用于数据处理场景")
print()
print("🚀 常见用法：")
print("  • for a, b in zip(list1, list2):")
print("  • dict(zip(keys, values))")
print("  • list(zip(data1, data2))")
print("  • a, b = zip(*paired_data)")
print()
print("🎉 现在你完全掌握了zip函数！")