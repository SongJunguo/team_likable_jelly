"""
生成器演示文件
展示生成器 vs 列表的区别
"""
import sys

def demonstrate_generators():
    """演示生成器的特点"""
    
    print("=" * 50)
    print("🔍 生成器 vs 列表对比演示")
    print("=" * 50)
    
    # 1. 内存使用对比
    print("\n📊 内存使用对比:")
    
    # 列表推导式 - 立即计算所有值
    numbers_list = [x**2 for x in range(10)]
    print(f"列表: {numbers_list}")
    print(f"列表大小: {sys.getsizeof(numbers_list)} 字节")
    print(f"列表类型: {type(numbers_list)}")
    
    # 生成器推导式 - 惰性计算
    numbers_gen = (x**2 for x in range(10))
    print(f"生成器: {numbers_gen}")
    print(f"生成器大小: {sys.getsizeof(numbers_gen)} 字节")
    print(f"生成器类型: {type(numbers_gen)}")
    
    # 2. 使用方式对比
    print("\n🎯 使用方式对比:")
    
    # 列表：可以随机访问
    print("列表可以随机访问:")
    print(f"  第1个元素: {numbers_list[0]}")
    print(f"  第5个元素: {numbers_list[4]}")
    print(f"  长度: {len(numbers_list)}")
    
    # 生成器：只能顺序访问
    print("生成器只能顺序访问:")
    numbers_gen = (x**2 for x in range(10))  # 重新创建
    print(f"  第1个元素: {next(numbers_gen)}")
    print(f"  第2个元素: {next(numbers_gen)}")
    print(f"  第3个元素: {next(numbers_gen)}")
    # print(f"  长度: {len(numbers_gen)}")  # 这会报错！
    
    # 3. 迭代对比
    print("\n🔄 迭代行为对比:")
    
    # 列表：可以多次迭代
    print("列表可以多次迭代:")
    for i in range(2):
        print(f"  第{i+1}次迭代:", [x for x in numbers_list[:3]])
    
    # 生成器：只能迭代一次
    print("生成器只能迭代一次:")
    numbers_gen = (x**2 for x in range(5))
    print("  第1次迭代:", [x for x in numbers_gen])
    print("  第2次迭代:", [x for x in numbers_gen])  # 空的！
    
    # 4. 大数据集的内存优势
    print("\n🚀 大数据集内存优势:")
    
    # 模拟大数据集
    BIG_SIZE = 100000
    
    # 列表方式
    big_list = [x**2 for x in range(BIG_SIZE)]
    print(f"大列表({BIG_SIZE}个元素)内存: {sys.getsizeof(big_list):,} 字节")
    
    # 生成器方式
    big_gen = (x**2 for x in range(BIG_SIZE))
    print(f"大生成器({BIG_SIZE}个元素)内存: {sys.getsizeof(big_gen):,} 字节")
    
    print(f"内存节省: {(sys.getsizeof(big_list) - sys.getsizeof(big_gen)):,} 字节")

def practical_examples():
    """实际应用示例"""
    
    print("\n" + "=" * 50)
    print("🎪 生成器的实际应用场景")
    print("=" * 50)
    
    # 场景1：处理大文件
    def read_large_file_lines(filename):
        """模拟读取大文件的生成器"""
        # 这是一个生成器函数（使用yield）
        for i in range(10):  # 模拟文件行
            yield f"文件第{i+1}行内容"
    
    print("\n📁 场景1：处理大文件")
    file_gen = read_large_file_lines("big_file.txt")
    print("只读取前3行:")
    for i, line in enumerate(file_gen):
        if i < 3:
            print(f"  {line}")
        else:
            break
    
    # 场景2：无限序列
    def fibonacci_generator():
        """斐波那契数列生成器"""
        a, b = 0, 1
        while True:  # 无限循环！
            yield a
            a, b = b, a + b
    
    print("\n🔢 场景2：无限斐波那契数列")
    fib_gen = fibonacci_generator()
    print("前10个斐波那契数:")
    for i, num in enumerate(fib_gen):
        if i < 10:
            print(f"  F({i}) = {num}")
        else:
            break
    
    # 场景3：数据流处理
    def process_data_stream(data):
        """数据流处理生成器"""
        for item in data:
            # 模拟复杂的数据处理
            processed = item * 2 + 1
            yield processed
    
    print("\n🌊 场景3：数据流处理")
    raw_data = range(5)
    processed_stream = process_data_stream(raw_data)
    print("处理数据流:")
    for original, processed in zip(raw_data, processed_stream):
        print(f"  {original} -> {processed}")

def generator_vs_function():
    """生成器函数 vs 普通函数"""
    
    print("\n" + "=" * 50)
    print("🔧 生成器函数 vs 普通函数")
    print("=" * 50)
    
    # 普通函数：一次性返回所有结果
    def normal_function():
        result = []
        for i in range(5):
            result.append(i**2)
        return result
    
    # 生成器函数：使用yield逐个返回结果
    def generator_function():
        for i in range(5):
            print(f"    生成: {i**2}")
            yield i**2
    
    print("\n普通函数（一次性返回）:")
    normal_result = normal_function()
    print(f"结果: {normal_result}")
    
    print("\n生成器函数（逐个生成）:")
    gen_result = generator_function()
    print(f"生成器对象: {gen_result}")
    print("逐个获取值:")
    for value in gen_result:
        print(f"  得到: {value}")

if __name__ == "__main__":
    demonstrate_generators()
    practical_examples()
    generator_vs_function()
    
    print("\n" + "=" * 50)
    print("📝 总结")
    print("=" * 50)
    print("✅ 生成器优点:")
    print("  - 节省内存（惰性计算）")
    print("  - 支持无限序列")
    print("  - 适合大数据流处理")
    print("⚠️  生成器限制:")
    print("  - 只能顺序访问")
    print("  - 只能迭代一次")
    print("  - 无法获取长度")