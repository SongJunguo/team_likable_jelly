#!/usr/bin/env bash
set -euo pipefail

# 一键批量重生成 complete 数据（使用“仅填内部洞+20s限洞”逻辑）
# 不会覆盖原目录，支持并行与断点续跑（已存在的目标文件将跳过，除非 --force）。
#
# 用法示例：
#   bash junguo_analysis_for_opensky2022/analysis_for_interpolation/regenerate_complete_all.sh \
#     --input-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories \
#     --output-dir /workspace/aircraft_trajectory/team_likable_jelly/complete_high_quality_trajectories__v2_lim20s_inside \
#     --ids-file high_quality_flight_ids.txt \
#     --procs 6 --from 2022-01-01 --to 2022-12-31
#
# 依赖：
#   - Python 可执行：junguo_analysis_for_opensky2022/analysis_for_interpolation/regenerate_complete_sample.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_RUN="$SCRIPT_DIR/regenerate_complete_sample.py"

IN_DIR=/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v7
OUT_DIR=/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/interpolate_trajs_doublepass_loop_lim20s_inside_v8
IDS_FILE=/workspace/aircraft_trajectory/team_likable_jelly/high_quality_flight_ids.txt
PROCS=8
DATE_FROM=2022-12-28
DATE_TO=2022-12-28
FORCE=0
DRYRUN="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir) IN_DIR="$2"; shift 2;;
    --output-dir) OUT_DIR="$2"; shift 2;;
    --ids-file) IDS_FILE="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --force) FORCE="1"; shift;;
    --dry-run) DRYRUN="1"; shift;;
    -h|--help)
      sed -n '1,80p' "$0"; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if [[ -z "$IN_DIR" || -z "$OUT_DIR" ]]; then
  echo "❌ 必须指定 --input-dir 与 --output-dir"; exit 1
fi

if [[ ! -f "$PY_RUN" ]]; then
  echo "❌ 找不到 Python 脚本: $PY_RUN"; exit 1
fi

mkdir -p "$OUT_DIR" "$OUT_DIR/.logs"

# 构建日期列表
mapfile -t DLIST < <(ls "$IN_DIR"/2022-*.parquet 2>/dev/null | sed 's#.*/##; s/.parquet$//' | sort)
if [[ ${#DLIST[@]} -eq 0 ]]; then
  echo "❌ 在 $IN_DIR 未找到 2022-*.parquet"; exit 1
fi

FILTERED=()
for d in "${DLIST[@]}"; do
  # 过滤起止日期（字符串比较对 YYYY-MM-DD 成立）
  if [[ -n "$DATE_FROM" && "$d" < "$DATE_FROM" ]]; then continue; fi
  if [[ -n "$DATE_TO" && "$d" > "$DATE_TO" ]]; then continue; fi
  # 跳过已存在（除非 --force）
  if [[ "$FORCE" != "1" && -f "$OUT_DIR/complete_${d}.parquet" ]]; then
    echo "↪︎ 跳过已存在: complete_${d}.parquet"
    continue
  fi
  FILTERED+=("$d")
done

if [[ ${#FILTERED[@]} -eq 0 ]]; then
  echo "✅ 无需处理：符合条件的日期文件均已存在输出（或起止日期筛空）。"; exit 0
fi

echo "📅 待处理文件数: ${#FILTERED[@]}"; echo

run_one() {
  local d="$1"
  local log="$OUT_DIR/.logs/${d}.log"
  echo "▶️  $d  →  $log"
  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN python $PY_RUN --date $d --input_dir $IN_DIR --output_dir $OUT_DIR --ids_file $IDS_FILE" | tee "$log"
    return 0
  fi
  python "$PY_RUN" \
    --date "$d" \
    --input_dir "$IN_DIR" \
    --output_dir "$OUT_DIR" \
    --ids_file "$IDS_FILE" \
    >"$log" 2>&1 || { echo "❌ 失败: $d (详见 $log)"; return 1; }
}

export -f run_one
export PY_RUN IN_DIR OUT_DIR IDS_FILE DRYRUN

printf "%s\n" "${FILTERED[@]}" | xargs -I{} -P "$PROCS" bash -c 'run_one "$@"' _ {}

echo
echo "✅ 全部任务已提交完成。输出目录: $OUT_DIR"
