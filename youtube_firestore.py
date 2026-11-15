import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.cloud import firestore

# 1. 認証情報の読み込み
load_dotenv()
API_KEY = os.getenv('YOUTUBE_API_KEY')

# 2. もう一つの鍵ファイル（gcp-key.json）を環境変数に紐付ける
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp-key.json"

# 3. クライアントの初期化（プロジェクトIDは明示せず、鍵ファイル内の情報を自動取得させる）
youtube = build('youtube', 'v3', developerKey=API_KEY)
db = firestore.Client()

# 先ほど取得成功したウマ娘の動画ID
VIDEO_ID = 'JkicR3MezYk'

def save_comments_to_firestore(video_id):
    print(f"通信開始: 動画ID [{video_id}] のコメントを取得し、Firestoreへ保存します...\n")
    
    # APIからデータ取得
    request = youtube.commentThreads().list(
        part="snippet",
        videoId=video_id,
        maxResults=5,
        order="relevance"
    )
    response = request.execute()

    # Firestoreの保存先コレクション
    collection_ref = db.collection('youtube_comments')

    saved_count = 0
    for item in response['items']:
        comment_id = item['id']
        snippet = item['snippet']['topLevelComment']['snippet']
        
        # 保存するデータの構造
        doc_data = {
            'video_id': video_id,
            'author': snippet['authorDisplayName'],
            'comment': snippet['textDisplay'],
            'likes': snippet['likeCount'],
            'published_at': snippet['publishedAt']
        }
        
        # Firestoreに書き込み
        collection_ref.document(comment_id).set(doc_data)
        saved_count += 1
        
        print(f"👤 {doc_data['author']} (👍 {doc_data['likes']} いいね) -> 保存完了")
        
    print("-" * 40)
    print(f"✅ テスト完了！ {saved_count}件のコメントをFirestoreに保存しました。")

if __name__ == "__main__":
    save_comments_to_firestore(VIDEO_ID)