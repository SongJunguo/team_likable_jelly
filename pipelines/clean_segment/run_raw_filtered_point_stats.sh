#!/bin/bash
# 一键执行 raw vs filtered 点数对比（包含 segmented/interpolated 比率）
# 环境变量：
#   ENABLE_RAW / ENABLE_FILTERED / ENABLE_SEGMENTED / ENABLE_INTERPOLATED 控制统计目录
#   DATE_FROM_OVERRIDE / DATE_TO_OVERRIDE 限制统计日期范围（默认跟随 staged pipeline 的 FROM/TO）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${SCRIPT_DIR}/config.sh"

if [[ "${ENABLE_POINT_STATS:-1}" != "1" ]]; then
  echo "ENABLE_POINT_STATS=0，跳过点数统计"
  exit 0
fi

RAW_DIR="${RAW_DIR:-}"
FILTERED_DIR="${FILTERED_DIR:-}"
REPORT_DIR="${REPORT_DIR:?REPORT_DIR 未设置}"
SEGMENTED_DIR="${SEGMENTED_DIR:-}"
INTERPOLATED_DIR="${INTERPOLATED_DIR:-}"
ENABLE_RAW="${ENABLE_RAW:-1}"
ENABLE_FILTERED="${ENABLE_FILTERED:-1}"
ENABLE_SEGMENTED="${ENABLE_SEGMENTED:-1}"
ENABLE_INTERPOLATED="${ENABLE_INTERPOLATED:-1}"
DATE_FROM_OVERRIDE="${DATE_FROM_OVERRIDE:-${FROM:-}}"
DATE_TO_OVERRIDE="${DATE_TO_OVERRIDE:-${TO:-}}"
OUTPUT_CSV="${OUTPUT_CSV:-${REPORT_DIR}/raw_vs_filtered_point_stats.csv}"
SUMMARY_TXT="${SUMMARY_TXT:-${REPORT_DIR}/raw_vs_filtered_point_stats_summary.txt}"

mkdir -p "${REPORT_DIR}"

PYTHON_SCRIPT="${REPO_ROOT}/analysis/raw_filtered_point_stats.py"

echo "==> 运行 raw vs filtered 点数 + 经纬高缺失率对比"
echo "    Raw       : ${RAW_DIR:-<未提供>}"
echo "    Filtered  : ${FILTERED_DIR:-<未提供>}"
echo "    Segmented : ${SEGMENTED_DIR:-<未提供>}"
echo "    Interp    : ${INTERPOLATED_DIR:-<未提供>}"
echo "    Output CSV: ${OUTPUT_CSV}"

ARGS=(
  --output-csv "${OUTPUT_CSV}"
  --summary-txt "${SUMMARY_TXT}"
)
if [[ -n "${DATE_FROM_OVERRIDE}" ]]; then
  ARGS+=(--from-date "${DATE_FROM_OVERRIDE}")
fi
if [[ -n "${DATE_TO_OVERRIDE}" ]]; then
  ARGS+=(--to-date "${DATE_TO_OVERRIDE}")
fi
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
