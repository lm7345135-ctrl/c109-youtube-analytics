import json
from pathlib import Path

import numpy as np
import pandas as pd
from prophet import Prophet

ROOT_DIR = Path(__file__).resolve().parents[2]
INPUT_PARQUET = ROOT_DIR / "data" / "outputs" / "clustered_comments.parquet"
OUTPUT_DIR = ROOT_DIR / "data" / "outputs"


def build_daily_series(df: pd.DataFrame) -> pd.DataFrame:
    # 日時カラムを自動検出（posted_at / published_at / extracted_date 等）
    date_col = next(
        (c for c in ["posted_at", "published_at", "comment_published_at", "extracted_date", "created_at"] if c in df.columns),
        None,
    )
    if date_col is None:
        raise ValueError(f"日時カラムが見つかりません: {list(df.columns)}")

    df = df.copy()
    df["ds"] = pd.to_datetime(df[date_col], errors="coerce", utc=True).dt.tz_localize(None).dt.floor("D")
    df = df.dropna(subset=["ds"])

    like_col = next((c for c in ["like_count", "likes"] if c in df.columns), None)
    df["heat_score"] = 1.0 + (df[like_col].fillna(0).astype(float) * 0.1 if like_col else 0.0)

    daily = (
        df[df["cluster_id"] != -1]
        .groupby(["cluster_id", "ds"], as_index=False)
        .agg(comment_count=("heat_score", "size"), y=("heat_score", "sum"))
    )
    return daily


def forecast_cluster(sub: pd.DataFrame, horizon_days: int = 7) -> tuple[pd.DataFrame, dict]:
    sub = sub.sort_values("ds").copy()
    # 欠損日を 0 埋めして連続日次系列にする
    full_dates = pd.date_range(sub["ds"].min(), sub["ds"].max(), freq="D")
    ts = pd.DataFrame({"ds": full_dates}).merge(sub[["ds", "y"]], on="ds", how="left")
    ts["y"] = ts["y"].fillna(0.0)

    # 外部変数：週末・配信イベント想定フラグ（熱量が中央値の1.5倍超をイベント日とみなす）
    ts["is_weekend"] = ts["ds"].dt.dayofweek.isin([5, 6]).astype(int)
    threshold = max(float(ts["y"].median()) * 1.5, 1.0)
    ts["is_event_spike"] = (ts["y"] >= threshold).astype(int)

    # 日数が2日未満の場合は単純減衰モデルでフォールバック
    if len(ts) < 2:
        last_date = ts["ds"].iloc[-1]
        base_y = float(ts["y"].iloc[-1])
        future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon_days, freq="D")
        decay = [round(base_y * (0.7 ** (i + 1)), 4) for i in range(horizon_days)]
        fc = pd.DataFrame({"ds": future_dates, "yhat": decay, "yhat_lower": [0.0] * horizon_days, "yhat_upper": decay})
        meta = {
            "method": "exponential_decay_fallback",
            "history_days": int(len(ts)),
            "predicted_7d_total_heat": round(float(sum(decay)), 2),
            "decay_rate_estimate": 0.7,
        }
        return fc, meta

    model = Prophet(weekly_seasonality=True, daily_seasonality=False, yearly_seasonality=False)
    model.add_regressor("is_weekend")
    model.add_regressor("is_event_spike")
    model.fit(ts[["ds", "y", "is_weekend", "is_event_spike"]])

    future = model.make_future_dataframe(periods=horizon_days, freq="D")
    future["is_weekend"] = future["ds"].dt.dayofweek.isin([5, 6]).astype(int)
    future["is_event_spike"] = 0

    forecast = model.predict(future)[["ds", "yhat", "yhat_lower", "yhat_upper"]]
    forecast["yhat"] = forecast["yhat"].clip(lower=0.0)
    forecast["yhat_lower"] = forecast["yhat_lower"].clip(lower=0.0)
    forecast["yhat_upper"] = forecast["yhat_upper"].clip(lower=0.0)

    future_only = forecast.tail(horizon_days)
    peak_y = max(float(ts["y"].max()), 1e-6)
    end_y = float(future_only["yhat"].iloc[-1])
    meta = {
        "method": "prophet_with_regressors",
        "history_days": int(len(ts)),
        "predicted_7d_total_heat": round(float(future_only["yhat"].sum()), 2),
        "retention_ratio_vs_peak": round(min(end_y / peak_y, 1.0), 4),
    }
    return future_only, meta


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(INPUT_PARQUET)
    daily = build_daily_series(df)

    all_forecasts = []
    summary = {}
    for cid, sub in daily.groupby("cluster_id"):
        fc, meta = forecast_cluster(sub, horizon_days=7)
        fc["cluster_id"] = int(cid)
        all_forecasts.append(fc)
        summary[str(int(cid))] = meta

    out_parquet = OUTPUT_DIR / "prophet_forecast.parquet"
    if all_forecasts:
        pd.concat(all_forecasts, ignore_index=True).to_parquet(out_parquet, index=False)

    out_summary = OUTPUT_DIR / "prophet_summary.json"
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Saved: {out_parquet}")
    print(f"[OK] Saved: {out_summary}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()