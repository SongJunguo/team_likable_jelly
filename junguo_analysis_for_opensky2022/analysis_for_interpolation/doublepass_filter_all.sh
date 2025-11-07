#!/usr/bin/env bash
set -euo pipefail

# 批量运行“二次三点投票（classic_dp_loop）”过滤，生成双过滤后的日文件。
# 特点：
# - 并行按天处理（HDD 建议并发 6–8）
# - 已存在的输出默认跳过（--force 可覆盖重跑）
# - 起止日期可筛选；每日日志写入 .logs
#
# 用法示例：
#   conda activate opensky
#   bash junguo_analysis_for_opensky2022/analysis_for_interpolation/doublepass_filter_all.sh \
#     --input-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories \
#     --output-dir /workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v1 \
#     --procs 8 --from 2022-01-01 --to 2022-12-31

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

IN_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories"
OUT_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v1"
PROCS=32
DATE_FROM="2022-01-01"
DATE_TO="2022-12-31"
FORCE=0
DRYRUN=0
STRATEGY="classic_dp_loop"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir) IN_DIR="$2"; shift 2;;
    --output-dir) OUT_DIR="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --from) DATE_FROM="$2"; shift 2;;
    --to) DATE_TO="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --strategy) STRATEGY="$2"; shift 2;;
    -h|--help)
      sed -n '1,80p' "$0"; exit 0;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

mkdir -p "$OUT_DIR" "$OUT_DIR/.logs"

mapfile -t DLIST < <(ls "$IN_DIR"/2022-*.parquet 2>/dev/null | sed 's#.*/##; s/.parquet$//' | sort)
if [[ ${#DLIST[@]} -eq 0 ]]; then
  echo "❌ 未在 $IN_DIR 找到 2022-*.parquet"; exit 1
fi

FILTERED=()
for d in "${DLIST[@]}"; do
  if [[ -n "$DATE_FROM" && "$d" < "$DATE_FROM" ]]; then continue; fi
  if [[ -n "$DATE_TO" && "$d" > "$DATE_TO" ]]; then continue; fi
  if [[ "$FORCE" != "1" && -f "$OUT_DIR/${d}.parquet" ]]; then
    echo "↪︎ 跳过已存在: ${d}.parquet"; continue
  fi
  FILTERED+=("$d")
done

if [[ ${#FILTERED[@]} -eq 0 ]]; then
  echo "✅ 无需处理：符合条件的日期文件均已存在输出（或筛选为空）。"; exit 0
fi

echo "📅 待处理文件数: ${#FILTERED[@]}"

run_one() {
  local d="$1"
  local in_f="$IN_DIR/${d}.parquet"
  local out_f="$OUT_DIR/${d}.parquet"
  local log="$OUT_DIR/.logs/${d}.log"
  echo "▶️  $d → $out_f" | tee "$log"
  if [[ "$DRYRUN" == "1" ]]; then
    echo "DRYRUN python filter_trajs.py -t_in $in_f -t_out $out_f -strategy $STRATEGY" | tee -a "$log"
    return 0
  fi
  python filter_trajs.py -t_in "$in_f" -t_out "$out_f" -strategy "$STRATEGY" >>"$log" 2>&1 \
    || { echo "❌ 失败: $d (详见 $log)"; return 1; }
}

export -f run_one
export IN_DIR OUT_DIR DRYRUN STRATEGY

printf "%s\n" "${FILTERED[@]}" | xargs -I{} -P "$PROCS" bash -c 'run_one "$@"' _ {}

echo "✅ 双次投票过滤完成。输出目录: $OUT_DIR"
