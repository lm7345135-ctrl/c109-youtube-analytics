{{ config(
    materialized='table',
    partition_by={
        "field": "extracted_date",
        "data_type": "date",
        "granularity": "day"
    },
    cluster_by=["platform", "channel_name"]
) }}

WITH scored AS (
    SELECT
        post_id,
        platform,
        channel_name,
        posted_at,
        extracted_at,
        DATE(extracted_at) AS extracted_date,
        media_type,
        likes,
        collected_comment_count,
        like_rate,
        reply_chain_ratio,
        PERCENT_RANK() OVER (
            PARTITION BY platform ORDER BY COALESCE(like_rate, 0)
        ) AS like_rate_pct,
        PERCENT_RANK() OVER (
            PARTITION BY platform ORDER BY COALESCE(reply_chain_ratio, 0)
        ) AS reply_chain_pct,
        PERCENT_RANK() OVER (
            PARTITION BY platform ORDER BY COALESCE(collected_comment_count, 0)
        ) AS comment_volume_pct
    FROM {{ ref('mart_post_features') }}
)

SELECT
    post_id,
    platform,
    channel_name,
    posted_at,
    extracted_at,
    extracted_date,
    media_type,
    likes,
    collected_comment_count,
    like_rate,
    reply_chain_ratio,
    ROUND(
        (like_rate_pct * 0.35)
        + (reply_chain_pct * 0.35)
        + (comment_volume_pct * 0.30),
        4
    ) AS recommendation_score,
    RANK() OVER (
        PARTITION BY platform
        ORDER BY (
            (like_rate_pct * 0.35)
            + (reply_chain_pct * 0.35)
            + (comment_volume_pct * 0.30)
        ) DESC
    ) AS recommendation_rank
FROM scored