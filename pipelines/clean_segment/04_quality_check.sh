#!/usr/bin/env bash
set -euo pipefail

# ========== 质量检查脚本 ==========
# 功能：
# 1. 跳变检测（调用原有的run_detect_jumps_all.sh）
# 2. NaN检测（确保最终轨迹0个NaN）
# 3. 基础统计（文件数、segment数、总点数）

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.sh"

# 引用原有的跳变检测脚本
JUMP_DETECT="$REPO_ROOT/legacy/analysis_for_interpolation/run_detect_jumps_all.sh"
NAN_CHECK="$REPO_ROOT/legacy/analysis_for_interpolation/check_nan_values.py"

usage() {
  cat <<'EOF'
用法: bash 04_quality_check.sh [选项]

质量检查：
  1. 跳变检测（短时间内跨越超远距离）
  2. NaN检测（确保0个NaN）
  3. 基础统计（文件数、segment数）

选项:
  --data-dir DIR      输入目录（默认: $INTERPOLATED_DIR）
  --out-dir DIR       报告输出目录（默认: $REPORT_DIR）
  --from DATE         起始日期（默认: $DATE_FROM）
  --to DATE           截止日期（默认: $DATE_TO）
  --procs N           并发数（默认: $QUALITY_CHECK_PROCS）
  --skip-jump         跳过跳变检测
  --skip-nan          跳过NaN检测
  --force             重新检测（忽略已有报告）
  -h|--help           显示帮助
EOF
}

DATA_DIR="${INTERPOLATED_DIR}"
OUT_DIR="${REPORT_DIR}"
PROCS="${QUALITY_CHECK_PROCS}"
FROM="${DATE_FROM}"
TO="${DATE_TO}"
SKIP_JUMP=0
SKIP_NAN=0
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir) DATA_DIR="$2"; shift 2;;
    --out-dir) OUT_DIR="$2"; shift 2;;
    --from) FROM="$2"; shift 2;;
    --to) TO="$2"; shift 2;;
    --procs) PROCS="$2"; shift 2;;
    --skip-jump) SKIP_JUMP=1; shift;;
    --skip-nan) SKIP_NAN=1; shift;;
    --force) FORCE=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown arg: $1"; usage; exit 1;;
  esac
done

mkdir -p "$OUT_DIR"

echo "=========================================="
echo "  质量检查（Clean-Segment-Interp）"
echo "=========================================="
echo "数据目录: $DATA_DIR"
echo "报告目录: $OUT_DIR"
echo ""

# ========== 检查1：跳变检测 ==========
if [[ "$SKIP_JUMP" == "0" && "$ENABLE_JUMP_DETECTION" == "1" ]]; then
  echo "[1/3] 跳变检测..."

  if [[ ! -f "$JUMP_DETECT" ]]; then
    echo "  ⚠️  跳过：找不到跳变检测脚本 $JUMP_DETECT"
  else
    JUMP_OUT="$OUT_DIR/jump_detection"

    MIN_SPEED_KMH=""
    if [[ -n "${MAX_SPEED_MPS:-}" ]]; then
      MIN_SPEED_KMH=$(awk -v v="$MAX_SPEED_MPS" 'BEGIN { printf "%.6f", v * 3.6 }')
    fi

    CMD=(bash "$JUMP_DETECT" --data-dir "$DATA_DIR" --out-dir "$JUMP_OUT" --procs "$PROCS")
    [[ -n "$FROM" ]] && CMD+=(--from "$FROM")
    [[ -n "$TO" ]] && CMD+=(--to "$TO")
    [[ "$FORCE" == "1" ]] && CMD+=(--force)
    [[ -n "$MIN_SPEED_KMH" ]] && CMD+=(--min-speed "$MIN_SPEED_KMH")

    echo "  命令: ${CMD[*]}"
    if [[ -n "$MIN_SPEED_KMH" ]]; then
      echo "  ⚙️  跳变速度阈值同步 MAX_SPEED_MPS=${MAX_SPEED_MPS} → ${MIN_SPEED_KMH} km/h"
    fi
    "${CMD[@]}" || { echo "  ❌ 跳变检测失败"; exit 1; }
    echo "  ✅ 跳变检测完成：$JUMP_OUT"
  fi
else
  echo "[1/3] 跳过跳变检测（--skip-jump或ENABLE_JUMP_DETECTION=0）"
fi

echo ""

# ========== 检查2：NaN检测 ==========
if [[ "$SKIP_NAN" == "0" && "$ENABLE_NAN_CHECK" == "1" ]]; then
  echo "[2/3] NaN检测..."

  if [[ ! -f "$NAN_CHECK" ]]; then
    echo "  ⚠️  跳过：找不到NaN检测脚本 $NAN_CHECK"
  else
    NAN_REPORT="$OUT_DIR/nan_check_report.txt"

    python "$NAN_CHECK" \
      --input-dir "$DATA_DIR" \
      --output "$NAN_REPORT" \
      --processes "$NAN_CHECK_PROCS" \
      --columns $NAN_CHECK_COLUMNS || {
      echo "  ❌ NaN检测失败（发现NaN！）"
      echo "  详见: $NAN_REPORT"
      exit 1
    }

    echo "  ✅ NaN检测通过：0个NaN"
    echo "  报告: $NAN_REPORT"
  fi
else
  echo "[2/3] 跳过NaN检测（--skip-nan或ENABLE_NAN_CHECK=0）"
fi

echo ""

# ========== 检查3：基础统计 ==========
echo "[3/3] 基础统计..."

STATS_REPORT="$OUT_DIR/basic_statistics.txt"

# 统计文件数
NUM_FILES=$(find "$DATA_DIR" -name "*.parquet" 2>/dev/null | wc -l)

# 统计总点数和segment数（使用Python快速统计）
python - <<EOF > "$STATS_REPORT"
import pandas as pd
from pathlib import Path

data_dir = Path("$DATA_DIR")
files = sorted(data_dir.glob("*.parquet"))

total_points = 0
total_segments = 0
total_flights = 0

for f in files:
    try:
        df = pd.read_parquet(f)
        total_points += len(df)
        if 'flight_id' in df.columns:
            total_segments += df['flight_id'].nunique()
        if 'original_flight_id' in df.columns:
            total_flights += df['original_flight_id'].nunique()
    except Exception as e:
        print(f"警告：读取 {f.name} 失败: {e}")

print(f"文件数: {len(files)}")
print(f"总数据点: {total_points:,}")
print(f"总segment数: {total_segments:,}")
if total_flights > 0:
    print(f"原始航班数: {total_flights:,}")
    print(f"平均每航班segment数: {total_segments/total_flights:.2f}")
EOF

cat "$STATS_REPORT"
echo "  报告: $STATS_REPORT"

echo ""
echo "=========================================="
echo "  ✅ 质量检查完成"
echo "=========================================="
echo "所有报告位于: $OUT_DIR"
echo ""
echo "检查项："
echo "  ✅ 跳变检测: $OUT_DIR/jump_detection/"
echo "  ✅ NaN检测: $OUT_DIR/nan_check_report.txt"
echo "  ✅ 基础统计: $OUT_DIR/basic_statistics.txt"
