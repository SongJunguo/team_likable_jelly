#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
用法:
  bash analysis/data_distributions/run_distributions.sh --data-dir PATH [options] [-- extra_args...]

选项:
  --data-dir PATH                      数据目录（必填）
  --filter {none|eu_meta}               过滤（默认 eu_meta；eu_meta=起降都在欧洲）
  --date-from YYYY-MM-DD                起始日期（默认 2022-01-01）
  --date-to YYYY-MM-DD                  结束日期（默认 2022-02-28）
  --label LABEL                         输出子目录名（可选）
  --out-root PATH                       输出根目录（可选）
  -h, --help                            显示帮助

说明:
  - 额外参数可通过 "--" 透传给 analysis/data_distributions/plot_adsb_parquet_distributions.py
USAGE
}

# DATA_DIR="opensky_2024_PRC_dataset/interpolated_clean__PCA_v6"
DATA_DIR="opensky_2024_PRC_dataset/interpolated_clean_eu_v4"
FILTER="eu_meta"
DATE_FROM="2022-01-01"
DATE_TO="2022-02-28"
LABEL=""
OUT_ROOT=""
EXTRA_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir)
      DATA_DIR="$2"
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

if [ -z "$DATA_DIR" ]; then
  echo "必须指定 --data-dir" >&2
  usage
  exit 2
fi

if [ ! -d "$DATA_DIR" ]; then
  echo "数据目录不存在: $DATA_DIR" >&2
  exit 1
fi

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

args=(
  --data-dir "$DATA_DIR"
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
  args+=(--label "$LABEL")
fi

echo "[INFO] filter=$FILTER data_dir=$DATA_DIR"
python analysis/data_distributions/plot_adsb_parquet_distributions.py "${args[@]}" "${EXTRA_ARGS[@]}"
