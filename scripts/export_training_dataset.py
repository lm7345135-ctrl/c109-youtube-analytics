from pathlib import Path
from google.cloud import bigquery

PROJECT_ID = "vibrant-arcanum-514402-q3"
OUTPUT_PATH = Path("data/datasets/masked_comments_v1.parquet")


def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    client = bigquery.Client(project=PROJECT_ID)
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=1_000_000_000)

    sql = f"""
        SELECT
            comment_id, post_id, platform, channel_name,
            masked_comment_text, likes, depth, hierarchy_level, posted_at
        FROM `{PROJECT_ID}.dwh_mart.v_mart_comments_masked`
    """
    df = client.query(sql, job_config=job_config).to_dataframe()
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"[OK] Exported {len(df)} rows -> {OUTPUT_PATH}")


if __name__ == "__main__":
    main()