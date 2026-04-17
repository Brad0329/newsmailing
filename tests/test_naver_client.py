"""naver_client 순수 함수 단위 테스트 (API 호출 없음)."""
from datetime import datetime, timedelta, timezone

import pytest

from naver_client import (
    KST,
    Article,
    _is_recent,
    _items_to_articles,
    extract_source,
    filter_recent,
    parse_pubdate,
    strip_html,
)


# ---------- strip_html ----------


def test_strip_html_removes_tags_and_entities():
    raw = "해킹 한 번에 <b>영업정지</b>...카드업계 &quot;보안&quot;"
    assert strip_html(raw) == '해킹 한 번에 영업정지...카드업계 "보안"'


def test_strip_html_empty():
    assert strip_html("") == ""


# ---------- parse_pubdate ----------


def test_parse_pubdate_rfc822_with_tz():
    dt = parse_pubdate("Thu, 17 Apr 2026 09:30:00 +0900")
    assert dt.year == 2026 and dt.month == 4 and dt.day == 17
    assert dt.hour == 9 and dt.minute == 30


def test_parse_pubdate_without_tz_defaults_kst():
    dt = parse_pubdate("Thu, 17 Apr 2026 09:30:00")
    assert dt.utcoffset() == timedelta(hours=9)


# ---------- extract_source ----------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.hankyung.com/article/123", "한국경제"),
        ("https://news.mt.co.kr/mtview.php?no=1", "머니투데이"),
        ("https://biz.chosun.com/site/data/html_dir/2026/04/17/foo.html", "조선일보"),
        ("https://hansbiz.co.kr/news/articleView.html?idxno=1", "한스경제"),
        ("https://unknown-news.com/article/1", "unknown-news.com"),
        ("", ""),
    ],
)
def test_extract_source(url, expected):
    assert extract_source(url) == expected


# ---------- _is_recent / filter_recent ----------


def _make_article(dt: datetime) -> Article:
    return Article(
        title="t",
        link="https://example.com/a",
        source="example.com",
        pub_date=dt,
        description="",
        keyword="kw",
    )


def test_is_recent_today():
    now = datetime(2026, 4, 17, 10, 0, tzinfo=KST)
    today_morning = datetime(2026, 4, 17, 3, 0, tzinfo=KST)
    assert _is_recent(today_morning, now=now) is True


def test_is_recent_yesterday():
    now = datetime(2026, 4, 17, 10, 0, tzinfo=KST)
    yesterday = datetime(2026, 4, 16, 23, 59, tzinfo=KST)
    assert _is_recent(yesterday, now=now) is True


def test_is_recent_two_days_ago_excluded():
    now = datetime(2026, 4, 17, 10, 0, tzinfo=KST)
    two_days = datetime(2026, 4, 15, 23, 59, tzinfo=KST)
    assert _is_recent(two_days, now=now) is False


def test_is_recent_future_excluded():
    now = datetime(2026, 4, 17, 10, 0, tzinfo=KST)
    future = datetime(2026, 4, 17, 11, 0, tzinfo=KST)
    assert _is_recent(future, now=now) is False


def test_filter_recent_mixed():
    now = datetime(2026, 4, 17, 10, 0, tzinfo=KST)
    arts = [
        _make_article(datetime(2026, 4, 17, 9, 0, tzinfo=KST)),  # today
        _make_article(datetime(2026, 4, 16, 12, 0, tzinfo=KST)),  # yesterday
        _make_article(datetime(2026, 4, 10, 12, 0, tzinfo=KST)),  # old
    ]
    filtered = filter_recent(arts, now=now)
    assert len(filtered) == 2


# ---------- _items_to_articles ----------


def test_items_to_articles_parses_sample():
    sample = [
        {
            "title": "<b>카드</b> 보안 이슈 확산",
            "originallink": "https://www.hankyung.com/article/1",
            "link": "https://n.news.naver.com/1",
            "description": "보안 우려가 <b>확산</b>되고 있다",
            "pubDate": "Thu, 17 Apr 2026 09:00:00 +0900",
        },
        {
            "title": "핀테크 동향",
            "originallink": "https://hansbiz.co.kr/x",
            "link": "https://n.news.naver.com/2",
            "description": "최근 동향",
            "pubDate": "Wed, 16 Apr 2026 18:00:00 +0900",
        },
    ]
    arts = _items_to_articles(sample, keyword="카드")
    assert len(arts) == 2
    assert arts[0].title == "카드 보안 이슈 확산"
    assert arts[0].source == "한국경제"
    assert arts[0].link == "https://www.hankyung.com/article/1"
    assert arts[0].keyword == "카드"
    assert arts[1].source == "한스경제"


def test_items_to_articles_falls_back_to_link_when_no_originallink():
    sample = [
        {
            "title": "제목",
            "link": "https://n.news.naver.com/3",
            "description": "",
            "pubDate": "Thu, 17 Apr 2026 09:00:00 +0900",
        }
    ]
    arts = _items_to_articles(sample, keyword="kw")
    assert arts[0].link == "https://n.news.naver.com/3"


def test_items_to_articles_skips_bad_pubdate():
    sample = [
        {
            "title": "bad",
            "originallink": "https://x.com/1",
            "pubDate": "not-a-date",
        },
        {
            "title": "good",
            "originallink": "https://x.com/2",
            "pubDate": "Thu, 17 Apr 2026 09:00:00 +0900",
        },
    ]
    arts = _items_to_articles(sample, keyword="kw")
    assert len(arts) == 1
    assert arts[0].title == "good"
