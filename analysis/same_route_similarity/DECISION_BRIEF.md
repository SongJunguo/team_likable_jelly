# 跨天同航线相似度 1 页决策简报

## 结论（先看）
1. 同航班跨天与同航线跨天都显著优于随机异航线。
2. 同航班跨天只比同航线跨天小幅更优（中位约 8.3%），不是数量级提升。
3. 相似性集中在首尾阶段：起飞与降落明显更相似，中段最不相似。

## 核心数字
数据窗口：`2022-01-01` 到 `2022-02-28`，有效轨迹 `3671`，pair `40106`。

- `same_flight_cross_day`：`mean_pointwise_km` 中位 `19.538`
- `same_route_cross_day`：`mean_pointwise_km` 中位 `21.308`
- `diff_route_random`：`mean_pointwise_km` 中位 `963.807`

阶段对比（跨天）：

- 同航班：起飞 `0-5% = 3.278 km`，降落 `95-100% = 2.460 km`，全程 `19.538 km`
- 同航线：起飞 `0-5% = 4.493 km`，降落 `95-100% = 3.130 km`，全程 `21.308 km`

## 业务含义
1. “同航班记忆”有价值，但不能单独当主策略。
2. 更稳健策略是“同航线召回 + 同航班重排 + 阶段加权”。
3. 对小模型，应优先用高稳定航线构建参考库，再叠加同航班残差记忆。

## 推荐落地方案
1. 召回层：按 `adep+ades` 检索候选历史轨迹。
2. 重排层：加入 `callsign`、阶段匹配（起飞/进近）、天气上下文。
3. 训练层：提高 `0-10%`、`90-100%` 损失权重，降低中段权重。
4. 质控层：建立“高稳定航线白名单”（例如航线中位相似度 `<=15km`）。

## 风险与边界
1. 当前时间窗仅 2 个月，季节与长期运行变化未覆盖。
2. 当前按归一化时间对齐，未做按弧长/关键事件点对齐。
3. 未显式引入跑道、流控、天气扰动等外生变量。

## 关键图与数据
- 全局分布：`analysis/same_route_similarity/output/figures/distribution_boxplot_log.png`
- 全局 CDF：`analysis/same_route_similarity/output/figures/distance_cdf_log.png`
- 阶段轮廓：`analysis/same_route_similarity/output/figures/phase_profile_focus_linear.png`
- 阶段汇总：`analysis/same_route_similarity/output/phase_similarity_summary.csv`
- 起降细分：`analysis/same_route_similarity/output/takeoff_landing_segment_summary.csv`
