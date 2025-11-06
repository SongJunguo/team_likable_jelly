#!/usr/bin/env bash
set -euo pipefail

# 串行执行：
# 1) 从 doublepass 过滤输出生成 complete（仅内部洞 + 20s 限洞）
# 2) 将 complete 切成“无缺失连续片段”的 segmented
#
# 约定：
# - 运行前请进入 conda 环境：conda activate opensky
# - 默认并发 8（HDD 建议 6–8），可用 --procs 覆盖
# - 可用 --from/--to 选择日期范围；--force 覆盖已存在；--dry-run 仅打印命令

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_REGEN="$SCRIPT_DIR/regenerate_complete_all.sh"
RUN_SPLIT="$SCRIPT_DIR/split_segments_all.sh"

# 默认目录（可通过命令行覆盖）
FILTER_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories__doublepass_v1"
COMPLETE_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/interpolate_trajs_doublepass_lim20s_inside_v1"
SEGMENTED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/segmented_trajs_doublepass_lim20s_inside_v1"
IDS_FILE="/workspace/aircraft_trajectory/team_likable_jelly/high_quality_flight_ids.txt"
PROCS=8
DATE_FROM="2022-01-01"
DATE_TO="2022-12-31"
FORCE=0
DRYRUN=0

# 切段参数（与现有 split 脚本保持一致）
REQ_COLS="latitude longitude altitude"
MAX_DT=20
MIN_POINTS=30
MIN_DURATION=120

usage() {
  sed -n '1,120p' "$0" | sed -n '1,60p'
  cat <<EOF

用法示例：
  bash $0 \\
    --filter-dir    /.../classic_filtered_trajectories__doublepass_v1 \\
    --complete-dir  /.../trajs_doublepass_lim20s_inside_v1 \\
    --segmented-dir /.../segmented_trajs_doublepass_lim20s_inside_v1 \\
    --procs 8 --from 2022-01-01 --to 2022-12-31

可选参数：
  --ids-file PATH         高质量航班 ID 列表（传给 regenerate）
  --force                 覆盖已存在输出
  --dry-run               仅打印将要执行的命令
  --required-cols ...     切段必需列（空格分隔，默认：$REQ_COLS）
  --max-dt INT            切段最大允许间隔秒（默认：$MAX_DT）
  --min-points INT        分段最少点数（默认：$MIN_POINTS）
  --min-duration INT      分段最少时长秒（默认：$MIN_DURATION）
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --filter-dir)    FILTER_DIR="$2"; shift 2;;
    --complete-dir)  COMPLETE_DIR="$2"; shift 2;;
    --segmented-dir) SEGMENTED_DIR="$2"; shift 2;;
    --ids-file)      IDS_FILE="$2"; shift 2;;
    --procs)         PROCS="$2"; shift 2;;
    --from)          DATE_FROM="$2"; shift 2;;
    --to)            DATE_TO="$2"; shift 2;;
    --required-cols) shift; REQ_COLS=""; while [[ $# -gt 0 && "$1" != --* ]]; do REQ_COLS+="${REQ_COLS:+ }$1"; shift; done;;
    --max-dt)        MAX_DT="$2"; shift 2;;
    --min-points)    MIN_POINTS="$2"; shift 2;;
    --min-duration)  MIN_DURATION="$2"; shift 2;;
    --force)         FORCE=1; shift;;
    --dry-run)       DRYRUN=1; shift;;
    -h|--help)       usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$RUN_REGEN" ]] || { echo "❌ 找不到脚本文件: $RUN_REGEN"; exit 1; }
[[ -f "$RUN_SPLIT" ]] || { echo "❌ 找不到脚本文件: $RUN_SPLIT"; exit 1; }

echo "[1/2] 插补 complete（inside + 20s）"
CMD1=("bash" "$RUN_REGEN" --input-dir "$FILTER_DIR" --output-dir "$COMPLETE_DIR" --ids-file "$IDS_FILE" --procs "$PROCS" --from "$DATE_FROM" --to "$DATE_TO")
[[ "$FORCE" == "1" ]] && CMD1+=(--force)

if [[ "$DRYRUN" == "1" ]]; then
  echo "DRYRUN:" "${CMD1[@]}"
else
  "${CMD1[@]}"
fi

echo "[2/2] 切段 segmented（0 NaN 连续片段）"
CMD2=("bash" "$RUN_SPLIT" --input-dir "$COMPLETE_DIR" --output-dir "$SEGMENTED_DIR" --procs "$PROCS" --required-cols $REQ_COLS --max-dt "$MAX_DT" --min-points "$MIN_POINTS" --min-duration "$MIN_DURATION" --from "$DATE_FROM" --to "$DATE_TO")
[[ "$FORCE" == "1" ]] && CMD2+=(--force)

if [[ "$DRYRUN" == "1" ]]; then
  echo "DRYRUN:" "${CMD2[@]}"
else
  "${CMD2[@]}"
fi

echo "✅ 完成。complete 输出: $COMPLETE_DIR"
echo "✅ 完成。segmented 输出: $SEGMENTED_DIR"
