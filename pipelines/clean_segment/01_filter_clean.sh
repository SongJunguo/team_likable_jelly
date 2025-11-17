#!/usr/bin/env bash
set -euo pipefail

# ========== 阶段1：过滤清洗 ==========
# 功能：
# - 应用clean_segment_interp策略过滤原始轨迹
# - 输出：filtered_clean_v1/2022-XX-XX.parquet
#
# 过滤链：
# FilterCstLatLon → FilterCstPosition → FilterCstSpeed → FilterEdgeOutlier
#   → FilterMaxSpeedSkipNaNWithVoting → FilterIsolated

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

usage() {
  cat <<'EOF'
用法: bash 01_filter_clean.sh [选项]

阶段1：过滤清洗

选项:
  --raw-dir DIR       原始数据目录（默认: $RAW_DIR）
  --out-dir DIR       输出目录（默认: $FILTERED_DIR）
  --from DATE         起始日期（默认: $DATE_FROM）
  --to DATE           截止日期（默认: $DATE_TO）
  --procs N           并发数（默认: $FILTER_PROCS）
  --force             覆盖已存在文件
  --dry-run           仅打印命令
  --limit N           仅处理前N个文件（测试用）
  -h|--help           显示帮助

示例:
  # 单日测试
  bash 01_filter_clean.sh --from 2022-01-01 --to 2022-01-01

  # 全量运行
  bash 01_filter_clean.sh
EOF
}

RAW="$RAW_DIR"
OUT="$FILTERED_DIR"
PROCS="$FILTER_PROCS"
FROM="$DATE_FROM"
TO="$DATE_TO"
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
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit) LIMIT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

mkdir -p "$OUT" "$OUT/.logs"

echo "=========================================="
echo "  阶段1：过滤清洗（Clean）"
echo "=========================================="
echo "原始数据: $RAW"
echo "输出目录: $OUT"
echo "策略: $FILTER_STRATEGY"
echo "日期范围: $FROM ~ $TO"
echo "并发数: $PROCS"
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

  out_f="$OUT/${d}.parquet"
  if [[ "$FORCE" != "1" && -f "$out_f" ]]; then
    echo "↪︎ 跳过已存在: ${d}.parquet"
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
filter_one() {
  local d="$1"
  local in_f="$RAW/${d}.parquet"
  local out_f="$OUT/${d}.parquet"
  local log="$OUT/.logs/${d}.log"
  mkdir -p "$(dirname "$log")"

  echo "▶️  过滤 $d" | tee "$log"

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: python -m pipelines.clean_segment.filter_trajs -t_in $in_f -t_out $out_f -strategy $FILTER_STRATEGY" | tee -a "$log"
    return 0
  fi

  /opt/miniconda3/envs/opensky/bin/python -m pipelines.clean_segment.filter_trajs \
    -t_in "$in_f" \
    -t_out "$out_f" \
    -strategy "$FILTER_STRATEGY" \
    >>"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }

  echo "✅ 完成: $d" | tee -a "$log"
}

export -f filter_one
export RAW OUT FILTER_STRATEGY DRYRUN

# ========== 并行执行 ==========
echo "🚀 开始并行处理（$PROCS 进程）..."
echo ""

printf "%s\n" "${TARGETS[@]}" | xargs -I{} -P "$PROCS" bash -c 'filter_one "$@"' _ {}

echo ""
echo "=========================================="
echo "  ✅ 阶段1完成：过滤清洗"
echo "=========================================="
echo "输出目录: $OUT"
echo "日志目录: $OUT/.logs"
echo ""
echo "下一步："
echo "  bash 02_split_by_time.sh  # 切分"
