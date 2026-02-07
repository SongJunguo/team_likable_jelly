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
  --delta-columns COLS                 delta 列（可重复或逗号分隔；如 all）
  --delta-bin-width COL:WIDTH          delta bin 宽度（可重复）
  --delta-max COL:MAX                  delta 最大值（可重复）
  --delta-diff-mode {abs|signed}       delta 差值模式（可选）
  --sample-step-seconds SECONDS        时间抽样步长（可选；例如 20）
  -h, --help                            显示帮助

说明:
  - 间隔模式由脚本顶部 INTERVAL_MODE_DEFAULT 控制（1s 或 20s）
  - 20s 模式会自动注入一组保守 delta 参数与绘图 xlim（可在脚本顶部关闭）
  - 额外参数可通过 "--" 透传给 analysis/data_distributions/plot_adsb_parquet_distributions.py
USAGE
}

# =========================
# 运行模式配置（按需修改）
# =========================
# 可选：1s / 20s
INTERVAL_MODE_DEFAULT="20s"
# 默认 delta 差值模式（建议 signed；可通过命令行 --delta-diff-mode 覆盖）
DELTA_DIFF_MODE_DEFAULT="signed"
# 是否自动给输出 label 增加 mode 后缀，避免覆盖历史结果
AUTO_LABEL_WITH_MODE="true"
# 20s 模式下是否自动注入保守 plot-xlim（仅影响绘图显示，不影响统计）
AUTO_20S_PLOT_XLIM="true"

# DATA_DIR="opensky_2024_PRC_dataset/interpolated_clean__PCA_v6"
DATA_DIR="opensky_2024_PRC_dataset/interpolated_clean_eu_v5"
FILTER="eu_meta"
DATE_FROM="2022-01-01"
DATE_TO="2022-02-28"
LABEL=""
OUT_ROOT=""
DELTA_COLUMNS=()
DELTA_BIN_WIDTH=()
DELTA_MAX=()
DELTA_DIFF_MODE="$DELTA_DIFF_MODE_DEFAULT"
SAMPLE_STEP_SECONDS=""
EXTRA_ARGS=()
PRESET_DELTA_BIN_WIDTH=()
PRESET_DELTA_MAX=()
PRESET_EXTRA_ARGS=()
MODE_SUFFIX=""
INTERVAL_MODE="${INTERVAL_MODE:-$INTERVAL_MODE_DEFAULT}"

merge_colon_pairs() {
  local out_name="$1"
  shift
  local -n _out_arr="$out_name"
  local -A merged=()
  local -a order=()
  local item key

  for item in "$@"; do
    key="${item%%:*}"
    if [[ -z "$key" || "$key" == "$item" ]]; then
      echo "[WARN] 跳过格式异常的键值对: $item" >&2
      continue
    fi
    if [[ -z "${merged[$key]+x}" ]]; then
      order+=("$key")
    fi
    merged[$key]="$item"
  done

  _out_arr=()
  for key in "${order[@]}"; do
    _out_arr+=("${merged[$key]}")
  done
}

extract_and_dedup_plot_xlim() {
  local in_name="$1"
  local out_name="$2"
  local xlim_name="$3"
  local -n _in_arr="$in_name"
  local -n _out_arr="$out_name"
  local -n _xlim_arr="$xlim_name"
  local -a xlim_items=()
  local idx=0
  local token value

  _out_arr=()
  while [ $idx -lt ${#_in_arr[@]} ]; do
    token="${_in_arr[$idx]}"
    if [ "$token" = "--plot-xlim" ]; then
      idx=$((idx + 1))
      if [ $idx -ge ${#_in_arr[@]} ]; then
        echo "[WARN] --plot-xlim 缺少值，已忽略该参数" >&2
        break
      fi
      value="${_in_arr[$idx]}"
      xlim_items+=("$value")
    else
      _out_arr+=("$token")
    fi
    idx=$((idx + 1))
  done

  merge_colon_pairs _xlim_arr "${xlim_items[@]}"
}

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
    --delta-columns)
      DELTA_COLUMNS+=("$2")
      shift 2
      ;;
    --delta-bin-width)
      DELTA_BIN_WIDTH+=("$2")
      shift 2
      ;;
    --delta-max)
      DELTA_MAX+=("$2")
      shift 2
      ;;
    --delta-diff-mode)
      DELTA_DIFF_MODE="$2"
      shift 2
      ;;
    --sample-step-seconds)
      SAMPLE_STEP_SECONDS="$2"
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

case "$INTERVAL_MODE" in
  1s)
    MODE_SUFFIX="mode1s"
    if [ -z "$SAMPLE_STEP_SECONDS" ]; then
      SAMPLE_STEP_SECONDS="1"
    fi
    ;;
  20s)
    MODE_SUFFIX="mode20s"
    if [ -z "$SAMPLE_STEP_SECONDS" ]; then
      SAMPLE_STEP_SECONDS="20"
    fi
    PRESET_DELTA_BIN_WIDTH=(
      "latitude:2e-5"
      "longitude:2e-5"
      "altitude:20"
      "groundspeed:0.2"
      "track:0.2"
      "vertical_rate:2"
      "daltitude:20"
      "gsx:0.2"
      "gsy:0.2"
      "tasx:0.2"
      "tasy:0.2"
      "tas:0.2"
    )
    PRESET_DELTA_MAX=(
      "latitude:0.1"
      "longitude:0.12"
      "altitude:5000"
      "groundspeed:400"
      "track:180"
      "vertical_rate:20000"
      "daltitude:40000"
      "gsx:400"
      "gsy:400"
      "tasx:400"
      "tasy:400"
      "tas:400"
    )
    if [ "$AUTO_20S_PLOT_XLIM" = "true" ]; then
      PRESET_EXTRA_ARGS=(
        "--plot-xlim" "delta_altitude:-5000:5000"
        "--plot-xlim" "delta_groundspeed:-400:400"
        "--plot-xlim" "delta_vertical_rate:-20000:20000"
        "--plot-xlim" "delta_daltitude:-10000:10000"
        "--plot-xlim" "delta_track:-180:180"
      )
    fi
    ;;
  *)
    echo "INTERVAL_MODE 只能是 1s 或 20s，当前: $INTERVAL_MODE" >&2
    exit 2
    ;;
esac

if [ "$AUTO_LABEL_WITH_MODE" = "true" ]; then
  if [ -n "$LABEL" ]; then
    LABEL="${LABEL}_${MODE_SUFFIX}"
  else
    base_name="$(basename "$DATA_DIR")"
    if [ "$FILTER" != "none" ]; then
      LABEL="${base_name}_${FILTER}_${MODE_SUFFIX}"
    else
      LABEL="${base_name}_${MODE_SUFFIX}"
    fi
  fi
fi

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

effective_delta_bin_width=()
effective_delta_max=()
merge_colon_pairs effective_delta_bin_width "${PRESET_DELTA_BIN_WIDTH[@]}" "${DELTA_BIN_WIDTH[@]}"
merge_colon_pairs effective_delta_max "${PRESET_DELTA_MAX[@]}" "${DELTA_MAX[@]}"

for item in "${effective_delta_bin_width[@]}"; do
  args+=(--delta-bin-width "$item")
done
for item in "${effective_delta_max[@]}"; do
  args+=(--delta-max "$item")
done
for item in "${DELTA_COLUMNS[@]}"; do
  args+=(--delta-columns "$item")
done
if [ -n "$DELTA_DIFF_MODE" ]; then
  args+=(--delta-diff-mode "$DELTA_DIFF_MODE")
fi
if [ -n "$SAMPLE_STEP_SECONDS" ]; then
  args+=(--sample-step-seconds "$SAMPLE_STEP_SECONDS")
fi

raw_extra_args=("${PRESET_EXTRA_ARGS[@]}" "${EXTRA_ARGS[@]}")
final_extra_args=()
effective_plot_xlims=()
extract_and_dedup_plot_xlim raw_extra_args final_extra_args effective_plot_xlims
for item in "${effective_plot_xlims[@]}"; do
  final_extra_args+=(--plot-xlim "$item")
done

echo "[INFO] filter=$FILTER data_dir=$DATA_DIR interval_mode=$INTERVAL_MODE sample_step_seconds=$SAMPLE_STEP_SECONDS delta_diff_mode=$DELTA_DIFF_MODE"
if [ ${#effective_delta_max[@]} -gt 0 ]; then
  echo "[INFO] effective --delta-max (${#effective_delta_max[@]}): ${effective_delta_max[*]}"
else
  echo "[INFO] effective --delta-max: (none)"
fi
if [ ${#effective_plot_xlims[@]} -gt 0 ]; then
  echo "[INFO] effective --plot-xlim (${#effective_plot_xlims[@]}): ${effective_plot_xlims[*]}"
else
  echo "[INFO] effective --plot-xlim: (none)"
fi
python analysis/data_distributions/plot_adsb_parquet_distributions.py "${args[@]}" "${final_extra_args[@]}"
