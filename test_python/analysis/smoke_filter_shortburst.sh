#!/usr/bin/env bash
set -euo pipefail

# 冒烟测试：仅跑单日过滤（含 FilterShortBurst），并对指定航班出图 Raw vs Filter

DATE="${1:-2022-03-06}"
FID="${2:-249935181}"

RAW_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/rawtrajectories"
FILT_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/classic_filtered_trajectories__shortburst_v1"
OUT_PDF="reports/filter_shortburst_smoketest/plot_raw_vs_filter_${DATE}_${FID}.pdf"

mkdir -p "$FILT_DIR" "$(dirname "$OUT_PDF")"

echo "[1/2] Filtering (classic_shortburst w/ ShortBurst): $DATE"
python filter_trajs.py \
  -t_in  "$RAW_DIR/${DATE}.parquet" \
  -t_out "$FILT_DIR/${DATE}.parquet" \
  -strategy classic_shortburst

echo "[2/2] Plot Raw vs Filter for flight_id=$FID"
python test_python/analysis/plot_flight_before_after_filter.py \
  --date "$DATE" \
  --flight-id "$FID" \
  --raw-dir  "$RAW_DIR" \
  --filt-dir "$FILT_DIR" \
  --out-pdf  "$OUT_PDF"

echo "✅ Done. PDF: $OUT_PDF"
