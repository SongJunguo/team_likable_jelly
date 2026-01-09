#!/usr/bin/env bash
set -euo pipefail

# ========== 快速模式主流程 ==========
# 一口气处理：过滤 → 切分 → 插值（数据在内存中流转）
#
# 优势：
# - 减少I/O（机械硬盘友好）
# - 只输出最终结果
# - 并行处理所有日期文件
#
# 劣势：
# - 难以调试中间阶段（建议先用单日测试）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

PY_FAST="$SCRIPT_DIR/process_single_day_fast.py"

usage() {
  cat <<'EOF'
用法: bash run_fast_pipeline.sh [选项]

快速模式（一口气处理）：
  - 数据在内存中流转：过滤 → 切分 → 插值
  - 只输出最终结果到 interpolated_clean_v1/
  - 适合生产运行（机械硬盘友好）

选项:
  --raw-dir DIR       原始数据目录（默认: $RAW_DIR）
  --out-dir DIR       输出目录（默认: $INTERPOLATED_DIR）
  --from DATE         起始日期 YYYY-MM-DD（默认: $DATE_FROM）
  --to DATE           截止日期 YYYY-MM-DD（默认: $DATE_TO）
  --procs N           并发数（默认: $INTERP_PROCS）
  --smooth VAL        插值平滑系数（默认: $SMOOTH）
  --req-cols STR      必需列列表（空格分隔，默认: $REQ_COLS）
  --gap-mode MODE     gap处理方式 split|drop（默认: $GAP_HANDLING）
  --with-quality      完成后自动运行质量检查（默认开启）
  --no-quality        禁用质量检查
  --with-stats        完成后自动跑 raw/filter/segment/interp 点数统计（默认开启，缺目录自动跳过）
  --no-stats          禁用点数统计
  --force             覆盖已存在文件
  --dry-run           仅打印命令
  --limit N           仅处理前N个文件（测试用）
  -h|--help           显示帮助

示例:
  # 测试单日
  bash run_fast_pipeline.sh --from 2022-01-01 --to 2022-01-01

  # 全量运行
  bash run_fast_pipeline.sh

  # 自定义参数
  bash run_fast_pipeline.sh --procs 40 --smooth 1e-3
EOF
}

RAW="${RAW_DIR}"
OUT="${INTERPOLATED_DIR}"
PROCS="${INTERP_PROCS}"
FROM="${DATE_FROM}"
TO="${DATE_TO}"
SMOOTH_VAL="${SMOOTH}"
REQ_COLS_VAL="${REQ_COLS}"
GAP_MODE="${GAP_HANDLING:-split}"
WITH_QUALITY=1
WITH_STATS=1
FORCE=0
DRYRUN=0
LIMIT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw-dir) RAW="$2"; shift 2;;
    --out-dir) OUT="$2"; shift 2;;
    --from) FROM="$2"; shift 2;;
    --to) TO="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --smooth) SMOOTH_VAL="$2"; shift 2;;
    --req-cols) REQ_COLS_VAL="$2"; shift 2;;
    --gap-mode) GAP_MODE="$2"; shift 2;;
    --with-quality) WITH_QUALITY=1; shift;;
    --no-quality) WITH_QUALITY=0; shift;;
    --with-stats) WITH_STATS=1; shift;;
    --no-stats) WITH_STATS=0; shift;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit) LIMIT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$PY_FAST" ]] || { echo "❌ 找不到脚本: $PY_FAST"; exit 1; }

mkdir -p "$OUT" "$OUT/.logs"

echo "=========================================="
echo "  快速模式（Clean-Segment-Interp）"
echo "=========================================="
echo "原始数据: $RAW"
echo "输出目录: $OUT"
echo "策略: $FILTER_STRATEGY"
echo "日期范围: $FROM ~ $TO"
echo "并发数: $PROCS"
echo "平滑系数: $SMOOTH_VAL"
echo "最大插值间隔: $MAX_HOLE_SIZE"
echo "必需列: $REQ_COLS_VAL"
echo "gap处理: $GAP_MODE"
echo "元数据筛选: europe_only=${META_EUROPE_ONLY}, top_airports=${META_TOP_AIRPORTS}, top_aircraft=${META_TOP_AIRCRAFT}"
echo "机场邻近过滤: enable=${AIRPORT_PROXIMITY_ENABLE:-0}, threshold_km=${AIRPORT_PROXIMITY_THRESHOLD_KM:-10}"
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

# ========== 并行处理函数 ==========
run_one_fast() {
  local d="$1"
  local in_f="$RAW/${d}.parquet"
  local out_f="$OUT/interpolated_${d}.parquet"
  local log="$OUT/.logs/${d}.log"

  echo "▶️  快速处理 $d" | tee "$log"

  local meta_args=()
  [[ "${META_EUROPE_ONLY:-0}" == "1" ]] && meta_args+=(--europe-only)
  [[ "${META_TOP_AIRPORTS:-0}" != "0" ]] && meta_args+=(--top-airports "$META_TOP_AIRPORTS")
  [[ "${META_TOP_AIRCRAFT:-0}" != "0" ]] && meta_args+=(--top-aircraft "$META_TOP_AIRCRAFT")
  [[ "${META_INCLUDE_SUBMISSION:-0}" == "1" ]] && meta_args+=(--include-submission)
  [[ "${META_INCLUDE_FINAL:-0}" == "1" ]] && meta_args+=(--include-final)
  [[ -n "${META_FLIGHTS_PARQUET:-}" ]] && meta_args+=(--flights-parquet "$META_FLIGHTS_PARQUET")
  [[ -n "${META_AIRPORTS_PARQUET:-}" ]] && meta_args+=(--airports-parquet "$META_AIRPORTS_PARQUET")
  [[ -n "${META_EUROPE_CONTINENT:-}" ]] && meta_args+=(--europe-continent "$META_EUROPE_CONTINENT")
  [[ -n "${META_PROCS:-}" ]] && meta_args+=(--meta-procs "$META_PROCS")

  local airport_args=()
  if [[ "${AIRPORT_PROXIMITY_ENABLE:-0}" == "1" ]]; then
    airport_args+=(--airport-filter --airport-threshold-km "${AIRPORT_PROXIMITY_THRESHOLD_KM:-10}")
  fi

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: python $PY_FAST -t_in $in_f -t_out $out_f -strategy $FILTER_STRATEGY -smooth $SMOOTH_VAL --max-dt $MAX_DT --req-cols \"$REQ_COLS_VAL\" --gap-mode $GAP_MODE --min-points $MIN_POINTS --min-duration $MIN_DURATION --max-hole-size $MAX_HOLE_SIZE ${meta_args[*]} ${airport_args[*]}" | tee -a "$log"
    return 0
  fi

   "$PY_FAST" \
    -t_in "$in_f" \
    -t_out "$out_f" \
    -strategy "$FILTER_STRATEGY" \
    -smooth "$SMOOTH_VAL" \
    --max-dt "$MAX_DT" \
    --req-cols "$REQ_COLS_VAL" \
    --gap-mode "$GAP_MODE" \
    --min-points "$MIN_POINTS" \
    --min-duration "$MIN_DURATION" \
    --max-hole-size "$MAX_HOLE_SIZE" \
    "${meta_args[@]}" \
    "${airport_args[@]}" \
    >>"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }

  echo "✅ 完成: $d" | tee -a "$log"
}

export -f run_one_fast
export PY_FAST RAW OUT FILTER_STRATEGY SMOOTH_VAL MAX_DT REQ_COLS_VAL GAP_MODE MIN_POINTS MIN_DURATION MAX_HOLE_SIZE DRYRUN

# ========== 并行执行 ==========
echo "🚀 开始并行处理（$PROCS 进程）..."
echo ""

printf "%s\n" "${TARGETS[@]}" | xargs -I{} -P "$PROCS" bash -c 'run_one_fast "$@"' _ {}

echo ""
echo "=========================================="
echo "  ✅ 快速模式完成"
echo "=========================================="
echo "输出目录: $OUT"
echo "日志目录: $OUT/.logs"

# ========== 可选：质量检查 ==========
if [[ "$WITH_QUALITY" == "1" ]]; then
  echo ""
  echo "=========================================="
  echo "  ▶️  质量检查"
  echo "=========================================="
  QC_PROCS="${QUALITY_CHECK_PROCS:-$PROCS}"
  QC_CMD=(bash "$SCRIPT_DIR/04_quality_check.sh" --data-dir "$OUT" --from "$FROM" --to "$TO" --procs "$QC_PROCS")
  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${QC_CMD[*]}"
  else
    "${QC_CMD[@]}"
  fi
fi

# ========== 可选：点数与缺失率统计 ==========
if [[ "$WITH_STATS" == "1" && "${ENABLE_POINT_STATS:-1}" == "1" ]]; then
  echo ""
  echo "=========================================="
  echo "  ▶️  raw vs filtered 点数统计"
  echo "=========================================="
  STATS_CMD=(bash "$SCRIPT_DIR/run_raw_filtered_point_stats.sh")
  STATS_CMD+=(FROM="$FROM" TO="$TO" RAW_DIR="$RAW" INTERPOLATED_DIR="$OUT")
  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: ${STATS_CMD[*]}"
  else
    "${STATS_CMD[@]}"
  fi
fi
