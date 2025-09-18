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
)

# 历史注记：航班 248803487（2022-01-03）在 unwrap 操作上曾发现异常，保留此条以备排查
from traffic.core import Traffic
import matplotlib.pyplot as plt


def nointerpolate(x):
    """恒等函数，传给 traffic 以禁用内置插值。"""
    return x


def read_trajectories(f, strategy):
    """读取轨迹文件并按策略执行滤波。

    :param f: 输入的 parquet 文件路径。
    :param strategy: 滤波策略名称（目前仅支持 ``classic``）。
    :return: 过滤完成的 ``pandas.DataFrame``。
    """

    df = pd.read_parquet(f)
    for v in ["flight_id"]:
        df[v] = df[v].astype(np.int64)

    # 以航班号+时间戳去重后按时间排序，确保时间序列严格递增
    df = (
        df.drop_duplicates(["flight_id", "timestamp"])
        .sort_values(["flight_id", "timestamp"])
        .reset_index(drop=True)
    )  # .head(10_000)

    if strategy == "classic":
        # 经典策略的滤波器链条，顺序与“数据清理流程”文档保持一致
        filter_chain = (
            FilterCstLatLon()
            | FilterCstPosition()
            | FilterCstSpeed()
            | MyFilterDerivative()
            | FilterIsolated()
        )
    else:
        raise Exception(f"strategy '{strategy}' not implemented")

    dftrafficin = (
        Traffic(df)
        .filter(filter=filter_chain, strategy=nointerpolate)
        .eval(max_workers=1)
        .data
    )

    # 变量屏蔽联动：若位置或高度被置 NaN，同步屏蔽相关天气变量
    dico_tomask = {
        # "track": ["track_unwrapped"],  # 如需同步屏蔽航迹角，可按需启用
        "latitude": ["u_component_of_wind", "v_component_of_wind", "temperature"],
        "altitude": ["u_component_of_wind", "v_component_of_wind", "temperature"],
    }
    for k, lvar in dico_tomask.items():
        for v in lvar:
            dftrafficin[v] = dftrafficin[[v]].mask(dftrafficin[k].isna())

    return dftrafficin


def main():
    parser = argparse.ArgumentParser(
        description="过滤掉高概率异常的轨迹观测",
    )
    parser.add_argument("-t_in", help="输入轨迹 parquet 文件路径")
    parser.add_argument("-t_out", help="输出过滤后 parquet 文件路径")
    parser.add_argument("-strategy", help="过滤策略名称，目前支持 classic")
    args = parser.parse_args()

    df = read_trajectories(args.t_in, args.strategy)
    df.to_parquet(args.t_out, index=False)


if __name__ == "__main__":
    main()
