#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RAW_DIR_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/rawtrajectories"
OUT_DIR_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/xue_processed_raw__v1"
FLIGHTS_PARQUET_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/flights/challenge_set.parquet"
AIRPORTS_PARQUET_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/airports_tz.parquet"

PROCS_DEFAULT=14

usage() {
  cat <<EOF
用法: bash pipelines/Xue_Zhengye_process/run_xue_process_raw.sh [选项]

功能:
  - 读取 rawtrajectories 按天 parquet
  - 仅保留 challenge_set.parquet 中的 flight_id
  - 运行薛正烨轨迹处理算法并按天落盘: xue_<date>.parquet
  - 合并 adep/ades/aircraft_type，并补充机场经纬度

选项:
  --raw-dir DIR       原始目录（默认: $RAW_DIR_DEFAULT）
  --out-dir DIR       输出目录（默认: $OUT_DIR_DEFAULT）
  --from DATE         起始日期 YYYY-MM-DD（默认: 自动）
  --to DATE           截止日期 YYYY-MM-DD（默认: 自动）
  --procs N           并发数（默认: $PROCS_DEFAULT）
  --force             覆盖已存在输出
  --dry-run           仅打印将处理的文件
  --limit-days N      仅处理前 N 天（测试用）
  --limit-flights N   每天仅处理前 N 条航迹（测试用）
  -h|--help           显示帮助

环境:
  - 默认优先激活 conda 环境 data；若不存在则回退 opensky
EOF
}

RAW_DIR="$RAW_DIR_DEFAULT"
OUT_DIR="$OUT_DIR_DEFAULT"
FROM=""
TO=""
PROCS="$PROCS_DEFAULT"
FORCE=0
DRYRUN=0
LIMIT_DAYS=0
LIMIT_FLIGHTS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --raw-dir) RAW_DIR="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --from) FROM="$2"; shift 2;;
    --to) TO="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --force) FORCE=1; shift;;
    --dry-run) DRYRUN=1; shift;;
    --limit-days) LIMIT_DAYS="$2"; shift 2;;
    --limit-flights) LIMIT_FLIGHTS="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

echo "==> 尝试激活 conda 环境（优先 data，其次 opensky）"
if command -v conda >/dev/null 2>&1; then
  eval "$(conda shell.bash hook)" || true
  conda activate data 2>/dev/null || conda activate opensky
else
  echo "⚠️  未找到 conda 命令，将直接使用当前 Python 环境"
fi

# 多进程时避免 BLAS/OMP 线程过度抢占
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

PY_CMD=(python -m pipelines.Xue_Zhengye_process.process_rawtrajectories_by_day)
PY_CMD+=(--raw_dir "$RAW_DIR" --out_dir "$OUT_DIR")
PY_CMD+=(--flights_parquet "$FLIGHTS_PARQUET_DEFAULT" --airports_parquet "$AIRPORTS_PARQUET_DEFAULT")
PY_CMD+=(--max_workers "$PROCS" --log_level INFO)

[[ -n "$FROM" ]] && PY_CMD+=(--from "$FROM")
[[ -n "$TO" ]] && PY_CMD+=(--to "$TO")
[[ "$FORCE" == "1" ]] && PY_CMD+=(--force)
[[ "$DRYRUN" == "1" ]] && PY_CMD+=(--dry_run)
[[ "$LIMIT_DAYS" != "0" ]] && PY_CMD+=(--limit_days "$LIMIT_DAYS")
[[ "$LIMIT_FLIGHTS" != "0" ]] && PY_CMD+=(--limit_flights "$LIMIT_FLIGHTS")

echo "==> 运行: ${PY_CMD[*]}"
"${PY_CMD[@]}"

