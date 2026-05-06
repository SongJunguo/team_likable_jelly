# `run_staged_pipeline.sh` 完整说明

> 版本说明
>
> - 代码分支：`main`
> - 代码提交：`012747d`
> - 代码快照说明：本文档内容对应当前工作区内 `run_staged_pipeline.sh` 及其关联脚本的仓库快照，不是独立发布版 tag
> - 流程版本：`clean_eu_v5`，依据 [`config.sh`](./config.sh) 中默认输出目录 `filtered_clean_eu_v5 / segmented_clean_eu_v5 / interpolated_clean_eu_v5`
> - 文档构建时间：`2026-03-26 21:48:49 CST (+0800)`

本文档专门对应 [`run_staged_pipeline.sh`](./run_staged_pipeline.sh)，目标是把这条分阶段数据清理流程的入口行为、依赖数据集、每个阶段的输入输出、关键参数、当前仓库中的数据现状，以及脚本源码里一些容易踩坑的实现细节一次性讲清楚。

---

## 1. 这条脚本到底做什么

`pipelines/clean_segment/run_staged_pipeline.sh` 是一条 **按阶段落盘** 的轨迹清理总控脚本。它按顺序调度下面 5 个步骤：

1. `01_filter_clean.sh`：过滤清洗
2. `02_split_by_time.sh`：按时间切分 segment
3. `03_interpolate_segments.sh`：对每个 segment 做 1Hz 插值和平滑
4. `04_quality_check.sh`：质量检查
5. `run_raw_filtered_point_stats.sh`：raw / filtered / segmented / interpolated 点数与缺失率统计

和 `run_fast_pipeline.sh` 的区别是：

- `run_staged_pipeline.sh` 会把每个阶段的中间结果都写到磁盘，方便抽查、断点续跑、定位问题。
- 代价是 I/O 明显更多，特别是机械盘环境下会比 fast pipeline 更慢。

---

## 2. 调用关系总览

```text
run_staged_pipeline.sh
├── source config.sh
├── 01_filter_clean.sh
│   └── python -m pipelines.clean_segment.filter_trajs
├── 02_split_by_time.sh
│   └── python pipelines/clean_segment/split_single_day.py
├── 03_interpolate_segments.sh
│   └── python pipelines/clean_segment/interpolate_single_day.py
├── 04_quality_check.sh
│   ├── bash pipelines/clean_segment/run_detect_jumps_all.sh
│   └── python pipelines/clean_segment/check_nan_values.py
└── run_raw_filtered_point_stats.sh
    └── python analysis/raw_filtered_point_stats.py
```

这条链路的核心设计是：

- **先过滤，再切分，再插值**
- 插值只发生在已经被裁成短而连续的 segment 内
- 质量检查和点数统计不参与生成数据，但会给出能否继续使用数据的直接结论

---

## 3. 当前 `config.sh` 快照

本文档基于当前仓库里的 [`config.sh`](./config.sh) 写成。当前默认配置如下。

### 3.1 目录

| 变量 | 当前值 |
| --- | --- |
| `RAW_DIR` | `opensky_2024_PRC_dataset/rawtrajectories` |
| `FILTERED_DIR` | `opensky_2024_PRC_dataset/filtered_clean_eu_v5` |
| `SEGMENTED_DIR` | `opensky_2024_PRC_dataset/segmented_clean_eu_v5` |
| `INTERPOLATED_DIR` | `opensky_2024_PRC_dataset/interpolated_clean_eu_v5` |
| `REPORT_DIR` | `reports/quality_check_clean_eu_v5` |

### 3.2 日期和并发

| 变量 | 当前值 |
| --- | --- |
| `DATE_FROM` | `2022-01-01` |
| `DATE_TO` | `2022-02-28` |
| `FILTER_PROCS` | `8` |
| `SPLIT_PROCS` | `4` |
| `INTERP_PROCS` | `4` |
| `QUALITY_CHECK_PROCS` | `4` |
| `NAN_CHECK_PROCS` | `4` |

### 3.3 元数据筛选和机场过滤

| 变量 | 当前值 |
| --- | --- |
| `META_EUROPE_ONLY` | `1` |
| `META_TOP_AIRPORTS` | `64` |
| `META_TOP_AIRCRAFT` | `25` |
| `META_INCLUDE_SUBMISSION` | `0` |
| `META_INCLUDE_FINAL` | `0` |
| `META_FLIGHTS_PARQUET` | `opensky_2024_PRC_dataset/flights/challenge_set.parquet` |
| `META_AIRPORTS_PARQUET` | `opensky_2024_PRC_dataset/airports_tz.parquet` |
| `AIRPORT_PROXIMITY_ENABLE` | `1` |
| `AIRPORT_PROXIMITY_THRESHOLD_KM` | `10` |

### 3.4 过滤 / 切分 / 插值阈值

| 变量 | 当前值 |
| --- | --- |
| `MAX_SPEED_MPS` | `600.0` |
| `MAX_ACCEL_MPS2` | `450.0` |
| `ALT_DERIV_FIRST_FTPS` | `201` |
| `ALT_DERIV_SECOND_FTPS2` | `51` |
| `VOTE_THRESHOLD` | `2` |
| `ENABLE_SPATIAL_PCA` | `1` |
| `PCA_MIN_POINTS` | `40` |
| `PCA_MAD_SCALE` | `6.0` |
| `PCA_WINDOW_SIZE` | `256` |
| `ENABLE_SKIPNAN_POST_PCA` | `1` |
| `POST_PCA_SKIPNAN_MAX_ITER` | `30` |
| `REQ_COLS` | `latitude longitude altitude groundspeed track vertical_rate` |
| `MAX_DT` | `1200` 秒 |
| `GAP_HANDLING` | `drop` |
| `MIN_POINTS` | `300` |
| `MIN_DURATION` | `600` 秒 |
| `MAX_HOLE_SIZE` | `1200` 秒 |
| `SMOOTH` | `1e-2` |

---

## 4. 这条流程依赖哪些数据集

这条 pipeline 主要依赖 4 类数据资产：

1. 原始日度轨迹 `rawtrajectories/*.parquet`
2. 航班元数据 `flights/challenge_set.parquet`
3. 机场表 `airports_tz.parquet`
4. 最终输出目录 `interpolated_clean_eu_v5/`

另外仓库里还有 `weather/`、`thunder/`、`METARs.parquet` 等目录，但 **这条 staged pipeline 本身并不直接读取这些目录**。它用到的天气字段已经内嵌在原始轨迹 parquet 列里。

### 4.1 原始轨迹数据 `rawtrajectories`

当前工作区里：

- 文件数：`365`
- 日期范围：`2022-01-01` 到 `2022-12-31`
- 总行数：`6,390,198,052`
- 体积：约 `286G`（`306,373,396,928` bytes）

当前配置默认只处理 `2022-01-01 ~ 2022-02-28`，对应：

- 文件数：`59`
- 总行数：`689,634,097`
- 体积：约 `30.94 GiB`

命名规则：

- 每天一个文件，例如 `2022-01-01.parquet`
- 是按 **UTC 自然日** 切分，不是按完整航班切分
- 同一个 `flight_id` 可以跨午夜，出现在相邻两天文件里

当前 parquet schema 快照：

| 列名 | 类型 | 单位 / 语义 |
| --- | --- | --- |
| `flight_id` | `int64` | 原始航班 ID |
| `timestamp` | `timestamp[ns, UTC]` | UTC 时间戳 |
| `latitude` | `double` | 纬度，度 |
| `longitude` | `double` | 经度，度 |
| `altitude` | `double` | 高度，ft |
| `groundspeed` | `double` | 地速，kt |
| `track` | `double` | 航迹角，度 |
| `vertical_rate` | `double` | 垂直速度，ft/min |
| `icao24` | `int64` | 挑战数据里的 ICAO24 混淆字段 |
| `u_component_of_wind` | `double` | 风东向分量，m/s |
| `v_component_of_wind` | `double` | 风北向分量，m/s |
| `temperature` | `double` | 温度，K |
| `specific_humidity` | `double` | 比湿，kg/kg |

### 4.2 航班元数据 `flights/challenge_set.parquet`

这张表是整条流程最重要的元数据来源：

- 行数：`369,013`
- 覆盖天数：`365`
- 日期范围：`2022-01-01` 到 `2022-12-31`
- `adep` 去重数：`460`
- `ades` 去重数：`367`
- `aircraft_type` 去重数：`30`

主要列：

- `flight_id`
- `date`
- `callsign`
- `adep` / `ades`
- `name_adep` / `name_ades`
- `country_code_adep` / `country_code_ades`
- `actual_offblock_time`
- `arrival_time`
- `aircraft_type`
- `wtc`
- `airline`
- `flight_duration`
- `taxiout_time`
- `flown_distance`
- `tow`

语义上：

- `challenge_set` 是带标签训练集，`tow` 有值
- `submission_set.csv` 是排行榜提交集，`tow` 为空
- `final_submission_set.csv` 是最终榜阶段附加的隐藏测试集

当前工作区里相关文件状态：

- `challenge_set.parquet`：存在
- `final_submission_set.parquet`：存在，`158,149` 行
- `submission_set.csv`：存在，`105,959` 行
- `submission_set.parquet`：**当前不存在**

这意味着：

- 按默认配置，脚本只读 `challenge_set.parquet`，不会受影响
- 如果你把 `META_INCLUDE_SUBMISSION=1` 打开，当前仓库会因为缺少 `submission_set.parquet` 而报错，除非先把 CSV 转成 parquet

### 4.3 机场表 `airports_tz.parquet`

这张表给阶段 1 和阶段 2 提供机场坐标和 continent 信息。

当前工作区里：

- 行数：`502`
- `icao_code` 去重数：`502`
- `iata_code` 去重数：`497`
- `time_zone` 去重数：`130`
- `continent='EU'` 的机场数：`297`

主要列：

- `icao_code`
- `iata_code`
- `latitude_deg`
- `longitude_deg`
- `continent`
- `time_zone`

这张表在流程里有两种用途：

1. 阶段 1：当 `META_EUROPE_ONLY=1` 时，用 `continent=EU` 定义“欧洲机场集合”
2. 阶段 2：机场邻近过滤时，根据 `adep/ades` 找机场坐标并计算起点/终点到机场的球面距离

### 4.4 当前最终输出 `interpolated_clean_eu_v5`

当前工作区里已经存在一份 Jan-Feb 成品：

- 文件数：`59`
- 日期范围：`2022-01-01` 到 `2022-02-28`
- 总行数：`106,339,053`
- 体积：约 `14.24 GiB`

当前 schema 快照：

基础轨迹列保留了 `raw` 中的大部分字段，同时新增了：

- `original_flight_id`
- `segment_index`
- `flight_seg_info`
- `gsx`
- `gsy`
- `tasx`
- `tasy`
- `tas`
- `wind`
- `daltitude`

其中：

- `flight_id` 已经不再是原始航班 ID，而是 segment ID
- `original_flight_id` 才是切分前航班 ID

---

## 5. 当前默认元数据筛选到底保留多少航班

这件事对理解阶段 1 很关键，因为 `rawtrajectories` 里并不只有比赛目标航班。

按当前 `config.sh` 默认值：

- `META_EUROPE_ONLY=1`
- `META_TOP_AIRPORTS=64`
- `META_TOP_AIRCRAFT=25`
- 元数据源只用 `challenge_set.parquet`

实际筛选结果是：

### 全年 challenge_set

- 输入：`369,013` 架次
- 欧洲起降过滤后：`292,837`
- 再叠加 Top-64 机场 + Top-25 机型后：`245,218`

### 默认处理窗口 Jan-Feb

- 输入：`38,569` 架次
- 欧洲起降过滤后：`29,768`
- 再叠加 Top-64 机场 + Top-25 机型后：`26,111`

也就是说，**当前 staged pipeline 默认不是“跑全年所有 raw 航班”，而是“先根据 challenge_set 元数据生成白名单，再去 raw 里挑这些航班对应的轨迹点”**。

---

## 6. 入口参数详解

`run_staged_pipeline.sh` 支持的参数如下。

| 参数 | 含义 | 当前默认值 / 真实行为 |
| --- | --- | --- |
| `--raw-dir DIR` | 原始数据目录 | `RAW_DIR` |
| `--from DATE` | 起始日期 | `DATE_FROM=2022-01-01` |
| `--to DATE` | 结束日期 | `DATE_TO=2022-02-28` |
| `--procs N` | 并发数 | 默认取 `FILTER_PROCS=8`，然后同一个值透传给 01/02/03/04 |
| `--smooth VAL` | 插值平滑系数 | `SMOOTH=1e-2` |
| `--max-hole-size N` | 最大补洞长度 | `MAX_HOLE_SIZE=1200` |
| `--skip-filter` | 跳过阶段 1 | 默认不跳过 |
| `--skip-split` | 跳过阶段 2 | 默认不跳过 |
| `--skip-interp` | 跳过阶段 3 | 默认不跳过 |
| `--skip-quality` | 跳过阶段 4 | 默认不跳过 |
| `--skip-stats` | 跳过阶段 5 | 默认不跳过 |
| `--force` | 覆盖已有文件 | 见“源码注意事项”，当前实现里实际上默认就是覆盖 |
| `--dry-run` | 只打印命令 | 不执行子脚本 |
| `--limit N` | 只处理排序后的前 N 个文件 | 调试用 |
| `-h`, `--help` | 打印帮助 | 只显示帮助 |

推荐用法：

```bash
# 跑默认 Jan-Feb
bash pipelines/clean_segment/run_staged_pipeline.sh

# 只跑单日
bash pipelines/clean_segment/run_staged_pipeline.sh --from 2022-01-01 --to 2022-01-01

# 从切分阶段继续
bash pipelines/clean_segment/run_staged_pipeline.sh --skip-filter

# 只看会执行什么
bash pipelines/clean_segment/run_staged_pipeline.sh --dry-run --limit 2
```

---

## 7. 阶段 0：预检查和日志目录

正式开始前，入口脚本会：

1. `source config.sh`
2. 打印当前的原始数据目录、日期范围、平滑参数、机场邻近过滤开关
3. 对 `FILTERED_DIR`、`SEGMENTED_DIR`、`INTERPOLATED_DIR` 调用 `ensure_logs_dir`

`ensure_logs_dir` 会确保每个输出目录都存在：

- 目录本身
- 目录下的 `.logs/`

这一步的作用是防止后面 `xargs -P` 并行跑子任务时，因为日志路径不存在而直接失败。

---

## 8. 阶段 1：过滤清洗

调用脚本：[`01_filter_clean.sh`](./01_filter_clean.sh)

核心 Python：[`filter_trajs.py`](./filter_trajs.py)

### 8.1 输入

- `RAW_DIR/2022-*.parquet`
- 元数据白名单来自 `challenge_set.parquet`
- 欧洲机场集合来自 `airports_tz.parquet`

### 8.2 文件级处理逻辑

对每个日文件：

1. 读 parquet
2. 把 `flight_id` 转成 `int64`
3. 如果启用元数据筛选，只保留白名单 `flight_id`
4. 按 `(flight_id, timestamp)` 去重
5. 按 `(flight_id, timestamp)` 排序
6. 对每个航班应用过滤器链

### 8.3 当前默认过滤器链

当前策略名：`clean_segment_interp`

过滤器顺序是：

```text
FilterCstLatLon
→ FilterCstPosition
→ FilterCstSpeed
→ FilterEdgeOutlier
→ FilterMaxSpeedSkipNaNWithVoting
→ MyFilterDerivative(只看 altitude)
→ FilterSpatialPCAOutlier(可选)
→ FilterMaxSpeedSkipNaN(post PCA，可选)
→ FilterIsolated
```

其中最关键的是：

- `FilterMaxSpeedSkipNaNWithVoting`
  - `max_speed_mps=600`
  - `max_accel_mps2=450`
  - `vote_threshold=2`
  - `max_iterations=10`
- 高度导数检测
  - 一阶阈值 `201 ft/s`
  - 二阶阈值 `51 ft/s²`
- PCA 空间异常检测
  - 最少有效点 `40`
  - `MAD scale=6.0`
  - 滑窗 `256`
- 后置 SkipNaN 复检
  - 最大迭代 `30`

### 8.4 过滤后的列行为

这个阶段 **不做插值**，也不删整条轨迹。它的主要动作是：

- 对可疑观测置 `NaN`
- 保留轨迹的时间结构
- 为下一阶段切分做准备

另外还会做联动屏蔽：

- 如果 `latitude` 是 `NaN`，则同步把 `u_component_of_wind`、`v_component_of_wind`、`temperature` 置 `NaN`
- 如果 `altitude` 是 `NaN`，也会同步屏蔽这三列

### 8.5 输出

- 路径：`FILTERED_DIR/<date>.parquet`
- 命名示例：`filtered_clean_eu_v5/2022-01-01.parquet`
- 日志：`FILTERED_DIR/.logs/<date>.log`

输出 schema 基本和 raw 相同，但数值列可能带 `NaN`。

---

## 9. 阶段 2：按时间切分

调用脚本：[`02_split_by_time.sh`](./02_split_by_time.sh)

核心 Python：[`split_single_day.py`](./split_single_day.py)

### 9.1 输入

- `FILTERED_DIR/2022-*.parquet`
- 可选机场表：`airports_tz.parquet`
- 可选航班表：`challenge_set.parquet`

### 9.2 先做什么

如果 `AIRPORT_PROXIMITY_ENABLE=1`，当前默认会先做一次机场邻近过滤：

- 先按 `flight_id` 去 `challenge_set.parquet` 找该航班的 `adep/ades`
- 再按 `adep/ades` 去 `airports_tz.parquet` 找机场坐标
- 对每个航班取：
  - 第一条有效经纬度点作为起点
  - 最后一条有效经纬度点作为终点
- 判断：
  - 起点到 `adep` 距离是否 `<= 10 km`
  - 终点到 `ades` 距离是否 `<= 10 km`

两个条件都满足才保留该航班。

这一步不是按“整条轨迹是否一直靠近机场”判断，而是只看 **起点/终点**。

### 9.3 切分规则

在默认配置下，切分逻辑是：

1. 先对 `REQ_COLS` 执行 `dropna`
   - 当前必需列是
     - `latitude`
     - `longitude`
     - `altitude`
     - `groundspeed`
     - `track`
     - `vertical_rate`
2. 对同一 `flight_id` 按时间排序
3. 计算相邻采样时间差 `dt`
4. 当前 `GAP_HANDLING=drop`
   - 只要存在 `dt > 1200s`，整条轨迹直接丢弃
5. 若切分后某段：
   - 点数 `< 300`
   - 或时长 `< 600s`
   - 则丢弃

### 9.4 切分后的 ID 规则

切分后会新增 3 列：

| 列 | 含义 |
| --- | --- |
| `original_flight_id` | 切分前的原始航班 ID |
| `segment_index` | segment 序号 |
| `flight_seg_info` | 人类可读的 segment 描述串 |

同时，`flight_id` 会被重写成：

```text
flight_id = original_flight_id * 10000 + segment_index
```

例如：

```text
original_flight_id = 248750643
segment_index = 1
flight_id = 2487506430001
```

### 9.5 输出

- 路径：`SEGMENTED_DIR/segmented_<date>.parquet`
- 日志：`SEGMENTED_DIR/.logs/<date>.log`

---

## 10. 阶段 3：插值和平滑

调用脚本：[`03_interpolate_segments.sh`](./03_interpolate_segments.sh)

核心 Python：

- [`interpolate_single_day.py`](./interpolate_single_day.py)
- [`interpolate.py`](./interpolate.py)
- [`tools/io/readers.py`](../../tools/io/readers.py)

### 10.1 输入

- `SEGMENTED_DIR/segmented_<date>.parquet`

### 10.2 每个 segment 的处理逻辑

对每个 segment：

1. 重建 1Hz 时间网格
2. 保留原始观测点，缺失秒补出空位
3. 对 `track` 先 `unwrap(period=360)`，避免 359°/0° 跳变影响平滑
4. 对各测量列用 `csaps` 做平滑样条
5. 只在洞长 `<= MAX_HOLE_SIZE` 时允许插值
6. 超过 `MAX_HOLE_SIZE` 的洞保持 `NaN`

不过因为阶段 2 已经要求 segment 内连续且足够长，正常成品应接近或达到 0 NaN。

### 10.3 当前默认插值参数

- `smooth = 1e-2`
- `max_hole_size = 1200`

### 10.4 插值阶段会额外生成哪些列

在切分后的基础上，还会派生：

| 列 | 含义 | 单位 |
| --- | --- | --- |
| `gsx`, `gsy` | 地速东/北向分量 | kt |
| `tasx`, `tasy` | 真空速东/北向分量 | kt |
| `tas` | 真空速大小 | kt |
| `wind` | 风速大小 | m/s |
| `daltitude` | 由平滑高度导数得到的爬升率 | ft/min |

### 10.5 输出

- 路径：`INTERPOLATED_DIR/interpolated_<date>.parquet`
- 日志：`INTERPOLATED_DIR/.logs/<date>.log`

---

## 11. 阶段 4：质量检查

调用脚本：[`04_quality_check.sh`](./04_quality_check.sh)

### 11.1 跳变检测

内部会调用：

- [`run_detect_jumps_all.sh`](./run_detect_jumps_all.sh)
- [`analysis/detect_perfect_jumps.py`](../../analysis/detect_perfect_jumps.py)

默认规则来自 `detect_perfect_jumps.py`：

- `Δt ≤ 120s 且 Δs ≥ 10km`
- `Δt ≤ 300s 且 Δs ≥ 50km`
- 或 `速度 ≥ 1500 km/h`

但 `04_quality_check.sh` 会把第三条速度阈值同步到 `MAX_SPEED_MPS * 3.6`。

因此在当前配置下，实际速度阈值是：

- `600 m/s × 3.6 = 2160 km/h`

输出目录：

- `REPORT_DIR/jump_detection/`

典型产物：

- `perfect_jumps_YYYY-MM-DD.csv`
- `perfect_jumps_summary_YYYY-MM-DD.csv`
- `jump_events_summary.csv`
- `jump_events_all.csv`
- `detect_perfect_jumps.log`

### 11.2 NaN 检测

内部调用：

- [`check_nan_values.py`](./check_nan_values.py)

当前默认检查列：

- `latitude`
- `longitude`
- `altitude`
- `groundspeed`
- `track`
- `vertical_rate`

输出：

- `REPORT_DIR/nan_check_report.txt`

只要任意被检查列仍有 NaN，脚本会报错退出。

### 11.3 基础统计

最后会生成：

- `REPORT_DIR/basic_statistics.txt`

统计包括：

- parquet 文件数
- 总点数
- `flight_id` 去重数
- 如果存在 `original_flight_id`，再统计原始航班数和平均每航班 segment 数

---

## 12. 阶段 5：raw vs filtered 点数与缺失率统计

调用脚本：[`run_raw_filtered_point_stats.sh`](./run_raw_filtered_point_stats.sh)

核心 Python：[`analysis/raw_filtered_point_stats.py`](../../analysis/raw_filtered_point_stats.py)

这个阶段会比较：

- `raw`
- `filtered`
- `segmented`
- `interpolated`

的：

- 文件数
- 总点数
- 文件体积
- `REQ_COLS` 的缺失数 / 缺失率
- 任意一列缺失的比例

输出文件：

- `REPORT_DIR/raw_vs_filtered_point_stats.csv`
- `REPORT_DIR/raw_vs_filtered_point_stats_summary.txt`

统计逻辑的几个关键点：

- 如果某列在某数据集中根本不存在，会按该列 **100% 缺失** 计入
- 如果 `filtered` 目录存在，会用它所覆盖的日期去对齐 `raw`
- 这个阶段本质是做“目录级 QA”，不是阶段 1/2/3 的一部分

---

## 13. 输入输出命名规则

### 输入

- `rawtrajectories/2022-01-01.parquet`

### 阶段 1 输出

- `filtered_clean_eu_v5/2022-01-01.parquet`

### 阶段 2 输出

- `segmented_clean_eu_v5/segmented_2022-01-01.parquet`

### 阶段 3 输出

- `interpolated_clean_eu_v5/interpolated_2022-01-01.parquet`

### 日志

- `filtered_clean_eu_v5/.logs/2022-01-01.log`
- `segmented_clean_eu_v5/.logs/2022-01-01.log`
- `interpolated_clean_eu_v5/.logs/2022-01-01.log`

### 报告

- `reports/quality_check_clean_eu_v5/...`

---

## 14. 从哪里续跑

这条脚本的一个核心价值就是可以按阶段续跑。

### 从切分开始

```bash
bash pipelines/clean_segment/run_staged_pipeline.sh --skip-filter
```

前提：

- `FILTERED_DIR` 里对应日期的 parquet 已经存在

### 从插值开始

```bash
bash pipelines/clean_segment/run_staged_pipeline.sh --skip-filter --skip-split
```

前提：

- `SEGMENTED_DIR` 里对应日期的 parquet 已经存在

### 只做质量检查和统计

```bash
bash pipelines/clean_segment/run_staged_pipeline.sh \
  --skip-filter --skip-split --skip-interp
```

前提：

- `INTERPOLATED_DIR` 里对应日期的 parquet 已经存在

---

## 15. 源码里需要特别注意的实现细节

这一节不是概念说明，而是“脚本真实行为”和表面文案不完全一致的地方。

### 15.1 `--force` 当前实现里实际上默认就是开启的

`run_staged_pipeline.sh` 里：

```bash
FORCE=1
```

因此即使你不传 `--force`，父脚本也会把 `--force` 继续透传给 01/02/03 阶段。也就是说：

- 当前实现默认会覆盖已存在输出
- `--force` 选项目前更像“冗余声明”，不是“从关闭切到开启”

### 15.2 `--procs` 的默认值来自 `FILTER_PROCS`

虽然 `config.sh` 同时有：

- `FILTER_PROCS`
- `SPLIT_PROCS`
- `INTERP_PROCS`
- `QUALITY_CHECK_PROCS`

但 `run_staged_pipeline.sh` 自己的默认并发值是：

```bash
PROCS="$FILTER_PROCS"
```

然后把同一个 `PROCS` 传给：

- `01_filter_clean.sh`
- `02_split_by_time.sh`
- `03_interpolate_segments.sh`
- `04_quality_check.sh`

也就是说，用入口脚本时，默认不会分别使用 `SPLIT_PROCS` 和 `INTERP_PROCS`。

### 15.3 帮助文本里的默认值不会展开

`usage()` 使用的是单引号 heredoc：

```bash
cat <<'EOF'
```

所以帮助里的：

- `$RAW_DIR`
- `$DATE_FROM`
- `$FILTER_PROCS`

会原样打印，不会替换成真实值。

### 15.4 脚本横幅里仍然写着旧的 `v1` 目录名

入口脚本打印的：

- `filtered_clean_v1`
- `segmented_clean_v1`
- `interpolated_clean_v1`
- `reports/quality_check_clean_v1`

只是旧文案遗留，**并不代表真实输出目录**。真实输出始终以 `config.sh` 为准，也就是当前的 `*_clean_eu_v5`。

### 15.5 阶段 5 的日期限制当前没有真正生效

入口脚本对点数统计阶段构造命令时写的是：

```bash
STATS_CMD+=(FROM="$FROM" TO="$TO")
```

这会把 `FROM=...`、`TO=...` 当成普通位置参数传给 shell 脚本，而不是环境变量。

而 `run_raw_filtered_point_stats.sh` 本身并不解析这两个位置参数，它真正读取的是：

- `DATE_FROM_OVERRIDE`
- `DATE_TO_OVERRIDE`

因此当前实现下：

- 阶段 5 会运行
- 但不会按 `--from/--to` 真正限制统计日期

如果你要单独精确限制统计日期，应该直接这样调：

```bash
DATE_FROM_OVERRIDE=2022-01-01 \
DATE_TO_OVERRIDE=2022-01-07 \
bash pipelines/clean_segment/run_raw_filtered_point_stats.sh
```

### 15.6 `META_INCLUDE_SUBMISSION=1` 目前会撞到文件缺失

当前工作区：

- 有 `submission_set.csv`
- 没有 `submission_set.parquet`

而元数据筛选代码只认 parquet。

所以如果你开启：

```bash
META_INCLUDE_SUBMISSION=1
```

在当前仓库状态下会直接失败，除非先把 CSV 转成 parquet。

---

## 16. 一句话总结这条流程的边界

这条 staged pipeline 不是“单纯把 raw 轨迹洗干净”那么简单，它的真实行为是：

1. 用 `challenge_set + airports_tz` 先把目标航班集合收窄
2. 在日度 raw parquet 中对这些航班做强过滤
3. 只保留关键列连续、起降点靠近机场、时长足够长的 segment
4. 对 segment 重建 1Hz 轨迹并补出派生运动量
5. 最后再用跳变检测、NaN 检查和点数统计给结果做验收

如果你把它理解成“一个带中间产物的、面向 PRC 挑战赛航班子集的 clean-segment-interpolate 生产脚本”，就是准确的。
