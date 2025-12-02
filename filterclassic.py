"""filterclassic
================

本模块实现 ``filter_trajs.py`` 中“经典滤波（classic）”策略所用的一系列基础
滤波器。所有滤波器均遵循 :class:`traffic.algorithms.filters.FilterBase` 的组合
接口，可以通过管道串联。整个策略的核心理念是：**只通过将异常观测置为 NaN 来
屏蔽数据，不在此阶段做任何形式的插值**，以免引入非真实的轨迹点。

包含的滤波器：

- ``FilterCstLatLon`` —— 检测相邻采样的经纬度是否重复广播。
- ``FilterCstPosition`` —— 三维位置整体未更新时将其清空。
- ``FilterCstSpeed`` —— 垂直速度、航迹角、对地速度同时静止时屏蔽。
- ``MyFilterDerivative`` —— 基于一阶/二阶导阈值识别“突刺点”。
- ``FilterIsolated`` —— 局部时间上过于孤立的观测直接置空。

在 ``docs/数据清理流程.md`` 中可以找到这些滤波器在清洗流程里的整体说明与
阈值表。本文件提供的实现只负责识别并屏蔽异常观测，不进行插值（策略中显式
设置 ``strategy="nointerpolate"``）。
"""

from traffic.algorithms import filters
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,  # for python 3.8 and impunity
    Generic,
    Optional,
    Protocol,
    Type,
    TypedDict,
    TypeVar,
    cast,
)


def checktime(df: pd.DataFrame) -> None:
    """验证 ``timestamp`` 是否严格递增。

    在数据预处理阶段，可用于快速断言轨迹时间序列已经排序且无重复。若发现
    任意非递增的时间步，会抛出 ``AssertionError``，提示需要先整理时间顺序。
    """
    t = df.timestamp.values
    assert (t[1:] > t[:-1]).all()


def isvar(v: np.ndarray) -> np.ndarray:
    """判断相邻采样是否发生变化。

    - 自动忽略任何一端为 NaN 的比较，避免错误触发。
    - 返回一个长度为 ``len(v) - 1`` 的布尔数组，对应 ``(i-1, i)`` 两点是否更新。
    """
    isnotnan = ~np.isnan(v)
    # 仅在两侧都非 NaN 的位置比较数值
    diffnotnan = np.logical_and(isnotnan[1:], isnotnan[:-1])
    diff = v[1:] != v[:-1]
    return np.logical_and(diff, diffnotnan)


class FilterCstLatLon(filters.FilterBase):
    """检测经纬度重复广播的滤波器。

    若当前采样与上一有效采样的 ``latitude`` 与 ``longitude`` 完全相同，判断为
    重复广播并置 NaN，以避免轨迹出现连续停滞的假象。
    """

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # 逐元素对比经纬度变化情况
        lat = df.latitude.values
        lon = df.longitude.values
        isupdated = np.zeros(lat.shape, dtype=bool)
        # 任何一项变化即可视为“更新过”
        isupdated[1:] = np.logical_or(isvar(lat), isvar(lon))
        # 对未更新的行（除首行外）清空经纬度
        df.loc[np.logical_not(isupdated), ["latitude", "longitude"]] = np.nan
        return df


def compute_holes(t: np.ndarray, inans: np.ndarray) -> np.ndarray:
    """计算每个采样点与最近有效观测之间的最小时间差。

    ``inans`` 为布尔掩码，表示当前变量在对应索引处是否已是 NaN。为了衡量有效
    观测之间的距离，需要在寻找前/后邻居时跳过这些 NaN 点。
    """
    tnan = t.copy()
    # 将 NaN 位置的时间戳清空，这样在填充时会被忽略
    tnan[inans] = np.nan
    # 前向/后向填充得到最近有效时间
    tf = pd.DataFrame({"tf": tnan}, dtype=np.float64).ffill().values[:, 0]
    tb = pd.DataFrame({"tb": tnan}, dtype=np.float64).bfill().values[:, 0]
    # 初始化为一个足够大的值，后续通过取最小值更新
    dt = 10000.0 * np.ones(tnan.shape[0], dtype=np.float64)
    # 最近未来有效点的时间差
    dt[:-1] = np.minimum(dt[:-1], tb[1:] - tnan[:-1])
    # 最近过去有效点的时间差
    dt[1:] = np.minimum(dt[1:], tnan[1:] - tf[:-1])
    return dt


class FilterIsolated(filters.FilterBase):
    """剔除与其它观测相距 20 秒以上的孤立点。

    对除标识符和时间列外的每个变量独立处理：若该变量在某时刻距其它任何有效
    观测的最短时间差 ≥ 20 秒或无法计算，则将该变量置为 NaN。
    """

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # 过滤掉标识和时间字段，只处理观测量
        lvar = [x for x in list(df) if x not in ["timestamp", "icao24", "flight_id"]]
        # 将时间戳转换为“自首个采样起的秒数”
        df["t"] = (
            (df.timestamp - df.timestamp.iloc[0]) / pd.to_timedelta(1, unit="s")
        ).values.astype(np.float64)
        for v in lvar:
            dt = compute_holes(df["t"], np.isnan(df[v].values))
            # 超过 20 秒即判定为孤立观测
            df[v] = df[v].mask(dt > 20)
            # 无法计算的情况（dt 为 NaN）同时屏蔽
            df[v] = df[v].mask(np.isnan(dt))
        return df.drop(columns=["t"])


class FilterCstPosition(filters.FilterBase):
    """若高度与经纬度三者均未更新，则清空当前行。

    与 ``FilterCstLatLon`` 类似，但将高度 ``altitude`` 也纳入判断，防止飞机在
    垂直方向上也被重复广播。
    """

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.shape[0] <= 1:
            return df
        alt = df.altitude.values
        lat = df.latitude.values
        lon = df.longitude.values
        isupdated = np.zeros(alt.shape, dtype=bool)
        # 只要高度或经纬度发生变化，就视为更新
        isupdated[1:] = np.logical_or(isvar(alt), isvar(lat))
        isupdated[1:] = np.logical_or(isupdated[1:], isvar(lon))
        df.loc[
            np.logical_not(isupdated), ["latitude", "longitude", "altitude"]
        ] = np.nan
        return df


class FilterCstSpeed(filters.FilterBase):
    """若速度相关指标全部未更新，则清空对应列。"""

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.shape[0] <= 1:
            return df
        vrate = df.vertical_rate.values
        track = df.track.values
        gs = df.groundspeed.values
        isupdated = np.zeros(vrate.shape, dtype=bool)
        # 垂直速度 / 对地速度 / 航迹角只要有任意项变化即可
        isupdated[1:] = np.logical_or(isvar(vrate), isvar(gs))
        isupdated[1:] = np.logical_or(isupdated[1:], isvar(track))
        df.loc[
            np.logical_not(isupdated), ["vertical_rate", "track", "groundspeed"]
        ] = np.nan
        return df


class DerivativeParams(TypedDict):
    # 一阶导（变化速率）阈值，单位与对应变量相匹配（例如高度/秒）
    first: float
    # 二阶导（变化加速度）阈值，用于识别强烈震荡
    second: float


class MyFilterDerivative(filters.FilterBase):
    """基于导数阈值识别突刺点的自定义滤波器。

    算法流程：

    - 使用 ``timestamp`` 计算真实的时间间隔 ``Δt``（秒）。
    - 对 ``track`` 先执行 ``np.unwrap(period=360)``，避免 0/360 跳变造成假差。
    - 一阶导 ``|x[i] - x[i-1]| / Δt[i]`` 近似变量的速度；
      二阶导 ``2 * |Δdx| / (Δt[i] + Δt[i-1])`` 反应突刺程度。
    - 二阶导超阈值时，对 ``i-1``、``i``、``i+1`` 三个点各加一票；
      一阶导超阈值时，对 ``i-1``、``i`` 各加一票；最终票数 ≥ 2 的点被置 NaN，
      兼顾稳健性与敏感度。
    """

    # 默认阈值配置，数值参考业务团队提供的经验参数
    default: ClassVar[dict[str, DerivativeParams]] = dict(
        altitude=dict(first=200, second=50),
        geoaltitude=dict(first=200, second=150),
        vertical_rate=dict(first=1500, second=1000),
        groundspeed=dict(first=12, second=10),
        track=dict(first=12, second=10),
        latitude=dict(first=0.01, second=0.06),
        longitude=dict(first=0.01, second=0.06),
    )

    def __init__(
        self, time_column: str = "timestamp", **kwargs: DerivativeParams
    ) -> None:
        """支持按列自定义阈值。

        :param time_column: 用于计算 ``Δt`` 的时间列名称，默认 ``timestamp``。
        :param kwargs: 以 ``变量名=dict(first=?, second=?)`` 的形式覆盖默认阈值。
        """
        self.columns = {**self.default, **kwargs}
        self.time_column = time_column

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        if data.shape[0] <= 2:
            return data
        for column, params in self.columns.items():
            if column not in data.columns:
                continue
            nanmask = np.isnan(data[column].values)
            index = data.index[np.logical_not(nanmask)]
            val = data[column].values[np.logical_not(nanmask)]
            # 计算相邻有效点的时间差（秒）
            timediff = (
                data.loc[np.logical_not(nanmask), self.time_column]
                .diff()
                .dt.total_seconds()
                .values[1:]
            )
            if column == "track":
                # 航迹角需要先解包，避免在 0/360° 处产生虚假跳变
                val = np.unwrap(val, period=360)
            # 一阶差分以及差分之间的变化量
            diff1val = val[1:] - val[:-1]
            diff1 = np.abs(diff1val)
            diff2 = np.abs(diff1val[1:] - diff1val[:-1])

            deriv1 = diff1 / timediff
            deriv2 = 2 * diff2 / (timediff[1:] + timediff[:-1])
            spikea = deriv2 >= params["second"]
            # 二阶导投票：影响前后各一个点
            killa = np.zeros(val.shape[0])
            killa[:-2] += spikea  # i-1
            killa[1:-1] += spikea  # i
            killa[2:] += spikea  # i+1
            spikev = deriv1 >= params["first"]
            # 一阶导投票：覆盖当前点及前一个点
            killv = np.zeros(val.shape[0])
            killv[:-1] += spikev  # i-1
            killv[1:] += spikev   # i
            data.loc[index[np.logical_or(killa >= 2, killv >= 2)], column] = np.nan

        return data
