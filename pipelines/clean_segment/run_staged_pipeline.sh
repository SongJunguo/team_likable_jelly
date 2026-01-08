#!/usr/bin/env bash
set -euo pipefail

# ========== 分阶段流程总控 ==========
# 功能：
# - 依次运行三个阶段：过滤 → 切分 → 插值
# - 每阶段存储中间结果
# - 便于调试和检查每阶段输出
#
# 优势：
# - 中间结果可检查
# - 失败后可从中断处继续
#
# 劣势：
# - I/O较多（机械硬盘慢）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

usage() {
  cat <<'EOF'
用法: bash run_staged_pipeline.sh [选项]

分阶段模式（Filter → Segment → Interpolate）：
  - 每阶段存储中间结果
  - 便于调试和检查
  - I/O较多（机械硬盘相对慢）

选项:
  --raw-dir DIR       原始数据目录（默认: $RAW_DIR）
  --from DATE         起始日期（默认: $DATE_FROM）
  --to DATE           截止日期（默认: $DATE_TO）
  --procs N           并发数（默认: $FILTER_PROCS）
  --smooth VAL        插值平滑系数（默认: $SMOOTH）
  --max-hole-size N   最大插值间隔（默认: $MAX_HOLE_SIZE）
  --skip-filter       跳过过滤阶段
  --skip-split        跳过切分阶段
  --skip-interp       跳过插值阶段
  --skip-quality      跳过质量检查
  --skip-stats        跳过 raw vs filtered 点数统计
  --force             覆盖已存在文件
  --dry-run           仅打印命令
  --limit N           仅处理前N个文件（测试用）
  -h|--help           显示帮助

示例:
  # 测试单日
  bash run_staged_pipeline.sh --from 2022-01-01 --to 2022-01-01

  # 全量运行
  bash run_staged_pipeline.sh

  # 从切分阶段开始（跳过过滤）
  bash run_staged_pipeline.sh --skip-filter
EOF
}

RAW="$RAW_DIR"
FROM="$DATE_FROM"
TO="$DATE_TO"
PROCS="$FILTER_PROCS"
SMOOTH_VAL="$SMOOTH"
MAX_HOLE_VAL="$MAX_HOLE_SIZE"
SKIP_FILTER=0
SKIP_SPLIT=0
SKIP_INTERP=0
SKIP_QUALITY=0
SKIP_STATS=0
FORCE=1
DRYRUN=0
LIMIT=0

ensure_logs_dir() {
  local dir="$1"
  [[ -z "$dir" ]] && return
  mkdir -p "$dir" "$dir/.logs"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw-dir) RAW="$2"; shift 2;;
    --from) FROM="$2"; shift 2;;
    --to) TO="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --smooth) SMOOTH_VAL="$2"; shift 2;;
    --max-hole-size) MAX_HOLE_VAL="$2"; shift 2;;
    --skip-filter) SKIP_FILTER=1; shift;;
    --skip-split) SKIP_SPLIT=1; shift;;
    --skip-interp) SKIP_INTERP=1; shift;;
    --skip-quality) SKIP_QUALITY=1; shift;;
    --skip-stats) SKIP_STATS=1; shift;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit) LIMIT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

echo "==========================================="
echo "  分阶段模式（Clean-Segment-Interp）"
echo "==========================================="
echo "原始数据: $RAW"
echo "日期范围: $FROM ~ $TO"
echo "并发数: $PROCS"
echo "平滑系数: $SMOOTH_VAL"
echo "最大插值间隔: $MAX_HOLE_VAL"
echo ""
echo "中间结果："
echo "  1. filtered_clean_v1/       (过滤后)"
echo "  2. segmented_clean_v1/      (切分后)"
echo "  3. interpolated_clean_v1/   (最终)"
echo ""

# 阶段输出目录预检查，避免日志目录缺失导致并行任务失败
ensure_logs_dir "$FILTERED_DIR"
ensure_logs_dir "$SEGMENTED_DIR"
ensure_logs_dir "$INTERPOLATED_DIR"

# ========== 阶段1：过滤 ==========
if [[ "$SKIP_FILTER" == "0" ]]; then
  echo "=========================================="
  echo "  [1/3] 阶段1：过滤清洗"
  echo "=========================================="
  echo ""

  CMD=(bash "$SCRIPT_DIR/01_filter_clean.sh" --raw-dir "$RAW" --procs "$PROCS")
  [[ -n "$FROM" ]] && CMD+=(--from "$FROM")
  [[ -n "$TO" ]] && CMD+=(--to "$TO")
  [[ "$FORCE" == "1" ]] && CMD+=(--force)
  [[ "$DRYRUN" == "1" ]] && CMD+=(--dry-run)
  [[ "$LIMIT" != "0" ]] && CMD+=(--limit "$LIMIT")

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${CMD[*]}"
  else
    "${CMD[@]}" || { echo "❌ 阶段1失败"; exit 1; }
  fi

  echo ""
else
  echo "↪︎ 跳过阶段1：过滤清洗"
  echo ""
fi

# ========== 阶段2：切分 ==========
if [[ "$SKIP_SPLIT" == "0" ]]; then
  echo "=========================================="
  echo "  [2/3] 阶段2：时间切分"
  echo "=========================================="
  echo ""

  CMD=(bash "$SCRIPT_DIR/02_split_by_time.sh" --procs "$PROCS")
  [[ -n "$FROM" ]] && CMD+=(--from "$FROM")
  [[ -n "$TO" ]] && CMD+=(--to "$TO")
  [[ "$FORCE" == "1" ]] && CMD+=(--force)
  [[ "$DRYRUN" == "1" ]] && CMD+=(--dry-run)
  [[ "$LIMIT" != "0" ]] && CMD+=(--limit "$LIMIT")

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${CMD[*]}"
  else
    "${CMD[@]}" || { echo "❌ 阶段2失败"; exit 1; }
  fi

  echo ""
else
  echo "↪︎ 跳过阶段2：时间切分"
  echo ""
fi

# ========== 阶段3：插值 ==========
if [[ "$SKIP_INTERP" == "0" ]]; then
  echo "=========================================="
  echo "  [3/3] 阶段3：插值"
  echo "=========================================="
  echo ""

  CMD=(bash "$SCRIPT_DIR/03_interpolate_segments.sh" --procs "$PROCS" --smooth "$SMOOTH_VAL" --max-hole-size "$MAX_HOLE_VAL")
  [[ -n "$FROM" ]] && CMD+=(--from "$FROM")
  [[ -n "$TO" ]] && CMD+=(--to "$TO")
  [[ "$FORCE" == "1" ]] && CMD+=(--force)
  [[ "$DRYRUN" == "1" ]] && CMD+=(--dry-run)
  [[ "$LIMIT" != "0" ]] && CMD+=(--limit "$LIMIT")

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${CMD[*]}"
  else
    "${CMD[@]}" || { echo "❌ 阶段3失败"; exit 1; }
  fi

  echo ""
else
  echo "↪︎ 跳过阶段3：插值"
  echo ""
fi

# ========== 阶段4：质量检查 ==========
if [[ "$SKIP_QUALITY" == "0" ]]; then
  echo "=========================================="
  echo "  [4/4] 阶段4：质量检查"
  echo "=========================================="
  echo ""

  CMD=(bash "$SCRIPT_DIR/04_quality_check.sh" --procs "$PROCS")
  [[ -n "$FROM" ]] && CMD+=(--from "$FROM")
  [[ -n "$TO" ]] && CMD+=(--to "$TO")

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${CMD[*]}"
  else
    "${CMD[@]}" || { echo "⚠️  质量检查发现问题"; exit 1; }
  fi

  echo ""
else
  echo "↪︎ 跳过阶段4：质量检查"
  echo ""
fi

# ========== 阶段5：raw vs filtered 点数与缺失率汇总 ==========
# 说明：
#   - 通过 run_raw_filtered_point_stats.sh 统计 filtered 覆盖日期的 raw 点数，
#     并对 filtered / segmented / interpolated 的点数占比与经纬高缺失率做对比。
#   - 生成 CSV + summary txt，方便写入质量报告。
if [[ "$SKIP_STATS" == "0" && "${ENABLE_POINT_STATS:-1}" == "1" ]]; then
  echo "=========================================="
  echo "  [5/5] raw vs filtered 点数对比"
  echo "=========================================="
  echo ""

  STATS_CMD=(bash "$SCRIPT_DIR/run_raw_filtered_point_stats.sh")

  # 按当前日期范围限制 raw/filtered 的统计范围
  STATS_CMD+=(FROM="$FROM" TO="$TO")

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${STATS_CMD[*]}"
  else
    "${STATS_CMD[@]}" || { echo "❌ 点数统计失败"; exit 1; }
  fi

  echo ""
else
  echo "↪︎ 跳过阶段5：raw vs filtered 点数统计"
  echo ""
fi

echo "==========================================="
echo "  ✅ 分阶段模式完成"
echo "==========================================="
echo ""
echo "中间结果："
echo "  - filtered_clean_v1/       (过滤后)"
echo "  - segmented_clean_v1/      (切分后)"
echo "  - interpolated_clean_v1/   (最终)"
echo ""
echo "质量报告："
echo "  - reports/quality_check_clean_v1/"
echo ""
echo "提示："
echo "  - 如需重新运行某阶段，使用对应的 0X_*.sh 脚本"
echo "  - 快速模式（减少I/O）：bash run_fast_pipeline.sh"
