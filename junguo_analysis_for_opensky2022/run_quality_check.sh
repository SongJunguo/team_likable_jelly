#!/bin/bash
# 高性能数据质量检测运行脚本
# 自动配置最优参数，充分利用80核CPU和512GB内存

set -e  # 遇到错误时退出

# 默认参数
RAW_DIR="../opensky_2024_PRC_dataset/rawtrajectories"
INTERP_DIR="../opensky_2024_PRC_dataset/classic__1e-2_interpolated_trajectories"
CONDA_ENV="opensky"
THREADS=80
START_DATE=""
END_DATE=""
LIMIT=""
SKIP_INTERP=false
SKIP_COMPARISON=false

# 帮助信息
show_help() {
    cat << EOF
高性能数据质量检测工具

用法: $0 [选项]

选项:
  -r, --raw-dir DIR          原始轨迹数据目录 (默认: $RAW_DIR)
  -i, --interp-dir DIR       插值轨迹数据目录 (默认: $INTERP_DIR)
  -s, --start-date DATE      开始日期 YYYY-MM-DD
  -e, --end-date DATE        结束日期 YYYY-MM-DD
  -l, --limit N              限制处理文件数量 (用于测试)
  -j, --threads N            Polars线程数 (默认: $THREADS)
  -c, --conda-env ENV        Conda环境名 (默认: $CONDA_ENV)
  --skip-interp              跳过插值数据分析
  --skip-comparison          跳过数据对比
  -h, --help                 显示此帮助信息

示例:
  # 快速测试 - 只处理前5天
  $0 -l 5
  
  # 处理2022年1月的数据
  $0 -s 2022-01-01 -e 2022-01-31
  
  # 全量分析 (默认)
  $0
  
  # 只分析原始数据，跳过插值数据
  $0 --skip-interp --skip-comparison
  
  # 指定自定义目录
  $0 -r /path/to/raw -i /path/to/interp

注意:
  - 脚本会自动激活指定的conda环境
  - 优化Polars配置以充分利用系统资源
  - 建议在tmux或screen中运行大规模分析
EOF
}

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--raw-dir)
            RAW_DIR="$2"
            shift 2
            ;;
        -i|--interp-dir)
            INTERP_DIR="$2"
            shift 2
            ;;
        -s|--start-date)
            START_DATE="$2"
            shift 2
            ;;
        -e|--end-date)
            END_DATE="$2"
            shift 2
            ;;
        -l|--limit)
            LIMIT="$2"
            shift 2
            ;;
        -j|--threads)
            THREADS="$2"
            shift 2
            ;;
        -c|--conda-env)
            CONDA_ENV="$2"
            shift 2
            ;;
        --skip-interp)
            SKIP_INTERP=true
            shift
            ;;
        --skip-comparison)
            SKIP_COMPARISON=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            echo "使用 -h 或 --help 查看帮助信息"
            exit 1
            ;;
    esac
done

# 显示配置信息
echo "=== 高性能数据质量检测配置 ==="
echo "Conda环境: $CONDA_ENV"
echo "Polars线程数: $THREADS"
echo "原始数据目录: $RAW_DIR"
echo "插值数据目录: $INTERP_DIR"
echo "日期范围: ${START_DATE:-全部} 到 ${END_DATE:-全部}"
echo "文件数量限制: ${LIMIT:-无限制}"
echo "跳过插值分析: $SKIP_INTERP"
echo "跳过数据对比: $SKIP_COMPARISON"
echo

# 检查conda环境
if ! conda info --envs | grep -q "^$CONDA_ENV "; then
    echo "错误: Conda环境 '$CONDA_ENV' 不存在"
    echo "可用环境:"
    conda info --envs
    exit 1
fi

# 激活conda环境
echo "激活conda环境: $CONDA_ENV"
source $(conda info --base)/etc/profile.d/conda.sh
conda activate $CONDA_ENV

# 设置环境变量优化性能
export POLARS_MAX_THREADS=$THREADS
export OMP_NUM_THREADS=$THREADS
export OPENBLAS_NUM_THREADS=$THREADS
export MKL_NUM_THREADS=$THREADS

# 构建Python命令参数
PYTHON_ARGS="--raw-dir $RAW_DIR --interp-dir $INTERP_DIR"

if [[ -n "$START_DATE" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --start-date $START_DATE"
fi

if [[ -n "$END_DATE" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --end-date $END_DATE"
fi

if [[ -n "$LIMIT" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --limit $LIMIT"
fi

if [[ "$SKIP_INTERP" == "true" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --skip-interp"
fi

if [[ "$SKIP_COMPARISON" == "true" ]]; then
    PYTHON_ARGS="$PYTHON_ARGS --skip-comparison"
fi

# 显示系统资源信息
echo "=== 系统资源信息 ==="
echo "CPU核心数: $(nproc)"
echo "内存总量: $(free -h | grep '^Mem:' | awk '{print $2}')"
echo "可用内存: $(free -h | grep '^Mem:' | awk '{print $7}')"
echo

# 记录开始时间
START_TIME=$(date +%s)
echo "开始时间: $(date)"
echo

# 运行分析
echo "=== 开始数据质量分析 ==="
echo "执行命令: python check_data_quality_polars.py $PYTHON_ARGS"
echo

# 使用exec来替换当前进程，确保信号正确传递
exec python check_data_quality_polars.py $PYTHON_ARGS

# 下面的代码不会被执行，但保留用于参考
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo
echo "=== 分析完成 ==="
echo "结束时间: $(date)"
echo "总耗时: ${DURATION} 秒 ($(($DURATION / 60)) 分钟)"