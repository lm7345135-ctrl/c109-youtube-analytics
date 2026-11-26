{% snapshot snap_post_features %}

{{
    config(
      target_schema='dwh_mart',
      unique_key='post_id',
      strategy='timestamp',
      updated_at='extracted_at',
      invalidate_hard_deletes=True
    )
}}

SELECT * FROM {{ ref('mart_post_features') }}

{% endsnapshot %}