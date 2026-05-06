# 工作要求
- 中文回答问题，保持沟通一致。
- 先给出计划和方案，我同意后再修改代码，不要直接修改代码。
- 对于不明白，不确定的地方，先提问确认，直到我给出明确答案再开始编程，不要盲目假设。
- 代码修改时，保持代码风格一致，注意代码可读性。
- 修改代码时同步更新对应的 markdown 说明。

# 环境信息
- CPU：AMD 9950X3d 16核32线程
- 内存：48 GB DDR5 6000MHz
- GPU：NVIDIA RTX 5090d 32GB
- 操作系统：ubuntu 22.04 LTS
- **数据处理**：使用conda虚拟环境 `conda activate opensky`
- **深度学习训练和测试**：使用conda虚拟环境 `conda activate torch290`


### 代码规范
- **Python数据处理**：必须考虑多进程优化，多进程一定考虑使用 spawn 而不是 fork，必要时考虑使用 SharedMemory。
- **文件组织**：
   - 测试文件统一放在 `test_python` 文件夹内，不要散放。
   - 跨项目长期说明放在 `docs` 文件夹；项目或工具专属说明和对应代码放在一起。
   - 报告类文档和实验输出放在 `report` 或 `reports` 文件夹。
   - 新增功能和代码，考虑新建子文件夹，同时把代码和说明markdown文件放在一起，保持组织清晰，说明markdown文件命名与代码文件有语义关系，方便查找。
   - 运行 Python 前先执行 `conda env list`，按任务自动选择合适的虚拟环境。

### 数据路径
7. **清洗好的数据位置**：`team_likable_jelly/perfect_trajectories`
   - 格式：Parquet，365个文件
   - 说明：这是raw数据的一个子集，并非全部轨迹数据
   - 原始数据和清洗的中间数据目录：`team_likable_jelly/opensky_2024_PRC_dataset`
   - 原始数据在 `team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories`
   - 过滤了，未插值，有很多缺失点的数据（nan值）在  `team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories`

### 开发流程
9. **文档更新**：更新代码后，必须更新对应的markdown文件，保持更改的可追踪性和可记忆性
10. **代码修改流程**：不要轻易直接更改现有代码，请先给出详细方案，等待确认后再更改代码

### 沟通规范
11. **语言**：使用中文回答所有问题
---

**注意**：这些规则适用于所有对话和代码修改，请严格遵守。
