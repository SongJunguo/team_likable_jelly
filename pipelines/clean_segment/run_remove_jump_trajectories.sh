#!/usr/bin/env bash
# 根据 jump_events_all.csv 的结果批量删除插值后的异常航迹
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

source "${SCRIPT_DIR}/config.sh"

CONDA_ENV="${CONDA_ENV:-opensky}"
if command -v conda >/dev/null 2>&1; then
  # shellcheck disable=SC1091
  eval "$(conda shell.bash hook)"
  conda activate "${CONDA_ENV}"
else
  echo "conda 未安装或未在 PATH 中，无法激活 opensky 环境" >&2
  exit 1
fi

PYTHON_SCRIPT="${SCRIPT_DIR}/remove_jump_trajectories.py"
DEFAULT_CSV="${REPO_ROOT}reports/quality_check_clean__PCA_v4/jump_detection/jump_events_all.csv"
DEFAULT_DATA_DIR="${INTERPOLATED_DIR}" # 来源于 config.sh，可覆盖
if [[ -z "${DEFAULT_DATA_DIR}" ]]; then
  echo "INTERPOLATED_DIR 未设置，请先在 config.sh 中配置" >&2
  exit 1
fi

if [[ ! -f "${PYTHON_SCRIPT}" ]]; then
  echo "找不到 Python 清理脚本: ${PYTHON_SCRIPT}" >&2
  exit 1
fi

ARGS=("$@")
USER_SET_CSV=0
USER_SET_DATA=0
for arg in "${ARGS[@]}"; do
  case "${arg}" in
    --csv|--csv=*) USER_SET_CSV=1 ;;
    --data-dir|--data-dir=*) USER_SET_DATA=1 ;;
  esac
done

# 构造命令
CMD=("python" "${PYTHON_SCRIPT}")
if [[ "${USER_SET_CSV}" -eq 0 ]]; then
  CMD+=(--csv "${DEFAULT_CSV}")
fi
if [[ "${USER_SET_DATA}" -eq 0 ]]; then
  CMD+=(--data-dir "${DEFAULT_DATA_DIR}")
fi
CMD+=("${ARGS[@]}")

if [[ "${USER_SET_CSV}" -eq 1 ]]; then
  DISPLAY_CSV="<自定义 --csv>"
else
  DISPLAY_CSV="${DEFAULT_CSV}"
fi
if [[ "${USER_SET_DATA}" -eq 1 ]]; then
  DISPLAY_DIR="<自定义 --data-dir>"
else
  DISPLAY_DIR="${DEFAULT_DATA_DIR}"
fi

echo "==> 删除 jump_events_all.csv 中的异常航迹"
echo "    CSV: ${DISPLAY_CSV}"
echo "    目录: ${DISPLAY_DIR}"
echo "    运行命令: ${CMD[*]}"

"${CMD[@]}"
