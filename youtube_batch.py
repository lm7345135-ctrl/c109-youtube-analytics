import os
import json
from googleapiclient.discovery import build
from google.cloud import bigquery, storage
from dotenv import load_dotenv

load_dotenv()

def run_batch():
    # 1. YouTube APIからデータ取得
    API_KEY = os.getenv("YOUTUBE_API_KEY")
    youtube = build("youtube", "v3", developerKey=API_KEY)
    request = youtube.search().list(part="snippet", q="ウマ娘", maxResults=10)
    response = request.execute()

    # 2. GCS（データレイク）へJSONとして生データを保存
    storage_client = storage.Client()
    bucket_name = "youtube-datalake-vibrant-arcanum-514402-q3"
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob("raw_data/youtube_search_latest.json")
    blob.upload_from_string(json.dumps(response), content_type="application/json")
    print("GCSへの生データ保存完了")

    # 3. BigQuery（DWH）へテーブル保存（Step 2に向けた準備）
    # ※実際のテーブルスキーマ定義とLoad処理はStep 2のDataform/dbtで行うため、ここでは到達確認のみ
    print("Slow Path バッチ処理完了")

if __name__ == "__main__":
    run_batch()