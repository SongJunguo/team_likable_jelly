"""
Python 四种主要数据类型对比演示
展示 list, tuple, dict, set 的特点和用法
"""

def demonstrate_data_types():
    """演示四种数据类型的特点"""
    
    print("=" * 60)
    print("🔍 Python 四种主要数据类型对比")
    print("=" * 60)
    
    # 创建示例数据
    sample_data = [1, 2, 2, 3, 3, 4, 5]
    
    # 1. List（列表）
    print("\n📝 1. List（列表）- 有序、可变、允许重复")
    my_list = [1, 2, 2, 3, 3, 4, 5]
    print(f"创建: my_list = {my_list}")
    print(f"类型: {type(my_list)}")
    print(f"长度: {len(my_list)}")
    print("特点:")
    print(f"  - 有序: my_list[0] = {my_list[0]}, my_list[-1] = {my_list[-1]}")
    print(f"  - 可变: 可以修改 -> my_list[0] = 10")
    my_list[0] = 10
    print(f"    修改后: {my_list}")
    print(f"  - 允许重复: 包含重复的2和3")
    print(f"  - 支持切片: my_list[1:4] = {my_list[1:4]}")
    
    # 2. Tuple（元组）
    print("\n📦 2. Tuple（元组）- 有序、不可变、允许重复")
    my_tuple = (1, 2, 2, 3, 3, 4, 5)
    print(f"创建: my_tuple = {my_tuple}")
    print(f"类型: {type(my_tuple)}")
    print(f"长度: {len(my_tuple)}")
    print("特点:")
    print(f"  - 有序: my_tuple[0] = {my_tuple[0]}, my_tuple[-1] = {my_tuple[-1]}")
    print(f"  - 不可变: 无法修改元素")
    print(f"  - 允许重复: 包含重复的2和3")
    print(f"  - 支持切片: my_tuple[1:4] = {my_tuple[1:4]}")
    # my_tuple[0] = 10  # 这会报错！
    
    # 3. Dict（字典）
    print("\n🗂️  3. Dict（字典）- 键值对、无序、键不重复")
    my_dict = {'a': 1, 'b': 2, 'c': 3, 'b': 4}  # 注意重复键'b'会被覆盖
    print(f"创建: my_dict = {my_dict}")
    print(f"类型: {type(my_dict)}")
    print(f"长度: {len(my_dict)}")
    print("特点:")
    print(f"  - 键值对: my_dict['a'] = {my_dict['a']}")
    print(f"  - 可变: 可以修改值 -> my_dict['a'] = 10")
    my_dict['a'] = 10
    print(f"    修改后: {my_dict}")
    print(f"  - 键不重复: 重复键'b'被覆盖，值为{my_dict['b']}")
    print(f"  - 快速查找: O(1)时间复杂度")
    
    # 4. Set（集合）
    print("\n🔢 4. Set（集合）- 无序、可变、不允许重复")
    my_set = {1, 2, 2, 3, 3, 4, 5}  # 重复元素会被自动去除
    print(f"创建: my_set = {my_set}")
    print(f"类型: {type(my_set)}")
    print(f"长度: {len(my_set)}")
    print("特点:")
    print(f"  - 无序: 元素没有固定位置，不支持索引")
    print(f"  - 可变: 可以添加/删除元素")
    my_set.add(6)
    print(f"    添加元素6后: {my_set}")
    my_set.remove(1)
    print(f"    删除元素1后: {my_set}")
    print(f"  - 自动去重: 原始重复的2和3被去除")
    print(f"  - 快速查找: O(1)时间复杂度")
    print(f"  - 成员检测: 3 in my_set = {3 in my_set}")

def demonstrate_set_operations():
    """演示集合的特殊操作"""
    
    print("\n" + "=" * 60)
    print("🧮 集合的特殊操作（数学集合运算）")
    print("=" * 60)
    
    # 创建两个集合
    airports_A = {'PEK', 'SHA', 'CAN', 'CTU', 'HKG'}
    airports_B = {'HKG', 'NRT', 'ICN', 'PEK', 'TPE'}
    
    print(f"机场集合A: {airports_A}")
    print(f"机场集合B: {airports_B}")
    
    # 并集（Union）- 所有不重复的元素
    union = airports_A | airports_B  # 或者 airports_A.union(airports_B)
    print(f"\n并集 (A ∪ B): {union}")
    print(f"  含义: 所有出现过的机场")
    
    # 交集（Intersection）- 共同的元素
    intersection = airports_A & airports_B  # 或者 airports_A.intersection(airports_B)
    print(f"交集 (A ∩ B): {intersection}")
    print(f"  含义: 两个集合都有的机场")
    
    # 差集（Difference）- 在A中但不在B中的元素
    difference = airports_A - airports_B  # 或者 airports_A.difference(airports_B)
    print(f"差集 (A - B): {difference}")
    print(f"  含义: 只在A中的机场")
    
    # 对称差集（Symmetric Difference）- 不在交集中的元素
    sym_diff = airports_A ^ airports_B  # 或者 airports_A.symmetric_difference(airports_B)
    print(f"对称差集 (A ⊕ B): {sym_diff}")
    print(f"  含义: 只在其中一个集合中的机场")

def practical_airport_example():
    """实际的机场代码处理示例"""
    
    print("\n" + "=" * 60)
    print("✈️  实际应用：机场代码去重处理")
    print("=" * 60)
    
    # 模拟从多个航班文件收集机场代码
    flight_file_1_airports = ['PEK', 'SHA', 'CAN', 'PEK', 'CTU']  # 有重复
    flight_file_2_airports = ['HKG', 'PEK', 'NRT', 'ICN', 'SHA']  # 有重复
    flight_file_3_airports = ['TPE', 'KIX', 'CAN', 'HKG', 'PEK']  # 有重复
    
    print("模拟航班文件中的机场代码:")
    print(f"  文件1: {flight_file_1_airports}")
    print(f"  文件2: {flight_file_2_airports}")
    print(f"  文件3: {flight_file_3_airports}")
    
    # 方法1：使用列表（保留重复）
    all_airports_list = flight_file_1_airports + flight_file_2_airports + flight_file_3_airports
    print(f"\n使用列表合并（保留重复）:")
    print(f"  结果: {all_airports_list}")
    print(f"  总数: {len(all_airports_list)} (包含重复)")
    
    # 方法2：使用集合（自动去重）
    usedairports = set()
    usedairports.update(flight_file_1_airports)  # 添加文件1的机场
    usedairports.update(flight_file_2_airports)  # 添加文件2的机场
    usedairports.update(flight_file_3_airports)  # 添加文件3的机场
    
    print(f"\n使用集合合并（自动去重）:")
    print(f"  结果: {usedairports}")
    print(f"  总数: {len(usedairports)} (去重后)")
    
    # 方法3：一步到位的集合操作
    one_step_set = set(flight_file_1_airports) | set(flight_file_2_airports) | set(flight_file_3_airports)
    print(f"\n一步到位的集合操作:")
    print(f"  结果: {one_step_set}")
    
    # 检查特定机场是否被使用
    check_airports = ['PEK', 'LAX', 'JFK']
    print(f"\n检查机场是否被使用:")
    for airport in check_airports:
        is_used = airport in usedairports
        print(f"  {airport}: {'✅ 已使用' if is_used else '❌ 未使用'}")

def performance_comparison():
    """性能对比演示"""
    
    print("\n" + "=" * 60)
    print("⚡ 性能对比：查找元素的速度")
    print("=" * 60)
    
    import time
    
    # 创建大数据集
    size = 10000
    large_list = list(range(size))
    large_set = set(range(size))
    
    # 查找元素（最坏情况：查找最后一个元素）
    target = size - 1
    
    # 列表查找（线性搜索）
    start_time = time.time()
    for _ in range(1000):  # 重复1000次以获得可测量的时间
        result = target in large_list
    list_time = time.time() - start_time
    
    # 集合查找（哈希表查找）
    start_time = time.time()
    for _ in range(1000):  # 重复1000次
        result = target in large_set
    set_time = time.time() - start_time
    
    print(f"数据规模: {size:,} 个元素")
    print(f"查找操作重复: 1,000 次")
    print(f"列表查找时间: {list_time:.6f} 秒")
    print(f"集合查找时间: {set_time:.6f} 秒")
    print(f"集合比列表快: {list_time/set_time:.1f} 倍")

if __name__ == "__main__":
    demonstrate_data_types()
    demonstrate_set_operations()
    practical_airport_example()
    performance_comparison()
    
    print("\n" + "=" * 60)
    print("📚 总结对比表")
    print("=" * 60)
    print("| 特性     | List | Tuple | Dict | Set |")
    print("|----------|------|-------|------|-----|")
    print("| 有序     | ✅   | ✅    | ❌   | ❌  |")
    print("| 可变     | ✅   | ❌    | ✅   | ✅  |")
    print("| 重复元素 | ✅   | ✅    | ❌*  | ❌  |")
    print("| 索引访问 | ✅   | ✅    | ❌   | ❌  |")
    print("| 键值访问 | ❌   | ❌    | ✅   | ❌  |")
    print("| 成员检测 | 慢   | 慢    | 快   | 快  |")
    print("| 数学运算 | ❌   | ❌    | ❌   | ✅  |")
    print("\n* Dict的键不能重复，但值可以重复")
    
    print("\n🎯 使用场景建议:")
    print("📝 List: 需要保持顺序、允许重复、频繁索引访问")
    print("📦 Tuple: 不可变数据、函数返回多值、字典的键")
    print("🗂️  Dict: 键值映射、快速查找、配置数据")
    print("🔢 Set: 去重、成员检测、集合运算")