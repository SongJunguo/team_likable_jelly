#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法:
  bash test_python/delta_scan/run_delta_scan.sh [options] [-- extra_args...]

选项:
  --data-dir PATH                 数据目录（默认 interpolated_clean_eu_v5）
  --date-from YYYY-MM-DD          起始日期（可选）
  --date-to YYYY-MM-DD            结束日期（可选）
  --columns COLS                  指定列（可重复或逗号分隔）
  --quantiles QLIST               分位数列表（默认 0.95,0.99,0.995,0.999,0.9999）
  --sample-size N                 每列抽样上限（默认 2000000）
  --plot-pdf                      生成 |delta| 分布 PDF
  --pdf-out PATH                  PDF 输出路径（可选）
  --quantiles-out PATH            分位数输出 CSV（可选）
  --workers N                     并行进程数（可选）
  --batch-size N                  batch_size（可选）
  --seed N                        随机种子（可选）
  --hist-bins N                   PDF 直方图 bins（可选）
  -h, --help                      显示帮助

说明:
  - 额外参数可通过 "--" 透传给 test_python/delta_scan/scan_delta_intervals.py
USAGE
}

DATA_DIR="opensky_2024_PRC_dataset/interpolated_clean_eu_v5"
DATE_FROM=""
DATE_TO=""
COLUMNS=()
QUANTILES=""
SAMPLE_SIZE="2000000"
PLOT_PDF="false"
PDF_OUT=""
QUANTILES_OUT=""
WORKERS=""
BATCH_SIZE=""
SEED=""
HIST_BINS=""
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir)
      DATA_DIR="$2"
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
    --columns)
      COLUMNS+=("$2")
      shift 2
      ;;
    --quantiles)
      QUANTILES="$2"
      shift 2
      ;;
    --sample-size)
      SAMPLE_SIZE="$2"
      shift 2
      ;;
    --plot-pdf)
      PLOT_PDF="true"
      shift 1
      ;;
    --pdf-out)
      PDF_OUT="$2"
      shift 2
      ;;
    --quantiles-out)
      QUANTILES_OUT="$2"
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
    --seed)
      SEED="$2"
      shift 2
      ;;
    --hist-bins)
      HIST_BINS="$2"
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
  --sample-size "$SAMPLE_SIZE"
)
if [ -n "$DATE_FROM" ]; then
  args+=(--date-from "$DATE_FROM")
fi
if [ -n "$DATE_TO" ]; then
  args+=(--date-to "$DATE_TO")
fi
for item in "${COLUMNS[@]}"; do
  args+=(--columns "$item")
done
if [ -n "$QUANTILES" ]; then
  args+=(--quantiles "$QUANTILES")
fi
if [ "$PLOT_PDF" = "true" ]; then
  args+=(--plot-pdf)
fi
if [ -n "$PDF_OUT" ]; then
  args+=(--pdf-out "$PDF_OUT")
fi
if [ -n "$QUANTILES_OUT" ]; then
  args+=(--quantiles-out "$QUANTILES_OUT")
fi
if [ -n "$WORKERS" ]; then
  args+=(--workers "$WORKERS")
fi
if [ -n "$BATCH_SIZE" ]; then
  args+=(--batch-size "$BATCH_SIZE")
fi
if [ -n "$SEED" ]; then
  args+=(--seed "$SEED")
fi
if [ -n "$HIST_BINS" ]; then
  args+=(--hist-bins "$HIST_BINS")
fi

python test_python/delta_scan/scan_delta_intervals.py "${args[@]}" "${EXTRA_ARGS[@]}"
