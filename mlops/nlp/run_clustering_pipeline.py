import json
import re
import sys
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
import torch
import umap
from hydra import compose, initialize_config_dir
from omegaconf import DictConfig, OmegaConf
from sentence_transformers import SentenceTransformer
from sklearn.cluster import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics import silhouette_score
from sudachipy import dictionary, tokenizer

ROOT_DIR = Path(__file__).resolve().parents[2]
optuna.logging.set_verbosity(optuna.logging.WARNING)


def load_custom_dict(csv_path: Path) -> list[tuple[str, str]]:
    if not csv_path.exists():
        return []
    df_dict = pd.read_csv(csv_path)
    # 長い語句を優先して置換
    pairs = list(zip(df_dict["surface"].astype(str), df_dict["normalized"].astype(str)))
    return sorted(pairs, key=lambda x: len(x[0]), reverse=True)


def normalize_and_tokenize(texts: list[str], custom_pairs: list[tuple[str, str]]) -> list[str]:
    tok = dictionary.Dictionary().create()
    mode = tokenizer.Tokenizer.SplitMode.C
    stop_pos = {"助詞", "助動詞", "記号", "補助記号", "空白"}

    tokenized_docs = []
    for raw in texts:
        text = str(raw or "")
        matched_terms = []
        for surface, normalized in custom_pairs:
            if surface in text:
                text = text.replace(surface, " ")
                matched_terms.append(normalized)

        # URLやマスク記号を除外して形態素解析
        text = re.sub(r"\[MASKED_[A-Z]+\]|@MASKED_USER", " ", text)
        tokens = []
        for m in tok.tokenize(text, mode):
            pos = m.part_of_speech()[0]
            lemma = m.normalized_form()
            if pos not in stop_pos and len(lemma) >= 2:
                tokens.append(lemma)
        tokenized_docs.append(" ".join(matched_terms + tokens))
    return tokenized_docs


def extract_ctfidf_keywords(docs: list[str], labels: np.ndarray, top_n: int = 8) -> dict[int, list[str]]:
    df_tmp = pd.DataFrame({"doc": docs, "cluster": labels})
    df_valid = df_tmp[df_tmp["cluster"] != -1]
    if df_valid.empty:
        return {}

    grouped = df_valid.groupby("cluster")["doc"].apply(lambda s: " ".join(s)).reset_index()
    vectorizer = CountVectorizer(token_pattern=r"(?u)\b\w+\b")
    tf = vectorizer.fit_transform(grouped["doc"]).toarray().astype(float)
    vocab = np.array(vectorizer.get_feature_names_out())

    if tf.shape[1] == 0:
        return {}

    # c-TF-IDF = (クラスター内語頻度 / クラスター総語数) * log(1 + 全平均語数 / 全クラスターでの語頻度合計)
    cluster_totals = np.maximum(tf.sum(axis=1, keepdims=True), 1.0)
    avg_words = tf.sum() / max(len(grouped), 1)
    term_totals = np.maximum(tf.sum(axis=0, keepdims=True), 1.0)
    ctfidf = (tf / cluster_totals) * np.log(1.0 + (avg_words / term_totals))

    keywords = {}
    for idx, cluster_id in enumerate(grouped["cluster"].tolist()):
        top_indices = np.argsort(ctfidf[idx])[::-1][:top_n]
        keywords[int(cluster_id)] = [vocab[i] for i in top_indices if ctfidf[idx, i] > 0]
    return keywords


def main(cfg: DictConfig) -> None:
    np.random.seed(cfg.seed)
    torch.manual_seed(cfg.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[INFO] Device: {device} | Config:\n{OmegaConf.to_yaml(cfg)}")

    input_path = ROOT_DIR / cfg.paths.input_parquet
    output_dir = ROOT_DIR / cfg.paths.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(input_path)
    df = df[df["masked_comment_text"].fillna("").str.strip() != ""].reset_index(drop=True)
    n_samples = len(df)
    print(f"[INFO] Loaded {n_samples} comments from {input_path}")

    # 1. 多言語埋め込み (Multilingual-E5)
    model = SentenceTransformer(cfg.embedding.model_name, device=device)
    passages = [f"{cfg.embedding.prefix}{t}" for t in df["masked_comment_text"].tolist()]
    embeddings = model.encode(
        passages,
        batch_size=cfg.embedding.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    # 2. Optuna による UMAP + HDBSCAN ハイパーパラメータ探索
    max_neighbors = min(cfg.optuna.umap_n_neighbors_max, max(cfg.optuna.umap_n_neighbors_min + 1, n_samples - 2))
    max_cluster_size = min(cfg.optuna.hdbscan_min_cluster_size_max, max(cfg.optuna.hdbscan_min_cluster_size_min + 1, n_samples // 4))

    def objective(trial: optuna.Trial) -> float:
        n_neighbors = trial.suggest_int("n_neighbors", cfg.optuna.umap_n_neighbors_min, max_neighbors)
        min_dist = trial.suggest_float("min_dist", 0.0, 0.3)
        min_cluster_size = trial.suggest_int("min_cluster_size", cfg.optuna.hdbscan_min_cluster_size_min, max_cluster_size)

        reducer = umap.UMAP(
            n_neighbors=n_neighbors,
            n_components=min(cfg.optuna.umap_n_components, max(2, n_samples - 2)),
            min_dist=min_dist,
            metric="cosine",
            random_state=cfg.seed,
        )
        reduced = reducer.fit_transform(embeddings)
        labels = HDBSCAN(min_cluster_size=min_cluster_size).fit_predict(reduced)

        mask = labels != -1
        unique_clusters = set(labels[mask])
        if len(unique_clusters) < 2 or mask.sum() < 10:
            return -1.0

        sil = silhouette_score(reduced[mask], labels[mask])
        noise_ratio = float((labels == -1).mean())
        # シルエット係数を最大化しつつ、ノイズ過多（>50%）にペナルティを課す
        return float(sil - max(0.0, noise_ratio - 0.5) * 0.5)

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=cfg.seed))
    study.optimize(objective, n_trials=cfg.optuna.n_trials)
    best = study.best_params
    print(f"[INFO] Optuna Best Score: {study.best_value:.4f} | Params: {best}")

    # 3. 最適パラメータで最終クラスタリング ＋ 可視化用 2D UMAP 座標を生成
    reducer_cluster = umap.UMAP(
        n_neighbors=best["n_neighbors"],
        n_components=min(cfg.optuna.umap_n_components, max(2, n_samples - 2)),
        min_dist=best["min_dist"],
        metric="cosine",
        random_state=cfg.seed,
    )
    reduced_cluster = reducer_cluster.fit_transform(embeddings)
    labels = HDBSCAN(min_cluster_size=best["min_cluster_size"]).fit_predict(reduced_cluster)

    reducer_2d = umap.UMAP(
        n_neighbors=best["n_neighbors"],
        n_components=2,
        min_dist=best["min_dist"],
        metric="cosine",
        random_state=cfg.seed,
    )
    coords_2d = reducer_2d.fit_transform(embeddings)

    # 4. SudachiPy + カスタム辞書による c-TF-IDF トレンド語抽出
    custom_pairs = load_custom_dict(ROOT_DIR / cfg.paths.custom_dict_csv)
    tokenized_docs = normalize_and_tokenize(df["masked_comment_text"].tolist(), custom_pairs)
    cluster_keywords = extract_ctfidf_keywords(tokenized_docs, labels, top_n=cfg.ctfidf.top_n_words)

    # 5. 結果保存
    df["cluster_id"] = labels
    df["umap_x"] = coords_2d[:, 0]
    df["umap_y"] = coords_2d[:, 1]
    df["cluster_keywords"] = df["cluster_id"].map(lambda c: ", ".join(cluster_keywords.get(int(c), [])))

    out_parquet = output_dir / "clustered_comments.parquet"
    df.to_parquet(out_parquet, index=False)

    noise_ratio = float((labels == -1).mean())
    summary = {
        "n_samples": n_samples,
        "device": device,
        "best_score": round(float(study.best_value), 4),
        "best_params": best,
        "n_clusters": len(set(labels) - {-1}),
        "noise_ratio": round(noise_ratio, 4),
        "cluster_keywords": {str(k): v for k, v in cluster_keywords.items()},
    }
    out_summary = output_dir / "cluster_summary.json"
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] Saved: {out_parquet}")
    print(f"[OK] Saved: {out_summary}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    config_dir = str((ROOT_DIR / "mlops" / "configs").resolve())
    overrides = [arg for arg in sys.argv[1:] if "=" in arg]
    with initialize_config_dir(version_base=None, config_dir=config_dir):
        cfg = compose(config_name="nlp_pipeline", overrides=overrides)
    main(cfg)