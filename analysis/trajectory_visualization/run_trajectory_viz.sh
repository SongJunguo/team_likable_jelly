#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法:
  bash analysis/trajectory_visualization/run_trajectory_viz.sh --flight-id ID [options] [-- extra_args...]

选项:
  --flight-id ID                     航班 ID（必填）
  --data-dir PATH                    数据目录（默认 interpolated_clean_eu_v5）
  --flight-id-col COL                flight_id 列名（可选）
  --date-from YYYY-MM-DD             起始日期（可选）
  --date-to YYYY-MM-DD               结束日期（可选）
  --out PATH                         输出 PDF 路径（可选）
  --columns COLS                     指定列（可重复或逗号分隔）
  --delta-required-dt-seconds SEC    差分 dt 秒数（默认 1.0）
  --delta-diff-mode {abs|signed}     差分模式（默认 signed）
  --workers N                        并行进程数（可选）
  --batch-size N                     batch_size（可选）
  -h, --help                         显示帮助

说明:
  - 额外参数可通过 "--" 透传给 analysis/trajectory_visualization/plot_trajectory_pdf.py
USAGE
}

DATA_DIR="opensky_2024_PRC_dataset/interpolated_clean_eu_v5"
FLIGHT_ID="248750643"
FLIGHT_ID_COL=""
DATE_FROM="2022-01-01"
DATE_TO="2022-02-28"
OUT_PATH=""
COLUMNS=()
DELTA_DT=""
DELTA_MODE=""
WORKERS=""
BATCH_SIZE=""
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --flight-id)
      FLIGHT_ID="$2"
      shift 2
      ;;
    --data-dir)
      DATA_DIR="$2"
      shift 2
      ;;
    --flight-id-col)
      FLIGHT_ID_COL="$2"
      shift 2
      ;;
    --date-from)
      DATE_FROM="$2"
      shift 2
      ;;
    --date-to)
      DATE_TO="$2"
      shift 2
      ;;
    --out)
      OUT_PATH="$2"
      shift 2
      ;;
    --columns)
      COLUMNS+=("$2")
      shift 2
      ;;
    --delta-required-dt-seconds)
      DELTA_DT="$2"
      shift 2
      ;;
    --delta-diff-mode)
      DELTA_MODE="$2"
      shift 2
      ;;
    --workers)
      WORKERS="$2"
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS=("$@")
      break
      ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [ -z "$FLIGHT_ID" ]; then
  echo "必须指定 --flight-id" >&2
  usage
  exit 2
fi

if [ ! -d "$DATA_DIR" ]; then
  echo "数据目录不存在: $DATA_DIR" >&2
  exit 1
fi

if [ -f /home/neu/miniconda3/etc/profile.d/conda.sh ]; then
  # shellcheck source=/dev/null
  source /home/neu/miniconda3/etc/profile.d/conda.sh
elif [ -f /home/neu/anaconda3/etc/profile.d/conda.sh ]; then
  # shellcheck source=/dev/null
  source /home/neu/anaconda3/etc/profile.d/conda.sh
else
  echo "找不到 conda.sh（/home/neu/miniconda3 或 /home/neu/anaconda3）" >&2
  exit 1
fi

conda activate opensky

args=(
  --data-dir "$DATA_DIR"
  --flight-id "$FLIGHT_ID"
)
if [ -n "$FLIGHT_ID_COL" ]; then
  args+=(--flight-id-col "$FLIGHT_ID_COL")
fi
if [ -n "$DATE_FROM" ]; then
  args+=(--date-from "$DATE_FROM")
fi
if [ -n "$DATE_TO" ]; then
  args+=(--date-to "$DATE_TO")
fi
if [ -n "$OUT_PATH" ]; then
  args+=(--out "$OUT_PATH")
fi
for item in "${COLUMNS[@]}"; do
  args+=(--columns "$item")
done
if [ -n "$DELTA_DT" ]; then
  args+=(--delta-required-dt-seconds "$DELTA_DT")
fi
if [ -n "$DELTA_MODE" ]; then
  args+=(--delta-diff-mode "$DELTA_MODE")
fi
if [ -n "$WORKERS" ]; then
  args+=(--workers "$WORKERS")
fi
if [ -n "$BATCH_SIZE" ]; then
  args+=(--batch-size "$BATCH_SIZE")
fi

python analysis/trajectory_visualization/plot_trajectory_pdf.py "${args[@]}" "${EXTRA_ARGS[@]}"
