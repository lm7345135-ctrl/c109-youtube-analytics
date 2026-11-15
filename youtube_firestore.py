import os
from googleapiclient.discovery import build
from google.cloud import firestore
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def fetch_youtube_data():
    try:
        API_KEY = os.getenv("YOUTUBE_API_KEY")
        youtube = build("youtube", "v3", developerKey=API_KEY)

        # サンプルデータ取得処理
        request = youtube.search().list(
            part="snippet",
            q="ウマ娘",
            maxResults=5
        )
        response = request.execute()

        db = firestore.Client(database="(default)")

        for item in response.get("items", []):
            video_id = item["id"].get("videoId")
            if video_id:
                title = item["snippet"]["title"]
                doc_ref = db.collection("youtube_videos").document(video_id)
                doc_ref.set({"title": title, "videoId": video_id})
        
        return jsonify({"status": "success", "message": "Data saved to Firestore"}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(debug=True, host="0.0.0.0", port=port)