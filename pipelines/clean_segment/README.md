# Clean-Segment-Interpolate 流程

## 🎯 设计理念

**核心思想**：过滤 → 切分 → 插值

**与旧流程的区别**：

| 维度 | 旧流程 | 新流程（Clean-Segment-Interp） |
|------|--------|-------------------------------|
| **流程顺序** | 过滤 → 插值 → 切分（带速度检查） | 过滤 → 切分 → 插值 |
| **速度检测** | 切分阶段再检查 | 过滤阶段一次性处理（投票机制） |
| **插值对象** | 完整轨迹（可能含大间隔） | 短小segment（内部连续） |
| **删除策略** | 单列或部分列 | 整行删除（位置+速度+天气） |
| **插值质量** | 可能跨异常段插值 | 仅在干净segment内插值 ✅ |

**优势**：
1. ✅ 速度异常在过滤阶段彻底处理（带投票机制，更稳健）
2. ✅ 位置异常时，天气参数联动删除（避免基于错误位置的数据）
3. ✅ 切分后的segment内部干净、时间连续，插值质量更高
4. ✅ 不对含异常段的数据插值，避免污染传播
5. ✅ 最终轨迹：0个NaN + 0个异常点 + 1Hz均匀采样
6. ✅ 新增 PCA 空间异常检测：距离主航迹很远的孤立段被自动剔除，并写入可追踪的统计日志

## 📂 目录结构

```
pipelines/clean_segment/
├── README.md                   # 本文档
├── config.sh                   # 统一配置
│
├── run_staged_pipeline.sh      # 【模式1】分阶段运行（便于调试）
├── run_fast_pipeline.sh        # 【模式2】一口气运行（快速，机械硬盘友好）
├── run_fast_pipeline_parallel.sh       # 新版（轨迹级并行）⭐
├── run_remove_jump_trajectories.sh     # 基于 jump_events_all 的异常航迹清理
└── remove_jump_trajectories.py         # 实际执行多进程过滤的脚本
│
├── 01_filter_clean.sh          # 阶段1：过滤
├── 02_split_by_time.sh         # 阶段2：切分
├── 03_interpolate_segments.sh  # 阶段3：插值
├── 04_quality_check.sh         # 阶段4：质量检查
│
├── process_single_day_fast.py  # 快速模式核心脚本
├── process_single_day_fast_parallel.py # 新版（轨迹级并行）⭐
│
└── utils/
    └── batch_utils.sh          # 批量处理工具

# 复用分析工具（不在本目录）
# - pipelines/clean_segment/check_nan_values.py  # NaN并行检测
# - pipelines/clean_segment/run_detect_jumps_all.sh  # 跳变检测
```

## ⚡ 并行策略速览

| 脚本 | 并行粒度 | 实际行为 | 命名备注 |
|------|---------|----------|-----------|
| `run_fast_pipeline_parallel.sh` | 默认：文件级串行 + 轨迹级多进程；多日期时自动切到文件级多进程，文件内单线程 | 单文件测试时将 `--workers` 传入 `process_single_day_fast_parallel.py`，对每个 flight_id 启动多进程；为防止 24×24 内存爆炸，若待处理文件>1 会用 `xargs -P` 做文件级并行并把 `--workers` 固定为1 | 名称中的“parallel”指**轨迹级**并行，README 特别说明了单/多文件的动态策略 |
| `run_fast_pipeline.sh` | 文件级并行 | `xargs -P $PROCS` 同时跑多个日期，每个 Python 进程内部串行完成“过滤→切分→插值” | “fast”指整合阶段、减少 I/O；并行业务在 README 中明确是文件级 |
| `run_staged_pipeline.sh` | 自身无并行，顺序调度 01~04 | 只负责根据参数依次调用阶段脚本，并将 `--procs` 透传 | 名称体现“分阶段”，并发逻辑完全在子脚本中 |
| `01_filter_clean.sh` | 文件级并行，轨迹级单进程 | 使用 `xargs -P $PROCS` 对不同日期并发，每个 `filter_trajs` 调用内部串行处理全部 flight | “filter” 已与阶段一致，说明其并行度可通过 `--procs` 控制 |
| `02_split_by_time.sh` | 文件级并行，segment 内单线程 | `split_single_day.py` 逐 segment 切分，外层用 `xargs -P` 并发多个日期 | 名称明确“split by time”，文档中补充该阶段同样是文件级并行 |
| `03_interpolate_segments.sh` | 文件级并行，segment 内单线程 | `interpolate_single_day.py` 顺序遍历 segment；外层 `xargs -P` 控制并发文件数 | “interpolate segments” 表达了作用对象，新增说明强调是文件级拆分 |
| `04_quality_check.sh` | 脚本整体串行；内部调用 `run_detect_jumps_all.sh` 和 `check_nan_values.py` 均支持文件级并行 | 跳变检测和NaN检测的 `--procs` 参数控制并行度（默认24进程），基础统计为单进程Python | ⭐ 已升级NaN检测为并行模式，24个文件仅需3-5秒 |

## 🚀 使用方法

> 运行前请先手动 `conda activate opensky`（脚本不再自动激活环境）。

### 快速开始（推荐）

#### 方式1：轨迹级并行（单日测试推荐）
```bash
cd pipelines/clean_segment

# 单日数据测试（充分利用多核，速度快！）
bash run_fast_pipeline_parallel.sh --from 2022-01-01 --to 2022-01-01 --workers 24

# 全量运行（顺序处理文件，每个文件内并行）
bash run_fast_pipeline_parallel.sh --workers 40
```

**特点**：
- ✅ 文件级串行：一个parquet一个parquet处理
- ✅ 轨迹级并行：每个文件内按flight_id并行
- ✅ 单日测试时充分利用多核（不用等很久！）
- ✅ 机械硬盘友好（顺序读文件，避免I/O竞争）

#### 方式2：文件级并行（全量运行推荐）
```bash
cd pipelines/clean_segment

# 多个文件并行处理
bash run_fast_pipeline.sh --from 2022-01-01 --to 2022-01-10

# 全量运行
bash run_fast_pipeline.sh

# 如需关闭自动质量检查 / 点数统计
bash run_fast_pipeline.sh --no-quality --no-stats
```

**特点**：
- ✅ 文件级并行：同时处理多个parquet文件
- ✅ 全量运行时效率高（365个文件并行）
- ⚙️  默认跑完自动执行质量检查与点数统计（缺少 filtered/segmented 目录时自动跳过对应统计项）
- ⚠️  单日测试时无法并行（只有1个文件）

**如何选择**：
- **测试单日数据**：用 `run_fast_pipeline_parallel.sh`（轨迹级并行）
- **全量处理**：用 `run_fast_pipeline.sh`（文件级并行）或 `run_fast_pipeline_parallel.sh`（看机械硬盘I/O是否饱和）

### 分阶段运行（调试用）

```bash
# 分阶段运行，每阶段都会存储中间结果
bash run_staged_pipeline.sh --from 2022-01-01 --to 2022-01-01

# 中间结果：
# - filtered_clean_v1/2022-01-01.parquet         （过滤后）
# - segmented_clean_v1/segmented_2022-01-01.parquet  （切分后）
# - interpolated_clean_v1/interpolated_2022-01-01.parquet  （最终）
```

### 单独运行某阶段

```bash
bash 01_filter_clean.sh --date 2022-01-01
bash 02_split_by_time.sh --date 2022-01-01
bash 03_interpolate_segments.sh --date 2022-01-01
bash 04_quality_check.sh  # 检查最终结果
```

### 按报告删除跳变航迹（原地覆盖写回）

质量检查阶段会在 `reports/quality_check_clean__PCA_v4_manual/jump_detection/jump_events_all.csv` 中记录所有疑似跳变。可以使用新增的一键脚本根据该列表直接删除对应航迹，避免重新跑全量流程：

```bash
cd pipelines/clean_segment

# 先试跑（dry-run），仅统计将被删除的航迹数量
bash run_remove_jump_trajectories.sh --dry-run --processes 16 --limit 2

# 真正执行：会逐个 parquet 原地过滤，并写临时文件 + os.replace
bash run_remove_jump_trajectories.sh --processes 24 --verbose
```

脚本说明：
- 默认激活 `opensky` conda 环境，可通过 `CONDA_ENV` 环境变量覆盖。
- 自动读取 `config.sh` 中的 `INTERPOLATED_DIR` 作为数据目录，也可以通过 `--data-dir` 指定其他目录（例如某次试验输出）。
- 支持 `--limit`、`--day-file` 等调试参数，可在 700GB 机械盘环境下按文件粒度顺序写回，避免额外目录和重复 I/O。
- 如果想先审查具体航迹，可结合 `--dry-run --verbose` 查看每个 parquet 内删除的行数。

## ⚙️ 参数配置

编辑 `config.sh`：

### 过滤参数
```bash
FILTER_STRATEGY="clean_segment_interp"  # 策略名
MAX_SPEED_MPS=700        # 速度阈值（FilterMaxSpeedSkipNaNWithVoting读取）
MAX_ACCEL_MPS2=25.0      # 加速度阈值（FilterMaxSpeedSkipNaNWithVoting读取）
VOTE_THRESHOLD=2         # 投票阈值（≥2票才删除，FilterMaxSpeedSkipNaNWithVoting读取）
ALT_DERIV_FIRST_FTPS=151 # 高度一阶导阈值（ft/s）
ALT_DERIV_SECOND_FTPS2=51 # 高度二阶导阈值（ft/s²）
ENABLE_SPATIAL_PCA=1     # 1=启用PCA空间异常检测
PCA_MIN_POINTS=80        # 至少多少有效点才运行PCA
PCA_MAD_SCALE=6.0        # 阈值 = median(residual) + scale * 1.4826 * MAD
PCA_WINDOW_SIZE=256      # 滑动窗口大小（≤0表示仅全局PCA）
PCA_STATS_CSV="$REPORT_DIR/pca_flags.csv"  # 统计落盘路径（自动加锁，支持多进程）
ENABLE_SKIPNAN_POST_PCA=1    # 1=在PCA之后再执行一次跨NaN速度检测
POST_PCA_SKIPNAN_MAX_ITER=3  # 额外跨NaN速度检测的最大迭代次数（阈值复用MAX_SPEED_MPS）
```

### 元数据筛选（可选）

在过滤前按航班元数据筛选 `flight_id`（默认关闭）：

```bash
# 1=开启起降都在欧洲的航班过滤（continent==EU）
META_EUROPE_ONLY=0

# Top-N 频次筛选（0=关闭）
META_TOP_AIRPORTS=0     # adep+ades 合并统计
META_TOP_AIRCRAFT=0

# 元数据来源（默认仅 challenge_set）
META_INCLUDE_SUBMISSION=0
META_INCLUDE_FINAL=0

# 元数据文件路径
META_FLIGHTS_PARQUET="$REPO_ROOT/opensky_2024_PRC_dataset/flights/challenge_set.parquet"
META_AIRPORTS_PARQUET="$REPO_ROOT/opensky_2024_PRC_dataset/airports_tz.parquet"
META_EUROPE_CONTINENT="EU"
META_PROCS=4
```

说明：
- 缺失/UNKNOWN 会被直接剔除
- Top-N 统计基于欧洲筛选后的子集（若开启欧洲筛选）

### 切分参数
```bash
MAX_DT=20                  # 最大时间间隔（秒）
MIN_POINTS=30              # 最小segment点数
MIN_DURATION=120           # 最小segment时长（秒）
MAX_HOLE_SIZE="$MAX_DT"    # 最大插值间隔，默认与MAX_DT保持一致，可单独调整
```

### 插值参数
```bash
SMOOTH=1e-2        # csaps平滑系数
# MAX_HOLE_SIZE 同上，由03/fast脚本透传给 pipelines/clean_segment/interpolate.py 限制最大补洞长度
```

### PCA 空间异常检测 + 跨NaN速度复检

- **触发条件**：同一航班有效经纬度点数 ≥ `PCA_MIN_POINTS`。
- **检测方式**：对 `(latitude, longitude)` 做 PCA，仅保留第一主轴并计算每个点的重建残差。
- **阈值**：`median(residual) + PCA_MAD_SCALE * 1.4826 * MAD`，MAD 是残差相对中位数的绝对偏差的中位数。
- **滑动窗口**：`PCA_WINDOW_SIZE > 0` 时自动使用 50% overlap 的滑窗重复检测，可在长航段中捕获局部漂移。
- **输出**：所有航班的 `flagged/total/threshold` 等指标写入 `PCA_STATS_CSV`（默认 `reports/quality_check_clean_v6/pca_flags.csv`，支持多进程追加）。
- **复检**：若 `ENABLE_SKIPNAN_POST_PCA=1`，则在 PCA 之后调用 `FilterMaxSpeedSkipNaN`，阈值沿用 `MAX_SPEED_MPS`，迭代次数由 `POST_PCA_SKIPNAN_MAX_ITER` 控制，用于清理仍存在的“沿主轴但跨越大距离”的跳点。
- **可视化**：`test_python/analysis/filter_and_plot_single_flight.py --show-pca ...` 会在 Raw vs Filter 图上高亮被 PCA 删除的点，便于复审；跨NaN速度复检效果可通过对比 `reports/single_flight/*.parquet` 验证。

### 质量检测开关（⭐新增）
```bash
# 检测开关（可随时开启/关闭）
ENABLE_JUMP_DETECTION=1   # 1=启用跳变检测, 0=禁用
ENABLE_NAN_CHECK=1        # 1=启用NaN检测, 0=禁用

# NaN检测配置
NAN_CHECK_COLUMNS="latitude longitude altitude"  # 重点检查经纬高
NAN_CHECK_PROCS=24        # NaN检测并行进程数（⭐并行加速）
```

## 📊 质量检查（⭐已升级）

流程结束后自动运行质量检查（也可手动运行）：

```bash
# 完整检查（跳变 + NaN）
bash 04_quality_check.sh

# 仅NaN检查（跳过跳变检测，省时间）
bash 04_quality_check.sh --skip-jump

# 跳过NaN检测
bash 04_quality_check.sh --skip-nan

# 通过config.sh全局禁用
# 编辑config.sh，修改：
#   ENABLE_JUMP_DETECTION=0
#   ENABLE_NAN_CHECK=0
```
- 跳变检测会自动读取 `MAX_SPEED_MPS` 并换算成 km/h 传给 `run_detect_jumps_all.sh --min-speed`，确保质量检查阶段的速度阈值与过滤阶段一致。

### 输出报告

```
reports/quality_check_clean_v1/
├── jump_detection/             # 跳变检测详情
│   ├── jump_events_summary.csv
│   └── jump_events_all.csv
├── nan_check_report.txt        # NaN检测报告（⭐并行加速，3-5秒完成）
└── basic_statistics.txt        # 基础统计
```

### NaN检测输出示例（⭐改进）

**无NaN时（清晰的总体统计）**：
```
✅ 质量检查通过
   总文件数: 24
   总数据点: 66,807,887
   总轨迹数: 261,030
   经纬高缺失值: 0 (0.0000%)
```

**有NaN时（先总体统计，再问题列表）**：
```
❌ 质量检查失败
   总文件数: 24
   总数据点: 66,807,887

   各列缺失率:
     LATITUDE: 1,234 (0.0100%)
     LONGITUDE: 0 (0.0000%)
     ALTITUDE: 567 (0.0046%)

   问题文件 (前10个):
     📁 interpolated_2022-01-03.parquet: 801个NaN
     ...
```

### 检查项

- ✅ **跳变检测**：检测短时间内跨越超远距离的异常
- ✅ **NaN检测**：并行检查经纬高缺失值（⭐24进程，速度快）
- ✅ **基础统计**：文件数、数据点数、segment数

## 🔧 技术细节

### 过滤策略（clean_segment_interp）

```python
FilterCstLatLon()               # 删除经纬度重复点
| FilterCstPosition()           # 删除三维位置未更新点
| FilterCstSpeed()              # 删除速度指标未更新点
| FilterEdgeOutlier()           # 清理首尾离群点
| FilterMaxSpeedSkipNaNWithVoting(  # ★核心：跨NaN速度检测+投票
    max_speed_mps=${MAX_SPEED_MPS},
    max_accel_mps2=${MAX_ACCEL_MPS2},
    max_iterations=10,
    vote_threshold=${VOTE_THRESHOLD}
  )
| MyFilterDerivative(           # 高度三点投票（阈值来自config）
    altitude=dict(first=151, second=51)
  )
| FilterSpatialPCAOutlier()     # PCA 主轴残差检测
| FilterMaxSpeedSkipNaN()       # （可选）PCA 后再次跨NaN检测
| FilterIsolated()              # 删除孤立点（>20s距离）
```

> 提示：`MAX_SPEED_MPS` / `MAX_ACCEL_MPS2` / `VOTE_THRESHOLD` / `ALT_DERIV_*` 均来自 `config.sh`，修改后无需动代码即可生效。

**投票机制**：
- 速度异常：前后两点各得1票
- 加速度异常：前中后三点各得1票
- 票数≥2才删除（更稳健）

**整行删除**：
- 位置列：latitude, longitude, altitude, geoaltitude
- 速度列：groundspeed, track, vertical_rate
- 天气列：u_component_of_wind, v_component_of_wind, temperature, specific_humidity
- 衍生列：gsx, gsy, tasx, tasy, tas, wind, track_unwrapped

理由：位置错误 → 基于位置的所有数据都不可信

**高度突刺额外筛查**：
- `MyFilterDerivative` 仅监控 `altitude`，一阶/二阶导阈值可通过 `ALT_DERIV_FIRST_FTPS` / `ALT_DERIV_SECOND_FTPS2` 配置；
- 命中后将高度（及依赖天气字段）置 NaN，随后在切分阶段整行剔除，减少“高度突刺导致的段碎”。

### 两种运行模式

**模式1：分阶段模式**（便于调试）
- 每阶段存储中间结果
- 便于检查问题出在哪个阶段
- I/O较多（机械硬盘慢）

**模式2：快速模式**（生产推荐）
- 数据在内存中流转
- 只存储最终结果
- I/O最少（机械硬盘友好）✅

## 📈 性能优化

### 机械硬盘优化
- 使用快速模式（减少I/O）
- 并发度设置为24-40（避免磁盘饱和）
- 输出目录放在高速分区

### 并发配置
```bash
FILTER_PROCS=24      # 过滤阶段并发
SPLIT_PROCS=24       # 切分阶段并发
INTERP_PROCS=24      # 插值阶段并发（快速模式用）
```

## 🐛 故障排查

### 问题1：过滤后数据太少
**原因**：阈值过于严格

**解决**：
```bash
# config.sh中调整
MAX_SPEED_MPS=600    # 放宽到600 m/s
VOTE_THRESHOLD=3     # 提高投票阈值
```

### 问题2：最终轨迹仍有NaN
**原因**：插值阶段异常或切分参数过严

**解决**：
```bash
# 1. 查看NaN详细报告（⭐并行检测，快速定位问题）
bash 04_quality_check.sh --skip-jump
cat reports/quality_check_clean_v1/nan_check_report.txt

# 2. 检查插值日志
cat interpolated_clean_v1/.logs/2022-01-01.log

# 3. 调整切分参数（如果segment太短导致插值失败）
# 在config.sh中：
MIN_POINTS=20      # 降低最小点数要求
MIN_DURATION=60    # 降低最小时长要求

# 4. 手动重新运行
bash 03_interpolate_segments.sh --date 2022-01-01 --force
```

### 问题3：质量检查发现跳变
**原因**：过滤阶段漏检

**解决**：
```bash
# 降低速度阈值
MAX_SPEED_MPS=500

# 或增加检测轮次
max_iterations=15
```

### 问题4：environment: line XX: `<...>/.logs/YYYY-MM-DD.log`: No such file or directory
**原因**：阶段日志目录（`filtered_clean_v4/.logs`、`segmented_clean_v4/.logs`、`interpolated_clean_v4/.logs`）被手动清理或在上次异常中断后缺失，导致 tee/重定向无法写入日志。

**解决**：
```bash
# 任选一种：手动补齐或重新跑脚本都会自动创建
mkdir -p opensky_2024_PRC_dataset/filtered_clean_v4/.logs
mkdir -p opensky_2024_PRC_dataset/segmented_clean_v4/.logs
mkdir -p opensky_2024_PRC_dataset/interpolated_clean_v4/.logs

# 重新运行分阶段脚本（会再次自检并创建日志目录）
bash pipelines/clean_segment/run_staged_pipeline.sh --from 2022-01-01 --to 2022-01-24
```

## 📝 与旧流程对比

### 旧流程入口
```bash
legacy/analysis_for_interpolation/run_full_pipeline_with_interpolate.sh
```

### 新流程入口
```bash
pipelines/clean_segment/run_fast_pipeline.sh
```

**两者完全独立**，可同时运行、对比评估！

## 💡 最佳实践

1. **首次使用**：先用单日数据测试（--from/--to）
2. **参数调优**：根据质量检查结果调整阈值
3. **生产运行**：使用快速模式（run_fast_pipeline.sh）
4. **快速验证**：使用 `--skip-jump` 快速检查NaN（3-5秒完成）⭐
5. **开关控制**：通过config.sh中的开关变量控制检测项，避免重复运行⭐
6. **定期检查**：运行quality_check.sh确保数据质量

## 📞 技术支持

- 配置问题：检查config.sh
- 代码问题：查看对应脚本的注释
- 质量问题：分析quality_check报告
