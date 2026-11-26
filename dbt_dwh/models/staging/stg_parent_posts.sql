{{ config(
    materialized='table',
    partition_by={
      "field": "extracted_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["post_id", "channel_name"]
) }}

SELECT
    CAST(post_id AS STRING) AS post_id,
    TRIM(CAST(platform AS STRING)) AS platform,
    CAST(post_text AS STRING) AS post_text,
    CAST(impressions AS INT64) AS impressions,
    CAST(likes AS INT64) AS likes,
    CAST(comments AS INT64) AS comments,
    CAST(shares AS INT64) AS shares,
    CAST(extracted_at AS TIMESTAMP) AS extracted_at,
    DATE(CAST(extracted_at AS TIMESTAMP)) AS extracted_date,
    CAST(post_url AS STRING) AS post_url,
    CAST(posted_at AS TIMESTAMP) AS posted_at,
    CAST(media_type AS STRING) AS media_type,
    CAST(media_urls AS STRING) AS media_urls,
    COALESCE(NULLIF(TRIM(CAST(channel_name AS STRING)), ''), 'unknown_channel') AS channel_name,
    -- ToS 準拠 Tombstone（論理削除管理用）
    FALSE AS is_deleted,
    CAST(NULL AS TIMESTAMP) AS deleted_at
FROM {{ source('raw_sns', 'parent_posts') }}
WHERE post_id IS NOT NULL