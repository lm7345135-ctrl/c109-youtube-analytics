{{ config(
    materialized='table',
    partition_by={
      "field": "extracted_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["post_id", "channel_name"]
) }}

WITH comment_agg AS (
    SELECT
        platform,
        post_id,
        COUNT(*) AS collected_comment_count,
        COUNTIF(depth = 1) AS parent_comment_count,
        COUNTIF(depth = 2) AS reply_comment_count,
        SUM(likes) AS total_comment_likes,
        AVG(likes) AS avg_comment_likes,
        MAX(likes) AS max_comment_likes
    FROM {{ ref('int_comments_tree') }}
    WHERE NOT is_deleted
    GROUP BY platform, post_id
)

SELECT
    p.post_id,
    p.platform,
    p.channel_name,
    p.posted_at,
    p.extracted_at,
    p.extracted_date,
    p.media_type,
    p.impressions,
    p.likes,
    p.comments AS raw_comment_count,
    p.shares,
    COALESCE(c.collected_comment_count, 0) AS collected_comment_count,
    COALESCE(c.parent_comment_count, 0) AS parent_comment_count,
    COALESCE(c.reply_comment_count, 0) AS reply_comment_count,
    COALESCE(c.total_comment_likes, 0) AS total_comment_likes,
    ROUND(COALESCE(c.avg_comment_likes, 0), 2) AS avg_comment_likes,
    COALESCE(c.max_comment_likes, 0) AS max_comment_likes,
    -- エンゲージメント特徴量（ゼロ除算防止）
    SAFE_DIVIDE(p.likes, NULLIF(p.impressions, 0)) AS like_rate,
    SAFE_DIVIDE(COALESCE(c.reply_comment_count, 0), NULLIF(COALESCE(c.collected_comment_count, 0), 0)) AS reply_chain_ratio
FROM {{ ref('int_posts') }} p
LEFT JOIN comment_agg c
    ON p.post_id = c.post_id
    AND p.platform = c.platform
WHERE NOT p.is_deleted