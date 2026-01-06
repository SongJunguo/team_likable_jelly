#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

RAW_DIR_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/rawtrajectories"
OUT_DIR_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/xue_processed_eu_v1"
FLIGHTS_PARQUET_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/flights/challenge_set.parquet"
AIRPORTS_PARQUET_DEFAULT="$REPO_ROOT/opensky_2024_PRC_dataset/airports_tz.parquet"

PROCS_DEFAULT=28

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
  --europe-only       仅保留起降都在欧洲的航班（可选）
  --top-airports N    机场出现次数 Top-N（adep+ades 合并统计，可选）
  --top-aircraft N    机型出现次数 Top-N（可选）
  --include-submission  合并 submission_set.parquet 参与统计（可选）
  --include-final       合并 final_submission_set.parquet 参与统计（可选）
  --europe-continent C  Europe 大洲编码（默认 EU）
  --meta-procs N        元数据读取并发数（仅多源时生效）
  -h|--help           显示帮助

环境:
  - 默认优先激活 conda 环境 data；若不存在则回退 opensky
EOF
}

RAW_DIR="$RAW_DIR_DEFAULT"
OUT_DIR="$OUT_DIR_DEFAULT"
FROM="2022-01-01"
TO="2022-02-31"
PROCS="$PROCS_DEFAULT"
FORCE=0
DRYRUN=0
LIMIT_DAYS=0
LIMIT_FLIGHTS=0
EUROPE_ONLY=1
TOP_AIRPORTS=32
TOP_AIRCRAFT=16
INCLUDE_SUBMISSION=0
INCLUDE_FINAL=0
EUROPE_CONTINENT="EU"
META_PROCS=4

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
    --europe-only|--europe_only) EUROPE_ONLY=1; shift;;
    --top-airports|--top_airports) TOP_AIRPORTS="$2"; shift 2;;
    --top-aircraft|--top_aircraft) TOP_AIRCRAFT="$2"; shift 2;;
    --include-submission|--include_submission) INCLUDE_SUBMISSION=1; shift;;
    --include-final|--include_final) INCLUDE_FINAL=1; shift;;
    --europe-continent|--europe_continent) EUROPE_CONTINENT="$2"; shift 2;;
    --meta-procs|--meta_procs) META_PROCS="$2"; shift 2;;
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
[[ "$EUROPE_ONLY" == "1" ]] && PY_CMD+=(--europe_only)
[[ "$TOP_AIRPORTS" != "0" ]] && PY_CMD+=(--top_airports "$TOP_AIRPORTS")
[[ "$TOP_AIRCRAFT" != "0" ]] && PY_CMD+=(--top_aircraft "$TOP_AIRCRAFT")
[[ "$INCLUDE_SUBMISSION" == "1" ]] && PY_CMD+=(--include_submission)
[[ "$INCLUDE_FINAL" == "1" ]] && PY_CMD+=(--include_final)
[[ -n "$EUROPE_CONTINENT" ]] && PY_CMD+=(--europe_continent "$EUROPE_CONTINENT")
[[ -n "$META_PROCS" ]] && PY_CMD+=(--meta_procs "$META_PROCS")

echo "==> 运行: ${PY_CMD[*]}"
"${PY_CMD[@]}"
