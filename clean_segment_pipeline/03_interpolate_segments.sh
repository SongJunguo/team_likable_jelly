#!/usr/bin/env bash
set -euo pipefail

# ========== 阶段3：插值 ==========
# 功能：
# - 对切分后的segments插值
# - 输出：interpolated_clean_v1/interpolated_2022-XX-XX.parquet
#
# 插值策略：
# - 每个segment独立插值
# - 1Hz重采样
# - csaps平滑样条
# - 最终0个NaN

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

PY_INTERP="$SCRIPT_DIR/interpolate_single_day.py"

usage() {
  cat <<'EOF'
用法: bash 03_interpolate_segments.sh [选项]

阶段3：插值

选项:
  --in-dir DIR        输入目录（默认: $SEGMENTED_DIR）
  --out-dir DIR       输出目录（默认: $INTERPOLATED_DIR）
  --from DATE         起始日期（默认: $DATE_FROM）
  --to DATE           截止日期（默认: $DATE_TO）
  --procs N           并发数（默认: $INTERP_PROCS）
  --smooth VAL        平滑系数（默认: $SMOOTH）
  --force             覆盖已存在文件
  --dry-run           仅打印命令
  --limit N           仅处理前N个文件（测试用）
  -h|--help           显示帮助

示例:
  # 单日测试
  bash 03_interpolate_segments.sh --from 2022-01-01 --to 2022-01-01

  # 全量运行
  bash 03_interpolate_segments.sh
EOF
}

IN_DIR="$SEGMENTED_DIR"
OUT="$INTERPOLATED_DIR"
PROCS="$INTERP_PROCS"
FROM="$DATE_FROM"
TO="$DATE_TO"
SMOOTH_VAL="$SMOOTH"
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
    --smooth) SMOOTH_VAL="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit) LIMIT="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$PY_INTERP" ]] || { echo "❌ 找不到脚本: $PY_INTERP"; exit 1; }

mkdir -p "$OUT" "$OUT/.logs"

echo "=========================================="
echo "  阶段3：插值（Interpolate）"
echo "=========================================="
echo "输入目录: $IN_DIR"
echo "输出目录: $OUT"
echo "日期范围: $FROM ~ $TO"
echo "并发数: $PROCS"
echo "平滑系数: $SMOOTH_VAL"
echo ""

# 获取待处理文件列表
mapfile -t ALL_FILES < <(find "$IN_DIR" -name "segmented_2022-*.parquet" 2>/dev/null | sort)

if [[ ${#ALL_FILES[@]} -eq 0 ]]; then
  echo "❌ 未找到 segmented_2022-*.parquet 于 $IN_DIR"
  exit 1
fi

# 过滤日期范围
TARGETS=()
for f in "${ALL_FILES[@]}"; do
  # 从 segmented_2022-01-01.parquet 提取 2022-01-01
  d=$(basename "$f" .parquet | sed 's/^segmented_//')
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
interp_one() {
  local d="$1"
  local in_f="$IN_DIR/segmented_${d}.parquet"
  local out_f="$OUT/interpolated_${d}.parquet"
  local log="$OUT/.logs/${d}.log"
  mkdir -p "$(dirname "$log")"

  echo "▶️  插值 $d" | tee "$log"

  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN: python $PY_INTERP -t_in $in_f -t_out $out_f -smooth $SMOOTH_VAL" | tee -a "$log"
    return 0
  fi

  /opt/miniconda3/envs/opensky/bin/python "$PY_INTERP" \
    -t_in "$in_f" \
    -t_out "$out_f" \
    -smooth "$SMOOTH_VAL" \
    >>"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }

  echo "✅ 完成: $d" | tee -a "$log"
}

export -f interp_one
export PY_INTERP IN_DIR OUT SMOOTH_VAL DRYRUN

# ========== 并行执行 ==========
echo "🚀 开始并行处理（$PROCS 进程）..."
echo ""

printf "%s\n" "${TARGETS[@]}" | xargs -I{} -P "$PROCS" bash -c 'interp_one "$@"' _ {}

echo ""
echo "=========================================="
echo "  ✅ 阶段3完成：插值"
echo "=========================================="
echo "输出目录: $OUT"
echo "日志目录: $OUT/.logs"
echo ""
echo "下一步："
echo "  bash 04_quality_check.sh  # 质量检查"
