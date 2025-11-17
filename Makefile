.PHONY: download cleantrajectories features submission
# 伪目标：这些名称不会生成文件；每次调用都会执行
# Phony targets: these names don't create files; always run when invoked
.SECONDARY:
# 保留由模式规则生成的中间产物，避免被 make 自动清理
# Keep intermediate (pattern-generated) files from being deleted by `make`

# 载入环境相关的路径和参数（如 FOLDER_DATA、SUBMISSIONS_FOLDER 等）
# Load environment-specific paths and options (FOLDER_DATA, SUBMISSIONS_FOLDER, etc.)
include CONFIG

#### SMOOTHING SPLINE PARAMETER
# 平滑样条（csaps）的平滑系数；数值越大曲线越平滑（偏差↑、方差↓）
# Smoothing factor for csaps in interpolate.py. Larger => smoother curves (more bias).
INTERPOL_SMOOTH = 1e-2

#### 爬升切片参数（Climbing slicing parameter）
# 由 feature_climbing.py 使用：在插值轨迹上构造爬升阶段特征。
# 能率差分计算：energyrate(i+CLMB_PERIODS) - energyrate(i)
# Used by feature_climbing.py to build climb-phase features from interpolated trajectories.
# Energy-rate delta computed between indices i and i+CLMB_PERIODS.
# energyrate(i+CLMB_PERIODS)-energyrate(i)
# 爬升阶段差分间隔（采样点数），用于计算能率差分（i 到 i+CLMB_PERIODS）
CLMB_PERIODS = 5
# Keep points with vertical_rate > CLMB_THRESHOLD_VR (units: ft/min)
# 仅保留垂直速度超过该阈值的点（单位：ft/min）
CLMB_THRESHOLD_VR = 500
# Constant thrust flag used by the performance model (1: on, 0: off)
# 恒推力标志（性能模型用）（1 开启，0 关闭）
CLMB_CTHRUST = 1
# Variable used as the vertical-rate proxy (e.g., 'daltitude' from interpolate; units: ft/min)
# 用作垂直速度代理的变量名（通常为 daltitude，由 interpolate 生成，单位：ft/min）
CLMB_VRATE_VAR = daltitude
# If timestamp(i+CLMB_PERIODS)-timestamp(i) > CLMB_THRESHOLD_DT (seconds), drop the interval
# 若时间跨度超过该阈值（秒），丢弃该区间
CLMB_THRESHOLD_DT = 40
# Start of altitude slices (thousands of feet). -0.5 => -500 ft.
# 高度切片起点（千英尺），-0.5 等价于 -500 ft
CLMB_ALT_START = -0.5
# Slice thickness (thousands of feet). 1 => 1000 ft per slice.
# 高度切片步长（千英尺），1 等价于每片 1000 ft
CLMB_ALT_STEP = 1

# 巡航阶段的时间切片数量（feature_cruise_infos.py 使用）
# Number of scaled-time slices for cruise features (feature_cruise_infos.py)
CRUISE_NSPLIT = 20

# 在 filter_trajs.py 中使用的过滤策略名（目前仅实现 'classic'）
# Filtering strategy name used in filter_trajs.py (currently only 'classic' is implemented)
PREFIX_FILTER = classic

# 结果目录前缀编码了参数设置，避免不同配置的产物互相覆盖
# Result prefixes encode parameter settings to keep outputs separate for different configurations
PREFIX_INTERPOL = $(PREFIX_FILTER)__$(INTERPOL_SMOOTH)
PREFIX_MASS = $(PREFIX_INTERPOL)__$(CLMB_PERIODS)_$(CLMB_THRESHOLD_VR)_$(CLMB_THRESHOLD_DT)_$(CLMB_VRATE_VAR)_$(CLMB_CTHRUST)_$(CLMB_ALT_START)_$(CLMB_ALT_STEP)
PREFIX_CRUISE = $(PREFIX_INTERPOL)__$(CRUISE_NSPLIT)

# 输入/输出目录（相对于 CONFIG 中的 FOLDER_DATA）
# Input/output folders (rooted at FOLDER_DATA from CONFIG)
FOLDER_RAW = $(FOLDER_DATA)/rawtrajectories
FOLDER_FLGT = $(FOLDER_DATA)/flights
FOLDER_WEATHER = $(FOLDER_DATA)/weather
FOLDER_THUNDER = $(FOLDER_DATA)/thunder
FOLDER_WIND = $(FOLDER_DATA)/$(PREFIX_INTERPOL)_wind
FOLDER_CRUISE = $(FOLDER_DATA)/$(PREFIX_CRUISE)_cruise
FOLDER_FILT = $(FOLDER_DATA)/$(PREFIX_FILTER)_filtered_trajectories
FOLDER_INT = $(FOLDER_DATA)/$(PREFIX_INTERPOL)_interpolated_trajectories
FOLDER_MASS = $(FOLDER_DATA)/$(PREFIX_MASS)_masses



# 要处理的数据集分割（对应 flights 目录下的 parquet 文件名）
# Dataset splits to process (names correspond to flight parquet files)
FLIGHT_FILES = challenge_set final_submission_set



# 原始轨迹文件名列表（例如：2022-11-04.parquet）
TRAJS_SRC = $(shell ls $(FOLDER_RAW) )
# 示例：2022-11-04.parquet


# 插值后轨迹的目标列表（逐日输出）
TRAJS = $(foreach f,$(TRAJS_SRC),$(FOLDER_INT)/$(f))

# 航班 parquet 目标列表
FLIGHTS = $(foreach f,$(FLIGHT_FILES),$(FOLDER_FLGT)/$(f).parquet)


# 机场+时区 parquet / 预制的 METAR parquet
AIRPORTS = $(FOLDER_DATA)/airports_tz.parquet
METARS = $(FOLDER_DATA)/METARs.parquet
MASSES = $(foreach flight,$(FLIGHT_FILES), $(foreach f,$(TRAJS_SRC),$(FOLDER_MASS)/$(flight)/$(f)))
WINDS = $(foreach flight,$(FLIGHT_FILES), $(foreach f,$(TRAJS_SRC),$(FOLDER_WIND)/$(flight)/$(f)))
CRUISES = $(foreach flight,$(FLIGHT_FILES), $(foreach f,$(TRAJS_SRC),$(FOLDER_CRUISE)/$(flight)/$(f)))
WEATHERS = $(foreach flight,$(FLIGHT_FILES), $(FOLDER_WEATHER)/$(flight).parquet)
THUNDERS = $(foreach flight,$(FLIGHT_FILES), $(FOLDER_THUNDER)/$(flight).parquet)


# 准备输入：构建航班 parquet、复制原始轨迹、下载 METAR parquet
download: $(FLIGHTS) $(foreach f,$(shell ls $(EXISTING_DATA)/rawtrajectories/*.parquet 2>/dev/null | xargs -n 1 basename),$(FOLDER_RAW)/$(f)) $(METARS)

# 构建过滤 + 插值后的轨迹（按天）
cleantrajectories: $(TRAJS)

# 生成所有特征（巡航、爬升质量、风效应、天气、雷暴）
features: $(CRUISES) $(MASSES) $(WINDS) $(WEATHERS) $(THUNDERS)
# 可按需裁剪：#$(WEATHERS) $(THUNDERS) $(WINDS)

# 训练并生成提交：循环 20 个随机种子 + 产出 10/20 模型平均
submissions:
	mkdir -p $(SUBMISSIONS_FOLDER)
	for number in $(shell seq 0 19); do \
		python3 -m pipelines.training.regression -what submit -random_state $$number; \
	done;
	python3 -m pipelines.training.average_prediction -istop 10 -out_csv $(SUBMISSIONS_FOLDER)/averaged_10.csv
	python3 -m pipelines.training.average_prediction -istop 20 -out_csv $(SUBMISSIONS_FOLDER)/averaged_20.csv




# 宏：为单日轨迹计算爬升相关特征（质量、能率等）
define feature_climbing
	python3 -m pipelines.features.feature_climbing -is_climb -t_in $< -f_in $(FOLDER_FLGT)/$(patsubst $(FOLDER_MASS)/%/$(@F),%,$@).parquet -f_out $@ -periods $(CLMB_PERIODS) -thresh_dt $(CLMB_THRESHOLD_DT) -threshold_vr $(CLMB_THRESHOLD_VR) -cthrust $(CLMB_CTHRUST) -vrate_var $(CLMB_VRATE_VAR) -altstep $(CLMB_ALT_STEP)  -altstart $(CLMB_ALT_START) -airports $(AIRPORTS)
endef

# 宏：为单日轨迹计算巡航阶段信息特征
define feature_cruise
	python3 -m pipelines.features.feature_cruise_infos -t_in $< -f_in $(FOLDER_FLGT)/$(patsubst $(FOLDER_CRUISE)/%/$(@F),%,$@).parquet  -f_out $@ -airports $(AIRPORTS) -nsplit $(CRUISE_NSPLIT)
endef

# 宏：沿轨迹计算风效应特征
define feature_wind
	python3 -m pipelines.features.feature_wind_effect -t_in $< -f_in $(FOLDER_FLGT)/$(patsubst $(FOLDER_WIND)/%/$(@F),%,$@).parquet  -f_out $@ -airports $(AIRPORTS)
endef


# 依据航班列表过滤机场并补充时区，生成 airports_tz.parquet
$(AIRPORTS): $(FLIGHTS)
#	curl -o $(FOLDER_DATA)/airports.csv https://github.com/davidmegginson/ourairports-data/blob/main/airports.csv
	python3 -m tools.cli.airports_to_parquet -a_in ourairports2024-10-21.csv -a_out $@  -flights "$(FLIGHTS)"


# 下载预制的 METAR parquet（更可复现实验）；如需从头生成，见下方注释
$(METARS): $(AIRPORTS)
	gdown 'https://drive.google.com/uc?export=download&id=1udmsuT317LECvr1JJNEmhdp0bM2OGq9W' -O $@
	# uncomment below to generate it from scratch
	# result might be different as mesonet's files might have been updated
	# I've experienced one station's location update in a 2 weeks timespan
	# mkdir -p $(FOLDER_DATA)/METARs
	# python3 -m tools.cli.download_metars
	# python3 -m tools.cli.metars_folder_to_parquet -metars_folder_in $(FOLDER_DATA)/METARs -metars_parquet_out $@

# 航班级天气特征（来自 METAR）
$(FOLDER_WEATHER)/%.parquet: $(FOLDER_FLGT)/%.parquet $(AIRPORTS) $(METARS)
	@mkdir -p $(@D)
	python3 -m pipelines.features.feature_weather_from_metars -f_in $< -airports $(AIRPORTS) -metars $(METARS) -f_out $@ -geo_scale 1 -hour_scale 1


# 航班级雷暴指示特征（来自 METAR）
$(FOLDER_THUNDER)/%.parquet: $(FOLDER_FLGT)/%.parquet $(AIRPORTS) $(METARS)
	@mkdir -p $(@D)
	python3 -m pipelines.features.feature_thunder_from_metars -f_in $< -airports $(AIRPORTS) -metars $(METARS) -f_out $@ -geo_scale 1 -hour_scale 1

# 生成航班 parquet：优先使用 EXISTING_DATA 中的 CSV；若无则尝试现成 parquet；否则转换
$(FOLDER_FLGT)/%.parquet:
	mkdir -p $(@D)
	if [ -f "$(EXISTING_DATA)/flights/$(basename $(@F)).csv" ]; then \
		cp "$(EXISTING_DATA)/flights/$(basename $(@F)).csv" "$(FOLDER_FLGT)/$(basename $(@F)).csv"; \
	fi
	if [ ! -f "$(FOLDER_FLGT)/$(basename $(@F)).csv" ] && [ -f "$(EXISTING_DATA)/flights/$(basename $(@F)).parquet" ]; then \
		cp "$(EXISTING_DATA)/flights/$(basename $(@F)).parquet" "$@"; \
		exit 0; \
	fi
	python3 -m tools.cli.flights_to_parquet -f_in $(@:.parquet=.csv) -f_out $@

# 复制原始日轨迹 parquet（来自 EXISTING_DATA）
$(FOLDER_RAW)/%.parquet:
	mkdir -p $(@D)
	if [ -f "$(EXISTING_DATA)/rawtrajectories/$(@F)" ]; then \
		cp "$(EXISTING_DATA)/rawtrajectories/$(@F)" "$@"; \
	elif [ -f "$(EXISTING_DATA)/$(@F)" ]; then \
		cp "$(EXISTING_DATA)/$(@F)" "$@"; \
	else \
		echo "Cannot find $(@F) in $(EXISTING_DATA)/rawtrajectories or $(EXISTING_DATA)"; \
		exit 1; \
	fi

# 过滤重复/未更新/突刺/孤立点（仅置 NaN，不插值）
$(FOLDER_FILT)/%.parquet: $(FOLDER_RAW)/%.parquet
	@mkdir -p $(@D)
	python3 -m pipelines.clean_segment.filter_trajs -t_in $< -t_out $@ -strategy classic

# 平滑并做“限洞插值”（仅填充 <= 20s 的空洞）
$(FOLDER_INT)/%.parquet: $(FOLDER_FILT)/%.parquet
	@mkdir -p $(@D)
	python3 -m pipelines.clean_segment.interpolate -t_in $< -t_out $@ -smooth $(INTERPOL_SMOOTH)

# 单日爬升质量相关特征（final_submission_set）
$(FOLDER_MASS)/final_submission_set/%.parquet: $(FOLDER_INT)/%.parquet  $(AIRPORTS)
	@mkdir -p $(@D)
	$(call feature_climbing)

# 单日爬升质量相关特征（challenge_set）
$(FOLDER_MASS)/challenge_set/%.parquet: $(FOLDER_INT)/%.parquet  $(AIRPORTS)
	@mkdir -p $(@D)
	$(call feature_climbing)


# 单日巡航阶段信息特征（final_submission_set）
$(FOLDER_CRUISE)/final_submission_set/%.parquet: $(FOLDER_INT)/%.parquet  $(AIRPORTS)
	@mkdir -p $(@D)
	$(call feature_cruise)

# 单日巡航阶段信息特征（challenge_set）
$(FOLDER_CRUISE)/challenge_set/%.parquet: $(FOLDER_INT)/%.parquet  $(AIRPORTS)
	@mkdir -p $(@D)
	$(call feature_cruise)


# 单日风效应特征（final_submission_set）
$(FOLDER_WIND)/final_submission_set/%.parquet: $(FOLDER_INT)/%.parquet $(AIRPORTS)
	@mkdir -p $(@D)
	$(call feature_wind)

# 单日风效应特征（challenge_set）
$(FOLDER_WIND)/challenge_set/%.parquet: $(FOLDER_INT)/%.parquet $(AIRPORTS)
	@mkdir -p $(@D)
	$(call feature_wind)
