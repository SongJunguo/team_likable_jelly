# 过滤 
原始数据高度使用的ft做单位
投票前先过滤掉删掉只有经度没有纬度和只有纬度没有经度的点，以防转换米制失效，残留无法处理的异常点
三点投票使用新写的 FilterMaxSpeedSkipNaN进行三点投票的速度和加速度计算，因为是从经纬高转化到米制单位，更精确的过滤330m/s以上的异常点？可以把阈值设置宽松一些，比如600m/s
三点投票，只要投票出来就把一行全部删除，弄成nan，不再仅仅处理那一个经度，纬度或高度。（只有经度没有纬度和只有纬度没有经度的点，会导致转换米制失效）
循环三点投票，直到没有可以删除的异常点，因为有的异常段落，需要反复三点投票从两端慢慢蚕食异常点，一次投票可能只能去除左右两端的各自一个异常点。
* 新设计的过滤逻辑顺序,简化原来复杂的设计：
``` python
| FilterCstLatLon()
| FilterCstPosition()
| FilterCstSpeed()
| FilterEdgeOutlier()   
 # 第2道防线：跨越NaN检测间接超速（过滤器删除中间点后形成的超速）
| FilterMaxSpeedSkipNaN(max_speed_mps=550, max_iterations=10)
| FilterIsolated()
```


# 插值和切分轨迹
应该先根据时间戳进行轨迹切分，大于阈值（20秒）的空洞，就在空洞两端断成两个轨迹，不要中间的空洞了
然后再把每个小段重采样到标准的1hz，再线性插值，可以考虑使用带平滑的interpolate.py
具体，先根据原始小段的开头和结尾时间新建一个空的表，然后再根据时间戳把数据填进去，然后插值。

原有的过滤和插值切分轨迹代码在：
junguo_analysis_for_interpolation
junguo_analysis_for_opensky2022/analysis_for_interpolation
junguo_analysis_for_opensky2022/analysis_for_interpolation/todo.md
filter_trajs.py
filterclassic.py


FilterMaxSpeedSkipNaN是没有三点投票法的，是直接删除所有的异常点，投票可以参考MyFilterDerivative？
过滤脚本为什么不在已有的filter_trajs.py上新增呢？不过现在的项目太混乱了，尤其是junguo_analysis_for_opensky2022/analysis_for_interpolation下面，新建一个或许也可以？不过原有修改也很好。
阶段2：修改切分脚本会不会影响现有的流程？我在使用junguo_analysis_for_opensky2022/analysis_for_interpolation/run_full_pipeline_with_interpolate.sh。你帮我检查一下。
  2.2.3 阶段3：创建segment级别插值脚本，你一定多多参考现在有的代码不要缺少了功能。
现在项目代码有些太乱了，我自己看着都难受，你帮我多想想办法？把这次的新过滤代码都放独立的junguo_analysis_for_interpolation文件夹会有用吗？

# 第三次提问回答
classic_dp可以删除了，没有用，不好用
junguo_analysis_for_opensky2022/analysis_for_interpolation/run_detect_jumps_all.sh这个功能很重要，我用这个检查最后的生产的轨迹有没有异常点，这个怎么在新的目录里面安排？是移动过去？还是单纯引用？
新增strategy="todo_strict"换个更贴切的名字吧
FilterMaxSpeedSkipNaNWithVoting对于超速度的是当前两个点各投一票，超加速度的才是三个点前点、当前点、后点各加票，你没搞错吧？
  export FILTERED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/filtered_todo_strict_v1"
  export SEGMENTED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/segmented_todo_v1"
  export INTERPOLATED_DIR="/workspace/aircraft_trajectory/team_likable_jelly/opensky_2024_PRC_dataset/interpolated_todo_v1"

  # 过滤参数
  export FILTER_STRATEGY="todo_strict"
  别叫todo，想个更好的名字
  export MAX_HOLE_SIZE=3  # 保守：小间隔也不插值（可选）这个好像没有用，我要希望最后的轨迹一个nan都没有，一个异常点都没有。

因为我用的机械硬盘，我有个想法就是一个parquet读取进来了，能不能把filter 分割和插值一口气在内存做好，更快，不过这样不好检查哪个阶段出问题了，是不是还在现在每个阶段存储一次更好？

可视化工具暂时不着急，我有另一个工程用于parquet的可视化。质量检测run_detect_jumps_all.sh和最后的轨迹文件有没有nan很重要


# 第四次问答
  # 最终判决：
  data.loc[index[np.logical_or(killa >= 2, killv >= 2)], column] = np.nan
  # 票数≥2才删除
  注意整行删除，不是一个点的删除的。
MyFilterDerivative 在计算导数前会排除 NaN 并基于真实时间间隔（timestamp 列的 dt.total_seconds()）做不等间隔处理，同时对航迹角做 np.unwrap，这些处理在跨 NaN 的速度/加速度版本中也要同步，避免时间跨度、角度跳变带来的假报警。
“跨 NaN” 的速度需要明确是“忽略中间所有 NaN、直接连接最近的两个有效点”，那加速度就只能在至少三个有效点都存在的区间上计算；实现时要保证索引在这些条件不满足时不会访问越界。
由于 FilterMaxSpeedSkipNaNWithVoting 主要面向 latitude/longitude（或地速）而不是单一列，记得像 MyFilterDerivative 一样先在每列内部构建自己的 nanmask，不要跨列混用。
junguo_analysis_for_opensky2022/analysis_for_interpolation/check_nan_values.py是不是能检测nan数量，里面代码有没有问题？


# 第五次问答

  为什么整行删除？
  - 速度异常说明位置有问题，而位置包含lat/lon/alt
  - 位置异常→其他观测（速度、航迹角等）也不可信
  - 避免"只有经度无纬度"的部分坐标点（会导致插值异常）

  我觉得天气相关的所有都删除的好，因为位置有问题，相关的天气等等参数都是根据位置从气象模型获得，都可能有问题

  /opt/miniconda3/envs/opensky/bin/python   是正确的python路径

  
  1. 等待测试完成（后台运行中）
    - 检查：ls -lh /tmp/test_interpolated_2022-01-01.parquet
    - 如果成功，会生成约300-400MB的文件
  2. 验证结果质量
  /opt/miniconda3/envs/opensky/bin/python -c "
  import pandas as df
  df = pd.read_parquet('/tmp/test_interpolated_2022-01-01.parquet')
  print(f'总点数: {len(df):,}')
  print(f'Segments: {df[\"flight_id\"].nunique()}')
  print(f'NaN数: {df.isna().sum().sum()}')
  "
  3. 修复run_fast_pipeline.sh
    - 将Python路径改为绝对路径（/opt/miniconda3/envs/opensky/bin/python）
    - 这样可以批量处理全年数据
  4. 全量运行（验证通过后）
  bash clean_segment_pipeline/run_fast_pipeline.sh

# 第六次提问

现在的多进程是在文件层面控制，也就是一次性控制多少parquet文件进行。但是这样的非常的不好，因为一个文件就很大，单独跑完一次测试，就是一个文件一个进程，要等很久很久。
能不能在更细致的层面控制呢？比如轨迹层面进行多进程？然后先一个parquet一个parquet进行，每个parquet内部根据轨迹进行多进程，不是现在多个parquet多进程。这会不会很复杂？

# 第七次提问
2025-11-09 02:51:48 INFO 22/24 interpolated_2022-01-04.parquet → 未发现跳变
2025-11-09 02:51:48 INFO 23/24 interpolated_2022-01-03.parquet → 未发现跳变
2025-11-09 02:51:48 INFO 24/24 interpolated_2022-01-02.parquet → 未发现跳变
2025-11-09 02:51:48 INFO 跳变事件总数: 14，涉及航班 3 架次
2025-11-09 02:51:48 INFO 汇总表已写入: /workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/jump_detection/jump_events_summary.csv
2025-11-09 02:51:48 INFO 事件明细总表: /workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/jump_detection/jump_events_all.csv
2025-11-09 02:51:48 INFO 日志输出: /workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/jump_detection/detect_perfect_jumps.log
✅ 跳变检测完成。输出目录: /workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/jump_detection
  ✅ 跳变检测完成：/workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/jump_detection

[2/3] NaN检测...
🔍 检查 24 个文件...
^[[A^[[A^[[A^[[B^[[B^[[B^[[B^[[B^[[A❌ 质量检查失败：发现24个文件有NaN
   详细报告: /workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/nan_check_report.txt
  ❌ NaN检测失败（发现NaN！）
  详见: /workspace/aircraft_trajectory/team_likable_jelly/reports/quality_check_clean_v1/nan_check_report.txt
(opensky) root@ea820f0b5965:/workspace/aircraft_trajectory/team_likable_jelly# 
  clean_segment_pipeline/run_fast_pipeline_parallel.sh
  clean_segment_pipeline/run_fast_pipeline.sh
  clean_segment_pipeline/run_staged_pipeline.sh\
  我希望可以自动执行检测，通过一个变量开关控制是否执行检测\\
  nan检测你可以应该汇报经纬高有没有缺失，，没有的话，给出一个总体的指标而不是每个文件单独给，看起费劲、\
  junguo_analysis_for_opensky2022/analysis_for_interpolation
  junguo_analysis_for_opensky2022/analysis_for_interpolation/All_trajectory_NaN_analysis.py
  junguo_analysis_for_opensky2022/analysis_for_interpolation/check_nan_values.py\
  你看看这两个nan检测功能更好吗？

  # 第八次提问
  > clean_segment_pipeline/config.sh\\
  里面export MAX_ACCEL_MPS2=15.0      # 加速度阈值这个阈值是怎么来的？\
  这个的单位是什么？
我想知道这个数据为什么设置为15？
还有我知道高度的原始单位是ft，分辨率是25，也就是高度上的速度和加速度计算都会受到影响的。
他这个加速度速度和加速度是计算的3维空间的吗？
现在阈值好像太严格了，轨迹被切的稀碎，每个小轨迹只有几百点。
我是不是应该分开给出经纬和高度的速度和加速度阈值？而不是使用3维空间的？
因为ads-b数据的经纬和高度不是同一个来源？

junguo_analysis_for_opensky2022/analysis_for_interpolation/run_full_pipeline_with_interpolate.sh这个会好一些，轨迹不很稀碎。

我在想能不能出一个报告，就是filter时候，告诉我filter掉了多少点？或者一些相关信息？或者先统计一下raw数据大部分的轨迹点之间的速度加速度是多少？我好判断经纬上的分辨率是多少？噪声有多少？

opensky_2024_PRC_dataset/rawtrajectories
opensky_2024_PRC_dataset/classic_filtered_trajectories_doublepass_loop_v8
能不能统计这两个raw和过滤了的轨迹数量和数据点的数量差距多少？
现在项目里面有没有能实现这个功能的代码？
没有的话，你给出实现方案？考虑多进程？

