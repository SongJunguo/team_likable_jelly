# Copilot 全局指令（Workspace-wide Rules）

请严格遵守以下规则生成或修改代码、命令与文档（除非用户明确要求临时偏离）：

## 环境与命令
- 任何**数据处理**相关命令/脚本，请假设使用 conda 环境：`conda activate data_wrangler`（Python 3.14，已安装 pandas、numpy、pyarrow、scipy、scikit-learn、matplotlib、seaborn、polars、geopandas、cartopy 等）。
- 任何**深度学习训练/测试**命令/脚本，请假设使用 conda 环境：`conda activate Time-MoE`。
- 命令行运行环境：Ubuntu 18.04 容器，无 sudo 权限，默认 root 用户；请避免需要 sudo 的操作。
- 服务器资源：80 核 CPU、512GB 内存、8×V100 32GB（SXM2）。
- 回答语言：**中文**。
- **注意**：`traffic` 包暂不兼容 Python 3.14，如需使用请临时切换到 `opensky` 环境（Python 3.9）。

## 数据与目录规范
- 飞行轨迹清洗后的数据（parquet，365 个文件）路径：
  `/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories`
  （这是 raw 的子集，并非全量）。
- 请勿随意在项目根目录直接创建 `.py` 文件。**必须**放到对应的子目录；若无目录请先新建。
- 测试用途的 Python 文件统一放在 `test_python/` 目录。
- 仓库使用“母仓库 + 子模块”模式管理：母仓库 `flightflow-superproject` 负责公共文档/脚本，子模块包含 `PatchTST_Trajectory`、`Time-MoE`、`TrajFlow`、`sundial-base-128m`；详细结构和操作指南参见 `analysis_docs/repo_layout.md`。

## 计算范式
- Python 数据处理：**必须考虑多进程/多核并行**（如 `multiprocessing`、`concurrent.futures`、批处理队列等）。
- 训练当前采用 **分布式数据并行（DDP）**，考虑 8 张 V100 的多进程问题（如进程间通信、随机种子、日志与输出目录隔离等）。
- 容器 `/dev/shm` 限制为 **64MB**：在使用 PyTorch `DataLoader` 时默认 `num_workers=0`，并避免依赖共享内存的设计。

## 模型与实验
- Time-MoE 为**专家混合**的**非确定性**模型；PatchTST 为**确定性**模型。涉及对比或复现实验时，请据此设计随机种子与评估方法。
- 任何训练/推理脚本需提供可配置的 DDP 参数（如 `--nproc_per_node 8`、`--device cuda` 等）。

## 变更流程与可追踪性
- **不要轻易直接更改现有代码**。在执行改动前，请先输出**详细方案**（变更点、影响范围、回滚策略），待我确认后再实施。
- 每次更新代码时，**同步更新对应的 Markdown 文档**（变更说明/使用说明/实验记录），确保可追踪、可记忆。
