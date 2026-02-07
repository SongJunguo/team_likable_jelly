#!/usr/bin/env bash
set -euo pipefail

# ================================
# 可调参数（按需修改）
# ================================
CONDA_ENV="opensky"

SOURCE_FILE="opensky_2024_PRC_dataset/interpolated_clean_eu_v5/interpolated_2022-01-30.parquet"
FLIGHT_ID="2492626310092"
T_START="2022-01-30T09:26:47Z"
T_END="2022-01-30T09:37:27Z"

INTERP_DIR="opensky_2024_PRC_dataset/interpolated_clean_eu_v5"
META_PARQUET="opensky_2024_PRC_dataset/flights/challenge_set.parquet"
OUTPUT_DIR="analysis/same_route_similarity/output"

RESAMPLE_POINTS="400"
MIN_TRAJ_POINTS="20"
TOP_K_WINDOW="5"
TOP_K_APP95="5"
WORKERS="14"

# ================================
# 固定执行逻辑（一般无需修改）
# ================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PY_SCRIPT="${SCRIPT_DIR}/analyze_single_target_same_flight.py"

resolve_path() {
  local p="$1"
  if [[ "${p}" = /* ]]; then
    printf "%s" "${p}"
  else
    printf "%s/%s" "${PROJECT_ROOT}" "${p}"
  fi
}

SOURCE_FILE_ABS="$(resolve_path "${SOURCE_FILE}")"
INTERP_DIR_ABS="$(resolve_path "${INTERP_DIR}")"
META_PARQUET_ABS="$(resolve_path "${META_PARQUET}")"
OUTPUT_DIR_ABS="$(resolve_path "${OUTPUT_DIR}")"

if [[ ! -f "${PY_SCRIPT}" ]]; then
  echo "[ERROR] Python脚本不存在: ${PY_SCRIPT}" >&2
  exit 1
fi

if [[ ! -f "${SOURCE_FILE_ABS}" ]]; then
  echo "[ERROR] source_file不存在: ${SOURCE_FILE_ABS}" >&2
  exit 1
fi

if [[ ! -f "${META_PARQUET_ABS}" ]]; then
  echo "[ERROR] meta_parquet不存在: ${META_PARQUET_ABS}" >&2
  exit 1
fi

if [[ ! -d "${INTERP_DIR_ABS}" ]]; then
  echo "[ERROR] interp_dir不存在: ${INTERP_DIR_ABS}" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR_ABS}" "${OUTPUT_DIR_ABS}/figures"

echo "[INFO] Project root: ${PROJECT_ROOT}"
echo "[INFO] Python script: ${PY_SCRIPT}"
echo "[INFO] Conda env: ${CONDA_ENV}"
echo "[INFO] Target flight_id: ${FLIGHT_ID}"
echo "[INFO] Query window: ${T_START} -> ${T_END}"

time conda run --no-capture-output -n "${CONDA_ENV}" python "${PY_SCRIPT}" \
  --source-file "${SOURCE_FILE_ABS}" \
  --flight-id "${FLIGHT_ID}" \
  --t-start "${T_START}" \
  --t-end "${T_END}" \
  --interp-dir "${INTERP_DIR_ABS}" \
  --meta-parquet "${META_PARQUET_ABS}" \
  --output-dir "${OUTPUT_DIR_ABS}" \
  --resample-points "${RESAMPLE_POINTS}" \
  --min-traj-points "${MIN_TRAJ_POINTS}" \
  --top-k-window "${TOP_K_WINDOW}" \
  --top-k-app95 "${TOP_K_APP95}" \
  --workers "${WORKERS}"

TARGET_PREFIX="target_${FLIGHT_ID}"

echo "[INFO] 主要输出文件:"
echo "- ${OUTPUT_DIR_ABS}/${TARGET_PREFIX}_summary.csv"
echo "- ${OUTPUT_DIR_ABS}/${TARGET_PREFIX}_same_flight_similarity.csv"
echo "- ${OUTPUT_DIR_ABS}/figures/${TARGET_PREFIX}_top_refs_overlay.png"
echo "- ${OUTPUT_DIR_ABS}/figures/${TARGET_PREFIX}_top_refs_overlay_query_window.png"
echo "- ${OUTPUT_DIR_ABS}/figures/${TARGET_PREFIX}_distance_profile.png"
