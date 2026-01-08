#!/bin/bash
# 统一配置文件 - Clean-Segment-Interpolate 流程

# ========== 内部变量（不要修改） ==========
SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export SCRIPT_DIR="$SCRIPT_PATH"
export REPO_ROOT="$(cd "$SCRIPT_PATH/../.." && pwd)"

# ========== 目录配置 ==========
export RAW_DIR="${REPO_ROOT}/opensky_2024_PRC_dataset/rawtrajectories"

# 新流程输出目录（清晰命名）
export FILTERED_DIR="${REPO_ROOT}/opensky_2024_PRC_dataset/filtered_clean_eu_v4"
export SEGMENTED_DIR="${REPO_ROOT}/opensky_2024_PRC_dataset/segmented_clean_eu_v4"
export INTERPOLATED_DIR="${REPO_ROOT}/opensky_2024_PRC_dataset/interpolated_clean_eu_v4"
export REPORT_DIR="${REPO_ROOT}/reports/quality_check_clean_eu_v4"

# ========== 元数据筛选（可选，默认关闭） ==========
export META_EUROPE_ONLY=1
export META_TOP_AIRPORTS=64
export META_TOP_AIRCRAFT=25
export META_INCLUDE_SUBMISSION=0
export META_INCLUDE_FINAL=0
export META_FLIGHTS_PARQUET="${REPO_ROOT}/opensky_2024_PRC_dataset/flights/challenge_set.parquet"
export META_AIRPORTS_PARQUET="${REPO_ROOT}/opensky_2024_PRC_dataset/airports_tz.parquet"
export META_EUROPE_CONTINENT="EU"
export META_PROCS=4


# ========== 过滤参数 ==========
export FILTER_STRATEGY="clean_segment_interp"  # 新策略名
export MAX_SPEED_MPS=600.0        # 速度阈值（可调：550或600）单位 m/s
export MAX_ACCEL_MPS2=450.0      # 加速度阈值 （m/s²）
export ALT_DERIV_FIRST_FTPS=201   # 高度一阶导阈值（ft/s）
export ALT_DERIV_SECOND_FTPS2=51  # 高度二阶导阈值（ft/s²）
export VOTE_THRESHOLD=2            # 投票阈值（≥2票才删除）
export ENABLE_SPATIAL_PCA=1        # 1=启用 PCA 空间异常检测
export PCA_MIN_POINTS=40           # 至少多少有效点才运行PCA
export PCA_MAD_SCALE=6.0           # 阈值=median+scale*1.4826*MAD
export PCA_WINDOW_SIZE=256         # 滑动窗口大小（≤0禁用）
export PCA_STATS_CSV="$REPORT_DIR/pca_flags.csv"  # 统计输出
export ENABLE_SKIPNAN_POST_PCA=1    # 1=在PCA后再执行一次跨NaN速度检测
export POST_PCA_SKIPNAN_MAX_ITER=30  # 额外跨NaN速度检测最大迭代次数

# ========== 切分参数 ==========
export REQ_COLS="latitude longitude altitude groundspeed track vertical_rate"  # 切分时的“必需列”。只有这些列全都非 NaN的行才保留进入切分
export MAX_DT=1200                # 最大时间间隔（秒）
export GAP_HANDLING="drop"       # split=相邻时间间隔>MAX_DT就切段；drop=若存在>MAX_DT则丢弃整条轨迹（在dropna(REQ_COLS)之后判断）
export MIN_POINTS=300            # 每个 segment 的最小点数，不满足就丢弃
export MIN_DURATION=600         # 每个 segment 的最小时长（秒），不满足就丢弃
export MAX_HOLE_SIZE="$MAX_DT"   # 插值阶段允许跨越的最大缺口（秒），超过就保持 NaN（不插值） 最大插值间隔（默认跟MAX_DT一致，可单独调整）

# ========== 插值参数 ==========
export SMOOTH=1e-2              # csaps平滑系数
# 注意：segment内部通过切分控制Δt≤MAX_DT，插值阶段再按MAX_HOLE_SIZE限制缺口

# ========== 并发配置 ==========
export FILTER_PROCS=8
export SPLIT_PROCS=4
export INTERP_PROCS=4
export MAX_WORKERS=4 #用于检测raw和filter点数的差异
# ========== 日期范围 ==========
export DATE_FROM="2022-01-01"
export DATE_TO="2022-02-28"

# ========== 质量检测参数 ==========
export QUALITY_CHECK_PROCS=4

# ========== 质量检测开关 ==========
export ENABLE_JUMP_DETECTION=1   # 1=启用跳变检测, 0=禁用
export ENABLE_NAN_CHECK=1        # 1=启用NaN检测, 0=禁用

# ========== NaN检测配置 ==========
export NAN_CHECK_COLUMNS="latitude longitude altitude groundspeed track vertical_rate"  # 重点检查经纬高
export NAN_CHECK_PROCS=4        # NaN检测并行进程数

# ========== 点数统计选项（用于 run_raw_filtered_point_stats.sh） ==========
# 可根据需要关闭某些目录的统计。例如仅比较 raw vs filtered 时可将 ENABLE_SEGMENTED=0 ENABLE_INTERPOLATED=0。
export ENABLE_POINT_STATS=1
export ENABLE_RAW=1
export ENABLE_FILTERED=1
export ENABLE_SEGMENTED=1
export ENABLE_INTERPOLATED=1
