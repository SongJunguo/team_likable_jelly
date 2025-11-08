#!/usr/bin/env bash
set -euo pipefail

# ========== 快速并行模式（轨迹级并行） ==========
# 相比run_fast_pipeline.sh的改进：
# - 文件级串行：一个parquet一个parquet顺序处理
# - 轨迹级并行：每个parquet内部按flight_id并行
# - 测试单日数据时充分利用多核（不用等很久！）
#
# 优势：
# - 单文件测试时速度快（24-40核全开）
# - 避免文件级并行的I/O竞争
# - 机械硬盘友好（顺序读文件）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

PY_FAST="$SCRIPT_DIR/process_single_day_fast_parallel.py"

usage() {
  cat <<'EOF'
用法: bash run_fast_pipeline_parallel.sh [选项]

快速并行模式（轨迹级并行）：
  - 文件级串行：一个parquet一个parquet处理
  - 轨迹级并行：每个文件内部按flight_id多进程
  - 适合测试单日数据（充分利用多核）

选项:
  --raw-dir DIR       原始数据目录（默认: $RAW_DIR）
  --out-dir DIR       输出目录（默认: $INTERPOLATED_DIR）
  --from DATE         起始日期 YYYY-MM-DD（默认: $DATE_FROM）
  --to DATE           截止日期 YYYY-MM-DD（默认: $DATE_TO）
  --workers N         并行worker数（默认: $INTERP_PROCS）
  --smooth VAL        插值平滑系数（默认: $SMOOTH）
  --force             覆盖已存在文件
  --dry-run           仅打印命令
  --limit N           仅处理前N个文件（测试用）
  -h|--help           显示帮助

示例:
  # 测试单日（轨迹级并行，充分利用多核）
  bash run_fast_pipeline_parallel.sh --from 2022-01-01 --to 2022-01-01

  # 全量运行（文件顺序处理，每个文件内并行）
  bash run_fast_pipeline_parallel.sh

  # 自定义并行度
  bash run_fast_pipeline_parallel.sh --workers 40 --smooth 1e-3
EOF
}

RAW="$RAW_DIR"
OUT="$INTERPOLATED_DIR"
WORKERS="$INTERP_PROCS"
FROM="$DATE_FROM"
TO="$DATE_TO"
SMOOTH_VAL="$SMOOTH"
FORCE=0
DRYRUN=0
LIMIT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw-dir) RAW="$2"; shift 2;;
    --out-dir) OUT="$2"; shift 2;;
    --from) FROM="$2"; shift 2;;
    --to) TO="$2"; shift 2;;
    --workers) WORKERS="$2"; shift 2;;
    --smooth) SMOOTH_VAL="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit) LIMIT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$PY_FAST" ]] || { echo "❌ 找不到脚本: $PY_FAST"; exit 1; }

mkdir -p "$OUT" "$OUT/.logs"

echo "==========================================="
echo "  快速并行模式（Trajectory-Level Parallel）"
echo "==========================================="
echo "原始数据: $RAW"
echo "输出目录: $OUT"
echo "策略: $FILTER_STRATEGY"
echo "日期范围: $FROM ~ $TO"
echo "并行worker数: $WORKERS（每个文件内并行）"
echo "平滑系数: $SMOOTH_VAL"
echo ""
echo "并行策略："
echo "  - 文件级：串行（一个一个处理）"
echo "  - 轨迹级：并行（每个文件内${WORKERS}核并行）"
echo ""

# 获取待处理文件列表
mapfile -t ALL_FILES < <(find "$RAW" -name "2022-*.parquet" 2>/dev/null | sort)

if [[ ${#ALL_FILES[@]} -eq 0 ]]; then
  echo "❌ 未找到 2022-*.parquet 于 $RAW"
  exit 1
fi

# 过滤日期范围
TARGETS=()
for f in "${ALL_FILES[@]}"; do
  d=$(basename "$f" .parquet)
  [[ -n "$FROM" && "$d" < "$FROM" ]] && continue
  [[ -n "$TO" && "$d" > "$TO" ]] && continue

  out_f="$OUT/interpolated_${d}.parquet"
  if [[ "$FORCE" != "1" && -f "$out_f" ]]; then
    echo "↪︎ 跳过已存在: interpolated_${d}.parquet"
    continue
  fi

  TARGETS+=("$d")
done

# 限制处理数量（测试用）
if [[ "$LIMIT" != "0" && "$LIMIT" -lt "${#TARGETS[@]}" ]]; then
  echo "⚠️  限制处理前 $LIMIT 个文件（测试模式）"
  TARGETS=("${TARGETS[@]:0:$LIMIT}")
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "✅ 无需处理：符合条件的文件均已存在输出"
  exit 0
fi

echo "📅 待处理文件数: ${#TARGETS[@]}"
echo ""

# ========== 串行处理（每个文件内部并行） ==========
echo "🚀 开始顺序处理（每个文件内${WORKERS}核并行）..."
echo ""

SUCCESS=0
FAILED=0

for d in "${TARGETS[@]}"; do
  in_f="$RAW/${d}.parquet"
  out_f="$OUT/interpolated_${d}.parquet"
  log="$OUT/.logs/${d}.log"

  echo "▶️  处理 $d (内部${WORKERS}核并行)..."

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: python $PY_FAST -t_in $in_f -t_out $out_f -strategy $FILTER_STRATEGY -smooth $SMOOTH_VAL --workers $WORKERS"
    continue
  fi

  if /opt/miniconda3/envs/opensky/bin/python "$PY_FAST" \
    -t_in "$in_f" \
    -t_out "$out_f" \
    -strategy "$FILTER_STRATEGY" \
    -smooth "$SMOOTH_VAL" \
    --max-dt "$MAX_DT" \
    --min-points "$MIN_POINTS" \
    --min-duration "$MIN_DURATION" \
    --workers "$WORKERS" \
    >"$log" 2>&1; then
    echo "  ✅ 完成: $d"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "  ❌ 失败: $d (详见 $log)"
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "==========================================="
echo "  快速并行模式完成"
echo "==========================================="
echo "成功: $SUCCESS 个文件"
[[ $FAILED -gt 0 ]] && echo "失败: $FAILED 个文件"
echo "输出目录: $OUT"
echo "日志目录: $OUT/.logs"
echo ""
echo "下一步："
echo "  bash 04_quality_check.sh  # 质量检查"

[[ $FAILED -gt 0 ]] && exit 1
exit 0
