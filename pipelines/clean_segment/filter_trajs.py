"""轨迹过滤主脚本。

命令入口：``python -m pipelines.clean_segment.filter_trajs -t_in <raw> -t_out <filtered> -strategy classic``。
脚本读取原始 parquet 轨迹文件，按照策略拼接多个滤波器（参见 :mod:`pipelines.classic_filters.filterclassic`），
以 ``strategy=nointerpolate`` 的方式仅对异常观测置 NaN，不做任何插值。
"""

import argparse
import datetime
import logging
import os
import fcntl
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
import numpy as np
from tools.common import utils
from pipelines.classic_filters.filterclassic import (
    FilterCstLatLon,
    FilterCstPosition,
    FilterCstSpeed,
    FilterIsolated,
    FilterSpatialPCAOutlier,
    MyFilterDerivative,
    FilterShortBurst,
    FilterDerivativeLoop,
    FilterEdgeOutlier,
    FilterMaxSpeed,
    FilterAxisSpeed,
    FilterMaxSpeedSkipNaN,
    FilterMaxSpeedSkipNaNWithVoting,
)
from traffic.algorithms import filters

# 历史注记：航班 248803487（2022-01-03）在 unwrap 操作上曾发现异常，保留此条以备排查
from traffic.core import Traffic
import matplotlib.pyplot as plt

from pipelines.common import meta_filters

DERIV_PARAMS = {
    "latitude": dict(first=0.004, second=0.02),
    "longitude": dict(first=0.004, second=0.02),
    "altitude": dict(first=126, second=50),
}


def _get_env_float(name: str, default: float) -> float:
    """读取环境变量中的浮点数，异常时回退默认值。"""
    try:
        value = os.environ.get(name, None)
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def _get_env_int(name: str, default: int) -> int:
    """读取环境变量中的整数，异常时回退默认值。"""
    try:
        value = os.environ.get(name, None)
        return int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        return int(default)


def _make_derivative(**overrides):
    params = {k: v.copy() for k, v in DERIV_PARAMS.items()}
    for key, value in overrides.items():
        params[key] = value
    return MyFilterDerivative(**params)


def nointerpolate(x):
    """恒等函数，传给 traffic 以禁用内置插值。"""
    return x


class PCAStatsWriter:
    """跨进程安全地把 PCA 统计写入 CSV。"""

    HEADER = [
        "timestamp_utc",
        "source_file",
        "strategy",
        "flight_id",
        "points_total",
        "points_flagged",
        "global_threshold",
        "window_size",
        "windows_evaluated",
        "window_threshold_min",
        "window_threshold_max",
        "mad_scale",
    ]

    def __init__(self, path: str, *, source_file: Optional[str] = None, strategy: Optional[str] = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.source_file = source_file
        self.strategy = strategy
        self._ensure_header()

    def _ensure_header(self) -> None:
        if not self.path.exists() or self.path.stat().st_size == 0:
            with self.path.open("w", encoding="utf-8") as fh:
                fh.write(",".join(self.HEADER) + "\n")

    def write(self, stats: dict[str, object]) -> None:
        # 运行期间目录可能被清理，写入前再次确保目录/文件存在
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header()
        row = {
            "timestamp_utc": datetime.datetime.utcnow().isoformat(),
            "source_file": stats.get("source_file") or self.source_file or "",
            "strategy": stats.get("strategy") or self.strategy or "",
            "flight_id": stats.get("flight_id", ""),
            "points_total": stats.get("points_total", ""),
            "points_flagged": stats.get("points_flagged", ""),
            "global_threshold": stats.get("global_threshold", ""),
            "window_size": stats.get("window_size", ""),
            "windows_evaluated": stats.get("windows_evaluated", ""),
            "window_threshold_min": stats.get("window_threshold_min", ""),
            "window_threshold_max": stats.get("window_threshold_max", ""),
            "mad_scale": stats.get("mad_scale", ""),
        }
        line = ",".join(self._stringify(row[h]) for h in self.HEADER) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            fh.write(line)
            fh.flush()
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _stringify(value: object) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, float):
            return f"{value:.6f}"
        return str(value)


def build_filter_chain(
    strategy: str,
    *,
    pca_stats_callback: Optional[Callable[[dict[str, object]], None]] = None,
) -> filters.FilterBase:
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
    elif strategy == "clean_segment_interp":
        """
        清洗-分段-插值流程的过滤策略（Clean-Segment-Interpolate）

        设计理念：
        - 严格的过滤顺序（参考todo.md）
        - 使用带投票的跨NaN速度检测（更稳健）
        - 整行删除（位置+速度+天气+衍生特征）
        - 为后续分段和插值提供干净的数据

        与classic_dp_loop的区别：
        - 不使用MyFilterDerivative（改用FilterMaxSpeedSkipNaNWithVoting）
        - 更严格的整行删除策略
        - 天气参数联动删除

        流程：过滤（此策略） → 切分 → 插值
        """
        # 从环境变量读取参数，提供默认值以确保代码健壮性，通过sh脚本设置环境变量覆盖默认值
        max_speed_mps = _get_env_float("MAX_SPEED_MPS", 700.0)
        max_accel_mps2 = _get_env_float("MAX_ACCEL_MPS2", 25.0)
        vote_threshold = _get_env_int("VOTE_THRESHOLD", 2)
        alt_first = _get_env_float("ALT_DERIV_FIRST_FTPS", 151.0)
        alt_second = _get_env_float("ALT_DERIV_SECOND_FTPS2", 51.0)
        print(
            "[clean_segment_interp] "
            f"max_speed_mps={max_speed_mps}, max_accel_mps2={max_accel_mps2}, "
            f"vote_threshold={vote_threshold}, "
            f"alt_first_ftps={alt_first}, alt_second_ftps2={alt_second}"
        )
        altitude_filter = MyFilterDerivative(
            time_column="timestamp",
            altitude=dict(first=alt_first, second=alt_second),
        )
        # 只监控高度一列，避免默认参数把经纬度也纳入票决
        altitude_filter.columns = {"altitude": dict(first=alt_first, second=alt_second)}
        chain = (
            FilterCstLatLon()
            | FilterCstPosition()
            | FilterCstSpeed()
            | FilterEdgeOutlier()
            | FilterMaxSpeedSkipNaNWithVoting(
                max_speed_mps=max_speed_mps,
                max_accel_mps2=max_accel_mps2,
                max_iterations=10,       # 循环直到收敛
                vote_threshold=vote_threshold
            )
            | altitude_filter               # 高度三点投票
        )
        spatial_pca = _build_spatial_pca(pca_stats_callback)
        if spatial_pca is not None:
            chain = chain | spatial_pca
        if _get_env_int("ENABLE_SKIPNAN_POST_PCA", 1):
            post_iter = _get_env_int("POST_PCA_SKIPNAN_MAX_ITER", 3)
            chain = chain | FilterMaxSpeedSkipNaN(
                max_speed_mps=max_speed_mps,
                max_iterations=post_iter,
            )
        return chain | FilterIsolated()
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


def _build_spatial_pca(
    stats_callback: Optional[Callable[[dict[str, object]], None]],
) -> Optional[FilterSpatialPCAOutlier]:
    enable = _get_env_int("ENABLE_SPATIAL_PCA", 1) != 0
    if not enable:
        return None
    min_points = _get_env_int("PCA_MIN_POINTS", 80)
    mad_scale = _get_env_float("PCA_MAD_SCALE", 6.0)
    window_size = _get_env_int("PCA_WINDOW_SIZE", 0)
    return FilterSpatialPCAOutlier(
        min_points=min_points,
        mad_scale=mad_scale,
        window_size=window_size if window_size > 0 else None,
        include_altitude=False,
        stats_callback=stats_callback,
    )


def read_trajectories(f, strategy, allowed_ids=None):
    """读取轨迹文件并按策略执行滤波。"""

    df = pd.read_parquet(f)
    for v in ["flight_id"]:
        df[v] = df[v].astype(np.int64)

    if allowed_ids is not None:
        allowed_arr = np.asarray(allowed_ids, dtype=np.int64)
        if allowed_arr.size == 0:
            return df.iloc[0:0].copy()
        before = len(df)
        df = df[df["flight_id"].isin(allowed_arr)].copy()
        logging.info("meta flight_id filter: %s -> %s", before, len(df))

    # 以航班号+时间戳去重后按时间排序，确保时间序列严格递增
    df = (
        df.drop_duplicates(["flight_id", "timestamp"])
        .sort_values(["flight_id", "timestamp"])
        .reset_index(drop=True)
    )  # .head(10_000)

    stats_callback = None
    stats_path = os.environ.get("PCA_STATS_CSV", "").strip()
    if stats_path:
        writer = PCAStatsWriter(
            stats_path,
            source_file=os.path.basename(f),
            strategy=strategy,
        )
        stats_callback = lambda payload: writer.write(
            {
                **payload,
                "strategy": strategy,
                "source_file": os.path.basename(f),
            }
        )
    filter_chain = build_filter_chain(strategy, pca_stats_callback=stats_callback)

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


def _build_allowed_ids_from_args(args):
    if not (args.europe_only or args.top_airports > 0 or args.top_aircraft > 0):
        return None

    flights_parquet = Path(args.flights_parquet).resolve()
    airports_parquet = Path(args.airports_parquet).resolve()
    allowed_ids, stats = meta_filters.build_allowed_flight_ids(
        flights_parquet=flights_parquet,
        airports_parquet=airports_parquet,
        include_submission=args.include_submission,
        include_final=args.include_final,
        europe_only=args.europe_only,
        top_airports=args.top_airports,
        top_aircraft=args.top_aircraft,
        europe_continent=args.europe_continent,
        procs=args.meta_procs,
    )
    print(meta_filters.format_stats(stats))
    return allowed_ids


def main():
    parser = argparse.ArgumentParser(
        description="过滤掉高概率异常的轨迹观测",
    )
    parser.add_argument("-t_in", help="输入轨迹 parquet 文件路径")
    parser.add_argument("-t_out", help="输出过滤后 parquet 文件路径")
    parser.add_argument(
        "-strategy",
        help="过滤策略名称: classic / classic_shortburst / classic_dp_loop / clean_segment_interp",
    )
    parser.add_argument(
        "--europe-only",
        "--europe_only",
        action="store_true",
        help="仅保留起降都在欧洲的航班（可选）",
    )
    parser.add_argument(
        "--top-airports",
        "--top_airports",
        type=int,
        default=0,
        help="机场出现次数 Top-N（adep+ades 合并统计，可选）",
    )
    parser.add_argument(
        "--top-aircraft",
        "--top_aircraft",
        type=int,
        default=0,
        help="机型出现次数 Top-N（可选）",
    )
    parser.add_argument(
        "--flights-parquet",
        "--flights_parquet",
        default="opensky_2024_PRC_dataset/flights/challenge_set.parquet",
        help="航班元数据（默认 challenge_set）",
    )
    parser.add_argument(
        "--airports-parquet",
        "--airports_parquet",
        default="opensky_2024_PRC_dataset/airports_tz.parquet",
        help="机场信息（continent 用于欧洲筛选）",
    )
    parser.add_argument(
        "--include-submission",
        "--include_submission",
        action="store_true",
        help="合并 submission_set.parquet 参与统计（可选）",
    )
    parser.add_argument(
        "--include-final",
        "--include_final",
        action="store_true",
        help="合并 final_submission_set.parquet 参与统计（可选）",
    )
    parser.add_argument(
        "--europe-continent",
        "--europe_continent",
        default=meta_filters.DEFAULT_EUROPE_CONTINENT,
        help="Europe 大洲编码（默认 EU）",
    )
    parser.add_argument(
        "--meta-procs",
        "--meta_procs",
        type=int,
        default=4,
        help="元数据读取并发数（仅多源时生效）",
    )
    args = parser.parse_args()

    allowed_ids = _build_allowed_ids_from_args(args)
    df = read_trajectories(args.t_in, args.strategy, allowed_ids=allowed_ids)
    df.to_parquet(args.t_out, index=False)


if __name__ == "__main__":
    main()
