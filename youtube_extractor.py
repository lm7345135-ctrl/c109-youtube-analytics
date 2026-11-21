import os
import re
import time
import requests

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
WEBHOOK_URL = "https://sns-data-receiver-643940969500.us-central1.run.app"

PROMO_REGEX = re.compile(
    "|".join([
        r"\[PR\]", r"#PR\b", r"#広告", r"プロモーションを含",
        r"(?:^|\n)\s*PR\s*(?:\n|$)",
        r"amazon\.co\.jp", r"amzn\.to", r"a\.r10\.to", r"hb\.afl\.rakuten",
        r"bit\.ly/", r"tinyurl\.com", r"lin\.ee/", r"line\.me/",
        r"lit\.link", r"linktr\.ee", r"t\.me/",
        r"プロフ(ィール)?(から|見て|欄|リンク|に)",
        r"(詳細|続き|動画|本編)(は|を)プロフ",
        r"(現金|無料|PayPay|アマギフ|ギフト)(配布|プレゼント)",
        r"(副業|在宅ワーク|不労所得|稼げる|月収\d+万|投資案件)",
        r"DM(ください|まで|で|送って|お待ち)",
        r"裏垢(女子|男子)?",
    ]),
    re.IGNORECASE,
)


def normalize_for_compare(text: str) -> str:
    s = re.sub(r"@[A-Za-z0-9_]+", "", text or "")
    return re.sub(r"\s+", "", s).strip()


def get_spam_bot_reason(text: str, parent_text: str = ""):
    """YouTubeコメント用のPR・宣伝bot・海外ゾンビ・コピペ除外判定"""
    t = (text or "").strip()
    if not t:
        return "空コメント"
    if PROMO_REGEX.search(t):
        return "PR/アフィ/宣伝bot"
    if len(re.findall(r"[#＃][^\s#＃]+", t)) >= 4:
        return "ハッシュタグ乱用bot"
    if not re.search(r"[ぁ-んァ-ヶ一-龠a-zA-Z0-9]", t):
        return "絵文字/記号のみスパム"
    if re.search(r"[\u0600-\u06FF\u0900-\u097F\u0980-\u09FF\u0A00-\u0A7F]", t):
        return "海外スパム(文字種)"

    parent_has_jp = bool(re.search(r"[ぁ-んァ-ヶ一-龠]", parent_text or ""))
    text_has_jp = bool(re.search(r"[ぁ-んァ-ヶ一-龠]", t))
    if parent_has_jp and not text_has_jp:
        cleaned = re.sub(r"https?://\S+|@[A-Za-z0-9_]+", "", t).strip()
        if len(cleaned.split()) >= 4:
            return "無関係な外国語スパム"

    norm_t = normalize_for_compare(t)
    norm_p = normalize_for_compare(parent_text)
    if len(norm_p) >= 12 and len(norm_t) >= 12:
        if norm_t == norm_p or (len(norm_p) >= 20 and norm_t.startswith(norm_p[:20])):
            return "親本文コピペbot"

    return None


def extract_video_id(url_or_id: str) -> str:
    patterns = [
        r"(?:v=|youtu\.be\/|shorts\/|live\/|embed\/)([0-9A-Za-z_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url_or_id)
        if m:
            return m.group(1)
    return url_or_id.strip()


def resolve_channel_id(channel_input: str):
    if not channel_input:
        return None
    s = channel_input.strip()
    if s.startswith("UC") and len(s) == 24:
        return s

    m_ch = re.search(r"/channel/(UC[0-9A-Za-z_-]{22})", s)
    if m_ch:
        return m_ch.group(1)

    m_handle = re.search(r"@([0-9A-Za-z_.-]+)", s)
    if m_handle:
        handle = m_handle.group(1)
        res = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "id,snippet", "forHandle": handle, "key": YOUTUBE_API_KEY},
            timeout=30,
        )
        res.raise_for_status()
        items = res.json().get("items", [])
        if items:
            print(f"チャンネル解決(@ハンドル): {items[0]['snippet']['title']} ({items[0]['id']})")
            return items[0]["id"]

    res = requests.get(
        "https://www.googleapis.com/youtube/v3/search",
        params={
            "part": "snippet",
            "type": "channel",
            "q": s,
            "maxResults": 1,
            "key": YOUTUBE_API_KEY,
        },
        timeout=30,
    )
    res.raise_for_status()
    items = res.json().get("items", [])
    if not items:
        raise ValueError(f"チャンネルが見つかりません: {channel_input}")

    ch_id = items[0]["snippet"]["channelId"]
    ch_title = items[0]["snippet"]["title"]
    print(f"チャンネル解決(名前検索): {ch_title} ({ch_id})")
    return ch_id


def to_rfc3339_jst(date_str: str, is_end: bool = False):
    if not date_str:
        return None
    s = date_str.strip()
    if "T" in s:
        return s
    return f"{s}T23:59:59+09:00" if is_end else f"{s}T00:00:00+09:00"


def search_top_youtube_videos(
    channel_name: str = None,
    search_query: str = None,
    date_from: str = None,
    date_to: str = None,
    top_n: int = 4,
    candidate_limit: int = 50,     # 1回のsearch API(50件)で完結させてエコ化
    sort_by: str = "likes",
    min_views: int = 0,
    min_likes: int = 0,
):
    channel_id = resolve_channel_id(channel_name) if channel_name else None
    query_str = (search_query or "").strip() or None
    if not channel_id and not query_str:
        raise ValueError("channel_name または search_query のどちらか一方を指定してください。")

    published_after = to_rfc3339_jst(date_from, is_end=False)
    published_before = to_rfc3339_jst(date_to, is_end=True)
    search_order = "relevance" if query_str else "viewCount"

    video_ids = []
    next_page_token = None

    while len(video_ids) < candidate_limit:
        params = {
            "part": "id",
            "type": "video",
            "order": search_order,
            "maxResults": min(50, candidate_limit - len(video_ids)),
            "key": YOUTUBE_API_KEY,
        }
        if query_str:
            params["q"] = query_str
        if channel_id:
            params["channelId"] = channel_id
        if published_after:
            params["publishedAfter"] = published_after
        if published_before:
            params["publishedBefore"] = published_before
        if next_page_token:
            params["pageToken"] = next_page_token

        res = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=params,
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()

        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            if vid and vid not in video_ids:
                video_ids.append(vid)

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    if not video_ids:
        print("検索条件に一致する動画が0件でした。")
        return []

    candidates = []
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        v_res = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet,statistics", "id": ",".join(chunk), "key": YOUTUBE_API_KEY},
            timeout=30,
        )
        v_res.raise_for_status()

        for item in v_res.json().get("items", []):
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            stats = item.get("statistics", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))

            if views < min_views or likes < min_likes:
                continue

            candidates.append({
                "video_id": item["id"],
                "title": title,
                "published_at": snippet.get("publishedAt", "")[:10],
                "views": views,
                "likes": likes,
                "url": f"https://www.youtube.com/watch?v={item['id']}",
            })

    if sort_by == "views":
        candidates.sort(key=lambda x: (x["views"], x["likes"]), reverse=True)
    else:
        candidates.sort(key=lambda x: (x["likes"], x["views"]), reverse=True)

    selected = candidates[:top_n]
    print(f"\n=== 抽出条件: チャンネル={channel_name} / 検索語={query_str} / 期間={date_from}〜{date_to} ===")
    print(f"=== 候補{len(video_ids)}本 → 条件一致{len(candidates)}本 → 上位{len(selected)}本 ({sort_by}順) ===")
    for idx, c in enumerate(selected, start=1):
        print(f"  {idx:2d}位: [{c['published_at']}] いいね {c['likes']:,} / 再生 {c['views']:,} | {c['title'][:38]}")
    print()

    return [c["url"] for c in selected]


def fetch_top_replies(parent_comment_id: str, parent_text: str = "", top_n: int = 3, max_pages: int = 1):
    """孫コメントを1ページ(最大100件)取得し、スパム除外後のいいね上位N件を返す"""
    replies = []
    next_page_token = None

    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "parentId": parent_comment_id,
            "maxResults": 100,
            "textFormat": "plainText",
            "key": YOUTUBE_API_KEY,
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        res = requests.get(
            "https://www.googleapis.com/youtube/v3/comments",
            params=params,
            timeout=30,
        )
        if res.status_code != 200:
            break
        data = res.json()

        for item in data.get("items", []):
            s = item["snippet"]
            text = s.get("textDisplay", "")
            if get_spam_bot_reason(text, parent_text):
                continue
            replies.append({
                "comment_id": item["id"],
                "parent_comment_id": parent_comment_id,
                "depth": 2,
                "text": text,
                "likes": int(s.get("likeCount", 0)),
                "impressions": None,
                "posted_at": s.get("publishedAt"),
                "media_type": "text_only",
                "media_urls": None,
            })

        next_page_token = data.get("nextPageToken")
        if not next_page_token:
            break

    replies.sort(key=lambda x: x["likes"], reverse=True)
    top_replies = []
    for idx, r in enumerate(replies[:top_n], start=1):
        r["rank"] = idx
        top_replies.append(r)
    return top_replies


def fetch_youtube_video_and_tree(url_or_id: str, top_n: int = 3, reply_top_n: int = 3, max_pages: int = 1):
    """人気順(relevance)で子コメントを1ページ(100件)取得し、スパム除外後の子3×孫3を抽出する"""
    video_id = extract_video_id(url_or_id)

    video_res = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet,statistics", "id": video_id, "key": YOUTUBE_API_KEY},
        timeout=30,
    )
    video_res.raise_for_status()
    items = video_res.json().get("items", [])
    if not items:
        raise ValueError(f"動画が見つかりません: {video_id}")

    item = items[0]
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})

    parent_post = {
        "post_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel_name": snippet.get("channelTitle"),
        "text": snippet.get("title"),
        "impressions": stats.get("viewCount"),
        "likes": stats.get("likeCount"),
        "comments": stats.get("commentCount"),
        "shares": None,
        "posted_at": snippet.get("publishedAt"),
        "media_type": "video",
        "media_urls": [f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"],
    }

    all_comments = []
    excluded_count = 0
    seen_norm_texts = set()
    next_page_token = None

    for _ in range(max_pages):
        params = {
            "part": "snippet",
            "videoId": video_id,
            "order": "relevance",  # 人気順で1ページ(100件)取得してエコ化
            "maxResults": 100,
            "textFormat": "plainText",
            "key": YOUTUBE_API_KEY,
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        c_res = requests.get(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            params=params,
            timeout=30,
        )
        if c_res.status_code == 403:
            break
        c_res.raise_for_status()
        c_data = c_res.json()

        for thread in c_data.get("items", []):
            top_c = thread["snippet"]["topLevelComment"]
            s = top_c["snippet"]
            text = s.get("textDisplay", "")

            if get_spam_bot_reason(text, parent_post["text"]):
                excluded_count += 1
                continue

            norm = normalize_for_compare(text)
            if len(norm) >= 12:
                if norm in seen_norm_texts:
                    excluded_count += 1
                    continue
                seen_norm_texts.add(norm)

            all_comments.append({
                "comment_id": top_c["id"],
                "parent_comment_id": None,
                "depth": 1,
                "reply_count": int(thread["snippet"].get("totalReplyCount", 0)),
                "text": text,
                "likes": int(s.get("likeCount", 0)),
                "impressions": None,
                "posted_at": s.get("publishedAt"),
                "media_type": "text_only",
                "media_urls": None,
            })

        next_page_token = c_data.get("nextPageToken")
        if not next_page_token:
            break

    all_comments.sort(key=lambda x: x["likes"], reverse=True)
    top_children = []
    top_grandchildren = []

    for idx, c in enumerate(all_comments[:top_n], start=1):
        reply_count = c.pop("reply_count", 0)
        c["rank"] = idx
        top_children.append(c)

        if reply_top_n > 0 and reply_count > 0:
            replies = fetch_top_replies(c["comment_id"], parent_text=c["text"], top_n=reply_top_n, max_pages=1)
            top_grandchildren.extend(replies)

    payload = {
        "platform": "YouTube",
        "parent_post": parent_post,
        "child_comments": {
            "top_by_likes": top_children,
            "reply_top_by_likes": top_grandchildren,
        },
    }

    print(
        f"取得完了: {parent_post['text'][:38]} "
        f"(有効:{len(all_comments)}件 / スパム除外:{excluded_count}件 → 子:{len(top_children)}件 / 孫:{len(top_grandchildren)}件)"
    )
    return payload


def send_to_bigquery_via_cloud_run(payload: dict):
    res = requests.post(WEBHOOK_URL, json=payload, timeout=60)
    res.raise_for_status()
    print("  -> BigQuery送信成功:", res.text)


if __name__ == "__main__":
    CHANNEL_NAME = "ゆずっこちゃんねる"
    SEARCH_QUERY = "ウマ娘"
    DATE_FROM = "2026-01-01"
    DATE_TO = "2026-11-21"

    PARENT_TOP_N = 4
    SORT_BY = "likes"
    MIN_VIEWS = 10000
    MIN_LIKES = 100

    target_urls = search_top_youtube_videos(
        channel_name=CHANNEL_NAME,
        search_query=SEARCH_QUERY,
        date_from=DATE_FROM,
        date_to=DATE_TO,
        top_n=PARENT_TOP_N,
        candidate_limit=50,
        sort_by=SORT_BY,
        min_views=MIN_VIEWS,
        min_likes=MIN_LIKES,
    )

    for idx, url in enumerate(target_urls, start=1):
        print(f"[{idx}/{len(target_urls)}] 処理中: {url}")
        try:
            data = fetch_youtube_video_and_tree(url, top_n=3, reply_top_n=3, max_pages=1)
            send_to_bigquery_via_cloud_run(data)
        except Exception as e:
            print(f"  -> スキップ（エラー）: {e}")
        time.sleep(1)