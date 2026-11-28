import json
import os
from datetime import datetime, timezone
from pathlib import Path

import mlflow
from huggingface_hub import HfApi

ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT_DIR / "data" / "outputs"
CONFIG_PATH = ROOT_DIR / "mlops" / "configs" / "nlp_pipeline.yaml"


def load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def log_to_mlflow(cluster_summary: dict, prophet_summary: dict) -> str:
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        raise RuntimeError("MLFLOW_TRACKING_URI が設定されていません。.env を確認してください。")

    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("c109-youtube-nlp-pipeline")

    run_name = f"phase3_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    with mlflow.start_run(run_name=run_name) as run:
        # パラメータ記録
        best_params = cluster_summary.get("best_params", {})
        mlflow.log_params({
            "n_samples": cluster_summary.get("n_samples", 0),
            "device": cluster_summary.get("device", "unknown"),
            "umap_n_neighbors": best_params.get("n_neighbors"),
            "umap_min_dist": round(float(best_params.get("min_dist", 0.0)), 6),
            "hdbscan_min_cluster_size": best_params.get("min_cluster_size"),
        })

        # メトリクス記録（クラスタリング + Prophet）
        metrics = {
            "optuna_best_score": float(cluster_summary.get("best_score", 0.0)),
            "n_clusters": float(cluster_summary.get("n_clusters", 0)),
            "noise_ratio": float(cluster_summary.get("noise_ratio", 0.0)),
        }
        if prophet_summary:
            total_7d_heat = sum(float(v.get("predicted_7d_total_heat", 0.0)) for v in prophet_summary.values())
            metrics["prophet_total_7d_heat"] = round(total_7d_heat, 4)
            for cid, meta in prophet_summary.items():
                metrics[f"cluster_{cid}_7d_heat"] = float(meta.get("predicted_7d_total_heat", 0.0))
        mlflow.log_metrics(metrics)

        # タグ記録
        mlflow.set_tags({
            "phase": "phase3-mlops",
            "embedding_model": "intfloat/multilingual-e5-small",
            "forecast_model": "prophet_with_regressors",
        })

        # アーティファクト（設定ファイル・結果JSON・Parquet）を登録
        for path in [
            CONFIG_PATH,
            OUTPUT_DIR / "cluster_summary.json",
            OUTPUT_DIR / "prophet_summary.json",
            OUTPUT_DIR / "clustered_comments.parquet",
            OUTPUT_DIR / "prophet_forecast.parquet",
        ]:
            if path.exists():
                mlflow.log_artifact(str(path))

        return run.info.run_id


def upload_to_huggingface() -> str:
    token = os.environ.get("HF_TOKEN")
    repo_id = os.environ.get("HF_REPO_ID")
    if not token or not repo_id:
        raise RuntimeError("HF_TOKEN または HF_REPO_ID が設定されていません。.env を確認してください。")

    api = HfApi(token=token)
    # 成果物保存用のプライベート Dataset リポジトリを作成（既存ならスキップ）
    api.create_repo(repo_id=repo_id, repo_type="dataset", private=True, exist_ok=True)

    target_files = [
        "cluster_summary.json",
        "prophet_summary.json",
        "clustered_comments.parquet",
        "prophet_forecast.parquet",
    ]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    for fname in target_files:
        fpath = OUTPUT_DIR / fname
        if fpath.exists():
            api.upload_file(
                path_or_fileobj=str(fpath),
                path_in_repo=f"latest/{fname}",
                repo_id=repo_id,
                repo_type="dataset",
                commit_message=f"Update {fname} ({stamp})",
            )

    return f"https://huggingface.co/datasets/{repo_id}"


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")

    cluster_path = OUTPUT_DIR / "cluster_summary.json"
    prophet_path = OUTPUT_DIR / "prophet_summary.json"
    if not cluster_path.exists():
        raise FileNotFoundError(f"{cluster_path} が見つかりません。先にクラスタリングを実行してください。")

    cluster_summary = json.loads(cluster_path.read_text(encoding="utf-8"))
    prophet_summary = json.loads(prophet_path.read_text(encoding="utf-8")) if prophet_path.exists() else {}

    print("[INFO] Logging experiment to DagsHub MLflow...")
    run_id = log_to_mlflow(cluster_summary, prophet_summary)
    print(f"[OK] MLflow Run ID: {run_id}")
    print("[OK] DagsHub Experiments: https://dagshub.com/lm7345135-ctrl/c109-youtube-analytics/experiments")

    print("[INFO] Uploading versioned artifacts to Hugging Face Hub...")
    hf_url = upload_to_huggingface()
    print(f"[OK] Hugging Face Dataset: {hf_url}")


if __name__ == "__main__":
    main()