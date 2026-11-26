{{ config(
    materialized='table',
    partition_by={
      "field": "extracted_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["post_id", "channel_name"]
) }}

WITH deduplicated AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY platform, post_id
            ORDER BY extracted_at DESC
        ) AS rn
    FROM {{ ref('stg_parent_posts') }}
)

SELECT
    post_id,
    platform,
    post_text,
    COALESCE(impressions, 0) AS impressions,
    COALESCE(likes, 0) AS likes,
    COALESCE(comments, 0) AS comments,
    COALESCE(shares, 0) AS shares,
    extracted_at,
    extracted_date,
    post_url,
    posted_at,
    COALESCE(media_type, 'unknown') AS media_type,
    media_urls,
    channel_name,
    is_deleted,
    deleted_at
FROM deduplicated
WHERE rn = 1