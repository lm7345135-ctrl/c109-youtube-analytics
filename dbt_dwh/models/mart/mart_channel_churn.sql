{{ config(
    materialized='table',
    partition_by={
      "field": "latest_extracted_date",
      "data_type": "date",
      "granularity": "day"
    },
    cluster_by=["platform", "channel_name"]
) }}

WITH post_intervals AS (
    SELECT
        platform,
        channel_name,
        post_id,
        posted_at,
        extracted_date,
        LAG(posted_at) OVER (
            PARTITION BY platform, channel_name
            ORDER BY posted_at
        ) AS prev_posted_at,
        DATE_DIFF(
            DATE(posted_at),
            DATE(LAG(posted_at) OVER (
                PARTITION BY platform, channel_name
                ORDER BY posted_at
            )),
            DAY
        ) AS days_since_prev_post
    FROM {{ ref('int_posts') }}
    WHERE NOT is_deleted
      AND posted_at IS NOT NULL
)

SELECT
    platform,
    channel_name,
    COUNT(DISTINCT post_id) AS total_posts,
    MIN(posted_at) AS first_posted_at,
    MAX(posted_at) AS last_posted_at,
    MAX(extracted_date) AS latest_extracted_date,
    ROUND(AVG(days_since_prev_post), 2) AS avg_post_interval_days,
    DATE_DIFF(CURRENT_DATE(), DATE(MAX(posted_at)), DAY) AS days_since_last_post,
    CASE
        WHEN DATE_DIFF(CURRENT_DATE(), DATE(MAX(posted_at)), DAY) <= 14 THEN 'active'
        WHEN DATE_DIFF(CURRENT_DATE(), DATE(MAX(posted_at)), DAY) <= 30 THEN 'at_risk'
        ELSE 'churned'
    END AS retention_status
FROM post_intervals
GROUP BY platform, channel_name