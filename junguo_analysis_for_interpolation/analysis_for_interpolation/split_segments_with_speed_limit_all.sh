#!/usr/bin/env bash
set -euo pipefail

# 批量把 complete_* 日文件切成"无缺失、无超速的连续片段"
#
# 改进：在原有逻辑基础上增加速度检查
# - 删除超速点（设为NaN）
# - 删除所有NaN行
# - 按时间间隔切段
# - 保证每个segment：无NaN + 无超速 + 时间连续
#
# 输出 segmented_YYYY-MM-DD.parquet 到指定目录；已存在默认跳过（--force 覆盖）。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SPLIT="$SCRIPT_DIR/../split_segments_with_speed_check.py"

# 默认参数
PROCS=8
# 必需列以空格分隔的字符串（便于在 xargs 的子 shell 中传递）
REQ_COLS="latitude longitude altitude"
MAX_DT=20          # 最大时间间隔（秒）
MAX_SPEED=600      # 最大速度（米/秒）= 2160 km/h
MIN_POINTS=30      # 最小点数
MIN_DURATION=120   # 最小时长（秒）
FORCE=0
DRYRUN=0
DATE_FROM="2022-01-01"
DATE_TO="2022-12-31"

usage() {
    cat <<EOF
用法: $(basename "$0") [选项]

批量切段脚本（带速度限制）

必需参数:
  --input-dir DIR     输入目录（complete_*.parquet）
  --output-dir DIR    输出目录（segmented_*.parquet）

可选参数:
  --procs N           并行进程数（默认: $PROCS）
  --required-cols ... 必需列（默认: $REQ_COLS）
  --max-dt SECONDS    最大时间间隔（默认: $MAX_DT 秒）
  --max-speed MPS     最大速度（默认: $MAX_SPEED 米/秒 = 2160 km/h）
  --min-points N      最小点数（默认: $MIN_POINTS）
  --min-duration SEC  最小时长（默认: $MIN_DURATION 秒）
  --from DATE         起始日期（默认: $DATE_FROM）
  --to DATE           结束日期（默认: $DATE_TO）
  --force             覆盖已存在的输出
  --dry-run           仅打印命令不执行
  -h|--help           显示帮助

逻辑说明:
  1. 检查速度，删除超速点（设为NaN）
  2. 删除所有NaN行
  3. 按时间间隔切段（Δt > max_dt 则切断）
  4. 过滤太短的segment

结果保证:
  每个segment内部：无NaN + 无超速 + 时间连续

示例:
  bash $0 \\
    --input-dir /path/to/interpolate_trajs \\
    --output-dir /path/to/segmented_trajs_speed_limited \\
    --procs 8 --max-speed 600
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir) IN_DIR="$2"; shift 2;;
    --output-dir) OUT_DIR="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --required-cols) shift; REQ_COLS=""; while [[ $# -gt 0 && "$1" != --* ]]; do REQ_COLS+="${REQ_COLS:+ }$1"; shift; done;;
    --max-dt) MAX_DT="$2"; shift 2;;
    --max-speed) MAX_SPEED="$2"; shift 2;;
    --min-points) MIN_POINTS="$2"; shift 2;;
    --min-duration) MIN_DURATION="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

# 检查必需参数
if [[ -z "${IN_DIR:-}" || -z "${OUT_DIR:-}" ]]; then
    echo "❌ 错误：必须指定 --input-dir 和 --output-dir"
    echo ""
    usage
    exit 1
fi

# 检查Python脚本是否存在
if [[ ! -f "$PY_SPLIT" ]]; then
    echo "❌ 找不到 Python 脚本: $PY_SPLIT"
    exit 1
fi

mkdir -p "$OUT_DIR" "$OUT_DIR/.logs"

mapfile -t DLIST < <(ls "$IN_DIR"/complete_2022-*.parquet 2>/dev/null | sed 's#.*/complete_##; s/.parquet$//' | sort)
if [[ ${#DLIST[@]} -eq 0 ]]; then
    echo "❌ 未找到 complete_2022-*.parquet 于 $IN_DIR"
    exit 1
fi

FILTERED=()
for d in "${DLIST[@]}"; do
  if [[ -n "$DATE_FROM" && "$d" < "$DATE_FROM" ]]; then continue; fi
  if [[ -n "$DATE_TO" && "$d" > "$DATE_TO" ]]; then continue; fi
  if [[ "$FORCE" != "1" && -f "$OUT_DIR/segmented_${d}.parquet" ]]; then
    echo "↪︎ 跳过已存在: segmented_${d}.parquet"; continue
  fi
  FILTERED+=("$d")
done

if [[ ${#FILTERED[@]} -eq 0 ]]; then
    echo "✅ 无需处理：符合条件的日期文件均已存在输出（或筛选为空）。"
    exit 0
fi

echo "📅 待处理文件数: ${#FILTERED[@]}"
echo "📊 参数配置:"
echo "   - 最大时间间隔: ${MAX_DT} 秒"
# 计算 km/h (使用bash整数运算)
MAX_SPEED_KMH=$((MAX_SPEED * 36 / 10))
echo "   - 最大速度: ${MAX_SPEED} m/s (${MAX_SPEED_KMH} km/h)"
echo "   - 最小点数: ${MIN_POINTS}"
echo "   - 最小时长: ${MIN_DURATION} 秒"
echo ""

run_one() {
  local d="$1"
  local in_f="$IN_DIR/complete_${d}.parquet"
  local out_f="$OUT_DIR/segmented_${d}.parquet"
  local log="$OUT_DIR/.logs/${d}.log"

  echo "▶️  $d → $out_f" | tee "$log"
  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN python $PY_SPLIT --input-file $in_f --output-file $out_f --required-cols $REQ_COLS --max-dt $MAX_DT --max-speed $MAX_SPEED --min-points $MIN_POINTS --min-duration $MIN_DURATION" | tee -a "$log"
    return 0
  fi

  python "$PY_SPLIT" \
    --input-file "$in_f" \
    --output-file "$out_f" \
    --required-cols $REQ_COLS \
    --max-dt "$MAX_DT" \
    --max-speed "$MAX_SPEED" \
    --min-points "$MIN_POINTS" \
    --min-duration "$MIN_DURATION" \
    >>"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }
}

export -f run_one
export PY_SPLIT IN_DIR OUT_DIR REQ_COLS MAX_DT MAX_SPEED MIN_POINTS MIN_DURATION DRYRUN

printf "%s\n" "${FILTERED[@]}" | xargs -I{} -P "$PROCS" bash -c 'run_one "$@"' _ {}

echo ""
echo "✅ 切段完成（带速度限制）。输出目录: $OUT_DIR"
echo "📊 配置: max_dt=${MAX_DT}s, max_speed=${MAX_SPEED}m/s, min_points=${MIN_POINTS}, min_duration=${MIN_DURATION}s"
