import subprocess
import sys
from pathlib import Path
from google.cloud import bigquery

PROJECT_ID = "vibrant-arcanum-514402-q3"
DUMMY_ID = "__tombstone_test_dummy__"
ROOT_DIR = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT_DIR / "dbt_dwh"


def count_rows(client, table_ref):
    job_config = bigquery.QueryJobConfig(maximum_bytes_billed=1_000_000_000)
    sql = f"SELECT COUNT(*) AS cnt FROM `{table_ref}` WHERE comment_id = '{DUMMY_ID}'"
    return list(client.query(sql, job_config=job_config).result())[0].cnt


def main():
    client = bigquery.Client(project=PROJECT_ID)
    int_table = f"{PROJECT_ID}.dwh_intermediate.int_comments_tree"
    masked_view = f"{PROJECT_ID}.dwh_mart.v_mart_comments_masked"

    # 1. 31日前に論理削除されたダミーレコードを1件挿入
    insert_sql = f"""
        INSERT INTO `{int_table}` (
            comment_id, post_id, platform, channel_name, comment_text,
            likes, extracted_at, extracted_date, depth, hierarchy_level,
            is_deleted, deleted_at
        )
        VALUES (
            '{DUMMY_ID}', '__dummy_post__', 'YouTube', '__dummy_channel__', 'dummy',
            0, CURRENT_TIMESTAMP(), CURRENT_DATE(), 1, 'parent_comment',
            TRUE, TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 31 DAY)
        )
    """
    client.query(insert_sql).result()
    c_int_before = count_rows(client, int_table)
    c_view_before = count_rows(client, masked_view)
    print(f"[1. 論理削除直後] int_comments_tree={c_int_before} (期待:1), v_mart_comments_masked={c_view_before} (期待:0)")
    assert c_int_before == 1 and c_view_before == 0, "論理削除の非表示検証に失敗しました"

    # 2. dbt の Tombstone 物理削除マクロを実行
    subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", "run-operation", "run_tombstone_compaction", "--profiles-dir", "."],
        cwd=DBT_DIR,
        check=True,
    )

    # 3. 物理削除されたことを確認
    c_int_after = count_rows(client, int_table)
    print(f"[2. コンパクション後] int_comments_tree={c_int_after} (期待:0)")
    assert c_int_after == 0, "物理削除（コンパクション）の検証に失敗しました"
    print("[OK] Tombstone 論理削除 -> ビュー非表示 -> 30日超過物理削除の全工程を確認しました")


if __name__ == "__main__":
    main()