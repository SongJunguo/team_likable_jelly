#!/usr/bin/env bash
set -euo pipefail

source clean_segment_pipeline/config.sh
export STRATEGY="clean_segment_interp" #"classic_dp_loop"  #"clean_segment_interp"  # 新策略名
# export MAX_SPEED_MPS=3000.0        # 速度阈值（可调：550或600）单位 m/s
# export MAX_ACCEL_MPS2=1000.0      # 加速度阈值
# export ALT_DERIV_FIRST_FTPS=201   # 高度一阶导阈值（ft/s）
# export ALT_DERIV_SECOND_FTPS2=51  # 高度二阶导阈值（ft/s²）
# export VOTE_THRESHOLD=2            # 投票阈值（≥2票才删除）

DATE="${1:-2022-01-07}"
FLIGHT_ID="${2:-248867985}"
# STRATEGY="${3:-clean_segment_interp}"
RAW_DIR="${RAW_DIR:-/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories}"
OUT_DIR="${OUT_DIR:-reports/single_flight}"
ENV_NAME="${ENV_NAME:-opensky}"
SAVE_PARQUET="${SAVE_PARQUET:-1}"
OUT_PDF="${OUT_DIR}/plot_${DATE}_${FLIGHT_ID}_${STRATEGY}.pdf"
OUT_PARQUET_DIR="${OUT_PARQUET_DIR:-$OUT_DIR}"
OUT_METRICS_PDF="${OUT_METRICS_PDF:-${OUT_DIR}/plot_${DATE}_${FLIGHT_ID}_${STRATEGY}_metrics.pdf}"
mkdir -p "$OUT_DIR"
CMD=(python test_python/analysis/filter_and_plot_single_flight.py \
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
