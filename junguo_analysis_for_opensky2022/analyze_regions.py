#!/usr/bin/env python3
"""
大规模统计原始飞行轨迹的地区分布（欧洲 vs 美国）与轨迹数量。

设计目标与思路（单机 512GB RAM / 80 线程）：
- 使用 Polars 的懒加载与流式 groupby，避免一次性加载 280GB 数据。
- 两阶段（per-file 聚合 -> 全局汇总）更稳健，适合跨 365 个 parquet 文件。
- 地区判定使用经纬度的近似边界框：
  * US = 美国本土 + 阿拉斯加 + 夏威夷（粗略范围）
  * EU = 欧洲大致范围（粗略范围）
- 统计两类口径：
  1) 基于“点”的分布（每条轨迹点属于哪个区域）
  2) 基于“航班”的分布（按每个 flight_id 在各区域的点数多数表决）

输出：
- 中间 per-file 聚合文件（小）：`tmp_region_counts/region_counts_*.parquet`
- 汇总结果：`region_summary.json` 与 `region_summary.csv`

用法示例：
python junguo_analysis_for_opensky2022/analyze_regions.py \
  --raw-dir opensky_2024_PRC_dataset/rawtrajectories \
  --tmp-dir junguo_analysis_for_opensky2022/tmp_region_counts \
  --out junguo_analysis_for_opensky2022/region_summary

依赖：
- pip install polars pyarrow
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from glob import glob
from typing import List

try:
    import polars as pl
except Exception as e:
    print("[ERROR] 需要安装 polars。请先执行: pip install polars pyarrow", file=sys.stderr)
    raise


def expr_is_us(lat: pl.Expr, lon: pl.Expr) -> pl.Expr:
    """粗略判定点是否位于美国（US 本土 + 阿拉斯加 + 夏威夷）。"""
    # contiguous US
    us_mainland = lat.is_between(24.0, 49.5) & lon.is_between(-125.0, -66.0)
    # Alaska (rough)
    alaska = lat.is_between(51.0, 72.0) & lon.is_between(-170.0, -130.0)
    # Hawaii (rough)
    hawaii = lat.is_between(18.0, 22.8) & lon.is_between(-161.0, -154.0)
    return us_mainland | alaska | hawaii


def expr_is_eu(lat: pl.Expr, lon: pl.Expr) -> pl.Expr:
    """粗略判定点是否位于欧洲范围。
    边界近似：纬度 [35, 72]，经度 [-25, 45]
    注：此范围包含部分土耳其、俄罗斯西部、北非边缘等，目的在于快速统计，不做严谨地理边界裁剪。
    """
    return lat.is_between(35.0, 72.0) & lon.is_between(-25.0, 45.0)


def list_parquet_files(raw_dir: str) -> List[str]:
    files = sorted(glob(os.path.join(raw_dir, "*.parquet")))
    if not files:
        raise FileNotFoundError(f"未在目录 {raw_dir} 下找到 parquet 文件")
    return files


def aggregate_one_file(in_path: str) -> pl.DataFrame:
    """对单个 parquet 文件执行 per-file 聚合，返回结果 DataFrame（在内存中较小）。

    输出列：
    - flight_id: i64
    - cnt_us, cnt_eu, cnt_other, total_points: i64
    """
    lf = (
        pl.scan_parquet(in_path)
        .select(
            pl.col("flight_id").cast(pl.Int64),
            pl.col("latitude").cast(pl.Float64).alias("lat"),
            pl.col("longitude").cast(pl.Float64).alias("lon"),
            pl.col("timestamp"),  # 可为 Datetime/Utf8，后续不依赖其类型
        )
        .filter(
            pl.col("lat").is_not_null() & pl.col("lon").is_not_null()
            & pl.col("lat").is_between(-90.0, 90.0)
            & pl.col("lon").is_between(-180.0, 180.0)
        )
        .with_columns(
            in_us=expr_is_us(pl.col("lat"), pl.col("lon")).cast(pl.Int8),
            in_eu=expr_is_eu(pl.col("lat"), pl.col("lon")).cast(pl.Int8),
        )
        .with_columns(
            in_other=(pl.lit(1) - (pl.col("in_us") | pl.col("in_eu")).cast(pl.Int8)).alias("in_other")
        )
        .group_by("flight_id")
        .agg(
            cnt_us=pl.col("in_us").sum().cast(pl.Int64),
            cnt_eu=pl.col("in_eu").sum().cast(pl.Int64),
            cnt_other=pl.col("in_other").sum().cast(pl.Int64),
            total_points=pl.len().cast(pl.Int64),
        )
    )

    # 使用 streaming=True 降低峰值内存
    return lf.collect(streaming=True)


def write_parquet(df: pl.DataFrame, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.write_parquet(out_path)


def summarize_all(partials_glob: str, out_prefix: str, majority_threshold: float = 0.0) -> dict:
    """汇总所有 per-file 聚合结果，生成航班级分类与总体统计。

    参数 majority_threshold: 若一个地区占比 >= 该阈值才认定为该地区；否则记为 OTHER。
                             例如传 0.6 则需要 >=60% 的点在某地区；默认 0 表示直接以最大值多数表决。
    返回字典 summary，且将同时写出 CSV 和 JSON。
    """
    lf = (
        pl.scan_parquet(partials_glob)
        .group_by("flight_id")
        .agg(
            cnt_us=pl.col("cnt_us").sum().cast(pl.Int64),
            cnt_eu=pl.col("cnt_eu").sum().cast(pl.Int64),
            cnt_other=pl.col("cnt_other").sum().cast(pl.Int64),
            total_points=pl.col("total_points").sum().cast(pl.Int64),
        )
        .with_columns(
            frac_us=(pl.col("cnt_us") / pl.col("total_points")).alias("frac_us"),
            frac_eu=(pl.col("cnt_eu") / pl.col("total_points")).alias("frac_eu"),
            frac_other=(pl.col("cnt_other") / pl.col("total_points")).alias("frac_other"),
        )
        .with_columns(
            # 多数表决 + 可选阈值
            region=pl.when(
                (pl.col("cnt_us") >= pl.col("cnt_eu"))
                & (pl.col("cnt_us") >= pl.col("cnt_other"))
                & (pl.col("frac_us") >= majority_threshold)
            )
            .then(pl.lit("US"))
            .when(
                (pl.col("cnt_eu") >= pl.col("cnt_us"))
                & (pl.col("cnt_eu") >= pl.col("cnt_other"))
                & (pl.col("frac_eu") >= majority_threshold)
            )
            .then(pl.lit("EU"))
            .otherwise(pl.lit("OTHER"))
        )
    )

    flights_df = lf.collect(streaming=True)

    # 写出每个 flight_id 的地区分类
    flights_out = f"{out_prefix}_per_flight.csv"
    os.makedirs(os.path.dirname(flights_out), exist_ok=True)
    flights_df.select(["flight_id", "region", "cnt_us", "cnt_eu", "cnt_other", "total_points"]).write_csv(flights_out)

    total_flights = int(flights_df.height)
    # 统计汇总（按航班计数）
    by_flight = (
        flights_df
        .group_by("region")
        .agg(n_flights=pl.len().cast(pl.Int64))
        .sort("n_flights", descending=True)
    )

    # 统计整体点位占比（按点计数）
    point_totals = flights_df.select(
        pl.col("cnt_us").sum().alias("points_us"),
        pl.col("cnt_eu").sum().alias("points_eu"),
        pl.col("cnt_other").sum().alias("points_other"),
        pl.col("total_points").sum().alias("points_total"),
    ).to_dicts()[0]

    # 计算百分比（按航班）
    by_flight_map = {row["region"]: int(row["n_flights"]) for row in by_flight.to_dicts()}
    by_flight_pct = {k: (v * 100.0 / total_flights if total_flights else 0.0) for k, v in by_flight_map.items()}

    # 计算百分比（按点）
    points_total = float(point_totals.get("points_total", 0) or 0)
    by_points_map = {
        "US": int(point_totals.get("points_us", 0) or 0),
        "EU": int(point_totals.get("points_eu", 0) or 0),
        "OTHER": int(point_totals.get("points_other", 0) or 0),
    }
    by_points_pct = {k: (v * 100.0 / points_total if points_total else 0.0) for k, v in by_points_map.items()}

    summary = {
        "total_flights": total_flights,
        "by_flight": by_flight_map,
        "by_flight_pct": {k: round(v, 2) for k, v in by_flight_pct.items()},
        "by_points": {
            "points_us": by_points_map["US"],
            "points_eu": by_points_map["EU"],
            "points_other": by_points_map["OTHER"],
            "points_total": int(points_total),
        },
        "by_points_pct": {k: round(v, 2) for k, v in by_points_pct.items()},
    }

    # 主区域（按航班计数）
    if summary["by_flight"]:
        main_region = max(summary["by_flight"].items(), key=lambda x: x[1])[0]
        summary["main_region_by_flights"] = main_region

    # 主区域（按点计数）
    points_comp = {
        "US": point_totals["points_us"],
        "EU": point_totals["points_eu"],
        "OTHER": point_totals["points_other"],
    }
    summary["main_region_by_points"] = max(points_comp.items(), key=lambda x: x[1])[0]

    # 写出 JSON 与 CSV 汇总
    json_out = f"{out_prefix}_summary.json"
    csv_out = f"{out_prefix}_summary.csv"
    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 合成 CSV：包含航班与点位两种口径的数量与百分比
    points_df = pl.DataFrame({
        "region": ["EU", "US", "OTHER"],
        "points": [by_points_map.get("EU", 0), by_points_map.get("US", 0), by_points_map.get("OTHER", 0)],
    }).with_columns(
        ((pl.col("points") * 100.0) / points_total if points_total else pl.lit(0.0)).alias("pct_points")
    )

    by_flight_with_pct = by_flight.with_columns(
        ((pl.col("n_flights") * 100.0) / total_flights if total_flights else pl.lit(0.0)).alias("pct_flights")
    )

    combined = by_flight_with_pct.join(points_df, on="region", how="full").fill_null(0.0)
    # 列顺序
    combined = combined.select(["region", "n_flights", "pct_flights", "points", "pct_points"]).sort("n_flights", descending=True)
    combined.write_csv(csv_out)

    return summary


def main():
    parser = argparse.ArgumentParser(description="统计原始飞行轨迹地区分布（欧洲 vs 美国）与轨迹数量")
    parser.add_argument("--raw-dir", default="opensky_2024_PRC_dataset/rawtrajectories", help="原始轨迹 parquet 所在目录")
    parser.add_argument("--tmp-dir", default="junguo_analysis_for_opensky2022/tmp_region_counts", help="中间聚合结果输出目录")
    parser.add_argument("--out", default="junguo_analysis_for_opensky2022/region_summary", help="输出前缀（不含扩展名）")
    parser.add_argument("--majority-threshold", type=float, default=0.0, help="按航班多数表决的阈值（0~1）。例如 0.6 表示>=60% 才认定为该区域")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 个文件（调试用），0 表示全部")
    args = parser.parse_args()

    files = list_parquet_files(args.raw_dir)
    if args.limit and args.limit > 0:
        files = files[: args.limit]

    # 第一阶段：per-file 聚合
    os.makedirs(args.tmp_dir, exist_ok=True)
    for i, fpath in enumerate(files, 1):
        day = os.path.splitext(os.path.basename(fpath))[0]
        out_part = os.path.join(args.tmp_dir, f"region_counts_{day}.parquet")
        if os.path.exists(out_part):
            print(f"[{i}/{len(files)}] 跳过已存在: {out_part}")
            continue

        print(f"[{i}/{len(files)}] 处理 {fpath} -> {out_part}")
        try:
            df_part = aggregate_one_file(fpath)
            write_parquet(df_part, out_part)
        except Exception as e:
            print(f"  [WARN] 跳过 {fpath}，错误: {e}")

    # 第二阶段：全局汇总
    partials_glob = os.path.join(args.tmp_dir, "region_counts_*.parquet")
    print("汇总全局结果…")
    summary = summarize_all(partials_glob, args.out, majority_threshold=args.majority_threshold)

    print("=== 汇总完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # 让 Polars 使用全部 CPU 线程（默认即如此）
    # 可按需：os.environ["POLARS_MAX_THREADS"] = "80"
    main()
