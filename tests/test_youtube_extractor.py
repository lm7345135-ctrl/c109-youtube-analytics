import pytest
from youtube_extractor import (
    extract_video_id,
    to_rfc3339_jst,
    get_spam_bot_reason,
    normalize_for_compare,
)


@pytest.mark.parametrize(
    "raw_input, expected",
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?si=abcd", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_extract_video_id(raw_input, expected):
    assert extract_video_id(raw_input) == expected


def test_to_rfc3339_jst():
    assert to_rfc3339_jst("2026-11-21", is_end=False) == "2026-11-21T00:00:00+09:00"
    assert to_rfc3339_jst("2026-11-21", is_end=True) == "2026-11-21T23:59:59+09:00"
    assert to_rfc3339_jst(None) is None


def test_spam_bot_filter_excludes_noise():
    assert get_spam_bot_reason("") == "空コメント"
    assert get_spam_bot_reason("詳細はプロフから！ https://bit.ly/xxx") == "PR/アフィ/宣伝bot"
    assert get_spam_bot_reason("#a #b #c #d テスト") == "ハッシュタグ乱用bot"
    assert get_spam_bot_reason("😂😂😂!!!") == "絵文字/記号のみスパム"
    assert (
        get_spam_bot_reason(
            "This is completely unrelated English spam comment",
            parent_text="ウマ娘の反応集動画です",
        )
        == "無関係な外国語スパム"
    )
    assert (
        get_spam_bot_reason(
            "【ウマ娘】ぱかライブTV5周年まとめ感想",
            parent_text="【ウマ娘】ぱかライブTV5周年まとめ感想",
        )
        == "親本文コピペbot"
    )


def test_spam_bot_filter_allows_valid_comments():
    assert get_spam_bot_reason("2:03:26 助かる", parent_text="ぱかライブTV") is None
    assert get_spam_bot_reason("デアリングタクトの演出よかった！", parent_text="ウマ娘反応集") is None


def test_normalize_for_compare():
    assert normalize_for_compare("@user123  テスト 投稿 ") == "テスト投稿"