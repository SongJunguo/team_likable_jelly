#!/usr/bin/env bash
set -euo pipefail

# Summary-only runner: recompute the final JSON/CSV from existing per-file partials
# without reprocessing the raw parquet files.

TMP_DIR="junguo_analysis_for_opensky2022/tmp_region_counts"
OUT_PREFIX="junguo_analysis_for_opensky2022/region_summary"
MAJ_THR="0.0"
THREADS="80"
CONDA_ENV="opensky"

usage() {
  cat <<EOF
Usage: bash junguo_analysis_for_opensky2022/summarize_region_analysis.sh [options]

Options:
  -t <tmp_dir>     Path to per-file partial outputs (default: ${TMP_DIR})
  -o <out_prefix>  Output prefix for summary files (default: ${OUT_PREFIX})
  -m <threshold>   Majority threshold in [0,1] (default: ${MAJ_THR})
  -j <threads>     POLARS_MAX_THREADS (default: ${THREADS})
  -e <conda_env>   Conda env to activate (default: ${CONDA_ENV})
  -h               Show this help

Examples:
  bash junguo_analysis_for_opensky2022/summarize_region_analysis.sh
  bash junguo_analysis_for_opensky2022/summarize_region_analysis.sh -m 0.6
EOF
}

while getopts ":t:o:m:j:e:h" opt; do
  case "$opt" in
    t) TMP_DIR="$OPTARG" ;;
    o) OUT_PREFIX="$OPTARG" ;;
    m) MAJ_THR="$OPTARG" ;;
    j) THREADS="$OPTARG" ;;
    e) CONDA_ENV="$OPTARG" ;;
    h) usage; exit 0 ;;
    :) echo "Error: -$OPTARG requires an argument" >&2; usage; exit 2 ;;
    \?) echo "Error: invalid option -$OPTARG" >&2; usage; exit 2 ;;
  esac
done

# Activate conda env if available
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

echo "== Summary-only config =="
echo "TMP_DIR     : $TMP_DIR"
echo "OUT_PREFIX  : $OUT_PREFIX"
echo "MAJ_THR     : $MAJ_THR"
echo "THREADS     : $THREADS"
echo "CONDA_ENV   : $CONDA_ENV"
echo "Python      : $(command -v python || true)"
python -V || true

set -x
python - <<'PY'
from junguo_analysis_for_opensky2022.analyze_regions import summarize_all
import os

tmp_dir = os.environ.get('TMP_DIR_OVERRIDE', None)
out_prefix = os.environ.get('OUT_PREFIX_OVERRIDE', None)
maj = float(os.environ.get('MAJ_THR_OVERRIDE', '0.0'))

if tmp_dir is None or out_prefix is None:
    # fall back to argv passed via wrapper
    import sys
    tmp_dir = sys.argv[1]
    out_prefix = sys.argv[2]

partials_glob = os.path.join(tmp_dir, 'region_counts_*.parquet')
summary = summarize_all(partials_glob, out_prefix, majority_threshold=maj)
print(summary)
PY
"$TMP_DIR" "$OUT_PREFIX"
set +x

echo "== Done. Outputs =="
echo "Per-flight CSV : ${OUT_PREFIX}_per_flight.csv"
echo "Summary JSON   : ${OUT_PREFIX}_summary.json"
echo "Summary CSV    : ${OUT_PREFIX}_summary.csv"

