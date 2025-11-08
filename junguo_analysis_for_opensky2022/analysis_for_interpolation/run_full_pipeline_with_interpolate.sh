#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_FILTER="$SCRIPT_DIR/doublepass_filter_all.sh"
RUN_SPLIT="$REPO_ROOT/junguo_analysis_for_interpolation/analysis_for_interpolation/split_segments_with_speed_limit_all.sh"
RUN_JUMP="$SCRIPT_DIR/run_detect_jumps_all.sh"
PY_INTERPOLATE="$REPO_ROOT/interpolate.py"

RAW_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories"
FILTER_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v7"
INTERP_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/interpolate_trajs_doublepass_loop_lim20s_inside_v8_csaps"
SEGMENT_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/segmented_trajs_speed_limited_v8_csaps"
JUMP_DIR="/workspace/aircraft_trajectory/team_likable_jelly/reports/jump_reports_segmented_v8_csaps"
DATE_FROM="2022-01-01"
DATE_TO="2022-12-31"
SMOOTH="1e-2"
FILTER_PROCS=24
INTERP_PROCS=24
SPLIT_PROCS=24
JUMP_PROCS=24
MAX_SPEED=600
REQ_COLS="latitude longitude altitude"
MAX_DT=20
MIN_POINTS=30
MIN_DURATION=120
FORCE_FILTER=0
FORCE_INTERP=0
FORCE_SPLIT=0
FORCE_JUMP=0
SKIP_FILTER=0
SKIP_INTERP=0
SKIP_SPLIT=0
SKIP_JUMP=0
DRYRUN=0

usage() {
  cat <<'USAGE'
用法: bash run_full_pipeline_with_interpolate.sh [选项]
  --raw-dir DIR             原始 raw 数据目录 (默认: ${RAW_DIR})
  --filtered-dir DIR        过滤输出目录 (默认: ${FILTER_DIR})
  --interpolated-dir DIR    interpolate.py 输出目录 (默认: ${INTERP_DIR})
  --segmented-dir DIR       切段输出目录 (默认: ${SEGMENT_DIR})
  --jump-dir DIR            跳变检测输出目录 (默认: ${JUMP_DIR})
  --from DATE               起始日期 YYYY-MM-DD (默认: ${DATE_FROM})
  --to DATE                 截止日期 YYYY-MM-DD (默认: ${DATE_TO})
  --smooth VAL              csaps 平滑系数 (默认: ${SMOOTH})
  --filter-procs N          过滤阶段并发 (默认: ${FILTER_PROCS})
  --interpolate-procs N     插值阶段并发 (默认: ${INTERP_PROCS})
  --split-procs N           切段阶段并发 (默认: ${SPLIT_PROCS})
  --jump-procs N            跳变检测并发 (默认: ${JUMP_PROCS})
  --max-speed MPS           切段阶段速度阈值 (默认: ${MAX_SPEED})
  --max-dt SEC              切段阶段最大间隔 (默认: ${MAX_DT})
  --min-points N            切段最小点数 (默认: ${MIN_POINTS})
  --min-duration SEC        切段最小时长 (默认: ${MIN_DURATION})
  --skip-filter             跳过过滤阶段
  --skip-interpolate        跳过插值阶段
  --skip-split              跳过切段阶段
  --skip-jump               跳过跳变检测阶段
  --force-filter            即使输出存在也重跑过滤阶段
  --force-interpolate       即使输出存在也重跑插值阶段
  --force-split             即使输出存在也重跑切段阶段
  --force-jump              即使输出存在也重跑跳变检测阶段
  --dry-run                 仅打印各阶段命令
  -h|--help                 显示帮助
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw-dir) RAW_DIR="$2"; shift 2;;
    --filtered-dir) FILTER_DIR="$2"; shift 2;;
    --interpolated-dir) INTERP_DIR="$2"; shift 2;;
    --segmented-dir) SEGMENT_DIR="$2"; shift 2;;
    --jump-dir) JUMP_DIR="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --smooth) SMOOTH="$2"; shift 2;;
    --filter-procs) FILTER_PROCS="$2"; shift 2;;
    --interpolate-procs) INTERP_PROCS="$2"; shift 2;;
    --split-procs) SPLIT_PROCS="$2"; shift 2;;
    --jump-procs) JUMP_PROCS="$2"; shift 2;;
    --max-speed) MAX_SPEED="$2"; shift 2;;
    --max-dt) MAX_DT="$2"; shift 2;;
    --min-points) MIN_POINTS="$2"; shift 2;;
    --min-duration) MIN_DURATION="$2"; shift 2;;
    --skip-filter) SKIP_FILTER=1; shift;;
    --skip-interpolate) SKIP_INTERP=1; shift;;
    --skip-split) SKIP_SPLIT=1; shift;;
    --skip-jump) SKIP_JUMP=1; shift;;
    --force-filter) FORCE_FILTER=1; shift;;
    --force-interpolate) FORCE_INTERP=1; shift;;
    --force-split) FORCE_SPLIT=1; shift;;
    --force-jump) FORCE_JUMP=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

[[ -f "$RUN_FILTER" ]] || { echo "❌ 找不到过滤脚本: $RUN_FILTER"; exit 1; }
[[ -f "$RUN_SPLIT" ]] || { echo "❌ 找不到切段脚本: $RUN_SPLIT"; exit 1; }
[[ -f "$RUN_JUMP" ]] || { echo "❌ 找不到跳变脚本: $RUN_JUMP"; exit 1; }
[[ -f "$PY_INTERPOLATE" ]] || { echo "❌ 找不到 interpolate.py: $PY_INTERPOLATE"; exit 1; }

run_filter_stage() {
  if [[ "$SKIP_FILTER" == "1" ]]; then
    echo "⏭️  跳过过滤阶段"; return
  fi
  echo "[1/4] doublepass 过滤"
  local cmd=(bash "$RUN_FILTER" --input-dir "$RAW_DIR" --output-dir "$FILTER_DIR" --procs "$FILTER_PROCS" --from "$DATE_FROM" --to "$DATE_TO")
  [[ "$FORCE_FILTER" == "1" ]] && cmd+=(--force)
  [[ "$DRYRUN" == "1" ]] && cmd+=(--dry-run)
  echo "命令: ${cmd[*]}"
  if [[ "$DRYRUN" != "1" ]]; then
    "${cmd[@]}"
  fi
}

run_interpolate_stage() {
  if [[ "$SKIP_INTERP" == "1" ]]; then
    echo "⏭️  跳过插值阶段"; return
  fi
  mkdir -p "$INTERP_DIR" "$INTERP_DIR/.logs"
  mapfile -t DAYS < <(ls "$FILTER_DIR"/2022-*.parquet 2>/dev/null | sed 's#.*/##; s/.parquet$//' | sort)
  if [[ ${#DAYS[@]} -eq 0 ]]; then
    echo "❌ 插值阶段未在 $FILTER_DIR 找到 2022-*.parquet"; exit 1
  fi
  local TARGETS=()
  for d in "${DAYS[@]}"; do
    [[ -n "$DATE_FROM" && "$d" < "$DATE_FROM" ]] && continue
    [[ -n "$DATE_TO" && "$d" > "$DATE_TO" ]] && continue
    if [[ "$FORCE_INTERP" != "1" && -f "$INTERP_DIR/complete_${d}.parquet" ]]; then
      echo "↪︎ 插值阶段跳过已存在 complete_${d}.parquet"
      continue
    fi
    TARGETS+=("$d")
  done
  if [[ ${#TARGETS[@]} -eq 0 ]]; then
    echo "✅ 插值阶段无需处理"; return
  fi
  echo "[2/4] interpolate.py (smooth=${SMOOTH})"
  export PY_INTERPOLATE SMOOTH FILTER_DIR INTERP_DIR DRYRUN
  run_one_interpolate() {
    local d="$1"
    local in_f="$FILTER_DIR/${d}.parquet"
    local out_f="$INTERP_DIR/complete_${d}.parquet"
    local log="$INTERP_DIR/.logs/${d}.log"
    echo "▶️  插值 $d" | tee "$log"
    if [[ "$DRYRUN" == "1" ]]; then
      echo "DRYRUN python $PY_INTERPOLATE -t_in $in_f -t_out $out_f -smooth $SMOOTH" | tee -a "$log"
      return 0
    fi
    python "$PY_INTERPOLATE" -t_in "$in_f" -t_out "$out_f" -smooth "$SMOOTH" >>"$log" 2>&1 || { echo "❌ 插值失败: $d (详见 $log)"; return 1; }
  }
  export -f run_one_interpolate
  printf "%s\n" "${TARGETS[@]}" | xargs -I{} -P "$INTERP_PROCS" bash -c 'run_one_interpolate "$@"' _ {}
}

run_split_stage() {
  if [[ "$SKIP_SPLIT" == "1" ]]; then
    echo "⏭️  跳过切段阶段"; return
  fi
  echo "[3/4] 切段 (max_speed=${MAX_SPEED}m/s)"
  local cmd=(bash "$RUN_SPLIT" --input-dir "$INTERP_DIR" --output-dir "$SEGMENT_DIR" --procs "$SPLIT_PROCS" --required-cols $REQ_COLS --max-dt "$MAX_DT" --max-speed "$MAX_SPEED" --min-points "$MIN_POINTS" --min-duration "$MIN_DURATION" --from "$DATE_FROM" --to "$DATE_TO")
  [[ "$FORCE_SPLIT" == "1" ]] && cmd+=(--force)
  [[ "$DRYRUN" == "1" ]] && cmd+=(--dry-run)
  echo "命令: ${cmd[*]}"
  if [[ "$DRYRUN" != "1" ]]; then
    "${cmd[@]}"
  fi
}

run_jump_stage() {
  if [[ "$SKIP_JUMP" == "1" ]]; then
    echo "⏭️  跳过跳变检测"; return
  fi
  echo "[4/4] 跳变检测"
  local cmd=(bash "$RUN_JUMP" --data-dir "$SEGMENT_DIR" --out-dir "$JUMP_DIR" --procs "$JUMP_PROCS" --from "$DATE_FROM" --to "$DATE_TO")
  [[ "$FORCE_JUMP" == "1" ]] && cmd+=(--force)
  [[ "$DRYRUN" == "1" ]] && cmd+=(--dry-run)
  echo "命令: ${cmd[*]}"
  if [[ "$DRYRUN" != "1" ]]; then
    "${cmd[@]}"
  fi
}

run_filter_stage
run_interpolate_stage
run_split_stage
run_jump_stage

echo "✅ 全流水线完成"
