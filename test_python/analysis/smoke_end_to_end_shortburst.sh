#!/usr/bin/env bash
set -euo pipefail

# 一键冒烟：
# - 过滤单日（含 FilterShortBurst）→ 生成单日 classic_filtered_...__shortburst_v1
# - 绘制 Raw vs Filter PDF
# - 对 segmented_v2 做 post-clean（短簇剔除）→ 生成 segmented_v3，并绘制 before/after PDF
#
# 用法：
#   conda activate opensky
#   bash test_python/analysis/smoke_end_to_end_shortburst.sh 2022-03-06 249935181

DATE="${1:-2022-03-06}"
FID="${2:-249935181}"

ROOT="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset"
RAW_DIR="$ROOT/rawtrajectories"
FILT_DIR="$ROOT/classic_filtered_trajectories__shortburst_v1"
SEG_V2_DIR="$ROOT/segmented_trajectories_v2_lim20s_inside"
SEG_V3_DIR="$ROOT/segmented_trajectories_v3_postclean"

PLOT_FILTER_DIR="reports/filter_shortburst_smoketest"
PLOT_POSTCLEAN_DIR="reports/postclean_plots"

mkdir -p "$FILT_DIR" "$SEG_V3_DIR" "$PLOT_FILTER_DIR" "$PLOT_POSTCLEAN_DIR"

echo "[1/3] Filtering (classic_shortburst + ShortBurst): $DATE"
python -m pipelines.clean_segment.filter_trajs \
  -t_in  "$RAW_DIR/${DATE}.parquet" \
  -t_out "$FILT_DIR/${DATE}.parquet" \
  -strategy classic_shortburst

echo "[2/3] Plot Raw vs Filter for flight_id=$FID"
OUT1="$PLOT_FILTER_DIR/plot_raw_vs_filter_${DATE}_${FID}.pdf"
python test_python/analysis/plot_flight_before_after_filter.py \
  --date "$DATE" \
  --flight-id "$FID" \
  --raw-dir  "$RAW_DIR" \
  --filt-dir "$FILT_DIR" \
  --out-pdf  "$OUT1"

echo "[3/3] Post-clean segmented_v2 → segmented_v3 (and plot before/after)"
python legacy/analysis_for_interpolation/post_segment_short_burst_clean.py \
  --input-dir "$SEG_V2_DIR" \
  --output-dir "$SEG_V3_DIR" \
  --from "$DATE" --to "$DATE" \
  --procs 8 \
  --plot-flight-ids "$FID" \
  --plot-dir "$PLOT_POSTCLEAN_DIR"

echo
echo "✅ Done"
echo "  Filtered file:   $FILT_DIR/${DATE}.parquet"
echo "  Raw vs Filter:   $OUT1"
echo "  Seg v3 (day):    $SEG_V3_DIR/segmented_v3_${DATE}.parquet"
echo "  Post-clean PDFs: $PLOT_POSTCLEAN_DIR/clean_segmented_${DATE}_${FID}.pdf"
