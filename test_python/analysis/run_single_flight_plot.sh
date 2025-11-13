#!/usr/bin/env bash
set -euo pipefail

source clean_segment_pipeline/config.sh
# export FILTER_STRATEGY="clean_segment_interp"  # 新策略名
# export MAX_SPEED_MPS=1000.0        # 速度阈值（可调：550或600）单位 m/s
# export MAX_ACCEL_MPS2=15.0      # 加速度阈值
# export ALT_DERIV_FIRST_FTPS=201   # 高度一阶导阈值（ft/s）
# export ALT_DERIV_SECOND_FTPS2=51  # 高度二阶导阈值（ft/s²）
# export VOTE_THRESHOLD=2            # 投票阈值（≥2票才删除）

DATE="${1:-2022-01-01}"
FLIGHT_ID="${2:-248750611}"
STRATEGY="${3:-clean_segment_interp}"
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
