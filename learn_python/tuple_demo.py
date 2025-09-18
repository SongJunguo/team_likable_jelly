#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
元组(Tuple)详解和实战示例
========================

这个文件演示元组的各种用法，帮助理解flights_to_parquet.py中的逻辑
"""

print("=" * 50)
print("1. 元组的基本创建和访问")
print("=" * 50)

# 创建元组
student = ("张三", 18, "计算机科学", 95.5)
print(f"学生信息元组: {student}")
print(f"姓名: {student[0]}")
print(f"年龄: {student[1]}")
print(f"专业: {student[2]}")
print(f"成绩: {student[3]}")

print("\n" + "=" * 50)
print("2. 元组解包示例")
print("=" * 50)

# 元组解包
name, age, major, score = student
print("解包后的变量:")
print(f"name = {name}")
print(f"age = {age}")
print(f"major = {major}")
print(f"score = {score}")

print("\n" + "=" * 50)
print("3. 模拟flights_to_parquet.py中的逻辑")
print("=" * 50)

# 模拟数据类型配置（简化版）
data_types = [
    ("text", ["name", "city"]),           # 文本类型的列
    ("number", ["age", "score", "salary"]), # 数字类型的列
    ("date", ["birthday", "graduation"])   # 日期类型的列
]

print("数据类型配置:")
for i, item in enumerate(data_types):
    print(f"第{i+1}组: {item}")

print("\n双重循环处理过程:")
for data_type, column_list in data_types:
    print(f"\n当前处理数据类型: {data_type}")
    print(f"该类型包含的列: {column_list}")
    
    for column_name in column_list:
        print(f"  -> 将列 '{column_name}' 转换为 {data_type} 类型")

print("\n" + "=" * 50)
print("4. 更多元组用法示例")
print("=" * 50)

# 坐标点
coordinates = [(0, 0), (10, 5), (20, 15)]
print("坐标点列表:")
for x, y in coordinates:
    print(f"点坐标: ({x}, {y})")

# 配置信息
database_configs = [
    ("主数据库", "192.168.1.100", 3306),
    ("备份数据库", "192.168.1.101", 3306),
    ("测试数据库", "localhost", 3307)
]

print("\n数据库配置:")
for name, host, port in database_configs:
    print(f"{name}: {host}:{port}")

print("\n" + "=" * 50)
print("5. 元组 vs 列表对比")
print("=" * 50)

# 元组（不可变）
point_tuple = (3, 4)
print(f"元组: {point_tuple}")
# point_tuple[0] = 5  # 这会报错！

# 列表（可变）
point_list = [3, 4]
print(f"列表: {point_list}")
point_list[0] = 5  # 这是可以的
print(f"修改后的列表: {point_list}")

print("\n" + "=" * 50)
print("总结：元组的核心特点")
print("=" * 50)
print("1. 有序：元素有固定的位置")
print("2. 不可变：创建后不能修改")
print("3. 可解包：可以一次性赋值给多个变量")
print("4. 异构：可以存储不同类型的数据")
print("5. 高效：比列表更快，适合固定数据")