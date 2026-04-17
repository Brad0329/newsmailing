"""Naver 검색 API 클라이언트 + 필터/중복제거/출처 추출."""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable
from urllib.parse import urlparse

import requests

import config

NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_TAG_RE = re.compile(r"<[^>]+>")

# 한국 표준시 기준으로 "어제/오늘"을 계산
KST = timezone(timedelta(hours=9))

# 도메인 → 언론사 매핑 (초기 — Phase 005에서 확장)
# 여러 도메인이 같은 언론사인 경우 모두 등록
DOMAIN_TO_SOURCE: dict[str, str] = {
    "hankyung.com": "한국경제",
    "mk.co.kr": "매일경제",
    "mt.co.kr": "머니투데이",
    "sedaily.com": "서울경제",
    "etnews.com": "전자신문",
    "zdnet.co.kr": "ZDNet 코리아",
    "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보",
    "donga.com": "동아일보",
    "hani.co.kr": "한겨레",
    "khan.co.kr": "경향신문",
    "yna.co.kr": "연합뉴스",
    "ytn.co.kr": "YTN",
    "sbs.co.kr": "SBS",
    "kbs.co.kr": "KBS",
    "mbc.co.kr": "MBC",
    "news1.kr": "뉴스1",
    "newsis.com": "뉴시스",
    "hansbiz.co.kr": "한스경제",
    "fnnews.com": "파이낸셜뉴스",
    "edaily.co.kr": "이데일리",
    "asiae.co.kr": "아시아경제",
    "inews24.com": "아이뉴스24",
    "dt.co.kr": "디지털타임스",
    "mediapen.com": "미디어펜",
    "newdaily.co.kr": "뉴데일리",
    "ajunews.com": "아주경제",
    "thebell.co.kr": "더벨",
    "kmib.co.kr": "국민일보",
    "munhwa.com": "문화일보",
}


@dataclass
class Article:
    title: str
    link: str  # 원본 기사 링크 (originallink 우선, 없으면 link)
    source: str
    pub_date: datetime
    description: str
    keyword: str  # 어떤 검색어로 찾았는지

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pub_date"] = self.pub_date.isoformat()
        return d


def strip_html(text: str) -> str:
    """Naver 응답의 <b> 태그와 HTML 엔티티를 정리."""
    if not text:
        return ""
    stripped = _TAG_RE.sub("", text)
    return html.unescape(stripped).strip()


def parse_pubdate(raw: str) -> datetime:
    """RFC 822 형식 (예: 'Thu, 17 Apr 2026 09:30:00 +0900') → datetime."""
    dt = parsedate_to_datetime(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    return dt


def extract_source(url: str) -> str:
    """URL → 언론사명. 매핑 없으면 도메인 그대로 반환."""
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return url
    # www., news. 등 흔한 서브도메인 제거
    netloc = re.sub(r"^(www|news|biz|sports|m|imnews|v)\.", "", netloc)
    return DOMAIN_TO_SOURCE.get(netloc, netloc)


def _is_recent(pub_date: datetime, now: datetime | None = None) -> bool:
    """어제 00:00(KST) ~ 현재(KST) 사이인지."""
    now = now or datetime.now(KST)
    yesterday_start = (now - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return yesterday_start <= pub_date.astimezone(KST) <= now


def search_news(query: str, display: int = 30, sort: str = "sim") -> list[dict]:
    """Naver 뉴스 검색 API 단일 호출. 원본 items 리스트를 반환."""
    config.check_naver()
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": sort}
    resp = requests.get(NAVER_NEWS_ENDPOINT, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("items", [])


def _items_to_articles(items: Iterable[dict], keyword: str) -> list[Article]:
    articles: list[Article] = []
    for it in items:
        link = it.get("originallink") or it.get("link") or ""
        try:
            pub_date = parse_pubdate(it.get("pubDate", ""))
        except Exception:
            continue
        articles.append(
            Article(
                title=strip_html(it.get("title", "")),
                link=link,
                source=extract_source(link),
                pub_date=pub_date,
                description=strip_html(it.get("description", "")),
                keyword=keyword,
            )
        )
    return articles


def filter_recent(articles: list[Article], now: datetime | None = None) -> list[Article]:
    return [a for a in articles if _is_recent(a.pub_date, now=now)]


def collect(
    keywords: list[str],
    per_keyword: int = 5,
    display: int = 30,
    now: datetime | None = None,
) -> list[Article]:
    """여러 키워드에 대해 기사 수집, 어제/오늘 필터, URL 기준 전역 중복 제거.

    - 각 키워드에 대해 Naver 검색 호출
    - pubDate로 어제~오늘 필터
    - 동일 URL이 여러 키워드에서 나오면 첫 번째만 유지 (키워드 정보도 첫 것 유지)
    - 키워드별 최대 per_keyword 개
    """
    seen_urls: set[str] = set()
    result: list[Article] = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        items = search_news(kw, display=display)
        candidates = _items_to_articles(items, keyword=kw)
        candidates = filter_recent(candidates, now=now)
        # 키워드 내에서는 게시 최신순 정렬
        candidates.sort(key=lambda a: a.pub_date, reverse=True)
        picked = 0
        for a in candidates:
            if picked >= per_keyword:
                break
            if a.link in seen_urls:
                continue
            seen_urls.add(a.link)
            result.append(a)
            picked += 1
    return result
