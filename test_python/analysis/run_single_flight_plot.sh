#!/usr/bin/env bash
set -euo pipefail

DATE="${1:-2022-10-12}"
FLIGHT_ID="${2:-256135680}"
STRATEGY="${3:-classic_dp_loop}"
RAW_DIR="${RAW_DIR:-/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories}"
OUT_DIR="${OUT_DIR:-reports/single_flight}"
ENV_NAME="${ENV_NAME:-opensky}"
OUT_PDF="${OUT_DIR}/plot_${DATE}_${FLIGHT_ID}_${STRATEGY}.pdf"
mkdir -p "$OUT_DIR"
CMD=(python test_python/analysis/filter_and_plot_single_flight.py \
  --date "$DATE" \
  --flight-id "$FLIGHT_ID" \
  --strategy "$STRATEGY" \
  --raw-dir "$RAW_DIR" \
  --out-pdf "$OUT_PDF")
if [[ -z "${CONDA_DEFAULT_ENV:-}" || "$CONDA_DEFAULT_ENV" != "$ENV_NAME" ]]; then
  echo "⚠️  当前未处于 $ENV_NAME 环境，将使用 conda run 调用"
  CMD=(conda run -n "$ENV_NAME" "${CMD[@]}")
fi
"${CMD[@]}"
