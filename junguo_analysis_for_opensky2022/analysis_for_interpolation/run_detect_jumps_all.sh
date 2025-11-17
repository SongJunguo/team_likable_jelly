#!/usr/bin/env bash
set -euo pipefail

# 一键并行运行跳变检测（analysis/detect_perfect_jumps.py）
# 默认输入：双过滤 + 限洞 + 分段后的轨迹目录

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY_DETECT="$REPO_ROOT/analysis/detect_perfect_jumps.py"

# DATA_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/segmented_trajs_doublepass_loop_lim20s_inside_v7_test1hz"
DATA_DIR="/tmp"
OUT_DIR="/workspace/aircraft_trajectory/team_likable_jelly/reports/test_interpolated_2022-01-01"
PROCS=41
DATE_FROM="2022-01-01"
DATE_TO="2022-12-31"
FORCE=0
DRYRUN=0
LIMIT=0
VERBOSE=0
LOG_FILE=""
MIN_SPEED=""

usage() {
  cat <<EOF
用法: bash $(basename "$0") [选项]
  --data-dir PATH      输入 segmented 目录（默认: $DATA_DIR）
  --out-dir PATH       输出目录（默认: $OUT_DIR）
  --procs N            并行进程数（默认: $PROCS）
  --from YYYY-MM-DD    起始日期（默认: $DATE_FROM）
  --to   YYYY-MM-DD    截止日期（默认: $DATE_TO）
  --limit N            仅处理前 N 个文件（调试用，默认0=全部）
  --min-speed KMH      速度阈值（km/h），覆盖 detect_perfect_jumps.py 的默认 1500
  --force              已存在输出也重算
  --verbose            输出更详细日志
  --log-file PATH      重定向日志文件（默认写到 out-dir/detect_perfect_jumps.log）
  --dry-run            仅打印命令
  -h|--help            查看帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir) DATA_DIR="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --limit) LIMIT="$2"; shift 2;;
    --min-speed) MIN_SPEED="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --verbose) VERBOSE=1; shift;;
    --log-file) LOG_FILE="$2"; shift 2;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$PY_DETECT" ]] || { echo "❌ 找不到 Python 脚本: $PY_DETECT"; exit 1; }
mkdir -p "$OUT_DIR"

CMD=("python" "$PY_DETECT" --data-dir "$DATA_DIR" --out-dir "$OUT_DIR" --procs "$PROCS")
[[ -n "$DATE_FROM" ]] && CMD+=(--from "$DATE_FROM")
[[ -n "$DATE_TO" ]] && CMD+=(--to "$DATE_TO")
[[ "$LIMIT" != "0" ]] && CMD+=(--limit "$LIMIT")
[[ "$FORCE" == "1" ]] && CMD+=(--force)
[[ "$VERBOSE" == "1" ]] && CMD+=(--verbose)
[[ -n "$LOG_FILE" ]] && CMD+=(--log-file "$LOG_FILE")
[[ -n "$MIN_SPEED" ]] && CMD+=(--min-speed "$MIN_SPEED")

if [[ "$DRYRUN" == "1" ]]; then
  echo "DRYRUN:" "${CMD[@]}"
else
  "${CMD[@]}"
fi

echo "✅ 跳变检测完成。输出目录: $OUT_DIR"
