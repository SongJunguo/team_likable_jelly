#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Python元组解包(Tuple Unpacking)详解
==================================

演示元组解包的触发条件、层数限制和各种用法
"""

print("=" * 60)
print("1. 元组解包的基本原理")
print("=" * 60)

# 原始元组
original_tuple = ("string", ["adep", "ades"])
print(f"原始元组: {original_tuple}")
print(f"元组类型: {type(original_tuple)}")

# 手动访问（不解包）
print("\n手动访问元组元素:")
print(f"original_tuple[0] = {original_tuple[0]} (类型: {type(original_tuple[0])})")
print(f"original_tuple[1] = {original_tuple[1]} (类型: {type(original_tuple[1])})")

# 元组解包
print("\n元组解包:")
dtype, lvar = original_tuple
print(f"dtype = {dtype} (类型: {type(dtype)})")
print(f"lvar = {lvar} (类型: {type(lvar)})")

print("\n" + "=" * 60)
print("2. 元组解包的触发条件")
print("=" * 60)

print("【条件1】等号左边的变量数量 = 右边元组的元素数量")
# 正确的解包
a, b = (1, 2)
print(f"a, b = (1, 2) → a={a}, b={b}")

# 错误示例（会报错，但这里用注释说明）
# a, b = (1, 2, 3)  # 错误！左边2个变量，右边3个元素
# a, b, c = (1, 2)  # 错误！左边3个变量，右边2个元素

print("\n【条件2】for循环中的自动解包")
tuples_list = [("A", 1), ("B", 2), ("C", 3)]
print("原始数据:", tuples_list)

print("\n不解包的循环:")
for item in tuples_list:
    print(f"item = {item} (类型: {type(item)})")

print("\n解包的循环:")
for letter, number in tuples_list:
    print(f"letter = {letter}, number = {number}")

print("\n" + "=" * 60)
print("3. 元组解包只解1层！")
print("=" * 60)

# 嵌套结构
nested_data = ("string", ["adep", "ades"])
print(f"嵌套数据: {nested_data}")

# 解包只解外层元组
dtype, column_list = nested_data
print(f"dtype = {dtype}")
print(f"column_list = {column_list} (仍然是列表，没有进一步解包)")

# 如果要解包列表，需要单独操作
if len(column_list) == 2:
    col1, col2 = column_list  # 这是列表解包，不是元组解包
    print(f"列表解包: col1={col1}, col2={col2}")

print("\n" + "=" * 60)
print("4. 解包层数限制演示")
print("=" * 60)

# 多层嵌套
complex_data = ("group1", ("string", ["adep", "ades"]))
print(f"复杂数据: {complex_data}")

# 只能解包最外层
group_name, inner_tuple = complex_data
print(f"group_name = {group_name}")
print(f"inner_tuple = {inner_tuple} (仍然是元组)")

# 要继续解包内层，需要单独操作
inner_dtype, inner_list = inner_tuple
print(f"inner_dtype = {inner_dtype}")
print(f"inner_list = {inner_list}")

print("\n" + "=" * 60)
print("5. flights_to_parquet.py中的解包过程")
print("=" * 60)

# 模拟ltypes
ltypes = [
    ("string", ["adep", "ades"]),
    ("number", ["age", "score"])
]

print("原始ltypes:")
for i, item in enumerate(ltypes):
    print(f"  ltypes[{i}] = {item}")

print("\n循环解包过程:")
for dtype, lvar in ltypes:
    print(f"\n当前轮次:")
    print(f"  从元组 {(dtype, lvar)} 解包得到:")
    print(f"  dtype = {dtype} (类型: {type(dtype)})")
    print(f"  lvar = {lvar} (类型: {type(lvar)})")
    
    print(f"  lvar列表内容:")
    for j, column in enumerate(lvar):
        print(f"    lvar[{j}] = '{column}'")

print("\n" + "=" * 60)
print("6. 元组解包的各种触发场景")
print("=" * 60)

print("【场景1】赋值语句")
x, y = (10, 20)
print(f"x, y = (10, 20) → x={x}, y={y}")

print("\n【场景2】函数返回值")
def get_coordinates():
    return (100, 200)

x, y = get_coordinates()
print(f"x, y = get_coordinates() → x={x}, y={y}")

print("\n【场景3】for循环")
data = [("Alice", 25), ("Bob", 30)]
for name, age in data:
    print(f"姓名: {name}, 年龄: {age}")

print("\n【场景4】函数参数（少见）")
def process_data(name, age):
    return f"{name}今年{age}岁"

person = ("Charlie", 35)
result = process_data(*person)  # *号解包
print(f"process_data(*person) = {result}")

print("\n" + "=" * 60)
print("总结：元组解包规则")
print("=" * 60)
print("✓ 触发条件：左边变量数 = 右边元组元素数")
print("✓ 解包层数：只解1层（最外层）")
print("✓ 嵌套数据：内层需要单独解包")
print("✓ 常见场景：赋值、for循环、函数返回值")
print("✓ 错误避免：变量数量必须匹配")