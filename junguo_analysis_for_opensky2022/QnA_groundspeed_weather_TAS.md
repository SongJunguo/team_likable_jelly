# 飞行轨迹字段与天气/TAS问题答疑（保留对话记忆）

> 更新时间：2025-09-12  
> 目录：`junguo_analysis_for_opensky2022/QnA_groundspeed_weather_TAS.md`

---

## 提问（原文保留）

- `groundspeed` | float64 | 地面速度(节) | 0 到 1445 |  
  `track` | float64 | 航向角(度) | 0 到 359.89  
  这两个参数是不是根据经纬高轨迹计算出来的？

- `vertical_rate` | float64 | 垂直速度(英尺/分) | -30848 到 32640 | 是什么意思？飞机在高度上的变化速度？垂直于地面的高度的变化速度？

- `u_component_of_wind` | float64 | 风速U分量 | -43.62 到 103.33 |  
  `v_component_of_wind` | float64 | 风速V分量 | -68.43 到 59.89 |  
  `temperature` | float64 | 温度(K) | 171.70 到 305.47 |  
  `specific_humidity` | float64 | 比湿 | 0 到 0.02  
  这4个参数是怎么来的？可信吗？是数据自带的？还是通过额外的天气气象模型模型补上去的？对于飞行轨迹的影响大吗？我训练飞行轨迹预测模型需要专门考虑吗？

- `tasx/tasy/tas` 又是怎么获得的？怎么却缺失了30%？是因为插补导致的缺失吗？原始数据里面 `tasx/tasy/tas` 缺失的比例高吗？

---

## 回答（精炼结论 + 代码依据）

### 1) groundspeed / track 是否由经纬高计算？
- 结论：数据自带，不是本仓库里根据经纬度重算的。仓库仅做单位转换和向量分解。
- 代码依据：
  - 角度→弧度转换：`readers.py:43`（`track` 乘以 `np.pi/180`）
  - 速度单位转换：`readers.py:46`（`groundspeed` 乘以 `utils.KTS2MS` → m/s）
  - 分解地速向量：`readers.py:14-15`（`gsx = groundspeed*sin(track)`，`gsy = groundspeed*cos(track)`）

提示：groundspeed/track 也可由相邻位置+时间差近似推导，但本数据集中已由提供方计算好并下发。

### 2) vertical_rate 的含义
- 结论：垂直速度（ft/min），表示高度相对于地面的变化率；正为爬升，负为下降。
- 代码依据：
  - 单位换算：`readers.py:45`（`vertical_rate` 乘以 `utils.FEET2METER/60` → m/s）

### 3) 天气四字段的来源与可信度（u/v 风、温度、比湿）
- 结论：这四列在轨迹文件中“随点提供”，并非仓库内代码用 METAR 等再拼接。命名与单位风格表明它们来自格点化数值天气（如 ERA5/GFS 等）在航迹点的时空插值，而不是机载实测。仓库直接消费这些列（通常原始即 SI 单位）。
- 代码使用：
  - 计算空速向量（见下一节 TAS 计算）：`readers.py:18-21`
  - 风影响特征：`feature_wind_effect.py:16`（`dot(wind, groundspeed)/|groundspeed|`）
- 可信度：对大尺度与趋势（风向风速、气温廓线）可靠；对小尺度扰动受限于格点和时间分辨率。
- 对轨迹预测的影响：
  - 强烈建议纳入风场（u、v），对地速与航迹偏转是一阶影响，收益显著。
  - 温度/比湿在性能/爬升率/能量方程建模中更有价值；若仅做短期平面位置预测，作用次于风，可做可选增强特征。

补充：仓库也包含独立的 `METARs.parquet`（台站观测），但未见逐点将 METAR 与轨迹融合，轨迹上的天气更像是已对齐好的格点外生量。

### 4) TAS（tasx/tasy/tas）如何得到？为何出现 ~30% 缺失？
- 计算关系（空速 = 地速 − 风）：
  - `gsx = groundspeed * sin(track)`，`gsy = groundspeed * cos(track)`（地速向量）
  - `tasx = gsx − u_component_of_wind`，`tasy = gsy − v_component_of_wind`
  - `tas = sqrt(tasx^2 + tasy^2)`
  - 代码位置：`readers.py:14-21`；单位统一转换在 `readers.py:43-46`。
- 为什么你观察到 “缺失 ~33%”：
  - 这是“插值版轨迹”的统计，不是原始数据的问题。插值/平滑流程对超过阈值（默认 >20s）的时间裂缝整段掩蔽为 NaN；而 TAS 依赖多列（groundspeed、track、u、v），任一缺失会导致 TAS 缺失，放大 NaN 比例。
  - 证据：
    - 插值变量清单包含 `tasx/tasy/tas`：`pipelines/clean_segment/interpolate.py:62`
    - 平滑与分组阈值：`pipelines/clean_segment/interpolate.py:67,69-70`（风和速度类用较小平滑系数；温湿度单列平滑）
    - 位置/高度缺失时同时掩蔽天气：`pipelines/clean_segment/filter_trajs.py:28-30`
- 原始数据的 TAS 缺失率：原始 parquet 不直接包含 TAS（三者是派生量）。若在“原始点”逐点计算，只有当输入列（groundspeed/track 或 u/v）缺失时才会缺失。你在报告中统计的原始缺失（groundspeed/track/vertical_rate 约 0.28%）已很低，风场列原始通常也较完整，因此“原始逐点计算的 TAS 缺失率”应远低于插值版的 ~33%。

---

## 实操建议（用于模型训练）

- 必选特征：
  - 风场 `u_component_of_wind`、`v_component_of_wind`（或将其投影到航迹向/侧风分量）。
- 视任务可选：
  - `temperature`、`specific_humidity`（做能量方程/爬升率/马赫数等相关建模时收益更明显）。
- 派生特征参考：
  - `wind_effect = dot(wind, groundspeed)/|groundspeed|`，见 `feature_wind_effect.py:16`
  - `mach = tas→mach(altitude)`，见 `feature_cruise_infos.py:17`
- 数据源选择：
  - 优先使用原始轨迹（rawtrajectories/）。插值版轨迹在本仓库设置下会引入较多 NaN（`pipelines/clean_segment/interpolate.py` 的断点掩蔽与多列依赖所致）。

---

## 代码引用（便捷跳转）

- `readers.py:14`
- `readers.py:15`
- `readers.py:18`
- `readers.py:19`
- `readers.py:20`
- `readers.py:43`
- `readers.py:45`
- `readers.py:46`
- `pipelines/clean_segment/interpolate.py:62`
- `pipelines/clean_segment/interpolate.py:67`
- `pipelines/clean_segment/interpolate.py:69`
- `pipelines/clean_segment/interpolate.py:70`
- `pipelines/clean_segment/filter_trajs.py:28`
- `pipelines/clean_segment/filter_trajs.py:29`
- `pipelines/clean_segment/filter_trajs.py:30`
- `feature_wind_effect.py:16`
- `feature_cruise_infos.py:17`

---

## 后续可做

- 计算“原始逐点”TAS 的真实缺失率统计，用于和插值版对照。
- 增加风向量投影特征（沿航向/横风）与密度/马赫等气动特征模板。
- A/B 评估：含风 vs 不含风的短期轨迹预测精度差异。

---

以上整理包含原始提问与详细答复，并附上仓库内相关代码位置作为依据，便于复核与扩展。

