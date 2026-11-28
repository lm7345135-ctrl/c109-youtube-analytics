{{ config(
    materialized='view'
) }}

SELECT
    comment_id,
    TO_HEX(SHA256(CONCAT(platform, ':', comment_id))) AS anonymized_comment_key,
    post_id,
    platform,
    channel_name,
    category,
    rank,
    -- PII 動的マスキング（メール -> URL -> 電話番号 -> @メンション の順で置換）
    REGEXP_REPLACE(
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    COALESCE(comment_text, ''),
                    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
                    '[MASKED_EMAIL]'
                ),
                r'https?://[^\s]+',
                '[MASKED_URL]'
            ),
            r'0\d{1,4}-\d{1,4}-\d{3,4}',
            '[MASKED_PHONE]'
        ),
        r'@[A-Za-z0-9_.-]+',
        '@MASKED_USER'
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