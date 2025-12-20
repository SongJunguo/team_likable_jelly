#!/bin/bash

# ==============================================================================
# ** 航空轨迹数据预处理一键运行脚本 (适配 Parquet 单文件版) **
#
# ** 对应 Python 脚本: ** flight_data_preprocessor.py
# ** 功能: **
#   - 自动激活 Conda 环境
#   - 设置物理清洗与平滑参数
#   - 执行单文件并行处理流程
# ==============================================================================

# --- 1. 环境准备 ---
echo "--- 正在检查并激活 Conda 环境: traffic ---"

# 尝试在常见路径中寻找 conda 初始化脚本
if [ -f "/opt/miniconda3/etc/profile.d/conda.sh" ]; then
    source "/opt/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/miniconda3/etc/profile.d/conda.sh"
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
    source "$HOME/anaconda3/etc/profile.d/conda.sh"
elif [ -f "/opt/conda/etc/profile.d/conda.sh" ]; then
    source "/opt/conda/etc/profile.d/conda.sh"
else
    echo "警告: 未找到标准路径下的 conda 初始化脚本，尝试使用 conda init..."
    if command -v conda &> /dev/null; then
        eval "$(conda shell.bash hook)"
    else
        echo "❌ 错误: 无法找到 conda 命令，请确保已安装 Anaconda 或 Miniconda。"
        exit 1
    fi
fi

# 激活名为 traffic 的虚拟环境
conda activate traffic

if [ $? -ne 0 ]; then
    echo "❌ 激活环境失败！请检查是否存在名为 'traffic' 的环境。"
    exit 1
fi
echo "✓ 环境激活成功。"

# --- 2. 文件路径配置 ---

# 输入文件路径 (必须是 Parquet 格式的整合大文件)
INPUT_FILE="ProcessedData/combined_adsb_data.parquet"

# 输出文件路径
OUTPUT_FILE="TrainData/final_data.parquet"

# --- 3. 核心算法参数配置 ---

# 重采样频率 (1S = 1秒)
RESAMPLE_FREQ="1s"

# [物理参数] 速度/高度平滑 Sigma (建议 1.0~3.0)
GAUSSIAN_SIGMA=2.0

# [过滤] 高度范围 (单位与数据一致)
H_MIN=-1000
H_MAX=42000

# [过滤] 垂直速率限制 (ft/min)
VR_MIN=-6000
VR_MAX=6000

GS_MIN=50
GS_MAX=600
# [融合] 高度互补滤波权重 (0.95 代表非常信任积分推算)
ALT_FUSION_WEIGHT=0.60

# [过滤] 最小有效轨迹长度 (点数)
# 注意：你的旧脚本设置为 792，这里保留该值，如果太严格可改为 50
MIN_LEN=792

# 并行工作进程数 (默认 4，根据你的 CPU 核心数调整)
MAX_WORKERS=8

# 日志级别
LOG_LEVEL="INFO"

# --- 4. 执行前检查 ---

# 检查输入文件是否存在
if [ ! -f "$INPUT_FILE" ]; then
    echo "❌ 错误: 输入文件 '$INPUT_FILE' 不存在！"
    echo "请确保你已经运行了数据合并脚本，生成了 Parquet 文件。"
    exit 1
fi

# 自动创建输出目录
OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
if [ ! -d "$OUTPUT_DIR" ]; then
    echo "--- 创建输出目录: $OUTPUT_DIR ---"
    mkdir -p "$OUTPUT_DIR"
fi

echo ""
echo "========================================================"
echo "   开始执行飞行数据预处理 (Python)"
echo "========================================================"
echo "  输入文件 : $INPUT_FILE"
echo "  输出文件 : $OUTPUT_FILE"
echo "  重采样率 : $RESAMPLE_FREQ"
echo "  并行进程 : $MAX_WORKERS"
echo "  高斯Sigma: $GAUSSIAN_SIGMA"
echo "  垂直限制 : $VR_MIN ~ $VR_MAX ft/min"
echo "========================================================"
echo ""

# --- 5. 构建命令并执行 ---

# 使用数组构建命令，精确匹配 flight_data_preprocessor.py 的 argparse 参数
CMD_ARGS=(
    --input_file "$INPUT_FILE"
    --output_file "$OUTPUT_FILE"
    --resample_freq "$RESAMPLE_FREQ"
    --gaussian_sigma "$GAUSSIAN_SIGMA"
    --h_min "$H_MIN"
    --h_max "$H_MAX"
    --vr_min "$VR_MIN"
    --vr_max "$VR_MAX"
    --gs_min "$GS_MIN"
    --gs_max "$GS_MAX"
    --alt_fusion_weight "$ALT_FUSION_WEIGHT"
    --min_len "$MIN_LEN"
    --max_workers "$MAX_WORKERS"
    --log_level "$LOG_LEVEL"
)

# 调用 Python 脚本
python flight_processor.py "${CMD_ARGS[@]}"

# 检查执行结果
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 预处理流程执行完毕！"
    echo "结果已保存至: $OUTPUT_FILE"
else
    echo ""
    echo "❌ 脚本执行过程中发生错误，请检查上方 Python 日志。"
    exit 1
fi