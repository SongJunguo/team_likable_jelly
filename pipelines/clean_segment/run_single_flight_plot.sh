#!/usr/bin/env bash
set -euo pipefail

PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$PIPELINE_DIR/config.sh"
: "${FILTER_STRATEGY:?FILTER_STRATEGY 未在 config.sh 中定义}"
STRATEGY="$FILTER_STRATEGY"

# DATE="${1:-2022-01-09}"
# FLIGHT_ID="${2:-248916822}"
# DATE="${1:-2022-01-11}"
# FLIGHT_ID="${2:-248959644}"

DATE="${1:-2022-02-17}"
FLIGHT_ID="${2:-249596793}"

RAW_DIR="${RAW_DIR:-${REPO_ROOT}/opensky_2024_PRC_dataset/rawtrajectories}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/reports/single_flight}"
ENV_NAME="${ENV_NAME:-opensky}"
SAVE_PARQUET="${SAVE_PARQUET:-1}"
OUT_PDF="${OUT_DIR}/plot_${DATE}_${FLIGHT_ID}_${STRATEGY}.pdf"
OUT_PARQUET_DIR="${OUT_PARQUET_DIR:-$OUT_DIR}"
OUT_METRICS_PDF="${OUT_METRICS_PDF:-${OUT_DIR}/plot_${DATE}_${FLIGHT_ID}_${STRATEGY}_metrics.pdf}"
mkdir -p "$OUT_DIR"
PY_SCRIPT="$REPO_ROOT/test_python/analysis/filter_and_plot_single_flight.py"
CMD=(python "$PY_SCRIPT" \
  --date "$DATE" \
  --flight-id "$FLIGHT_ID" \
  --strategy "$STRATEGY" \
  --raw-dir "$RAW_DIR" \
  --out-pdf "$OUT_PDF" \
  --metrics-pdf "$OUT_METRICS_PDF")
if [[ "$SAVE_PARQUET" != "0" ]]; then
  mkdir -p "$OUT_PARQUET_DIR"
  OUT_PARQUET="${OUT_PARQUET_DIR}/filtered_${DATE}_${FLIGHT_ID}_${STRATEGY}.parquet"
  CMD+=(--out-parquet "$OUT_PARQUET")
  echo "ℹ️  过滤结果将保存到 $OUT_PARQUET"
fi
echo "ℹ️  轨迹对比 PDF: $OUT_PDF"
echo "ℹ️  速度/加速度 PDF: $OUT_METRICS_PDF"
if [[ -z "${CONDA_DEFAULT_ENV:-}" || "$CONDA_DEFAULT_ENV" != "$ENV_NAME" ]]; then
  echo "⚠️  当前未处于 $ENV_NAME 环境，将使用 conda run 调用"
  CMD=(conda run -n "$ENV_NAME" "${CMD[@]}")
fi
"${CMD[@]}"
