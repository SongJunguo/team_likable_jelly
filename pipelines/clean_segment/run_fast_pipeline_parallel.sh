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
echo "最大插值间隔: $MAX_HOLE_SIZE"
echo "元数据筛选: europe_only=${META_EUROPE_ONLY}, top_airports=${META_TOP_AIRPORTS}, top_aircraft=${META_TOP_AIRCRAFT}"
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

# ========== 智能并行策略（避免内存爆炸） ==========
#
# 重要说明：
# 1. 过滤阶段（read_trajectories）是**串行**的，无法轨迹级并行
# 2. 切分阶段（split_by_time_parallel）支持轨迹级并行
# 3. 插值阶段（interpolate_parallel）支持轨迹级并行
#
# 内存考虑：
# - 单个文件在内存：~2-3GB（过滤后）
# - 如果24个文件 × 24个workers = 576个进程 → 内存爆炸！
#
# 安全策略：
# - 单文件测试：使用全部workers（充分利用CPU）
# - 多文件处理：只用文件级并行（避免内存爆炸）
# - 总进程数上限：24（保守值，避免机械硬盘I/O饱和）

NUM_FILES=${#TARGETS[@]}
TOTAL_CORES=24  # 保守上限

if [[ $NUM_FILES -eq 1 ]]; then
    # 单文件模式：文件串行，轨迹并行
    FILE_PROCS=1
    ACTUAL_WORKERS=$WORKERS
    echo "🔧 并行策略：单文件模式"
    echo "   - 文件级：1个文件（串行）"
    echo "   - 轨迹级：${ACTUAL_WORKERS}个worker（并行）"
    echo "   - 总进程：${ACTUAL_WORKERS}个"
    echo "   - 说明：过滤串行，切分和插值各用${ACTUAL_WORKERS}核"
else
    # 多文件模式：文件并行，轨迹串行
    FILE_PROCS=$(( NUM_FILES < TOTAL_CORES ? NUM_FILES : TOTAL_CORES ))
    ACTUAL_WORKERS=1
    echo "🔧 并行策略：多文件模式"
    echo "   - 文件级：${FILE_PROCS}个文件（并行）"
    echo "   - 轨迹级：1个worker（串行）"
    echo "   - 总进程：${FILE_PROCS}个"
    echo "   - 说明：避免内存爆炸（过滤阶段无法轨迹并行）"
fi

echo ""
echo "⚠️  重要：过滤阶段始终串行（read_trajectories不支持并行）"
echo "         切分和插值阶段会使用${ACTUAL_WORKERS}个worker并行"
echo ""

# ========== 并行处理函数 ==========
process_one_file() {
    local d=$1
    local actual_workers=$2
    local in_f="$RAW/${d}.parquet"
    local out_f="$OUT/interpolated_${d}.parquet"
    local log="$OUT/.logs/${d}.log"

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

    if python "$PY_FAST" \
        -t_in "$in_f" \
        -t_out "$out_f" \
        -strategy "$FILTER_STRATEGY" \
        -smooth "$SMOOTH_VAL" \
        --max-dt "$MAX_DT" \
        --min-points "$MIN_POINTS" \
        --min-duration "$MIN_DURATION" \
        --max-hole-size "$MAX_HOLE_SIZE" \
        --workers "$actual_workers" \
        "${meta_args[@]}" > "$log" 2>&1
    then
        echo "  ✅ 完成: $d"
        return 0
    else
        echo "  ❌ 失败: $d (详见 $log)"
        return 1
    fi
}

export -f process_one_file
export RAW OUT PY_FAST FILTER_STRATEGY SMOOTH_VAL MAX_DT MIN_POINTS MIN_DURATION MAX_HOLE_SIZE

echo "🚀 开始处理..."
echo ""

SUCCESS=0
FAILED=0

if [[ $FILE_PROCS -eq 1 ]]; then
    # 单文件模式：串行处理（但内部并行）
    for d in "${TARGETS[@]}"; do
        echo "▶️  处理 $d (内部${ACTUAL_WORKERS}核并行)..."

        if [[ "$DRYRUN" == "1" ]]; then
            echo "DRYRUN: process_one_file $d $ACTUAL_WORKERS"
            continue
        fi

        if process_one_file "$d" "$ACTUAL_WORKERS"; then
            SUCCESS=$((SUCCESS + 1))
        else
            FAILED=$((FAILED + 1))
        fi
    done
else
    # 多文件模式：文件级并行
    echo "📦 使用xargs并行处理${FILE_PROCS}个文件..."
    echo ""

    if [[ "$DRYRUN" == "1" ]]; then
        for d in "${TARGETS[@]}"; do
            echo "DRYRUN: process_one_file $d $ACTUAL_WORKERS"
        done
    else
        # 使用xargs并行，每个文件传递actual_workers参数
        printf "%s\n" "${TARGETS[@]}" | \
            xargs -I{} -P "$FILE_PROCS" bash -c "process_one_file {} $ACTUAL_WORKERS"

        # 统计结果（简化版，实际成功数通过日志判断）
        for d in "${TARGETS[@]}"; do
            log="$OUT/.logs/${d}.log"
            if [[ -f "$log" ]] && grep -q "✅ 完成" "$log" 2>/dev/null; then
                SUCCESS=$((SUCCESS + 1))
            else
                FAILED=$((FAILED + 1))
            fi
        done
    fi
fi

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
