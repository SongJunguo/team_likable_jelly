#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法:
  bash analysis/run_distributions.sh [options] [-- extra_args...]

选项:
  --dataset {raw|interpolated|xue|all}   数据集（默认 raw）
  --filter {none|eu_meta}               过滤（默认 none；eu_meta=起降都在欧洲）
  --date-from YYYY-MM-DD                起始日期（默认 2022-01-01）
  --date-to YYYY-MM-DD                  结束日期（默认 2022-02-28）
  --label LABEL                         输出子目录名（可选）
  --out-root PATH                       输出根目录（可选）
  --data-root PATH                      数据根目录（默认 opensky_2024_PRC_dataset）
  -h, --help                            显示帮助

说明:
  - 额外参数可通过 "--" 透传给 analysis/plot_adsb_parquet_distributions.py
  - --dataset all 会顺序跑 raw/interpolated/xue
USAGE
}

DATASET="xue"
FILTER="eu_meta"
DATE_FROM="2022-01-01"
DATE_TO="2022-02-28"
LABEL=""
OUT_ROOT=""
DATA_ROOT="opensky_2024_PRC_dataset"
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --dataset)
      DATASET="$2"
      shift 2
      ;;
    --filter)
      FILTER="$2"
      shift 2
      ;;
    --date-from)
      DATE_FROM="$2"
      shift 2
      ;;
    --date-to)
      DATE_TO="$2"
      shift 2
      ;;
    --label)
      LABEL="$2"
      shift 2
      ;;
    --out-root)
      OUT_ROOT="$2"
      shift 2
      ;;
    --data-root)
      DATA_ROOT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS=("$@")
      break
      ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 2
      ;;
  esac
done

case "$DATASET" in
  raw|interpolated|xue|all) ;;
  *)
    echo "dataset 只能是 raw|interpolated|xue|all" >&2
    exit 2
    ;;
esac

case "$FILTER" in
  none|eu_meta) ;;
  *)
    echo "filter 只能是 none|eu_meta" >&2
    exit 2
    ;;
esac

if [ -f /home/neu/miniconda3/etc/profile.d/conda.sh ]; then
  # shellcheck source=/dev/null
  source /home/neu/miniconda3/etc/profile.d/conda.sh
elif [ -f /home/neu/anaconda3/etc/profile.d/conda.sh ]; then
  # shellcheck source=/dev/null
  source /home/neu/anaconda3/etc/profile.d/conda.sh
else
  echo "找不到 conda.sh（/home/neu/miniconda3 或 /home/neu/anaconda3）" >&2
  exit 1
fi

conda activate opensky

run_one() {
  local dataset="$1"
  local subdir
  case "$dataset" in
    raw) subdir="rawtrajectories" ;;
    interpolated) subdir="interpolated_clean__PCA_v6" ;;
    xue) subdir="xue_processed_raw__v1" ;;
    *)
      echo "未知 dataset: $dataset" >&2
      exit 2
      ;;
  esac

  local data_dir="${DATA_ROOT}/${subdir}"
  if [ ! -d "$data_dir" ]; then
    echo "数据目录不存在: $data_dir" >&2
    exit 1
  fi

  local args=(
    --data-dir "$data_dir"
    --date-from "$DATE_FROM"
    --date-to "$DATE_TO"
  )
  if [ "$FILTER" != "none" ]; then
    args+=(--flight-filter "$FILTER")
  fi
  if [ -n "$OUT_ROOT" ]; then
    args+=(--out-root "$OUT_ROOT")
  fi
  if [ -n "$LABEL" ]; then
    local label_run="$LABEL"
    if [ "$DATASET" = "all" ]; then
      label_run="${LABEL}_${dataset}"
    fi
    args+=(--label "$label_run")
  fi

  echo "[INFO] dataset=$dataset filter=$FILTER data_dir=$data_dir"
  python analysis/plot_adsb_parquet_distributions.py "${args[@]}" "${EXTRA_ARGS[@]}"
}

if [ "$DATASET" = "all" ]; then
  run_one "raw"
  run_one "interpolated"
  run_one "xue"
else
  run_one "$DATASET"
fi
