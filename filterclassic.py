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
import math
from pandas.api.types import is_datetime64_any_dtype


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


class FilterDerivativeLoop(filters.FilterBase):
    """对 ``MyFilterDerivative`` 结果做多轮迭代，直至不再新增 NaN。

    适用于“残留 3+ 连点突刺”的情况：第一次使用默认阈值的 ``MyFilterDerivative``
    清理大部分异常后，再用轻放宽阈值在局部循环执行，凡是每一轮没有新增 NaN 时
    即提前收敛。通过 ``max_passes`` 控制最多迭代次数，避免意外死循环。
    """

    def __init__(
        self,
        base: Optional[MyFilterDerivative] = None,
        *,
        max_passes: int = 6,
        min_passes: int = 1,
    ) -> None:
        self.base = base or MyFilterDerivative()
        self.max_passes = max(1, int(max_passes))
        self.min_passes = max(1, min(self.max_passes, int(min_passes)))

    def apply(self, data: pd.DataFrame) -> pd.DataFrame:
        df = data
        monitored = [c for c in getattr(self.base, "columns", {}).keys() if c in df.columns]
        if not monitored:
            return self.base.apply(df)

        for idx in range(self.max_passes):
            before = df[monitored].isna().values.sum()
            df = self.base.apply(df)
            after = df[monitored].isna().values.sum()
            if after == before and idx + 1 >= self.min_passes:
                break
        return df


class FilterMaxSpeed(filters.FilterBase):
    """根据大圆距离估算整体地速，超阈值的相邻点直接剔除。"""

    def __init__(self, *, max_speed_mps: float = 1000.0, time_column: str = "timestamp") -> None:
        self.max_speed_mps = float(max_speed_mps)
        self.time_column = time_column

    @staticmethod
    def _haversine_m(lat1, lon1, lat2, lon2):
        lat1 = np.radians(lat1)
        lon1 = np.radians(lon1)
        lat2 = np.radians(lat2)
        lon2 = np.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
        c = 2.0 * np.arcsin(np.clip(np.sqrt(a), 0.0, 1.0))
        return 6371000.0 * c

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "flight_id" not in df:
            return df
        if "latitude" not in df.columns or "longitude" not in df.columns:
            return df

        df = df.copy()
        cols = [c for c in [
            "latitude",
            "longitude",
            "altitude",
            "groundspeed",
            "track",
            "vertical_rate",
        ] if c in df.columns]
        bad = np.zeros(len(df), dtype=bool)

        for _, g in df.groupby("flight_id"):
            idx = g.index.to_numpy()
            lat = g["latitude"].to_numpy()
            lon = g["longitude"].to_numpy()
            ts = pd.to_datetime(g[self.time_column], utc=True, errors="coerce").values
            valid = (~np.isnan(lat)) & (~np.isnan(lon)) & (~np.isnat(ts))
            if valid.sum() < 2:
                continue
            lat = lat[valid]
            lon = lon[valid]
            ts = ts[valid].astype("datetime64[s]").astype(float)
            idx_valid = idx[valid]
            dt = np.diff(ts)
            mask = dt > 0
            if not np.any(mask):
                continue
            dist = self._haversine_m(lat[:-1], lon[:-1], lat[1:], lon[1:])
            speed = np.zeros_like(dist)
            speed[mask] = dist[mask] / dt[mask]
            high = speed >= self.max_speed_mps
            if not np.any(high):
                continue
            hit_idx = np.unique(np.concatenate((idx_valid[:-1][high], idx_valid[1:][high])))
            bad[hit_idx] = True

        if bad.any():
            df.loc[bad, cols] = np.nan
        return df


class FilterAxisSpeed(filters.FilterBase):
    """分别对纬度/经度/高度计算变化率，超过阈值即删除。"""

    FT_TO_M = 0.3048
    LAT_M_PER_DEG = 111_320.0

    def __init__(
        self,
        *,
        max_lat_deg_per_sec: float = 0.0063,
        max_lon_deg_per_sec: float = 0.0063,
        max_alt_ft_per_sec: float = 164.0,
        time_column: str = "timestamp",
    ) -> None:
        self.max_lat_deg_per_sec = float(max_lat_deg_per_sec)
        self.max_lon_deg_per_sec = float(max_lon_deg_per_sec)
        self.max_alt_ft_per_sec = float(max_alt_ft_per_sec)
        self.time_column = time_column

    def _mark(self, idx, vals, times, threshold):
        if idx.size < 2:
            return np.array([], dtype=int)
        dt = np.diff(times)
        mask = dt > 0
        if not np.any(mask):
            return np.array([], dtype=int)
        diff = np.abs(np.diff(vals))
        rate = np.zeros_like(diff)
        rate[mask] = diff[mask] / dt[mask]
        high = rate >= threshold
        if not np.any(high):
            return np.array([], dtype=int)
        return np.unique(np.concatenate((idx[:-1][high], idx[1:][high])))

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "flight_id" not in df:
            return df
        cols = [c for c in [
            "latitude",
            "longitude",
            "altitude",
            "groundspeed",
            "track",
            "vertical_rate",
        ] if c in df.columns]
        if not cols:
            return df

        df = df.copy()
        bad = np.zeros(len(df), dtype=bool)

        for _, g in df.groupby("flight_id"):
            idx = g.index.to_numpy()
            ts = pd.to_datetime(g[self.time_column], utc=True, errors="coerce").values
            if ts.size == 0:
                continue
            ts_s = ts.astype("datetime64[s]").astype(float)

            if "latitude" in g.columns:
                lat = g["latitude"].to_numpy()
                valid = (~np.isnan(lat)) & (~np.isnat(ts))
                if valid.sum() >= 2:
                    bad[self._mark(
                        idx[valid],
                        lat[valid],
                        ts_s[valid],
                        self.max_lat_deg_per_sec,
                    )] = True

            if "longitude" in g.columns and "latitude" in g.columns:
                lon = g["longitude"].to_numpy()
                lat = g["latitude"].to_numpy()
                valid = (~np.isnan(lon)) & (~np.isnan(lat)) & (~np.isnat(ts))
                if valid.sum() >= 2:
                    lon_vals = lon[valid]
                    lat_vals = lat[valid]
                    ts_vals = ts_s[valid]
                    idx_vals = idx[valid]
                    dt = np.diff(ts_vals)
                    mask = dt > 0
                    if np.any(mask):
                        meters = np.abs(np.diff(lon_vals)) * self.LAT_M_PER_DEG * np.cos(
                            np.radians((lat_vals[:-1] + lat_vals[1:]) / 2.0)
                        )
                        rate = np.zeros_like(meters)
                        rate[mask] = meters[mask] / dt[mask]
                        high = rate >= (self.max_lon_deg_per_sec * self.LAT_M_PER_DEG)
                        if np.any(high):
                            bad[np.concatenate((idx_vals[:-1][high], idx_vals[1:][high]))] = True

            if "altitude" in g.columns:
                alt = g["altitude"].to_numpy()
                valid = (~np.isnan(alt)) & (~np.isnat(ts))
                if valid.sum() >= 2:
                    bad[self._mark(
                        idx[valid],
                        alt[valid],
                        ts_s[valid],
                        self.max_alt_ft_per_sec,
                    )] = True

        if bad.any():
            df.loc[bad, cols] = np.nan
        return df


class FilterMaxSpeedSkipNaN(filters.FilterBase):
    """跨越NaN检测有效点之间的速度，捕获间接超速。

    与 FilterMaxSpeed 的区别：
    - FilterMaxSpeed: 只检测原始数据中直接相邻的点
    - FilterMaxSpeedSkipNaN: 跳过中间的NaN，检测有效点之间的速度

    用途：捕获过滤器删除中间点后形成的"间接超速"。

    典型场景：
    - 原始数据: 点0 → 点1(卡死) → 点2(卡死) → 点3(超速跳变)
    - 过滤后: 点0 → NaN → NaN → NaN → 点7
    - 问题: 点0→点7距离大、时间长，形成间接超速
    - 本过滤器: 检测点0→点7，删除超速点对

    循环策略：删除后可能形成新的超速，需要迭代检测直至收敛。
    """

    def __init__(
        self,
        *,
        max_speed_mps: float = 600.0,
        time_column: str = "timestamp",
        max_iterations: int = 5,
    ) -> None:
        """初始化跨NaN速度过滤器。

        :param max_speed_mps: 最大允许速度（米/秒），默认600 m/s
        :param time_column: 时间列名，默认"timestamp"
        :param max_iterations: 最大循环次数，默认5次
        """
        self.max_speed_mps = float(max_speed_mps)
        self.time_column = time_column
        self.max_iterations = max(1, int(max_iterations))

    @staticmethod
    def _haversine_m(lat1, lon1, lat2, lon2):
        """计算两点间的Haversine距离（米）。"""
        lat1 = np.radians(lat1)
        lon1 = np.radians(lon1)
        lat2 = np.radians(lat2)
        lon2 = np.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
        c = 2.0 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
        return 6371000.0 * c

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        """应用过滤器，循环检测直至收敛。"""
        if df.empty or "flight_id" not in df.columns:
            return df

        # 循环检测，直到无新增删除
        for iteration in range(self.max_iterations):
            # 统计删除前的NaN数量
            if "latitude" in df.columns and "longitude" in df.columns:
                before_count = (df["latitude"].isna() & df["longitude"].isna()).sum()
            else:
                break

            df = self._apply_once(df)

            # 统计删除后的NaN数量
            after_count = (df["latitude"].isna() & df["longitude"].isna()).sum()

            if after_count == before_count:
                # 无新增删除，收敛
                break

        return df

    def _apply_once(self, df: pd.DataFrame) -> pd.DataFrame:
        """执行一次跨NaN速度检测。"""
        df = df.copy()
        cols = [
            c
            for c in [
                "latitude",
                "longitude",
                "altitude",
                "groundspeed",
                "track",
                "vertical_rate",
            ]
            if c in df.columns
        ]

        if "latitude" not in df.columns or "longitude" not in df.columns:
            return df

        # 使用set存储要删除的全局索引
        bad_indices = set()

        for _, g in df.groupby("flight_id"):
            idx = g.index.to_numpy()

            # 找到所有有效的经纬度点（非NaN）
            lat = g["latitude"].to_numpy()
            lon = g["longitude"].to_numpy()
            ts = pd.to_datetime(g[self.time_column], utc=True, errors="coerce").values

            valid = (~np.isnan(lat)) & (~np.isnan(lon)) & (~pd.isna(ts))

            if valid.sum() < 2:
                continue

            # 提取有效点的索引、坐标和时间
            valid_indices = idx[valid]
            valid_lats = lat[valid]
            valid_lons = lon[valid]
            valid_times = ts[valid].astype("datetime64[s]").astype(float)

            # 计算相邻有效点之间的速度
            for i in range(len(valid_indices) - 1):
                dt = valid_times[i + 1] - valid_times[i]

                if dt <= 0:
                    continue

                # 计算Haversine距离
                dist = self._haversine_m(
                    valid_lats[i],
                    valid_lons[i],
                    valid_lats[i + 1],
                    valid_lons[i + 1],
                )
                speed = dist / dt

                if speed >= self.max_speed_mps:
                    # 删除两个点（保守策略：无法判断哪个点异常，都删除）
                    bad_indices.add(valid_indices[i])
                    bad_indices.add(valid_indices[i + 1])

        if bad_indices:
            df.loc[list(bad_indices), cols] = np.nan

        return df


class FilterEdgeOutlier(filters.FilterBase):
    """专门清理每条轨迹首尾的离群点。

    规则：对每个 ``flight_id`` 取首个/最后一个具备经纬度的点，与其相邻点比较。
    若地理距离大于 ``dist_threshold_km``、或瞬时速度大于 ``speed_threshold_kmh``、
    或高度差超过 ``alt_threshold_ft``，则将该首/尾点视为异常并置 NaN。
    """

    def __init__(
        self,
        *,
        time_column: str = "timestamp",
        dist_threshold_km: float = 5.0,
        speed_threshold_kmh: float = 800.0,
        alt_threshold_ft: float = 3000.0,
        columns: Optional[list[str]] = None,
    ) -> None:
        self.time_column = time_column
        self.dist_threshold_km = float(dist_threshold_km)
        self.speed_threshold_kmh = float(speed_threshold_kmh)
        self.alt_threshold_ft = float(alt_threshold_ft)
        self.columns = columns or [
            "latitude",
            "longitude",
            "altitude",
            "groundspeed",
            "track",
            "vertical_rate",
        ]

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        a = min(1.0, max(0.0, a))
        return 2 * 6371.0 * math.asin(math.sqrt(a))

    def _needs_drop(
        self,
        row_a: pd.Series,
        row_b: pd.Series,
    ) -> bool:
        try:
            ts_a = pd.to_datetime(row_a[self.time_column], utc=True)
            ts_b = pd.to_datetime(row_b[self.time_column], utc=True)
        except KeyError:
            return False
        if any(pd.isna(row_a.get(col)) for col in ("latitude", "longitude")):
            return False
        if any(pd.isna(row_b.get(col)) for col in ("latitude", "longitude")):
            return False

        dist_km = self._haversine_km(
            float(row_a["latitude"]),
            float(row_a["longitude"]),
            float(row_b["latitude"]),
            float(row_b["longitude"]),
        )
        dt = (ts_b - ts_a).total_seconds()
        speed = float("inf") if dt <= 0 else dist_km / (dt / 3600.0)
        alt_a = row_a.get("altitude")
        alt_b = row_b.get("altitude")
        alt_diff = 0.0
        if pd.notna(alt_a) and pd.notna(alt_b):
            alt_diff = abs(float(alt_a) - float(alt_b))

        return (
            dist_km >= self.dist_threshold_km
            or speed >= self.speed_threshold_kmh
            or alt_diff >= self.alt_threshold_ft
        )

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or "flight_id" not in df or self.time_column not in df:
            return df

        df = df.copy()
        bad_idx: set[int] = set()

        for _, group in df.groupby("flight_id"):
            if group.shape[0] < 2:
                continue
            pos_valid = group[["latitude", "longitude"]].notna().all(axis=1)
            valid_idx = group.index[pos_valid].to_list()
            if len(valid_idx) < 2:
                continue
            first_idx, second_idx = valid_idx[0], valid_idx[1]
            if self._needs_drop(df.loc[first_idx], df.loc[second_idx]):
                bad_idx.add(first_idx)

            last_idx, prev_idx = valid_idx[-1], valid_idx[-2]
            if self._needs_drop(df.loc[last_idx], df.loc[prev_idx]):
                bad_idx.add(last_idx)

        if not bad_idx:
            return df

        cols = [c for c in self.columns if c in df.columns]
        df.loc[list(bad_idx), cols] = np.nan
        return df


class FilterShortBurst(filters.FilterBase):
    """剔除短小异常簇（基于滑窗动力学+局部密度）。

    设计目的：在 ``MyFilterDerivative`` 之后清理“段首/段尾残留的 1–2 点小突刺”，
    与 ``FilterIsolated`` 互补。仅基于经纬度主判定；若高度存在，再做垂直复核。

    规则摘要（保守默认）：
    - 轻筛：以滑窗稳健基线（中位数/MAD）筛选“速度/加速度”可疑点。
    - 精筛：仅对可疑点在 ±窗口内计算与邻域的 Haversine 距离密度：
        - 若最近邻距离 > R_km 且半径内邻居 < N_min，则记为异常。
    - 短簇门：仅删除连续异常长度 ≤ L_short 的簇（默认 2），避免误杀长异常段。
    - 联动：若经纬被删除，同步置空 ``altitude/groundspeed/track``（若存在）。
    """

    def __init__(
        self,
        *,
        time_column: str = "timestamp",
        win_sec: int = 60,
        seed_v_abs_kmh: float = 1000.0,
        seed_v_ratio: float = 3.0,
        seed_a_abs_mps2: float = 15.0,
        seed_a_ratio: float = 5.0,
        radius_km: float = 5.0,
        min_neighbors: int = 3,
        l_short: int = 2,
    ) -> None:
        self.time_column = time_column
        self.win_sec = int(win_sec)
        self.seed_v_abs_kmh = float(seed_v_abs_kmh)
        self.seed_v_ratio = float(seed_v_ratio)
        self.seed_a_abs_mps2 = float(seed_a_abs_mps2)
        self.seed_a_ratio = float(seed_a_ratio)
        self.radius_km = float(radius_km)
        self.min_neighbors = int(min_neighbors)
        self.l_short = int(l_short)

    @staticmethod
    def _haversine_km(lat1, lon1, lat2, lon2):
        lat1 = np.radians(lat1)
        lon1 = np.radians(lon1)
        lat2 = np.radians(lat2)
        lon2 = np.radians(lon2)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = np.sin(dlat / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2.0) ** 2
        a = np.clip(a, 0.0, 1.0)
        return 2.0 * 6371.0 * np.arcsin(np.sqrt(a))

    def apply(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if df.shape[0] <= 5:
            return df

        # 仅对经纬度可用的点进行判定
        valid = (~df.latitude.isna()) & (~df.longitude.isna())
        if valid.sum() <= 5:
            return df
        idx = np.where(valid.values)[0]
        sub = df.loc[valid, [self.time_column, "latitude", "longitude"]].copy()
        t = sub[self.time_column].values
        # pandas 时区感知 dtype 为 'datetime64[ns, UTC]'，np.issubdtype 会报错；
        # 使用 pandas 的类型检测更稳健。
        if not is_datetime64_any_dtype(sub[self.time_column]):
            sub[self.time_column] = pd.to_datetime(sub[self.time_column], utc=True, errors="coerce")
            t = sub[self.time_column].values
        t = t.astype("datetime64[ns]")
        lat = sub["latitude"].values.astype(float)
        lon = sub["longitude"].values.astype(float)

        # 真实时间差与相邻速度/加速度
        dt = (t[1:] - t[:-1]).astype("timedelta64[s]").astype(float)
        dt[dt <= 0] = np.nan
        dist = self._haversine_km(lat[:-1], lon[:-1], lat[1:], lon[1:])
        v_kmh = np.full(lat.shape[0], np.nan)
        v_kmh[1:] = dist / (dt / 3600.0)
        v_mps = v_kmh / 3.6
        dt2 = (t[2:] - t[:-2]).astype("timedelta64[s]").astype(float)
        a_mps2 = np.full(lat.shape[0], np.nan)
        a_mps2[1:-1] = 2 * (v_mps[2:] - v_mps[:-2]) / dt2

        # 将窗口秒数换算为样本窗口（以中位 dt 估计）
        med_dt = np.nanmedian(dt)
        win_n = int(max(5, min(301, round(self.win_sec / med_dt))) if np.isfinite(med_dt) and med_dt > 0 else 61)
        # 滑窗稳健基线
        v_ser = pd.Series(v_kmh)
        a_ser = pd.Series(a_mps2)
        v_med = v_ser.rolling(win_n, center=True, min_periods=max(3, win_n // 3)).median().fillna(v_ser.median())
        a_mad = (a_ser - a_ser.rolling(win_n, center=True, min_periods=max(3, win_n // 3)).median()).abs()
        a_mad = a_mad.rolling(win_n, center=True, min_periods=max(3, win_n // 3)).median().fillna(a_mad.median())

        cond_v = v_ser.values >= np.maximum(self.seed_v_abs_kmh, self.seed_v_ratio * v_med.values)
        cond_a = np.abs(a_ser.values) >= np.maximum(self.seed_a_abs_mps2, self.seed_a_ratio * a_mad.values)
        seeds = np.where(np.nan_to_num(cond_v | cond_a, nan=False))[0]
        if seeds.size == 0:
            return df

        half_n = max(3, win_n // 2)
        bad = np.zeros(lat.shape[0], dtype=bool)

        for k in seeds:
            i0 = max(0, k - half_n)
            i1 = min(lat.shape[0] - 1, k + half_n)
            jj = np.arange(i0, i1 + 1)
            if jj.size < 5:
                continue
            # 与窗口内其它点的 Haversine 距离
            dists = self._haversine_km(lat[k], lon[k], lat[jj], lon[jj])
            dists = dists[1:]  # 排除自身第一个 0
            dmin = np.nanmin(dists) if dists.size > 0 else np.inf
            cnt = int(np.sum(dists <= self.radius_km))
            if (dmin > self.radius_km) and (cnt < self.min_neighbors):
                bad[k] = True

        # 仅删除连续异常长度 ≤ L_short 的簇
        if bad.any():
            i = 0
            while i < bad.size:
                if bad[i]:
                    j = i
                    while j < bad.size and bad[j]:
                        j += 1
                    if (j - i) <= self.l_short:
                        pass  # 保持删除
                    else:
                        bad[i:j] = False  # 长异常簇不在此处处理
                    i = j
                else:
                    i += 1

        if not bad.any():
            return df

        # 将标记位置映射回原 DataFrame 索引
        bad_global = np.zeros(df.shape[0], dtype=bool)
        bad_global[idx[bad]] = True
        # 删除经纬度，联动屏蔽其它变量
        cols = [c for c in ["latitude", "longitude", "altitude", "groundspeed", "track"] if c in df.columns]
        df.loc[bad_global, cols] = np.nan
        return df
