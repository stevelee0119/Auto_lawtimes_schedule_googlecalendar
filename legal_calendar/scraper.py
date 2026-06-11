"""법률신문 '이주의 법조일정' 스크래퍼."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

import requests
from bs4 import BeautifulSoup

CALENDAR_URL = "https://www.lawtimes.co.kr/news/list?kind=A15"
ARTICLE_BASE = "https://www.lawtimes.co.kr"

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
    start_time: Optional[str]   # "HH:MM" or None (all-day)
    end_time: Optional[str]     # "HH:MM" or None
    location: Optional[str]
    description: Optional[str]
    source_url: str


def _parse_time(text: str) -> Optional[str]:
    m = re.search(r"(\d{1,2})[:\.](\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def _parse_date(text: str, reference_year: int) -> Optional[date]:
    """'MM월 DD일' 또는 'MM/DD' 형식 파싱."""
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


def _get_latest_calendar_url(session: requests.Session) -> Optional[str]:
    """목록 페이지에서 가장 최근 '이주의 법조일정' 기사 URL을 반환."""
    resp = session.get(CALENDAR_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # 목록의 첫 번째 기사 링크 탐색
    for a in soup.select("a[href]"):
        href = a["href"]
        if "/news/" in href and re.search(r"\d+", href):
            title_text = a.get_text(strip=True)
            if "법조일정" in title_text or "일정" in title_text:
                return ARTICLE_BASE + href if href.startswith("/") else href

    # 제목 기반 탐색 실패 시 첫 번째 뉴스 링크
    first = soup.select_one("ul.news-list li a, .article-list a, .list-item a")
    if first:
        href = first["href"]
        return ARTICLE_BASE + href if href.startswith("/") else href

    return None


def _parse_article(soup: BeautifulSoup, url: str) -> list[LegalEvent]:
    """기사 본문에서 개별 일정을 파싱한다."""
    events: list[LegalEvent] = []
    today = datetime.now()
    year = today.year

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
        # 날짜 헤더 (예: "6월 16일(월)")
        parsed = _parse_date(line, year)
        if parsed and len(line) < 30:
            current_date = parsed
            continue

        if not current_date:
            continue

        # 시간 + 내용이 있는 줄 (예: "10:00 대법원 전원합의체 공개변론")
        time_match = re.match(r"^(\d{1,2}[:.]\d{2})\s+(.+)", line)
        if time_match:
            start_time = _parse_time(time_match.group(1))
            rest = time_match.group(2)

            # 장소 추출 (괄호 안)
            loc_match = re.search(r"[（(]([^）)]+)[）)]", rest)
            location = loc_match.group(1) if loc_match else None
            title = re.sub(r"\s*[（(][^）)]+[）)]", "", rest).strip()

            # 종료 시간 추출 (~HH:MM)
            end_match = re.search(r"~(\d{1,2}[:.]\d{2})", line)
            end_time = _parse_time(end_match.group(1)) if end_match else None

            if title:
                events.append(
                    LegalEvent(
                        title=title,
                        date=current_date,
                        start_time=start_time,
                        end_time=end_time,
                        location=location,
                        description=line,
                        source_url=url,
                    )
                )
        elif len(line) > 5 and not re.match(r"^[\d\s]+$", line):
            # 시간 없는 일정 항목
            loc_match = re.search(r"[（(]([^）)]+)[）)]", line)
            location = loc_match.group(1) if loc_match else None
            title = re.sub(r"\s*[（(][^）)]+[）)]", "", line).strip()
            if title and len(title) > 3:
                events.append(
                    LegalEvent(
                        title=title,
                        date=current_date,
                        start_time=None,
                        end_time=None,
                        location=location,
                        description=line,
                        source_url=url,
                    )
                )

    return events


def fetch_this_week_events() -> list[LegalEvent]:
    """법률신문에서 이번 주 법조일정을 가져온다."""
    session = requests.Session()

    # 목록 페이지에서 최신 기사 URL 찾기
    article_url = _get_latest_calendar_url(session)
    if not article_url:
        raise RuntimeError("법률신문 목록에서 법조일정 기사를 찾을 수 없습니다.")

    resp = session.get(article_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events = _parse_article(soup, article_url)
    return events
