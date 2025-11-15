#!/bin/bash
# 一键执行 raw vs filtered 点数对比

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

source "${SCRIPT_DIR}/config.sh"

RAW_DIR="${RAW_DIR:?RAW_DIR 未设置}"
FILTERED_DIR="${FILTERED_DIR:?FILTERED_DIR 未设置}"
REPORT_DIR="${REPORT_DIR:?REPORT_DIR 未设置}"
OUTPUT_CSV="${OUTPUT_CSV:-${REPORT_DIR}/raw_vs_filtered_point_stats.csv}"
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
echo "    Raw       : ${RAW_DIR}"
echo "    Filtered  : ${FILTERED_DIR}"
echo "    Output CSV: ${OUTPUT_CSV}"
echo "    Conda Env : ${CONDA_ENV}"

python "${PYTHON_SCRIPT}" \
  --raw-dir "${RAW_DIR}" \
  --filtered-dir "${FILTERED_DIR}" \
  --output-csv "${OUTPUT_CSV}"

echo "==> 完成，CSV（含汇总 + 逐文件 raw/filtered 行）已写入 ${OUTPUT_CSV}"
