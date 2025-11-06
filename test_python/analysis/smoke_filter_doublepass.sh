#!/usr/bin/env bash
set -euo pipefail

# 冒烟测试：双次三点投票（classic_dp）+ Raw vs Filter 出图

DATE="${1:-2022-03-06}"
FID="${2:-249935181}"

ROOT="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset"
RAW_DIR="$ROOT/rawtrajectories"
FILT_DIR="$ROOT/classic_filtered_trajectories__doublepass_v1"
OUT_PDF="reports/filter_doublepass_smoketest/plot_raw_vs_filter_${DATE}_${FID}.pdf"

mkdir -p "$FILT_DIR" "$(dirname "$OUT_PDF")"

echo "[1/2] Filtering (classic_dp double-pass): $DATE"
python filter_trajs.py \
  -t_in  "$RAW_DIR/${DATE}.parquet" \
  -t_out "$FILT_DIR/${DATE}.parquet" \
  -strategy classic_dp

echo "[2/2] Plot Raw vs Filter for flight_id=$FID"
python test_python/analysis/plot_flight_before_after_filter.py \
  --date "$DATE" \
  --flight-id "$FID" \
  --raw-dir  "$RAW_DIR" \
  --filt-dir "$FILT_DIR" \
  --out-pdf  "$OUT_PDF"

echo "✅ Done. PDF: $OUT_PDF"

