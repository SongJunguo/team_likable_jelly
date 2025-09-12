#!/usr/bin/env bash
set -euo pipefail

# One-shot runner for region analysis (EU/US) using Polars
# Defaults are tailored for this repo layout and your conda env "opensky".

RAW_DIR="opensky_2024_PRC_dataset/rawtrajectories"
TMP_DIR="junguo_analysis_for_opensky2022/tmp_region_counts"
OUT_PREFIX="junguo_analysis_for_opensky2022/region_summary"
MAJ_THR="0.0"          # majority threshold (e.g., 0.6)
LIMIT=""               # number of days to process; empty = all
THREADS="80"           # POLARS_MAX_THREADS
CONDA_ENV="opensky"    # conda env name

usage() {
  cat <<EOF
Usage: bash junguo_analysis_for_opensky2022/run_region_analysis.sh [options]

Options:
  -r <raw_dir>        Path to raw parquet dir (default: ${RAW_DIR})
  -t <tmp_dir>        Path for per-file partial outputs (default: ${TMP_DIR})
  -o <out_prefix>     Output prefix for summary files (default: ${OUT_PREFIX})
  -m <threshold>      Majority threshold in [0,1] (default: ${MAJ_THR})
  -l <limit>          Only process first N files (default: all)
  -j <threads>        POLARS_MAX_THREADS (default: ${THREADS})
  -e <conda_env>      Conda env to activate (default: ${CONDA_ENV})
  -h                  Show this help

Examples:
  # Quick dry run on 2 days
  bash junguo_analysis_for_opensky2022/run_region_analysis.sh -l 2

  # Full run, 60% majority rule
  bash junguo_analysis_for_opensky2022/run_region_analysis.sh -m 0.6

EOF
}

while getopts ":r:t:o:m:l:j:e:h" opt; do
  case "$opt" in
    r) RAW_DIR="$OPTARG" ;;
    t) TMP_DIR="$OPTARG" ;;
    o) OUT_PREFIX="$OPTARG" ;;
    m) MAJ_THR="$OPTARG" ;;
    l) LIMIT="$OPTARG" ;;
    j) THREADS="$OPTARG" ;;
    e) CONDA_ENV="$OPTARG" ;;
    h) usage; exit 0 ;;
    :) echo "Error: -$OPTARG requires an argument" >&2; usage; exit 2 ;;
    \?) echo "Error: invalid option -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

# Try to source conda and activate env, if available
if command -v conda >/dev/null 2>&1; then
  CONDA_BASE=$(conda info --base 2>/dev/null || true)
  if [ -n "${CONDA_BASE:-}" ] && [ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]; then
    # shellcheck source=/dev/null
    . "$CONDA_BASE/etc/profile.d/conda.sh"
    conda activate "$CONDA_ENV" || true
  fi
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
  # shellcheck source=/dev/null
  . "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV" || true
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
  # shellcheck source=/dev/null
  . "/opt/conda/etc/profile.d/conda.sh"
  conda activate "$CONDA_ENV" || true
fi

export POLARS_MAX_THREADS="$THREADS"

echo "== Region analysis config =="
echo "RAW_DIR        : $RAW_DIR"
echo "TMP_DIR        : $TMP_DIR"
echo "OUT_PREFIX     : $OUT_PREFIX"
echo "MAJ_THR        : $MAJ_THR"
echo "LIMIT          : ${LIMIT:-<all>}"
echo "THREADS        : $THREADS"
echo "CONDA_ENV      : $CONDA_ENV"
echo "Python         : $(command -v python || true)"
python -V || true

set -x
if [ -n "${LIMIT}" ]; then
  python junguo_analysis_for_opensky2022/analyze_regions.py \
    --raw-dir "$RAW_DIR" \
    --tmp-dir "$TMP_DIR" \
    --out "$OUT_PREFIX" \
    --majority-threshold "$MAJ_THR" \
    --limit "$LIMIT"
else
  python junguo_analysis_for_opensky2022/analyze_regions.py \
    --raw-dir "$RAW_DIR" \
    --tmp-dir "$TMP_DIR" \
    --out "$OUT_PREFIX" \
    --majority-threshold "$MAJ_THR"
fi
set +x

echo "== Done. Outputs =="
echo "Per-flight CSV : ${OUT_PREFIX}_per_flight.csv"
echo "Summary JSON   : ${OUT_PREFIX}_summary.json"
echo "Summary CSV    : ${OUT_PREFIX}_summary.csv"

