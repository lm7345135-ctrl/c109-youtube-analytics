import requests
import json

def get_x_embed_data(tweet_url):
    """
    X (Twitter)の公式oEmbed APIを使用して、BANリスクなしで投稿の基本情報を取得する
    """
    # Xの公式oEmbedエンドポイント (認証不要・無料)
    api_url = f"https://publish.twitter.com/oembed?url={tweet_url}"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        # 取得できた基本情報を抽出 (名前、HTML本文など)
        extracted_info = {
            "platform": "X",
            "author_name": data.get("author_name", ""),
            "author_url": data.get("author_url", ""),
            "html_content": data.get("html", "")
        }
        return extracted_info
    except requests.exceptions.RequestException as e:
        print(f"X Embed API Error: {e}")
        return None

def get_tiktok_embed_data(tiktok_url):
    """
    TikTokの公式oEmbed APIを使用して、BANリスクなしで投稿の基本情報を取得する
    """
    # TikTokの公式oEmbedエンドポイント (認証不要・無料)
    api_url = f"https://www.tiktok.com/oembed?url={tiktok_url}"
    
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        data = response.json()
        
        # 取得できた基本情報を抽出 (タイトル、名前など)
        extracted_info = {
            "platform": "TikTok",
            "title": data.get("title", ""),
            "author_name": data.get("author_name", ""),
            "author_unique_id": data.get("author_unique_id", "")
        }
        return extracted_info
    except requests.exceptions.RequestException as e:
        print(f"TikTok Embed API Error: {e}")
        return None

if __name__ == "__main__":
    # --- テスト実行 ---
    
    # 1. Hoo の投稿ポストで一旦テスト
    x_test_url = "https://x.com/hoo441613952451/status/2120495254973436070"
    print("--- X (Twitter) API Test ---")
    x_result = get_x_embed_data(x_test_url)
    print(json.dumps(x_result, indent=2, ensure_ascii=False) if x_result else "取得失敗")

    # 2. ぱかチューブっ！公式TikTokの実在する動画のテスト
    tiktok_test_url = "https://www.tiktok.com/@umamusu_pd/video/7707856720013446407"
    print("\n--- TikTok API Test ---")
    tiktok_result = get_tiktok_embed_data(tiktok_test_url)
    print(json.dumps(tiktok_result, indent=2, ensure_ascii=False) if tiktok_result else "取得失敗")