#!/bin/bash
# 一键执行 raw vs filtered 点数对比

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/config.sh"

RAW_DIR="${RAW_DIR:-}"
FILTERED_DIR="${FILTERED_DIR:-}"
REPORT_DIR="${REPORT_DIR:?REPORT_DIR 未设置}"
SEGMENTED_DIR="${SEGMENTED_DIR:-}"
INTERPOLATED_DIR="${INTERPOLATED_DIR:-}"
ENABLE_RAW="${ENABLE_RAW:-1}"
ENABLE_FILTERED="${ENABLE_FILTERED:-1}"
ENABLE_SEGMENTED="${ENABLE_SEGMENTED:-1}"
ENABLE_INTERPOLATED="${ENABLE_INTERPOLATED:-1}"
OUTPUT_CSV="${OUTPUT_CSV:-${REPORT_DIR}/raw_vs_filtered_point_stats.csv}"
SUMMARY_TXT="${SUMMARY_TXT:-${REPORT_DIR}/raw_vs_filtered_point_stats_summary.txt}"
CONDA_ENV="${CONDA_ENV:-opensky}"

mkdir -p "${REPORT_DIR}"

if command -v conda >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  eval "$("conda" "shell.bash" "hook")"
  conda activate "${CONDA_ENV}"
else
  echo "conda 命令不存在，请先安装并配置 conda 环境" >&2
  exit 1
fi

PYTHON_SCRIPT="${REPO_ROOT}/analysis/raw_filtered_point_stats.py"

echo "==> 运行 raw vs filtered 点数 + 经纬高缺失率对比"
echo "    Raw       : ${RAW_DIR:-<未提供>}"
echo "    Filtered  : ${FILTERED_DIR:-<未提供>}"
echo "    Segmented : ${SEGMENTED_DIR:-<未提供>}"
echo "    Interp    : ${INTERPOLATED_DIR:-<未提供>}"
echo "    Output CSV: ${OUTPUT_CSV}"
echo "    Conda Env : ${CONDA_ENV}"

ARGS=(
  --output-csv "${OUTPUT_CSV}"
  --summary-txt "${SUMMARY_TXT}"
)
if [[ "${ENABLE_RAW}" == "1" && -n "${RAW_DIR}" ]]; then
  ARGS+=(--raw-dir "${RAW_DIR}")
else
  ARGS+=(--skip-raw)
fi
if [[ "${ENABLE_FILTERED}" == "1" && -n "${FILTERED_DIR}" ]]; then
  ARGS+=(--filtered-dir "${FILTERED_DIR}")
else
  ARGS+=(--skip-filtered)
fi
if [[ "${ENABLE_SEGMENTED}" == "1" && -n "${SEGMENTED_DIR}" ]]; then
  ARGS+=(--segment-dir "${SEGMENTED_DIR}")
else
  ARGS+=(--skip-segmented)
fi
if [[ "${ENABLE_INTERPOLATED}" == "1" && -n "${INTERPOLATED_DIR}" ]]; then
  ARGS+=(--interpolated-dir "${INTERPOLATED_DIR}")
else
  ARGS+=(--skip-interpolated)
fi

python "${PYTHON_SCRIPT}" "${ARGS[@]}"

echo "==> 完成，CSV（含汇总 + 逐文件 raw/filtered 行）已写入 ${OUTPUT_CSV}"
