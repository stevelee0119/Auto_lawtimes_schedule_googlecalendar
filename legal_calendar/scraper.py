"""법률신문 '이주의 법조일정' 스크래퍼."""

import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

ARTICLE_BASE = "https://www.lawtimes.co.kr"

# Google News RSS: 법률신문 '이번주 법조 일정' 검색
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
    "?q=%EC%9D%B4%EB%B2%88%EC%A3%BC+%EB%B2%95%EC%A1%B0+%EC%9D%BC%EC%A0%95"
    "+site%3Alawtimes.co.kr&hl=ko&gl=KR&ceid=KR%3Ako"
)

# 목록 페이지 후보 (사이트 개편으로 변경될 수 있음)
CALENDAR_LIST_CANDIDATES = [
    "https://www.lawtimes.co.kr/news/list?page=1&kind=AG02",
    "https://www.lawtimes.co.kr/news/list?page=1&kind=A15",
    "https://www.lawtimes.co.kr/news/list?page=1&kind=AG01",
    "https://www.lawtimes.co.kr/news/list?page=1&kind=AG03",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.lawtimes.co.kr/",
}


@dataclass
class LegalEvent:
    title: str
    date: date
    start_time: Optional[str]
    end_time: Optional[str]
    location: Optional[str]
    description: Optional[str]
    source_url: str


def _parse_time(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})[:\.](\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def _parse_date(text: str, reference_year: int) -> Optional[date]:
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        return date(reference_year, int(m.group(1)), int(m.group(2)))
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", text)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[./](\d{1,2})", text)
    if m:
        return date(reference_year, int(m.group(1)), int(m.group(2)))
    return None


def _is_schedule_article(title: str) -> bool:
    return "이번주" in title and ("법조" in title or "일정" in title)


def _get_latest_calendar_url_via_google_news(session: requests.Session) -> Optional[str]:
    """Google News RSS로 최신 '이번주 법조 일정' 기사 URL을 찾는다."""
    try:
        resp = session.get(GOOGLE_NEWS_RSS, timeout=15)
        if resp.status_code != 200:
            print(f"[DEBUG] Google News RSS: HTTP {resp.status_code}", file=sys.stderr)
            return None

        root = ET.fromstring(resp.content)
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(".//item")

        for item in items:
            title_elem = item.find("title")
            title_text = title_elem.text if title_elem is not None else ""

            # ET quirk: <link> in RSS is sometimes in title.tail
            link_url = None
            if title_elem is not None and title_elem.tail and title_elem.tail.strip():
                link_url = title_elem.tail.strip()

            if not link_url:
                link_elem = item.find("link")
                if link_elem is not None and link_elem.text:
                    link_url = link_elem.text.strip()

            if not link_url:
                guid_elem = item.find("guid")
                if guid_elem is not None and guid_elem.text:
                    link_url = guid_elem.text.strip()

            if link_url:
                if "lawtimes.co.kr" in link_url:
                    print(f"[DEBUG] Google News 직접 URL: {link_url}", file=sys.stderr)
                    return link_url
                # Google 리다이렉트 URL → 실제 기사 URL로 따라가기
                try:
                    r = session.get(link_url, headers=HEADERS, timeout=15, allow_redirects=True)
                    if "lawtimes.co.kr" in r.url:
                        print(f"[DEBUG] Google News 리다이렉트 URL: {r.url}", file=sys.stderr)
                        return r.url
                except Exception as e:
                    print(f"[DEBUG] 리다이렉트 실패: {e}", file=sys.stderr)

    except Exception as e:
        print(f"[DEBUG] Google News RSS 실패: {e}", file=sys.stderr)

    return None


def _get_latest_calendar_url_via_list(session: requests.Session) -> Optional[str]:
    """목록 페이지에서 '이번주 법조 일정' 기사 URL을 찾는다."""
    for list_url in CALENDAR_LIST_CANDIDATES:
        try:
            resp = session.get(list_url, headers=HEADERS, timeout=15)
            print(f"[DEBUG] 목록 URL {list_url}: HTTP {resp.status_code}", file=sys.stderr)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.select("a[href]"):
                href = a["href"]
                if "/news/" in href and re.search(r"\d+", href):
                    title_text = a.get_text(strip=True)
                    if _is_schedule_article(title_text):
                        url = ARTICLE_BASE + href if href.startswith("/") else href
                        print(f"[DEBUG] 목록에서 발견: {url}", file=sys.stderr)
                        return url
        except Exception as e:
            print(f"[DEBUG] 목록 URL 실패 {list_url}: {e}", file=sys.stderr)

    return None


def _get_latest_calendar_url(session: requests.Session) -> Optional[str]:
    """최신 '이번주 법조 일정' 기사 URL을 반환한다."""
    # 1순위: Google News RSS (목록 URL 변경에 영향받지 않음)
    url = _get_latest_calendar_url_via_google_news(session)
    if url:
        return url

    # 2순위: 목록 페이지 직접 접근
    url = _get_latest_calendar_url_via_list(session)
    if url:
        return url

    return None


def _parse_article(soup: BeautifulSoup, url: str) -> list[LegalEvent]:
    events: list[LegalEvent] = []
    year = datetime.now().year

    body = (
        soup.select_one(".article-body, .news-body, #article-body, .content-body")
        or soup.find("div", {"class": re.compile(r"(article|content|body)", re.I)})
    )
    if not body:
        body = soup.body

    text = body.get_text(separator="\n") if body else ""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    current_date: Optional[date] = None

    for line in lines:
        parsed = _parse_date(line, year)
        if parsed and len(line) < 30:
            current_date = parsed
            continue

        if not current_date:
            continue

        time_match = re.match(r"^(\d{1,2}[:.]\d{2})\s+(.+)", line)
        if time_match:
            start_time = _parse_time(time_match.group(1))
            rest = time_match.group(2)
            loc_match = re.search(r"[（(]([^）)]+)[）)]", rest)
            location = loc_match.group(1) if loc_match else None
            title = re.sub(r"\s*[（(][^）)]+[）)]", "", rest).strip()
            end_match = re.search(r"~(\d{1,2}[:.]\d{2})", line)
            end_time = _parse_time(end_match.group(1)) if end_match else None
            if title:
                events.append(LegalEvent(title, current_date, start_time, end_time, location, line, url))
        elif len(line) > 5 and not re.match(r"^[\d\s]+$", line):
            loc_match = re.search(r"[（(]([^）)]+)[）)]", line)
            location = loc_match.group(1) if loc_match else None
            title = re.sub(r"\s*[（(][^）)]+[）)]", "", line).strip()
            if title and len(title) > 3:
                events.append(LegalEvent(title, current_date, None, None, location, line, url))

    return events


def fetch_this_week_events() -> list[LegalEvent]:
    """법률신문에서 이번 주 법조일정을 가져온다."""
    session = requests.Session()

    article_url = _get_latest_calendar_url(session)
    if not article_url:
        raise RuntimeError("법률신문에서 법조일정 기사를 찾을 수 없습니다. (Google News RSS 및 목록 페이지 모두 실패)")

    print(f"기사 URL: {article_url}", file=sys.stderr)
    resp = session.get(article_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    return _parse_article(soup, article_url)
