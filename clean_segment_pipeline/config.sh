#!/bin/bash
# 统一配置文件 - Clean-Segment-Interpolate 流程

# ========== 目录配置 ==========
export RAW_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories"

# 新流程输出目录（清晰命名）
export FILTERED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/filtered_clean_v1"
export SEGMENTED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/segmented_clean_v1"
export INTERPOLATED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/interpolated_clean_v1"
export REPORT_DIR="/workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1"

# ========== 过滤参数 ==========
export FILTER_STRATEGY="clean_segment_interp"  # 新策略名
export MAX_SPEED_MPS=700.0        # 速度阈值（可调：550或600）单位 m/s
export MAX_ACCEL_MPS2=55.0        # 加速度阈值
export ALT_DERIV_FIRST_FTPS=151  # 高度一阶导阈值（ft/s）
export ALT_DERIV_SECOND_FTPS2=51 # 高度二阶导阈值（ft/s²）
export VOTE_THRESHOLD=2         # 投票阈值（≥2票才删除）

# ========== 切分参数 ==========
export REQ_COLS="latitude longitude altitude"
export MAX_DT=20                # 最大时间间隔（秒）
export MIN_POINTS=30            # 最小点数
export MIN_DURATION=120         # 最小时长（秒）

# ========== 插值参数 ==========
export SMOOTH=1e-2              # csaps平滑系数
# 注意：segment内部已保证时间连续（≤20s），不需要MAX_HOLE_SIZE限制

# ========== 并发配置 ==========
export FILTER_PROCS=24
export SPLIT_PROCS=24
export INTERP_PROCS=24

# ========== 日期范围 ==========
export DATE_FROM="2022-01-01"
export DATE_TO="2022-01-24"

# ========== 质量检测参数 ==========
export QUALITY_CHECK_PROCS=24

# ========== 质量检测开关 ==========
export ENABLE_JUMP_DETECTION=1   # 1=启用跳变检测, 0=禁用
export ENABLE_NAN_CHECK=1        # 1=启用NaN检测, 0=禁用

# ========== NaN检测配置 ==========
export NAN_CHECK_COLUMNS="latitude longitude altitude"  # 重点检查经纬高
export NAN_CHECK_PROCS=24        # NaN检测并行进程数

# ========== 内部变量（不要修改） ==========
export REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
