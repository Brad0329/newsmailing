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
import storage

NAVER_NEWS_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_TAG_RE = re.compile(r"<[^>]+>")

# 한국 표준시 기준으로 "어제/오늘"을 계산
KST = timezone(timedelta(hours=9))


# 도메인 → 언론사 매핑은 data/domain_map.json에서 로드 (storage.load_domain_map).
# 모듈 로드 시 1회 캐시. 운영 중 갱신이 필요하면 reload_domain_map() 호출.
_domain_map_cache: dict[str, str] | None = None


def _get_domain_map() -> dict[str, str]:
    global _domain_map_cache
    if _domain_map_cache is None:
        _domain_map_cache = storage.load_domain_map()
    return _domain_map_cache


def reload_domain_map() -> dict[str, str]:
    """파일을 다시 읽어 캐시 갱신. 매핑 파일을 외부에서 편집한 경우 사용."""
    global _domain_map_cache
    _domain_map_cache = storage.load_domain_map()
    return _domain_map_cache


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
    return _get_domain_map().get(netloc, netloc)


def _calc_range(days: int, now: datetime | None = None) -> tuple[datetime, datetime]:
    """최근 N일 범위 계산 (KST). days=1이면 오늘 00:00~현재, days=2면 어제 00:00~현재 등."""
    now = now or datetime.now(KST)
    days = max(1, int(days))
    start = (now - timedelta(days=days - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, now


def _is_in_range(
    pub_date: datetime, start_dt: datetime, end_dt: datetime
) -> bool:
    p = pub_date.astimezone(KST)
    return start_dt <= p <= end_dt


def _is_recent(pub_date: datetime, now: datetime | None = None) -> bool:
    """어제 00:00(KST) ~ 현재(KST) 사이인지. (backward-compatible — days=2 고정)"""
    start, end = _calc_range(2, now=now)
    return _is_in_range(pub_date, start, end)


def search_news(
    query: str, display: int = 30, sort: str = "sim", start: int = 1
) -> list[dict]:
    """Naver 뉴스 검색 API 단일 호출. 원본 items 리스트를 반환.

    start: 1~1000 페이지네이션 오프셋.
    """
    config.check_naver()
    headers = {
        "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "sort": sort, "start": start}
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


_MAX_PAGES = 2  # 키워드당 최대 페이지 수 (display=30 × 2 = 60건 스캔)
_DISPLAY_PER_PAGE = 30


def collect(
    keywords: list[str],
    per_keyword: int = 5,
    days: int = 2,
    now: datetime | None = None,
) -> list[Article]:
    """여러 키워드에 대해 기사 수집, 날짜 범위 필터, URL 기준 전역 중복 제거.

    - `sort=date` + `start` 페이지네이션으로 최신→오래된 순 스캔
    - 각 키워드당 최대 _MAX_PAGES 페이지(60건)만 보고 그 안에서 per_keyword개 수집
    - pub_date가 범위 시작 이전으로 내려가면 조기 종료 (API 절약)
    - 동일 URL이 여러 키워드에서 나오면 첫 번째만 유지
    """
    range_start, range_end = _calc_range(days, now=now)
    seen_urls: set[str] = set()
    result: list[Article] = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        picked = 0
        stop_older = False
        for page in range(_MAX_PAGES):
            start_pos = 1 + page * _DISPLAY_PER_PAGE
            items = search_news(
                kw, display=_DISPLAY_PER_PAGE, sort="date", start=start_pos
            )
            if not items:
                break
            articles = _items_to_articles(items, keyword=kw)
            for a in articles:
                p = a.pub_date.astimezone(KST)
                if p > range_end:
                    # sort=date 기준으론 보통 안 나오지만 방어적 skip
                    continue
                if p < range_start:
                    stop_older = True
                    break
                if a.link in seen_urls:
                    continue
                seen_urls.add(a.link)
                result.append(a)
                picked += 1
                if picked >= per_keyword:
                    break
            if picked >= per_keyword or stop_older:
                break
    return result
