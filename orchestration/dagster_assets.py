import subprocess
import sys
from pathlib import Path
from dagster import Definitions, asset

ROOT_DIR = Path(__file__).resolve().parent.parent
DBT_DIR = ROOT_DIR / "dbt_dwh"


def _run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, check=True, text=True)
    return result.returncode


@asset(group_name="step2_dwh")
def dbt_dwh_models():
    """Staging -> Intermediate -> Mart の3層DWHを構築"""
    _run([sys.executable, "-m", "dbt.cli.main", "run", "--profiles-dir", "."], DBT_DIR)


@asset(deps=[dbt_dwh_models], group_name="step2_dwh")
def dbt_quality_tests():
    """主キー・NULL・参照整合性・値域の品質テストを実行"""
    _run([sys.executable, "-m", "dbt.cli.main", "test", "--profiles-dir", "."], DBT_DIR)


@asset(deps=[dbt_quality_tests], group_name="step2_governance")
def bq_snapshots_and_compaction():
    """SCD Type2スナップショット・7日期限BQスナップショット・Tombstone物理削除"""
    _run([sys.executable, "-m", "dbt.cli.main", "snapshot", "--profiles-dir", "."], DBT_DIR)
    _run(
        [sys.executable, "-m", "dbt.cli.main", "run-operation", "create_bq_table_snapshot", "--profiles-dir", "."],
        DBT_DIR,
    )
    _run(
        [sys.executable, "-m", "dbt.cli.main", "run-operation", "run_tombstone_compaction", "--profiles-dir", "."],
        DBT_DIR,
    )


@asset(deps=[dbt_quality_tests], group_name="step2_feature_store")
def firestore_online_feature_store():
    """BigQuery Mart からオンラインFeature Store (Firestore) へ同期"""
    _run([sys.executable, "scripts/sync_feature_store.py"], ROOT_DIR)


@asset(deps=[dbt_quality_tests], group_name="step2_mlops")
def dvc_training_dataset():
    """PIIマスキング済み学習用Parquetを出力し、DVCでGCSへ版管理プッシュ"""
    _run([sys.executable, "scripts/export_training_dataset.py"], ROOT_DIR)
    _run([sys.executable, "-m", "dvc", "add", "data/datasets/masked_comments_v1.parquet"], ROOT_DIR)
    _run([sys.executable, "-m", "dvc", "push"], ROOT_DIR)


defs = Definitions(
    assets=[
        dbt_dwh_models,
        dbt_quality_tests,
        bq_snapshots_and_compaction,
        firestore_online_feature_store,
        dvc_training_dataset,
    ]
)

if __name__ == "__main__":
    from dagster import materialize

    result = materialize(
        [
            dbt_dwh_models,
            dbt_quality_tests,
            bq_snapshots_and_compaction,
            firestore_online_feature_store,
            dvc_training_dataset,
        ]
    )
    if not result.success:
        sys.exit(1)