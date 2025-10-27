# 项目 AGENTS.md — 飞行轨迹项目规则（必须遵守）

## 运行环境与资源
- 所有命令默认在 **Ubuntu 18.04 容器** 内执行；默认 root；**禁止使用 `sudo`**。
- 服务器硬件：80 核 CPU，512GB 内存，8 × V100 32GB（SXM2）。
- `/dev/shm` 仅 **64MB**。

## Conda 环境
- 数据处理：`conda activate opensky`
- 深度学习训练与测试：`conda activate Time-MoE`

## 代码组织
- **禁止**在项目根目录新建 `.py` 文件；Python 文件必须放在对应模块目录；若无则先创建目录。
- 测试用途 Python 文件统一放置在 `test_python/` 目录。

## 仓库结构
- 当前采用“母仓库 + 子模块”布局：`flightflow-superproject` 作为母仓库，统一跟踪公共文档、分析脚本与协作规则。
- 四个核心子项目以 Git 子模块方式挂载，路径分别为 `PatchTST_Trajectory/`、`Time-MoE/`、`TrajFlow/`、`sundial-base-128m/`，保留各自远端与历史。
- 母仓库结构、常见 Git 操作流程详见 `analysis_docs/repo_layout.md`；任何子模块指针或目录调整需同步更新该文档。

## 数据
- 飞行轨迹清洗后数据（parquet，365 个文件）路径：
  `/workspace/aircraft_trajectory/team_likable_jelly/perfect_trajectories`
  这是 **raw 的子集**，**不要**假设它是全量数据。

## 训练、多卡与多进程
- 当前使用 **DDP（分布式数据并行）** 在 **8 张 V100** 上训练。
- 由于 `/dev/shm=64MB`，**所有 PyTorch DataLoader 必须 `num_workers=0`**，
  同时避免 `persistent_workers`、`prefetch_factor` 等会占用共享内存的设置。
- CPU 侧**离线数据处理**可以使用多进程（`multiprocessing`/`joblib`），
  但 **DataLoader 内不另开进程**，避免与 DDP 冲突。
- 与 DDP 相关的 Python 入口需加 `if __name__ == "__main__":` 保护；
  支持使用 `torchrun --nproc_per_node=8 ...` 启动。

## 变更流程与文档
- **不要直接改现有代码**；先给出**详细方案**（设计、影响面、回滚方法），经同意后再动手。
- 任何代码更新，**同步更新对应的 Markdown 文档**，确保可追踪与可记忆。

## 统一规则（逐条硬性要求）
1. 数据处理使用 `conda activate opensky`
2. 命令行默认在 Ubuntu 18.04 容器；**不要使用 `sudo`**
3. 服务器：80C/512GB/8×V100 32GB（SXM2）
4. 训练/测试使用 `conda activate Time-MoE`
5. Python 数据处理程序**考虑多进程**（但 **PyTorch DataLoader 例外**，见上）
6. 不在项目主目录创建 `.py`；测试脚本放 `test_python/`
7. 洁净数据位于上述路径；这是 **raw 子集**
8. `/dev/shm=64MB` → **DataLoader `num_workers=0`**；所有改动需考虑 DDP 多进程
9. 更新代码时**必须**更新相应 Markdown 文档
10. **先方案后改码**，待批准后动手
11. **所有交流与输出使用中文**
12. Time‑MoE 为**非确定性**模型，PatchTST 为**确定性**模型。

## 默认行为
- 开始前先阅读 `README.md`、`docs/**.md`、本 `AGENTS.md`。
- Shell 命令均按容器内执行给出可复制版本；默认仅在仓库内写入。
