# 代码架构（2025-11 重构版）

为了解决根目录脚本过多、难以定位依赖的问题，本次整理将所有 Python/Shell 脚本按“功能域”收纳到 `pipelines/` 与 `tools/` 目录中，并约定所有命令均以 `python -m <package.module>` 方式调用。下面对新的结构与使用方法做一个总览，后续若继续迁移或新增模块，请同步更新本文件。

## 顶层布局

| 目录 | 作用 | 示例入口 |
| --- | --- | --- |
| `pipelines/clean_segment/` | Clean-Segment-Interpolate 全流程（含 shell 阶段脚本、`filter_trajs`、`interpolate`、批处理工具等） | `python -m pipelines.clean_segment.filter_trajs ...`、`bash pipelines/clean_segment/run_fast_pipeline.sh ...` |
| `pipelines/legacy_classic/` | 历史过滤策略与 `filterclassic.py`，供兼容/参考 | `python -m pipelines.legacy_classic.filterclassic --help` |
| `pipelines/features/` | 特征工程脚本（`feature_climbing`,`feature_weather_from_metars` 等） | `python -m pipelines.features.feature_climbing ...` |
| `pipelines/training/` | 特征装载、训练、调参、平均提交脚本 | `python -m pipelines.training.regression ...` |
| `tools/cli/` | 通用 CLI 工具（数据导入、机场/时间修正、METAR 下载等） | `python -m tools.cli.airports_to_parquet ...` |
| `tools/io/` | 读写函数（`readers.py`） | 供其它包 `from tools.io import readers` |
| `tools/common/` | 通用常量/工具函数（`utils.py`） | 供其它包 `from tools.common import utils` |
| `legacy/` | 未来归档区域，目前为空 | 待确认后迁入 |

> 📌 根目录不再放置 `.py` 文件，任何新增脚本都必须放入对应子目录。

## 运行约定

1. **环境**：数据处理统一在 `conda activate opensky` 环境内执行，深度学习训练/推理使用 `conda activate Time-MoE`（与 AGENTS 规则一致）。
2. **模块调用**：所有 Python CLI 统一使用模块调用方式，例如：
   ```bash
   # 过滤单日
   python -m pipelines.clean_segment.filter_trajs \
     -t_in opensky_2024_PRC_dataset/rawtrajectories/2022-01-01.parquet \
     -t_out opensky_2024_PRC_dataset/classic_filtered_trajectories/2022-01-01.parquet \
     -strategy classic

   # 生成机场 parquet
   python -m tools.cli.airports_to_parquet -a_in ourairports2024-10-21.csv -a_out airports_tz.parquet
   ```
3. **Shell 脚本**：`pipelines/clean_segment/run_*.sh` 仍可直接 `bash` 调用，内部已指向新的模块路径。
4. **导入路径**：脚本内部统一使用 `from tools.io import readers`、`from pipelines.clean_segment import filter_trajs` 等包路径，不再依赖运行目录的 `sys.path`。

## 兼容性说明

- 原命令 `python filter_trajs.py ...`、`python interpolate.py ...` 等需改为 `python -m pipelines.<...>`。相关 README/教程已同步更新；如仍发现旧路径，请在对应文档中补充链接。
- `clean_segment_pipeline/` 目录已迁移至 `pipelines/clean_segment/`，不存在旧的拷贝，因此所有参考文档必须引用新路径。
- 任何新的工具脚本请归类到上述包中：数据导入 → `tools/cli`，特征/训练 → `pipelines/features`/`pipelines/training`，避免回退到根目录。

## 待办

- `legacy/analysis_for_interpolation/` 保存 2025Q3 之前的再生成/合并脚本，所有关联报告（`complete_dataset_regeneration_report_*.txt`、`final_dataset_report_*.txt`、`trajectory_count_stats_multiprocess.csv` 等）集中在 `reports/legacy_clean_segment_2025Q3/`。
- 若新增包（例如 `pipelines/analysis/`），请在本文件增加一行说明用途与入口命令。
- 若新增包（例如 `pipelines/analysis/`），请在本文件增加一行说明用途与入口命令。
- 继续补充 `docs/file_inventory.md` 中的修改记录，保持与本架构说明一致。
