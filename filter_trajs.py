"""轨迹过滤主脚本。

命令入口：``python3 filter_trajs.py -t_in <raw> -t_out <filtered> -strategy classic``。
脚本读取原始 parquet 轨迹文件，按照策略拼接多个滤波器（参见 :mod:`filterclassic`），
以 ``strategy=nointerpolate`` 的方式仅对异常观测置 NaN，不做任何插值。
"""

import argparse

import pandas as pd
import numpy as np
import utils
from filterclassic import (
    FilterCstLatLon,
    FilterCstPosition,
    FilterCstSpeed,
    FilterIsolated,
    MyFilterDerivative,
    FilterShortBurst,
    FilterDerivativeLoop,
    FilterEdgeOutlier,
    FilterMaxSpeed,
    FilterAxisSpeed,
    FilterMaxSpeedSkipNaN,
)
from traffic.algorithms import filters

# 历史注记：航班 248803487（2022-01-03）在 unwrap 操作上曾发现异常，保留此条以备排查
from traffic.core import Traffic
import matplotlib.pyplot as plt

DERIV_PARAMS = {
    "latitude": dict(first=0.004, second=0.02),
    "longitude": dict(first=0.004, second=0.02),
    "altitude": dict(first=126, second=50),
}


def _make_derivative(**overrides):
    params = {k: v.copy() for k, v in DERIV_PARAMS.items()}
    for key, value in overrides.items():
        params[key] = value
    return MyFilterDerivative(**params)


def nointerpolate(x):
    """恒等函数，传给 traffic 以禁用内置插值。"""
    return x


def build_filter_chain(strategy: str) -> filters.FilterBase:
    if strategy == "classic":
        # 构建经典过滤器链：按数据清理流程文档的顺序组合多个过滤器
        # 使用管道操作符 | 实现链式过滤，每个过滤器依次处理数据
        return (
            FilterCstLatLon()
            | FilterCstPosition()
            | FilterCstSpeed()
            | _make_derivative()
            | FilterEdgeOutlier()
            | FilterIsolated()
        )
    elif strategy == "classic_shortburst":
        # 在 classic 基础上增加“短簇剔除”（滑窗+密度，保守参数）
        return (
            FilterCstLatLon()
            | FilterCstPosition()
            | FilterCstSpeed()
            | _make_derivative()
            | FilterShortBurst()
            | FilterEdgeOutlier()
            | FilterIsolated()
        )
    elif strategy == "classic_dp":
        # 双次三点投票（double-pass）：第一次默认阈值，第二次轻微放宽一阶阈值
        dp2 = _make_derivative()
        return (
            FilterCstLatLon()
            | FilterCstPosition()
            | FilterCstSpeed()
            | _make_derivative()
            | dp2
            | FilterEdgeOutlier()
            | FilterIsolated()
        )
    elif strategy == "classic_dp_loop":
        dp_relaxed = _make_derivative()
        return (
            # 第1道防线：在原始数据上过滤极端速度异常，避免时间聚合误判
            FilterMaxSpeed(max_speed_mps=550)
            | FilterAxisSpeed(
                max_lat_deg_per_sec=0.0054,   # 600 m/s
                max_lon_deg_per_sec=0.008,    # 全球适用（赤道890m/s，60°N 445m/s）
                max_alt_ft_per_sec=164.0      # 50 m/s ≈ 9843 ft/min
            )
            | FilterCstLatLon()
            | FilterCstPosition()
            | FilterCstSpeed()
            | _make_derivative()    # pass1
            | FilterDerivativeLoop(base=dp_relaxed, max_passes=10, min_passes=4)
            | FilterEdgeOutlier()
            # 第2道防线：跨越NaN检测间接超速（过滤器删除中间点后形成的超速）
            | FilterMaxSpeedSkipNaN(max_speed_mps=550, max_iterations=5)
            | FilterIsolated()
        )
    else:
        raise Exception(f"strategy '{strategy}' not implemented")


def read_trajectories(f, strategy):
    """读取轨迹文件并按策略执行滤波。"""

    df = pd.read_parquet(f)
    for v in ["flight_id"]:
        df[v] = df[v].astype(np.int64)

    # 以航班号+时间戳去重后按时间排序，确保时间序列严格递增
    df = (
        df.drop_duplicates(["flight_id", "timestamp"])
        .sort_values(["flight_id", "timestamp"])
        .reset_index(drop=True)
    )  # .head(10_000)

    filter_chain = build_filter_chain(strategy)

    # 执行过滤器链：应用所有过滤器并禁用内置插值
    dftrafficin = (
        Traffic(df)
        .filter(filter=filter_chain, strategy=nointerpolate)  # 应用过滤器链
        .eval(max_workers=1)  # 单线程执行（便于调试和稳定性）
        .data                 # 提取处理后的DataFrame
    )

    # 数据质量联动屏蔽：当关键位置变量异常时，同步屏蔽依赖的天气变量
    # 逻辑：如果不知道飞机位置，对应位置的天气数据就无意义
    dico_tomask = {
        # "track": ["track_unwrapped"],  # 航迹角屏蔽（可选）
        "latitude": ["u_component_of_wind", "v_component_of_wind", "temperature"],   # 纬度异常→屏蔽天气
        "altitude": ["u_component_of_wind", "v_component_of_wind", "temperature"],   # 高度异常→屏蔽天气
    }
    for k, lvar in dico_tomask.items():           # k: 主变量, lvar: 依赖变量列表
        for v in lvar:                            # v: 当前要屏蔽的依赖变量
            # 若主变量k为NaN，则将依赖变量v的对应行也置为NaN
            dftrafficin[v] = dftrafficin[[v]].mask(dftrafficin[k].isna())

    return dftrafficin


def main():
    parser = argparse.ArgumentParser(
        description="过滤掉高概率异常的轨迹观测",
    )
    parser.add_argument("-t_in", help="输入轨迹 parquet 文件路径")
    parser.add_argument("-t_out", help="输出过滤后 parquet 文件路径")
    parser.add_argument(
        "-strategy",
        help="过滤策略名称: classic / classic_shortburst / classic_dp / classic_dp_loop",
    )
    args = parser.parse_args()

    df = read_trajectories(args.t_in, args.strategy)
    df.to_parquet(args.t_out, index=False)


if __name__ == "__main__":
    main()
