import os
from datetime import datetime, timezone
from google.cloud import bigquery, firestore

PROJECT_ID = "vibrant-arcanum-514402-q3"
MAX_BYTES_BILLED = 1_000_000_000  # 1GB上限ガードレール


def _serialize(value):
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def sync_table_to_firestore(bq_client, fs_client, query, collection_name, id_field):
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    rows = list(bq_client.query(query, job_config=job_config).result())

    batch = fs_client.batch()
    count = 0
    synced_at = datetime.now(timezone.utc).isoformat()

    for row in rows:
        doc_data = {k: _serialize(v) for k, v in dict(row).items()}
        doc_data["synced_at"] = synced_at
        doc_id = str(doc_data[id_field]).replace("/", "_")
        doc_ref = fs_client.collection(collection_name).document(doc_id)
        batch.set(doc_ref, doc_data, merge=True)
        count += 1

        # Firestore バッチ上限（500件）対策
        if count % 400 == 0:
            batch.commit()
            batch = fs_client.batch()

    if count % 400 != 0:
        batch.commit()

    print(f"[OK] Synced {count} docs -> Firestore collection: '{collection_name}'")


def main():
    bq_client = bigquery.Client(project=PROJECT_ID)
    fs_client = firestore.Client(project=PROJECT_ID)

    post_features_sql = f"""
        SELECT
            post_id, platform, channel_name, posted_at, extracted_at,
            media_type, impressions, likes, raw_comment_count, shares,
            collected_comment_count, parent_comment_count, reply_comment_count,
            total_comment_likes, avg_comment_likes, max_comment_likes,
            like_rate, reply_chain_ratio
        FROM `{PROJECT_ID}.dwh_mart.mart_post_features`
    """
    sync_table_to_firestore(
        bq_client, fs_client, post_features_sql, "online_post_features", "post_id"
    )

    churn_sql = f"""
        SELECT
            platform, channel_name, total_posts, first_posted_at, last_posted_at,
            avg_post_interval_days, days_since_last_post, retention_status
        FROM `{PROJECT_ID}.dwh_mart.mart_channel_churn`
    """
    sync_table_to_firestore(
        bq_client, fs_client, churn_sql, "online_channel_churn", "channel_name"
    )


if __name__ == "__main__":
    main()