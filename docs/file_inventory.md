# 项目文件清单（2025-11-17）

为了开始整理 `/workspace/aircraft_trajectory/team_likable_jelly`，先对根目录的一层子项做盘点，并记录最近修改日期与活跃度标签（以当前日期为基准，修改时间在 180 天内视为 **Active**，在 180~365 天之间视为 **Recent**，更久视为 **Stale**）。后续每次迁移或归档时，可以在此文档补充说明。

> ⚠️ 数据目录（`opensky_2024_PRC_dataset/`、`perfect_trajectories/` 等）体量巨大，本清单只记下入口，详细结构另见各自 README。

## 目录级别概览

| Path | Modified | Status | Notes / Next Step |
| --- | --- | --- | --- |
| `analysis/` | 2025-11-15 | Active | 分析脚本集中地，后续计划归入 `pipelines/` / `tools/analysis/` |
| `pipelines/clean_segment/` | 2025-11-17 | Active | 主力 Clean-Segment 流程 |
| `docs/` | 2025-11-15 | Active | 文档充足但分散，后续需要补充结构说明 |
| `reports/` | 2025-11-17 | Active | 自动生成的 QA / 统计报告，维持目录不动 |
| `reports/legacy_clean_segment_2025Q3/` | 2025-11-17 | Legacy | 旧流程（再生成+合并）产生的所有报告/CSV/PNG/Parquet 统一归档 |
| `legacy/analysis_for_interpolation/` | 2025-11-17 | Legacy | 原 `junguo_analysis_for_opensky2022/analysis_for_interpolation`，包含旧流程脚本 |
| `legacy/analysis/` | 2025-11-17 | Legacy | 老版分析脚本（缺失率/问题轨迹等）备查 |
| `analysis/junguo_analysis_for_opensky2022/` | 2025-09-25 | Active | 旧版分析工具，预计迁入 `pipelines/legacy_junguo/` |
| `complete_high_quality_trajectories/` | 2025-09-24 | Active | 清洗后成品，保持原位 |
| `interpolated_trajectories/` | 2025-09-23 | Active | 插值输出目录，保持原位 |
| `opensky_2024_PRC_dataset/` | 2025-11-15 | Active | 原始数据+中间结果，保持原位，仅在 README 中解释入口 |
| `perfect_trajectories/` | 2025-10-03 | Active | 清洗好的 365 份 parquet，保持原位 |
| `test_python/` | 2025-11-15 | Active | 测试脚本目录，结构合理 |
| `trajectory_statistics_analysis/` | 2025-09-29 | Active | 统计分析输出，保持原位 |
| `trajectory_stitching/` | 2025-09-25 | Active | 航迹拼接相关脚本，准备归档为 `pipelines/legacy_stitching/` |
| `learn_python/` | 2025-10-31 | Active | 临时学习脚本（应迁入 `legacy/learning/` 避免污染根目录） |
| `config/`、`.vscode/` 等 IDE/配置目录 | 2025-09 ~ 11 | Active | 不参与整理，仅在 `.gitignore` 控制 |

## 新的代码分层

| Path | Modified | Status | Notes |
| --- | --- | --- | --- |
| `pipelines/clean_segment/` | 2025-11-17 | Active | 原 `clean_segment_pipeline/` 全量迁入此包，含 shell + Python + utils |
| `pipelines/legacy_classic/` | 2025-11-14 | Active | 经典过滤器 `filterclassic.py`、老旧策略在此隔离 |
| `pipelines/features/` | 2025-11-15 | Active | 所有特征工程脚本（`feature_*`）集中于此 |
| `pipelines/training/` | 2025-11-15 | Active | 特征装载、回归、超参脚本（`features.py`,`regression.py`,`optimparam.py`...） |
| `tools/cli/` | 2025-11-17 | Active | 所有 CLI 脚本（`airports_to_parquet.py`,`add_localtime.py` 等） |
| `tools/common/` | 2025-11-15 | Active | 公共工具（`utils.py`、常量等） |
| `tools/io/` | 2025-11-15 | Active | 读写函数（`readers.py`） |
| `legacy/` | 2025-11-15 | Pending | 预留给未来要归档的脚本 |

> ✅ 根目录现已无 `.py`/`.sh` 脚本，运行命令一律使用 `python -m <package.module>`。

## 说明

1. **Active**：上述包均为最新结构，命令行示例与 README 已更新为 `python -m pipelines.clean_segment.filter_trajs ...` 等形式。
2. **Legacy**：`legacy/analysis_for_interpolation/`、`legacy/analysis/` 与 `reports/legacy_clean_segment_2025Q3/` 记录 2025Q3 之前的老流程，保留以便回溯；新流程不再触及这些脚本与数据。
3. **Recent**：仍在 `pipelines/training/` 中，但后续需梳理是否全部纳入训练流程；若无用例再迁入 `legacy/`。
4. **Stale**：当前不存在。若未来再出现散落的 `.py`，请立即登记到此文档并安排迁移。

下一步：架构说明详见 `docs/ARCHITECTURE.md`，持续在此表补充新增/归档目录的变更记录。
