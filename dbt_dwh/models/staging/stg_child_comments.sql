{{ config(
    materialized='table',
    partition_by={
      "field": "extracted_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["platform", "post_id"]
) }}

SELECT
    CAST(comment_id AS STRING) AS comment_id,
    CAST(post_id AS STRING) AS post_id,
    TRIM(CAST(platform AS STRING)) AS platform,
    CAST(category AS STRING) AS category,
    CAST(rank AS INT64) AS rank,
    CAST(comment_text AS STRING) AS comment_text,
    CAST(likes AS INT64) AS likes,
    CAST(impressions AS INT64) AS impressions,
    CAST(extracted_at AS TIMESTAMP) AS extracted_at,
    DATE(CAST(extracted_at AS TIMESTAMP)) AS extracted_date,
    CAST(posted_at AS TIMESTAMP) AS posted_at,
    CAST(media_type AS STRING) AS media_type,
    CAST(media_urls AS STRING) AS media_urls,
    NULLIF(TRIM(CAST(parent_comment_id AS STRING)), '') AS parent_comment_id,
    CAST(depth AS INT64) AS depth,
    -- ToS 準拠 Tombstone（論理削除管理用）
    FALSE AS is_deleted,
    CAST(NULL AS TIMESTAMP) AS deleted_at
FROM {{ source('raw_sns', 'child_comments') }}
WHERE comment_id IS NOT NULL
  AND post_id IS NOT NULL