# 轨迹过滤系统学习文档

## 文档概述

这是一套完整的轨迹过滤系统学习文档，帮助你深入理解OpenSky ADS-B数据的过滤流程和实现细节。

---

## 文档结构

### 📚 核心文档（按顺序阅读）

1. **[01_总体流程框架.md](./01_总体流程框架.md)**
   - 系统概述和设计理念
   - 数据流全景图
   - 模块划分和关键技术特征
   - 过滤器执行顺序的设计考量
   - **推荐学习时间**：30-45分钟

2. **[02_入口模块详解.md](./02_入口模块详解.md)**
   - pipelines/clean_segment/filter_trajs.py 源码解析
   - 核心函数详解
   - 数据流转示意图
   - 关键设计决策和常见问题
   - **推荐学习时间**：45-60分钟

3. **[03_过滤器模块详解.md](./03_过滤器模块详解.md)**
   - pipelines/legacy_classic/filterclassic.py 源码深度解析
   - 5个过滤器的详细实现
   - 导数阈值和投票机制
   - 参数调优指南
   - **推荐学习时间**：90-120分钟
   - **重点内容**：MyFilterDerivative 算法

4. **[04_实战案例分析.md](./04_实战案例分析.md)**
   - 5个真实场景的案例分析
   - 完整代码示例
   - 可视化效果展示
   - 调试技巧和最佳实践
   - **推荐学习时间**：60-90分钟
   - **实践性强**：建议边读边运行代码

5. **[快速参考卡片.md](./快速参考卡片.md)**
   - 常用命令速查
   - 参数配置表
   - 故障排查清单
   - **推荐使用场景**：日常开发参考

---

## 学习路径

### 🚀 快速入门（2-3小时）

适合想快速了解系统的读者：

1. 阅读 [01_总体流程框架.md](./01_总体流程框架.md) 的第1-5节
2. 阅读 [02_入口模块详解.md](./02_入口模块详解.md) 的第1-3节
3. 浏览 [03_过滤器模块详解.md](./03_过滤器模块详解.md) 的各过滤器功能介绍
4. 运行 [04_实战案例分析.md](./04_实战案例分析.md) 的案例1-2

**掌握目标**：
- ✅ 理解过滤系统的整体架构
- ✅ 知道如何运行过滤脚本
- ✅ 了解各过滤器的基本功能

### 📖 深度学习（6-8小时）

适合需要深入理解和修改代码的开发者：

1. **第1天（3-4小时）**
   - 完整阅读 01、02 文档
   - 理解数据流转和入口逻辑
   - 运行简单的过滤测试

2. **第2天（3-4小时）**
   - 详细阅读 03 文档
   - 重点理解 MyFilterDerivative 算法
   - 运行 04 文档的所有案例

3. **巩固练习**
   - 尝试调整过滤器参数
   - 可视化不同参数的效果
   - 处理真实数据并分析结果

**掌握目标**：
- ✅ 理解每个过滤器的实现细节
- ✅ 能够调整参数优化过滤效果
- ✅ 能够扩展和修改过滤器
- ✅ 能够调试过滤问题

### 🔧 实战应用（持续）

在实际项目中应用：

1. 处理真实数据集
2. 根据数据特征调整参数
3. 评估过滤效果（准确率、召回率）
4. 优化性能（并行处理、内存管理）
5. 开发自定义过滤器

---

## 前置知识

### 必备知识
- ✅ Python基础（numpy, pandas）
- ✅ 数据处理基本概念
- ✅ 命令行基础操作

### 推荐知识（有助于深入理解）
- 📖 信号处理基础（导数、滤波）
- 📖 ADS-B数据格式
- 📖 航空领域基础知识

---

## 实践环境

### 软件环境
```bash
# 激活conda环境
conda activate opensky

# 验证环境
python --version  # 应该是 3.8+
python -c "import pandas, numpy, traffic; print('环境OK')"
```

### 测试数据

**选项1：使用完整数据**
```bash
# 数据位置
/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories/
```

**选项2：创建测试数据**
```python
# 参考 04_实战案例分析.md 中的数据生成代码
import pandas as pd
import numpy as np

# 生成简单测试轨迹
data = pd.DataFrame({
    'flight_id': [12345] * 100,
    'timestamp': pd.date_range('2022-01-01 10:00:00', periods=100, freq='s'),
    'latitude': np.linspace(39.9042, 40.0000, 100),
    'longitude': np.linspace(116.4074, 116.5000, 100),
    'altitude': np.linspace(1000, 5000, 100),
    'vertical_rate': [200] * 100,
    'groundspeed': [250] * 100,
    'track': [90] * 100,
})
```

---

## 常用命令速查

### 单文件过滤
```bash
python -m pipelines.clean_segment.filter_trajs \
    -t_in rawtrajectories/2022-01-01.parquet \
    -t_out filtered_trajectories/2022-01-01.parquet \
    -strategy classic
```

### 批量过滤（串行）
```bash
make cleantrajectories
```

### 批量过滤（并行4进程）
```bash
make cleantrajectories -j4
```

### 查看过滤效果
```python
import pandas as pd

# 加载数据
df_raw = pd.read_parquet('rawtrajectories/2022-01-01.parquet')
df_filtered = pd.read_parquet('filtered_trajectories/2022-01-01.parquet')

# 统计NaN增长
for col in ['latitude', 'longitude', 'altitude']:
    nan_before = df_raw[col].isna().sum()
    nan_after = df_filtered[col].isna().sum()
    print(f"{col}: {nan_before} → {nan_after} (+{nan_after - nan_before})")
```

---

## 关键概念索引

### 过滤器类型
- **静态过滤器**：FilterCstLatLon, FilterCstPosition, FilterCstSpeed
- **动态过滤器**：MyFilterDerivative
- **拓扑过滤器**：FilterIsolated

### 核心算法
- **变化检测**：isvar() - 判断相邻采样是否变化
- **洞宽计算**：compute_holes() - 计算孤立度
- **导数投票**：MyFilterDerivative - 基于一阶/二阶导的异常检测
- **航迹角unwrap**：处理0/360度跳变

### 关键参数
- **孤立点阈值**：20秒
- **最大洞宽**：20秒（插值阶段）
- **导数阈值**：见 [03_过滤器模块详解.md](./03_过滤器模块详解.md) 第3.4节

---

## 故障排查

### 问题1：过滤后NaN过多（>30%）

**可能原因**：
- 阈值过于严格
- 原始数据质量差

**解决方法**：
1. 检查原始数据质量统计
2. 可视化被屏蔽的点
3. 适当放宽导数阈值

详见：[03_过滤器模块详解.md 第5节](./03_过滤器模块详解.md#五、参数调优指南)

### 问题2：时间序列未严格递增

**错误信息**：
```
AssertionError in checktime()
```

**解决方法**：
```python
# 在过滤前执行去重和排序
df = (
    df.drop_duplicates(["flight_id", "timestamp"])
    .sort_values(["flight_id", "timestamp"])
    .reset_index(drop=True)
)
```

### 问题3：处理速度慢

**优化建议**：
1. 使用多进程并行：`make cleantrajectories -j8`
2. 减少调试输出
3. 使用PyArrow引擎读取Parquet

---

## 相关资源

### 项目文档
- [数据清理流程.md](../数据清理流程.md)：完整的数据处理流程
- [CLAUDE.md](../../.claude/CLAUDE.md)：项目配置和编程规则

### 源代码
- [pipelines/clean_segment/filter_trajs.py](../../pipelines/clean_segment/filter_trajs.py)：主入口脚本
- [pipelines/legacy_classic/filterclassic.py](../../pipelines/legacy_classic/filterclassic.py)：过滤器实现
- [pipelines/clean_segment/interpolate.py](../../pipelines/clean_segment/interpolate.py)：后续插值流程

### 外部资源
- [traffic库文档](https://traffic-viz.github.io/)：FilterBase 接口说明
- [OpenSky Network](https://opensky-network.org/)：ADS-B数据规范
- [csaps文档](https://csaps.readthedocs.io/)：三次平滑样条（插值阶段使用）

---

## 贡献指南

如果你发现文档中的错误或有改进建议：

1. 直接修改对应的Markdown文件
2. 更新本README的"最后更新"日期
3. 在文档末尾的修订历史中记录变更

---

## 反馈与支持

- **提问**：在团队内部沟通渠道提问
- **Bug报告**：记录在项目issue中
- **文档改进**：欢迎提交修改建议

---

## 修订历史

| 日期 | 版本 | 说明 | 作者 |
|------|------|------|------|
| 2025-10-30 | v1.0 | 初始版本，创建完整学习文档 | Claude |

---

**文档版本**：v1.0
**创建日期**：2025-10-30
**最后更新**：2025-10-30

---

## 附录：术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| **ADS-B** | Automatic Dependent Surveillance-Broadcast | 自动相关监视广播，航空器位置报告系统 |
| **轨迹点** | Trajectory Point | 单个时刻的观测数据（位置、速度等） |
| **突刺点** | Spike | 数据中的异常跳变点 |
| **孤立点** | Isolated Point | 与其他观测时间相距较远的点 |
| **洞宽** | Hole Size | 数据缺失段的时间跨度 |
| **一阶导** | First Derivative | 变化率（速度） |
| **二阶导** | Second Derivative | 变化加速度 |
| **Unwrap** | - | 展开角度跳变，使其连续 |
| **NaN** | Not a Number | 缺失值或被屏蔽的数据 |
| **管道操作符** | Pipe Operator | `|` 用于串联过滤器 |
| **投票机制** | Voting Mechanism | 通过累计票数判定异常点 |

---

**祝学习愉快！** 🎉
