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
            PARTITION BY platform, comment_id
            ORDER BY extracted_at DESC
        ) AS rn
    FROM {{ ref('stg_child_comments') }}
),

normalized_tree AS (
    SELECT
        c.comment_id,
        c.post_id,
        c.platform,
        COALESCE(p.channel_name, 'unknown_channel') AS channel_name,
        c.category,
        c.rank,
        c.comment_text,
        COALESCE(c.likes, 0) AS likes,
        c.impressions,
        c.extracted_at,
        c.extracted_date,
        c.posted_at,
        COALESCE(c.media_type, 'text_only') AS media_type,
        c.media_urls,
        c.parent_comment_id,
        -- DDD 階層正規化（depth が NULL の場合は parent_comment_id の有無で 1:親コメント / 2:返信 を補完）
        COALESCE(c.depth, CASE WHEN c.parent_comment_id IS NULL THEN 1 ELSE 2 END) AS depth,
        CASE
            WHEN COALESCE(c.depth, CASE WHEN c.parent_comment_id IS NULL THEN 1 ELSE 2 END) = 1 THEN 'parent_comment'
            ELSE 'reply_comment'
        END AS hierarchy_level,
        (c.is_deleted OR COALESCE(p.is_deleted, FALSE)) AS is_deleted,
        COALESCE(c.deleted_at, p.deleted_at) AS deleted_at
    FROM deduplicated c
    INNER JOIN {{ ref('int_posts') }} p
        ON c.post_id = p.post_id
        AND c.platform = p.platform
    WHERE c.rn = 1
)

SELECT * FROM normalized_tree