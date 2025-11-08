#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DEFAULT_TARGET_DIR="${PROJECT_ROOT}/opensky_2024_PRC_dataset/segmented_trajs_speed_limited_v8_csaps"
TARGET_DIR="$DEFAULT_TARGET_DIR"
PY_ARGS=()
PROCESS_COUNT="48"

usage() {
  cat <<EOF
用法: ${0##*/} [--data-dir 路径] [--processes 数量] [其他 check_nan_values.py 参数]

说明:
  --data-dir/-d   指定需要检查的目录，默认: ${DEFAULT_TARGET_DIR}
  --processes/-p  设置 check_nan_values.py 的并行进程数
  其余参数将直接透传给 check_nan_values.py
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir|-d)
      if [[ $# -lt 2 ]]; then
        echo "❌ --data-dir 需要一个路径参数" >&2
        usage
        exit 1
      fi
      TARGET_DIR="$2"
      shift 2
      ;;
    --processes|-p)
      if [[ $# -lt 2 ]]; then
        echo "❌ --processes 需要一个数字参数" >&2
        usage
        exit 1
      fi
      PROCESS_COUNT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      PY_ARGS+=("$1")
      shift
      ;;
  esac
done

echo "📂 数据目录: $TARGET_DIR"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "❌ 指定目录不存在: $TARGET_DIR"
  exit 1
fi

CONDA_BASE="$(conda info --base 2>/dev/null)"
if [[ -z "${CONDA_BASE}" ]]; then
  echo "❌ 未找到conda，请先安装或确保conda在PATH中"
  exit 1
fi
# shellcheck disable=SC1090
source "${CONDA_BASE}/etc/profile.d/conda.sh"
conda activate opensky >/dev/null

REPORT_BASENAME="$(basename "$TARGET_DIR")"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="${PROJECT_ROOT}/reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="${REPORT_DIR}/nan_check_${REPORT_BASENAME}_${TIMESTAMP}.txt"

cd "$PROJECT_ROOT"
PY_CMD=(
  python junguo_analysis_for_opensky2022/analysis_for_interpolation/check_nan_values.py
  --input-dir "$TARGET_DIR"
  --output "$REPORT_FILE"
  --suffixes .parquet .csv
)

if [[ -n "$PROCESS_COUNT" ]]; then
  PY_CMD+=(--processes "$PROCESS_COUNT")
fi

PY_CMD+=("${PY_ARGS[@]}")

"${PY_CMD[@]}"

EXIT_CODE=$?
if [[ $EXIT_CODE -eq 0 ]]; then
  echo "✅ 检查完成：报告位于 $REPORT_FILE"
else
  echo "⚠️ 检查发现问题或执行失败：报告位于 $REPORT_FILE"
fi

exit $EXIT_CODE
