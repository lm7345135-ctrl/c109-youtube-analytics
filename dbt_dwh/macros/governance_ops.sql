{% macro create_bq_table_snapshot() %}
  {% set snap_date = modules.datetime.datetime.utcnow().strftime('%Y%m%d') %}
  {% set sql %}
    CREATE SNAPSHOT TABLE IF NOT EXISTS `vibrant-arcanum-514402-q3.dwh_mart.mart_post_features_snap_{{ snap_date }}`
    CLONE `vibrant-arcanum-514402-q3.dwh_mart.mart_post_features`
    OPTIONS (
      expiration_timestamp = TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 7 DAY),
      description = 'Step2: 無料枠(10GB)保護のため7日で自動期限切れとなる日次テーブルスナップショット'
    );
  {% endset %}
  {% do run_query(sql) %}
  {{ log("Created BigQuery snapshot: mart_post_features_snap_" ~ snap_date, info=True) }}
{% endmacro %}


{% macro run_tombstone_compaction(retention_days=30) %}
  {% set targets = [
      'vibrant-arcanum-514402-q3.dwh_staging.stg_parent_posts',
      'vibrant-arcanum-514402-q3.dwh_staging.stg_child_comments',
      'vibrant-arcanum-514402-q3.dwh_intermediate.int_posts',
      'vibrant-arcanum-514402-q3.dwh_intermediate.int_comments_tree'
  ] %}
  {% for table_name in targets %}
    {% set sql %}
      DELETE FROM `{{ table_name }}`
      WHERE is_deleted = TRUE
        AND deleted_at IS NOT NULL
        AND deleted_at < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {{ retention_days }} DAY);
    {% endset %}
    {% do run_query(sql) %}
    {{ log("Compacted tombstones (older than " ~ retention_days ~ " days) on: " ~ table_name, info=True) }}
  {% endfor %}
{% endmacro %}