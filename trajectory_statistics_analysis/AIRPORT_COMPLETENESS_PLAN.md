# 机场邻近度 + 高度模式 轨迹完整性判定方案（Phase A + Phase B）

本文档定义了在本项目中，基于“高度优先判定 + 机场邻近度验证”的完整性分析方案，并给出两阶段（A→B）的机场库构建方法、输入输出标准、并行策略、质量控制与自检规范。该方案用于修正“所有起降机场都是 URC”与“平均距离数千公里”等异常问题，支持对 `perfect_trajectories` 全量数据进行可重复、可扩展、可校验的分析。

## 目标与达成标准
- 覆盖数据源：对 `perfect_trajectories` 全量 366 个日分 parquet 文件（以及可选 `opensky_2024_PRC_dataset/rawtrajectories`）进行处理。
- 判定逻辑：
  - 高度优先：仅当检测到“起飞”或“降落”模式时，才执行相应端点的机场邻近度计算；无起降迹象则不做最近机场匹配（标注“未触发机场匹配”）。
  - 源优先级：若能从官方航班映射到 `(adep, ades)` 且能解析到坐标，则用“起点→adep、终点→ades”；否则回退到“最近机场”。
- 机场库构建：先用 Phase A（官方航班驱动）筛选“使用过机场”集合，再用 Phase B（轨迹驱动）增量补全，得到精简且命中高的机场库，提高效率与准确性。
- 输出统一：生成标准化的 parquet 与报告到 `trajectory_statistics_analysis/airport_completeness_analysis/`，供 `generate_comprehensive_report.py` 直接消费。
- 质量控制：分布自检、覆盖率统计、异常告警（例如平均距离异常大、Top1 机场占比异常、域错配等）。

## 规范与环境
- 必须在 Conda 环境运行：`conda activate opensky`
- 容器环境：Ubuntu 18.04（已满足）
- 服务器资源：80 核 CPU / 512GB 内存 / 8×V100(32GB)。本方案采用多进程 CPU 并行（无需 GPU）。
- 代码放置：仅在 `trajectory_statistics_analysis/` 或其子目录创建和修改 Python；测试脚本放 `test_python/`；不要在项目根目录新增 `.py` 文件。
- 多进程：所有数据处理脚本必须考虑并行（进程池/Executor），文件粒度并发，避免单进程长时间运行。

## 输入数据与字段说明
- 轨迹数据（二选一或都支持）：
  - `perfect_trajectories/*.parquet`（默认优先）
  - `opensky_2024_PRC_dataset/rawtrajectories/*.parquet`（可选）
  - 期望列：`flight_id`, `timestamp`, `latitude`, `longitude`, `altitude`（必要），其余可选。
  - 单位：`altitude` 通常为英尺（feet）；若检测为米（meters），需进行单位换算或阈值调整。
- 官方航班数据（可作为辅助映射）：
  - `opensky_2024_PRC_dataset/flights/challenge_set.csv`
  - `opensky_2024_PRC_dataset/flights/submission_set.csv`
  - `opensky_2024_PRC_dataset/flights/final_submission_set.csv`
  - 字段：`flight_id`, `adep`, `ades`, `actual_offblock_time`, `arrival_time` 等（部分可空）。
  - 注意：这三份 CSV 通常不覆盖所有轨迹，仅为子集；必须统计覆盖率，不能假定全量。
- 机场数据：
  - 原始全量 CSV：`ourairports2024-10-21.csv`（字段多、体量大，不直接用于全量匹配）
  - 精简机场 parquet（产物）：仅保留“使用过的机场”+ 必要字段（详见 Phase A/B），例如：
    - `opensky_2024_PRC_dataset/airports_used_phaseA.parquet`
    - `opensky_2024_PRC_dataset/airports_used_final.parquet`
  - 字段核心：`icao_code`（统一 ICAO）、`iata_code`、`latitude_deg`、`longitude_deg`、`type`（过滤 large/medium/small）。

## 关键概念与匹配规则（IATA/ICAO）
- `adep`（Airport of DEParture）/`ades`（Airport of DEStination）：起降机场代码，可能是 IATA（三字码，如 `PEK`）或 ICAO（四字码，如 `ZBAA`）。
- OurAirports 字段：
  - `iata_code`：IATA 三字码；
  - `gps_code`：常为 ICAO 四字码（若无 ICAO，可能为空）；
  - `ident`：原始标识符（大机场多等于 ICAO，小机场可能是本地码）；
  - 本项目建议统一出 `icao_code`（优先 `ident` 在用机场集合里时取 `ident`，否则取 `gps_code`）。
- 匹配顺序：
  - 若代码长度为 3（大写去空格后）→ 以 `iata_code` 优先匹配；
  - 若长度为 4 → 以 `icao_code`（或 `gps_code`）匹配；
  - 两者均匹配不到 → 用“最近机场”回退（仅对通过高度检测的端点），并标注回退来源。
- 禁止使用任何“默认机场代码”（如 `URC`）作为回填；一律采用明确匹配或最近回退。

## Phase A：基于官方航班的“使用过机场”筛选
**目标**：用 `flights/*.csv` 里出现的 `adep/ades` 作为“使用过机场”的初始集合，结合 OurAirports 生成精简机场 parquet。

- 步骤：
  1. 读取 `opensky_2024_PRC_dataset/flights/*.csv`（如无该目录，兼容 `opensky_2024_PRC_dataset/*.csv` 旧路径）
  2. 汇总 `flight_id → (adep, ades)`，统一代码：大写、去空格。
  3. 统计覆盖率：`轨迹 flight_id` 总数 vs `flights` 中的交集数量，输出覆盖率（用于后续策略判定）。
  4. 从 `ourairports2024-10-21.csv` 选取出现在 `(adep/ades)` 的机场，过滤 `type` ∈ {`large_airport`, `medium_airport`, `small_airport`}，排除 `heliport`/`seaplane_base`/`closed`。
  5. 生成 `icao_code`（统一 ICAO）：优先 `ident` 在使用集合中，否则取 `gps_code`；校验唯一性。
  6. 输出 `opensky_2024_PRC_dataset/airports_used_phaseA.parquet`。
- 说明与限制：
  - 若 `flights` 覆盖率偏低（如 <30–50%），此集合将明显不足，需要 Phase B 扩充。
  - 若 `(adep/ades)` 存在 IATA/ICAO 混用，生成时需双通道映射，并保留两种代码列。

## Phase B：基于轨迹的“使用过机场”增量补全
**目标**：通过“高度优先”的起终端点，在 OurAirports 全量库中做近邻搜索，发现 `flights` 未覆盖的实际使用机场，累积补全使用列表。

- 步骤：
  1. 抽样快速扫描（建议 3–5% 文件量，或每日日志若干文件）：
     - 逐 `flight_id` 计算高度特征（见后文“高度判定算法”）；仅对检测到“起飞/降落”的端点，计算至 OurAirports 全量库的最近机场（初期半径阈值放宽至 ≤150 km），统计近邻命中。
  2. 将近邻命中频次排个序，取 Top N（建议 500–1000）机场加入“使用过机场”集合；与 Phase A 结果合并去重，输出 `opensky_2024_PRC_dataset/airports_used_final.parquet`。
  3. 在第二轮全量分析过程中，若仍遇端点附近“未知机场”，允许将满足阈值（如 ≤50–80 km）且被命中多次的机场“动态追加”到一个增量文件（例如 `airports_used_dynamic.parquet`），并在结束时与 `airports_used_final.parquet` 合并归档。
- 控制与保护：
  - 限制增量追加的速度与条件，避免误把噪声点纳入库；例如需要至少 X 次命中且处于固定翼机场类型。
  - 可选限定区域（如通过端点分布推测主要地域后，按 `iso_country/continent` 过滤）。

## 全量处理（第二轮）流程
- 输入：轨迹文件（优先 `perfect_trajectories`），机场库用 `airports_used_final.parquet`（如无则退回 `airports_used_phaseA.parquet`）。
- 并发：文件粒度多进程（建议 24–40 个进程），每进程独立读取 parquet，单进程内按 `flight_id` 循环处理。
- 每条轨迹处理：
  1. 排序：按 `timestamp` 升序；若缺失时间则跳过（或标注为“缺时序”）。
  2. 提取端点：`start(lat, lon, alt, time)` 与 `end(lat, lon, alt, time)`。
  3. 高度判定：
     - 起飞检测（起始窗口 N 点/分钟）：起点低高度 + 持续爬升模式；
     - 降落检测（末端窗口 N 点/分钟）：持续下降 + 终点低高度；
     - 单位核验：feet 与 meters 阈值区别处理（见下一节）。
  4. 匹配策略：
     - 若有 `flight_id → (adep, ades)` 且能在机场库解析到坐标：
       - 起点→adep 距离（仅当“起飞”检测成立时计入）；
       - 终点→ades 距离（仅当“降落”检测成立时计入）。
     - 否则回退：
       - 对通过高度判定的端点，使用“最近机场”匹配；
       - 记录回退来源标志位（如 `start_match_source=nearest`）。
  5. 完整性标签：
     - Complete：两端（触发侧）≤50 km 且高度证据明确，且全局时长/点数达标；
     - Likely_Complete：一端≤50 km 且高度证据强，或两端邻近但高度证据一般；
     - Partial：证据不充分（仅高度或仅邻近）；
     - Fragment：点数/时长过短、地理/高度跨度极小。
  6. 结果记录：写入统一 parquet 架构（见“输出数据结构”）。

## 高度判定算法（建议参数）
- 预处理：
  - 对 `altitude` 做必要的缺失剔除与中值滤波（可选，窗口 3–5 点），减少尖噪影响。
- 单位与阈值：
  - 若 `altitude` 为英尺（feet）：
    - 低高度阈值（地面附近）：建议 ≤1500–2500 ft；
    - 起飞爬升检测：在首段窗口（如 2–5 分钟或前 100–300 点）内，`Δaltitude` > 1500–3000 ft，且平均垂直速率 > 指定阈值；
    - 降落下降检测：末段窗口内同理，`Δaltitude` < -1500–3000 ft，且终点低高度。
  - 若为米（meters）：按 1 ft ≈ 0.3048 m 等效换算阈值。
- 时长/点数约束：
  - 起飞/降落检测仅在 `point_count ≥ Pmin` 与 `duration ≥ Tmin` 时有效（例如 Pmin=200，Tmin=10–15 分钟）。
- 失败与回退：
  - 若高度缺失、时序异常或数据过稀则不进行机场匹配（标注“未触发”）。

## 距离计算
- 使用 Haversine 公式，地球半径 `R=6371 km`，输入输出均用弧度/度的一致规范。
- 实现层面：优先采用 NumPy 矢量化；无需引入第三方地理库，减少依赖。

## 输出数据结构（parquet 架构建议）
每条记录对应一个 `flight_id`（一段轨迹）：
- 基本信息：
  - `flight_id: int64`
  - `file_name: string`（来源文件名）
  - `point_count: int32`
  - `duration_hours: float32`
  - `start_time: timestamp[ns]` / `end_time: timestamp[ns]`
- 端点与高度：
  - `start_lat: float32`, `start_lon: float32`, `start_altitude: float32`
  - `end_lat: float32`, `end_lon: float32`, `end_altitude: float32`
  - `takeoff_detected: bool`, `landing_detected: bool`
- 官方映射（可能为空）：
  - `adep_official: string`，`ades_official: string`
- 实际使用的机场（官方/最近 二选一）：
  - `adep_used: string`，`ades_used: string`（若最近匹配生效则为最近机场代码）
  - `start_match_source: string`（`official`/`nearest`/`skipped`）
  - `end_match_source: string`（`official`/`nearest`/`skipped`）
- 邻近度：
  - `start_distance_km: float32`（仅当 takeoff_detected 且匹配成功）
  - `end_distance_km: float32`（仅当 landing_detected 且匹配成功）
- 完整性：
  - `completeness_label: string`（`Complete`/`Likely_Complete`/`Partial`/`Fragment`）
  - `quality_flags: string`（半结构化标志，例：`ALT_OK;OFFICIAL_OK;NEAREST_FALLBACK;`）

## 输出目录与文件
- 标准产物目录：`trajectory_statistics_analysis/airport_completeness_analysis`
  - 数据：`airport_completeness_analysis.parquet`
  - 文本报告：`airport_completeness_report.txt`
  - 图表：`airport_completeness_analysis.png`（分布/Top 机场/≤50km 占比等）
- 精简机场库产物：
  - `opensky_2024_PRC_dataset/airports_used_phaseA.parquet`
  - `opensky_2024_PRC_dataset/airports_used_final.parquet`
  - 动态增量（可选）：`opensky_2024_PRC_dataset/airports_used_dynamic.parquet`

## 质量控制与自检
- 覆盖率：
  - 官方映射覆盖率：`matchable_flight_ids / total_flight_ids`；
  - 高度检测覆盖率：`takeoff/landing 检出占比`。
- 邻近度指标：
  - 起点≤50 km、终点≤50 km、两端≤50 km 的占比；
  - `start_distance_km` 与 `end_distance_km` 的 P10/P50/P90/均值；
- 异常告警：
  - 平均距离 > 1000 km；
  - Top1 机场占比 > 30–40%；
  - 两端≤50 km 占比=0% 或 100%；
  - 单一机场（如 `URC`）异常占比；
- 随机抽样：
  - 抽取若干轨迹绘制端点与匹配机场散点图，人工定性核验；
  - 输出样例列表到 `airport_completeness_analysis/spotcheck_samples.txt`。

## 并行与性能
- 进程数：建议 24–40（80 核服务器留出内存/IO 余量）。
- I/O：按文件并行，单进程一次处理一个文件；避免把所有文件读入内存。
- 机场库加载：在每个进程初始化时加载一次“使用过机场”parquet 到内存结构（向量/数组即可）。
- 写出：结果分批缓冲写 parquet（或写到临时分区后合并）。

## 配置参数（建议）
- 输入路径：
  - `--trajectory-dir`：`perfect_trajectories`（默认）或 `opensky_2024_PRC_dataset/rawtrajectories`
  - `--flights-dir`：`opensky_2024_PRC_dataset/flights`
  - `--airports-csv`：`ourairports2024-10-21.csv`
- 并行：`--max-workers`（默认自动=min(文件数, 24)）
- 阈值：
  - `--distance-threshold-km`（默认 50）
  - `--coarse-nearest-threshold-km`（Phase B 抽样 150）
  - `--altitude-low-threshold-ft`（默认 2000 ft；按单位切换）
  - `--min-points`、`--min-duration-minutes`（默认 200 点 / 15 分钟）
- 机场类型过滤：`--airport-types=large,medium,small`
- 区域过滤（可选）：`--iso-country` 或 `--continent`

## 运行步骤（一览）
1. 统计与侦测：
   - 统计 `perfect_trajectories` 文件与 `flight_id` 数量；
   - 用 `match_official_flight_data.py` 或等效逻辑，计算 `flights/*.csv` 与轨迹的 `flight_id` 覆盖率；
2. Phase A：生成 `airports_used_phaseA.parquet`；
3. Phase B（抽样）：
   - 抽样扫描轨迹，基于高度检测的端点在 OurAirports 全量库中做近邻统计；
   - 合并到 `airports_used_final.parquet`；
4. 第二轮全量处理：
   - 使用 `airports_used_final.parquet`，对全量轨迹进行“高度优先 + 官方/最近 匹配”，生成 `airport_completeness_analysis.parquet`；
   - 生成 `airport_completeness_report.txt` 与图表；
5. 质量自检与告警处理：
   - 距离分布/Top 机场/占比/覆盖率；
   - 若异常，回溯“单位/区域/阈值/机场库”设置并修正；
6. 生成综合报告：
   - 运行 `generate_comprehensive_report.py`，验证机场模块统计已纠偏；
7. 归档：
   - 若运行中有 `airports_used_dynamic.parquet`，合并入 final 并保留日志。

## 风险与应对
- 官方 CSV 域不匹配/覆盖不足：
  - 以 Phase B + 最近机场回退为主线，官方映射作为可选增强；
- 单位错配（feet vs meters）：
  - 在处理前做单位探测（如通过分位数/典型高度判断），按单位调整阈值；
- 域错配（例如机场库是中国/PRC，但轨迹在欧洲）：
  - 通过 Phase B 的端点近邻统计，自适应发现主要区域的“使用过机场”，避免错误域导致的几千公里距离；
- 噪声/外点：
  - 使用最小时长/点数门槛、窗口平滑、命中次数阈值（Phase B 动态追加）来抑制噪声；
- 内存与 I/O 压力：
  - 文件粒度并行、分批写出、避免全量拼接。

## 与现有代码对接
- `trajectory_statistics_analysis/optimized_airport_analysis.py`
  - 将轨迹根目录优先指向 `perfect_trajectories`；
  - 读取 `opensky_2024_PRC_dataset/flights/*.csv`（新路径）构建官方映射；
  - 机场库优先使用 `airports_used_final.parquet`，无则退回 `airports_used_phaseA.parquet`；
  - 输出统一写入 `trajectory_statistics_analysis/airport_completeness_analysis/`（parquet/报告/图表）。
- `trajectory_statistics_analysis/generate_comprehensive_report.py`
  - 保持读取 `airport_completeness_analysis/airport_completeness_analysis.parquet`；
  - 新增字段（如 `*_match_source`, `quality_flags`）不影响现有统计，必要时可在报告中追加细分。
- `trajectory_statistics_analysis/match_official_flight_data.py`
  - 用于覆盖率与时长一致性报告，作为“官方映射可信度”的辅助参考。

## 时间与资源估算（经验值）
- Phase A：秒级到分钟级（取决于 CSV 大小）；
- Phase B 抽样：数分钟到十余分钟（抽样比例与近邻实现有关）；
- 全量处理：
  - 366 个日分 parquet，按 24–40 进程并发与单文件大小估算，典型在数十分钟到数小时区间（与 I/O、每条轨迹点数有关）。

## 附录：机场类型过滤建议
- 保留：`large_airport`, `medium_airport`, `small_airport`
- 排除：`heliport`, `seaplane_base`, `closed`（直升机场/水上机场/关闭机场对定翼航班的起降判定干扰较大）

---
如需我将本方案落地为代码（含 Phase A→B 工具、全量跑批、报告与图表统一输出），请确认，我会在不违反项目规则的前提下，把实现放在 `trajectory_statistics_analysis/`，并提供最小化配置与运行命令。

