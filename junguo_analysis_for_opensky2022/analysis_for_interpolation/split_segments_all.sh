#!/usr/bin/env bash
set -euo pipefail

# 批量把 complete_* 日文件切成“无缺失的连续片段”
# 输出 segmented_YYYY-MM-DD.parquet 到指定目录；已存在默认跳过（--force 覆盖）。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_SPLIT="$SCRIPT_DIR/split_segments_on_missing.py"

IN_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/complete_high_quality_trajectories_v2_lim20s_inside"
OUT_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/segmented_trajectories_v2_lim20s_inside"
PROCS=8
# 必需列以空格分隔的字符串（便于在 xargs 的子 shell 中传递）
REQ_COLS="latitude longitude altitude"
MAX_DT=20
MIN_POINTS=30
MIN_DURATION=120
FORCE=0
DRYRUN=0
DATE_FROM="2022-01-01"
DATE_TO="2022-12-31"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir) IN_DIR="$2"; shift 2;;
    --output-dir) OUT_DIR="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --required-cols) shift; REQ_COLS=""; while [[ $# -gt 0 && "$1" != --* ]]; do REQ_COLS+="${REQ_COLS:+ }$1"; shift; done;;
    --max-dt) MAX_DT="$2"; shift 2;;
    --min-points) MIN_POINTS="$2"; shift 2;;
    --min-duration) MIN_DURATION="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) sed -n '1,120p' "$0"; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

mkdir -p "$OUT_DIR" "$OUT_DIR/.logs"

mapfile -t DLIST < <(ls "$IN_DIR"/complete_2022-*.parquet 2>/dev/null | sed 's#.*/complete_##; s/.parquet$//' | sort)
if [[ ${#DLIST[@]} -eq 0 ]]; then echo "❌ 未找到 complete_2022-*.parquet 于 $IN_DIR"; exit 1; fi

FILTERED=()
for d in "${DLIST[@]}"; do
  if [[ -n "$DATE_FROM" && "$d" < "$DATE_FROM" ]]; then continue; fi
  if [[ -n "$DATE_TO" && "$d" > "$DATE_TO" ]]; then continue; fi
  if [[ "$FORCE" != "1" && -f "$OUT_DIR/segmented_${d}.parquet" ]]; then
    echo "↪︎ 跳过已存在: segmented_${d}.parquet"; continue
  fi
  FILTERED+=("$d")
done

echo "📅 待处理文件数: ${#FILTERED[@]}"

run_one() {
  local d="$1"
  local in_f="$IN_DIR/complete_${d}.parquet"
  local out_f="$OUT_DIR/segmented_${d}.parquet"
  local log="$OUT_DIR/.logs/${d}.log"

  echo "▶️  $d → $out_f" | tee "$log"
  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN python $PY_SPLIT --input-file $in_f --output-file $out_f --required-cols $REQ_COLS --max-dt $MAX_DT --min-points $MIN_POINTS --min-duration $MIN_DURATION" | tee -a "$log"
    return 0
  fi

  python "$PY_SPLIT" \
    --input-file "$in_f" \
    --output-file "$out_f" \
    --required-cols $REQ_COLS \
    --max-dt "$MAX_DT" \
    --min-points "$MIN_POINTS" \
    --min-duration "$MIN_DURATION" \
    >>"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }
}

export -f run_one
export PY_SPLIT IN_DIR OUT_DIR REQ_COLS MAX_DT MIN_POINTS MIN_DURATION DRYRUN

printf "%s\n" "${FILTERED[@]}" | xargs -I{} -P "$PROCS" bash -c 'run_one "$@"' _ {}

echo "✅ 切段完成。输出目录: $OUT_DIR"
