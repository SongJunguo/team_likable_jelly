# 项目编程规则

## 重要：请在所有对话中严格遵守以下规则

### 环境配置
1. **数据处理**：使用conda虚拟环境 `conda activate opensky`
2. **深度学习训练和测试**：使用conda虚拟环境 `conda activate Time-MoE`
3. **运行环境**：Ubuntu 18.04容器，无sudo权限，默认root用户
4. **硬件资源**：80核心CPU，512GB内存，8张32GB显存的V100显卡

### 代码规范
5. **Python数据处理**：必须考虑多进程优化
6. **文件组织**：
   - 不要在项目主目录创建py文件
   - Python文件放在相关的子目录下，如果没有则创建目录
   - 测试用途的Python文件放在 `test_python/` 目录下

### 数据路径
7. **清洗数据位置**：`/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories`
   - 格式：Parquet，365个文件
   - 说明：这是raw数据的一个子集，并非全部轨迹数据

### 深度学习训练
8. **重要限制**：
   - SHM限制为64MB，必须设置 `num_workers = 0` in DataLoader
   - 使用分布式数据并行(DDP)训练，充分利用8张V100显卡
   - 所有代码修改必须考虑DDP训练中的多进程问题

### 开发流程
9. **文档更新**：更新代码后，必须更新对应的markdown文件，保持更改的可追踪性和可记忆性
10. **代码修改流程**：不要轻易直接更改现有代码，请先给出详细方案，等待确认后再更改代码

### 沟通规范
11. **语言**：使用中文回答所有问题

### 模型特性
12. **模型类型**：
    - Time-MoE：专家混合模型，**非确定性模型**
    - PatchTST：**确定性模型**

### 仓库结构
13. **仓库架构**：采用"母仓库 + 子模块"结构
    - 母仓库：`flightflow-superproject` 统一跟踪公共文档与脚本
    - 子模块目录：
      - `PatchTST_Trajectory/`
      - `Time-MoE/`
      - `TrajFlow/`
      - `sundial-base-128m/`
    - 详细操作指引见：[`analysis_docs/repo_layout.md`](analysis_docs/repo_layout.md)

---

**注意**：这些规则适用于所有对话和代码修改，请严格遵守。
