#!/usr/bin/env python3
"""
解析 af 是什么类型的对象
pandas DataFrame 对象详解
"""

import pandas as pd
import numpy as np

print("🔍 af 是什么类型的对象？")
print("=" * 40)
print()

# 1. 创建一个DataFrame来演示
print("1️⃣ 创建DataFrame演示")
print("-" * 25)

af = pd.DataFrame({
    'ident': ['ZBAA', 'ZSSS', 'ZGGG'],
    'gps_code': ['ZBAA', 'ZSSS', 'ZGGG'],
    'name': ['北京首都', '上海虹桥', '广州白云']
})

print("af 的内容:")
print(af)
print()

# 2. 查看af的类型信息
print("2️⃣ af的类型信息")
print("-" * 25)

print(f"af的类型: {type(af)}")
print(f"af的类型名称: {type(af).__name__}")
print(f"af所属模块: {type(af).__module__}")
print(f"af是否是DataFrame: {isinstance(af, pd.DataFrame)}")
print()

# 3. DataFrame类的层次结构
print("3️⃣ DataFrame的类层次结构")
print("-" * 25)

print("DataFrame的继承关系:")
print(f"af.__class__: {af.__class__}")
print(f"父类(基类): {af.__class__.__bases__}")
print(f"所有基类: {af.__class__.__mro__}")
print()

# 4. af作为对象有哪些属性和方法
print("4️⃣ DataFrame对象的能力")
print("-" * 25)

print("🔸 数据属性:")
print(f"   形状(shape): {af.shape}")
print(f"   列名(columns): {list(af.columns)}")
print(f"   索引(index): {list(af.index)}")
print(f"   数据类型(dtypes):")
for col, dtype in af.dtypes.items():
    print(f"     {col}: {dtype}")
print()

print("🔸 常用方法示例:")
print("   af.head() - 查看前几行")
print("   af.info() - 查看数据信息")
print("   af.describe() - 统计描述")
print("   af.query() - 数据查询")
print("   af.assign() - 添加列")
print("   af.drop() - 删除列")
print("   af.to_parquet() - 保存为parquet")
print()

# 5. af在你的代码中的演变过程
print("5️⃣ af在代码中的演变过程")
print("-" * 25)

print("📝 af的生命周期:")
print()

print("步骤1: 创建")
print("   airportscsv = pd.read_csv(args.a_in)")
print("   # airportscsv 是 DataFrame 对象")
print()

print("步骤2: 传入函数")
print("   def airports_to_dataframe(af, flightsnames):")
print("   # af 参数接收 DataFrame 对象")
print("   # af 现在是 pandas.DataFrame 类的实例")
print()

print("步骤3: 数据操作")
print("   af = af.query(...)     # 返回新的 DataFrame")
print("   af = af.astype(...)    # 返回新的 DataFrame")
print("   af = af.assign(...)    # 返回新的 DataFrame")
print("   # 每次操作，af 都指向一个新的 DataFrame 对象")
print()

print("步骤4: 返回")
print("   return af  # 返回处理后的 DataFrame 对象")
print()

# 6. DataFrame vs 其他数据结构对比
print("6️⃣ DataFrame vs 其他数据结构")
print("-" * 25)

# 创建对比数据
list_data = [['ZBAA', '北京'], ['ZSSS', '上海']]
dict_data = {'code': ['ZBAA', 'ZSSS'], 'city': ['北京', '上海']}
array_data = np.array([['ZBAA', '北京'], ['ZSSS', '上海']])

print("🔸 数据结构对比:")
print(f"   list: {type(list_data)} - {list_data}")
print(f"   dict: {type(dict_data)} - {dict_data}")
print(f"   numpy array: {type(array_data)}")
print(f"   pandas DataFrame: {type(af)}")
print()

print("🔸 能力对比:")
print("   list: 基础容器，需要手动管理")
print("   dict: 键值对存储，无结构化操作")
print("   numpy array: 数值计算，但无列名标签")
print("   DataFrame: 结构化数据 + 强大操作方法")
print()

# 7. 为什么选择DataFrame
print("7️⃣ 为什么机场数据用DataFrame")
print("-" * 25)

print("✅ DataFrame的优势:")
print("   🏷️  有标签的列: 'ident', 'gps_code', 'name'")
print("   🔍 强大查询: af.query('gps_code.isin(@usedairports)')")
print("   🔄 数据转换: af.astype(), af.assign()")
print("   📊 数据操作: 过滤、排序、分组、聚合")
print("   💾 文件IO: .to_parquet(), .to_csv()")
print("   🧮 缺失值处理: .fillna(), .dropna()")
print("   📈 与其他库集成: matplotlib, seaborn等")
print()

# 8. af的内存结构
print("8️⃣ DataFrame的内存结构")
print("-" * 25)

print(f"📊 af的内存信息:")
print(f"   对象ID: {id(af)}")
print(f"   内存大小: {af.memory_usage(deep=True).sum()} bytes")
print(f"   行数 × 列数: {af.shape[0]} × {af.shape[1]}")
print()

print("🧩 DataFrame的组成:")
print("   • Index (行索引)")
print("   • Columns (列标签)") 
print("   • Data (实际数据，通常是numpy arrays)")
print("   • Metadata (数据类型、名称等)")
print()

# 9. 操作方法的分类
print("9️⃣ DataFrame方法分类")
print("-" * 25)

print("📂 DataFrame方法分类:")
print()
print("🔍 查询方法:")
print("   af.query(), af.loc[], af.iloc[], af[condition]")
print()
print("🔄 变换方法:")
print("   af.assign(), af.drop(), af.rename(), af.astype()")
print()
print("📊 聚合方法:")
print("   af.groupby(), af.sum(), af.mean(), af.count()")
print()
print("💾 IO方法:")
print("   af.to_parquet(), af.to_csv(), pd.read_csv()")
print()
print("ℹ️ 信息方法:")
print("   af.info(), af.describe(), af.shape, af.columns")
print()

# 10. 总结
print("🎯 总结")
print("-" * 15)

print("💡 关于 af:")
print(f"   ✅ af 是 {type(af).__name__} 类的实例")
print("   ✅ pandas.DataFrame 是一个强大的数据结构类")
print("   ✅ 专门用于处理结构化的表格数据")
print("   ✅ 提供了丰富的数据操作方法")
print("   ✅ 在数据科学和数据处理中广泛使用")
print()

print("🔧 在你的代码中:")
print("   af 代表机场(airports)数据的DataFrame")
print("   通过各种方法对机场数据进行:")
print("   • 过滤 (query)")
print("   • 类型转换 (astype)")  
print("   • 添加列 (assign)")
print("   • 删除列 (drop)")
print("   • 保存文件 (to_parquet)")
print()

print("🎉 af 就是一个功能强大的 pandas DataFrame 对象！")