{{ config(
    materialized='view'
) }}

SELECT
    comment_id,
    post_id,
    platform,
    channel_name,
    category,
    rank,
    -- PII 動的マスキング（@メンション・メールアドレス・URL を伏字化）
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                COALESCE(comment_text, ''),
                r'@[A-Za-z0-9_.-]+',
                '@MASKED_USER'
            ),
            r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
            '[MASKED_EMAIL]'
        ),
        r'https?://[^\s]+',
        '[MASKED_URL]'
    ) AS masked_comment_text,
    likes,
    impressions,
    extracted_at,
    extracted_date,
    posted_at,
    media_type,
    parent_comment_id,
    depth,
    hierarchy_level
FROM {{ ref('int_comments_tree') }}
WHERE NOT is_deleted