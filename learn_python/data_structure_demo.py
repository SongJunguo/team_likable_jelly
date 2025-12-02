#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据结构层次演示：List、Tuple、String的嵌套关系
==============================================

演示ltypes中的复杂数据结构
"""

print("=" * 60)
print("Python数据类型符号总结")
print("=" * 60)
print("LIST 列表    → 用中括号 []")
print("TUPLE 元组   → 用小括号 ()")
print("DICT 字典    → 用大括号 {}")
print("SET 集合     → 用大括号 {}")
print("STRING 字符串 → 用引号 '' 或 \"\"")

print("\n" + "=" * 60)
print("ltypes数据结构层次分解")
print("=" * 60)

# 模拟ltypes的简化版本
ltypes = [
    ("text", ["name", "city"]),
    ("number", ["age", "salary"]),
    ("date", ["birthday"])
]

print("完整结构:")
print(f"ltypes = {ltypes}")

print("\n逐层分解:")
print("第1层：最外层是LIST")
print(f"类型: {type(ltypes)}")
print(f"长度: {len(ltypes)}个元素")

print("\n第2层：每个元素都是TUPLE")
for i, item in enumerate(ltypes):
    print(f"第{i+1}个元素: {item}")
    print(f"  类型: {type(item)}")
    print(f"  长度: {len(item)}个子元素")
    
    print(f"  第1个子元素: {item[0]} (类型: {type(item[0])})")
    print(f"  第2个子元素: {item[1]} (类型: {type(item[1])})")
    
    print(f"  第3层：第2个子元素是LIST，包含STRING")
    for j, column in enumerate(item[1]):
        print(f"    列名{j+1}: '{column}' (类型: {type(column)})")
    print()

print("=" * 60)
print("访问方式演示")
print("=" * 60)

print("访问第1个元组:")
first_tuple = ltypes[0]
print(f"ltypes[0] = {first_tuple}")

print("\n解包第1个元组:")
data_type, column_list = first_tuple
print(f"data_type = {data_type}")
print(f"column_list = {column_list}")

print("\n访问列名列表中的第1个元素:")
first_column = column_list[0]
print(f"column_list[0] = '{first_column}'")

print("\n一步到位的访问:")
print(f"ltypes[0][0] = {ltypes[0][0]}  # 第1个元组的数据类型")
print(f"ltypes[0][1] = {ltypes[0][1]}  # 第1个元组的列名列表")
print(f"ltypes[0][1][0] = '{ltypes[0][1][0]}'  # 第1个元组的第1个列名")

print("\n" + "=" * 60)
print("嵌套结构图解")
print("=" * 60)
print("""
ltypes = [                           ← LIST（列表）用 []
    ("text", ["name", "city"]),      ← TUPLE（元组）用 ()
     ↑        ↑                      
   STRING   LIST                     ← LIST（列表）用 []
            ["name", "city"]         
             ↑       ↑               
           STRING  STRING            ← STRING（字符串）用 ''
           
    ("number", ["age", "salary"]),   ← 第2个TUPLE
     ↑          ↑                    
   STRING     LIST                   
              ["age", "salary"]      
               ↑      ↑              
             STRING STRING           
             
    ("date", ["birthday"])           ← 第3个TUPLE
     ↑        ↑                      
   STRING   LIST                     
            ["birthday"]             
             ↑                       
           STRING                    
]
""")

print("=" * 60)
print("总结：ltypes的数据结构")
print("=" * 60)
print("✓ 最外层：LIST列表 []")
print("✓ 第2层：TUPLE元组 ()")
print("✓ 元组第1个元素：STRING字符串（数据类型）")
print("✓ 元组第2个元素：LIST列表（列名列表）")
print("✓ 列名列表内部：STRING字符串（具体列名）")