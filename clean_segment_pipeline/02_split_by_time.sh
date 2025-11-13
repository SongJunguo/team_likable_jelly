#!/usr/bin/env bash
set -euo pipefail

# ========== 阶段2：时间切分 ==========
# 功能：
# - 按时间间隔切分过滤后的轨迹
# - 输出：segmented_clean_v1/segmented_2022-XX-XX.parquet
#
# 切分规则：
# - Δt > 20秒：切断
# - segment长度 < 30点：删除
# - segment时长 < 120秒：删除

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

PY_SPLIT="$SCRIPT_DIR/split_single_day.py"

usage() {
  cat <<'EOF'
用法: bash 02_split_by_time.sh [选项]

阶段2：时间切分

选项:
  --in-dir DIR        输入目录（默认: $FILTERED_DIR）
  --out-dir DIR       输出目录（默认: $SEGMENTED_DIR）
  --from DATE         起始日期（默认: $DATE_FROM）
  --to DATE           截止日期（默认: $DATE_TO）
  --procs N           并发数（默认: $SPLIT_PROCS）
  --max-dt N          最大时间间隔（默认: $MAX_DT）
  --min-points N      最小点数（默认: $MIN_POINTS）
  --min-duration N    最小时长（默认: $MIN_DURATION）
  --force             覆盖已存在文件
  --dry-run           仅打印命令
  --limit N           仅处理前N个文件（测试用）
  -h|--help           显示帮助

示例:
  # 单日测试
  bash 02_split_by_time.sh --from 2022-01-01 --to 2022-01-01

  # 全量运行
  bash 02_split_by_time.sh
EOF
}

IN_DIR="$FILTERED_DIR"
OUT="$SEGMENTED_DIR"
PROCS="$SPLIT_PROCS"
FROM="$DATE_FROM"
TO="$DATE_TO"
MAX_DT_VAL="$MAX_DT"
MIN_PTS="$MIN_POINTS"
MIN_DUR="$MIN_DURATION"
FORCE=0
DRYRUN=0
LIMIT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --in-dir) IN_DIR="$2"; shift 2;;
    --out-dir) OUT="$2"; shift 2;;
    --from) FROM="$2"; shift 2;;
    --to) TO="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --max-dt) MAX_DT_VAL="$2"; shift 2;;
    --min-points) MIN_PTS="$2"; shift 2;;
    --min-duration) MIN_DUR="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit) LIMIT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$PY_SPLIT" ]] || { echo "❌ 找不到脚本: $PY_SPLIT"; exit 1; }

mkdir -p "$OUT" "$OUT/.logs"

echo "=========================================="
echo "  阶段2：时间切分（Segment）"
echo "=========================================="
echo "输入目录: $IN_DIR"
echo "输出目录: $OUT"
echo "日期范围: $FROM ~ $TO"
echo "并发数: $PROCS"
echo "切分参数: max_dt=${MAX_DT_VAL}s, min_points=$MIN_PTS, min_duration=${MIN_DUR}s"
echo ""

# 获取待处理文件列表
mapfile -t ALL_FILES < <(find "$IN_DIR" -name "2022-*.parquet" 2>/dev/null | sort)

if [[ ${#ALL_FILES[@]} -eq 0 ]]; then
  echo "❌ 未找到 2022-*.parquet 于 $IN_DIR"
  exit 1
fi

# 过滤日期范围
TARGETS=()
for f in "${ALL_FILES[@]}"; do
  d=$(basename "$f" .parquet)
  [[ -n "$FROM" && "$d" < "$FROM" ]] && continue
  [[ -n "$TO" && "$d" > "$TO" ]] && continue

  out_f="$OUT/segmented_${d}.parquet"
  if [[ "$FORCE" != "1" && -f "$out_f" ]]; then
    echo "↪︎ 跳过已存在: segmented_${d}.parquet"
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
split_one() {
  local d="$1"
  local in_f="$IN_DIR/${d}.parquet"
  local out_f="$OUT/segmented_${d}.parquet"
  local log="$OUT/.logs/${d}.log"
  mkdir -p "$(dirname "$log")"

  echo "▶️  切分 $d" | tee "$log"

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: python $PY_SPLIT -t_in $in_f -t_out $out_f --max-dt $MAX_DT_VAL --min-points $MIN_PTS --min-duration $MIN_DUR" | tee -a "$log"
    return 0
  fi

  /opt/miniconda3/envs/opensky/bin/python "$PY_SPLIT" \
    -t_in "$in_f" \
    -t_out "$out_f" \
    --max-dt "$MAX_DT_VAL" \
    --min-points "$MIN_PTS" \
    --min-duration "$MIN_DUR" \
    >>"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }

  echo "✅ 完成: $d" | tee -a "$log"
}

export -f split_one
export PY_SPLIT IN_DIR OUT MAX_DT_VAL MIN_PTS MIN_DUR DRYRUN

# ========== 并行执行 ==========
echo "🚀 开始并行处理（$PROCS 进程）..."
echo ""

printf "%s\n" "${TARGETS[@]}" | xargs -I{} -P "$PROCS" bash -c 'split_one "$@"' _ {}

echo ""
echo "=========================================="
echo "  ✅ 阶段2完成：时间切分"
echo "=========================================="
echo "输出目录: $OUT"
echo "日志目录: $OUT/.logs"
echo ""
echo "下一步："
echo "  bash 03_interpolate_segments.sh  # 插值"
