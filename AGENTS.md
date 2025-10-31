# 项目编程规则

## 重要：请在所有对话中严格遵守以下规则

### 环境配置
1. **数据处理**：使用conda虚拟环境 `conda activate opensky`
2. **深度学习训练和测试**：使用conda虚拟环境 `conda activate Time-MoE`
3. **运行环境**：Ubuntu 18.04容器，无sudo权限，默认root用户
4. **硬件资源**：80核心CPU，512GB内存，8张32GB显存的V100显卡，硬盘是机械硬盘，没有固态硬盘。

### 代码规范
5. **Python数据处理**：必须考虑多进程优化
6. **文件组织**：
   - 不要在项目主目录创建py文件
   - Python文件放在相关的子目录下，如果没有则创建目录
   - 测试用途的Python文件放在 `test_python/` 目录下，可以在`test_python/`目录下创建更进一步的子目录，区分不同目的测试文件，必要可以加上markdown文件说明。

### 数据路径
7. **清洗好的数据位置**：`/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories`
   - 格式：Parquet，365个文件
   - 说明：这是raw数据的一个子集，并非全部轨迹数据
   - 原始数据和清洗的中间数据目录：`/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset`
   - 原始数据在 `/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories`
   - 过滤了，未插值，有很多缺失点的数据（nan值）在  `/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories`

### 开发流程
9. **文档更新**：更新代码后，必须更新对应的markdown文件，保持更改的可追踪性和可记忆性
10. **代码修改流程**：不要轻易直接更改现有代码，请先给出详细方案，等待确认后再更改代码

### 沟通规范
11. **语言**：使用中文回答所有问题
---

**注意**：这些规则适用于所有对话和代码修改，请严格遵守。
