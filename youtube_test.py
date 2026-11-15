import os
from dotenv import load_dotenv
from googleapiclient.discovery import build

# 1. .envファイルから安全にAPIキーを読み込む
load_dotenv()
API_KEY = os.getenv('YOUTUBE_API_KEY')

# 2. YouTube APIに接続する
youtube = build('youtube', 'v3', developerKey=API_KEY)

# 3. テスト対象の動画ID（★ここを書き換えてください）
VIDEO_ID = 'JkicR3MezYk'

def get_test_comments(video_id):
    print(f"通信開始: 動画ID [{video_id}] のコメントを取得しています...\n")
    
    # APIへリクエストを送信（テストとして関連度順トップ5件を取得）
    request = youtube.commentThreads().list(
        part="snippet",
        videoId=video_id,
        maxResults=5,
        order="relevance"
    )
    response = request.execute()

    # 取得したデータを画面に表示
    for item in response['items']:
        comment = item['snippet']['topLevelComment']['snippet']['textDisplay']
        author = item['snippet']['topLevelComment']['snippet']['authorDisplayName']
        likes = item['snippet']['topLevelComment']['snippet']['likeCount']
        
        print(f"👤 {author} (👍 {likes} いいね)")
        print(f"💬 {comment}")
        print("-" * 40)
        
    print("✅ 取得テスト完了！APIは正常に開通しています。")

if __name__ == "__main__":
    if VIDEO_ID == 'ここにテストしたい動画のIDを入力':
        print("❌ エラー: コード内の VIDEO_ID を実際の動画IDに書き換えてください！")
    else:
        get_test_comments(VIDEO_ID)
