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

# 네이버 뉴스 검색 - 법률신문 이번주 법조 일정 (최신순)
NAVER_SEARCH_URL = (
    "https://search.naver.com/search.naver?where=news"
    "&query=%EC%9D%B4%EB%B2%88%EC%A3%BC+%EB%B2%95%EC%A1%B0+%EC%9D%BC%EC%A0%95+%EB%B2%95%EB%A5%A0%EC%8B%A0%EB%AC%B8"
    "&sort=1&nso=so:dd,p:1m"
)

# 법률신문 RSS 후보
RSS_CANDIDATES = [
    "https://www.lawtimes.co.kr/rss/allArticle.xml",
    "https://www.lawtimes.co.kr/rss/index.xml",
    "https://www.lawtimes.co.kr/news/rss",
    "https://www.lawtimes.co.kr/rss/",
]


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
    # "오전/오후 N시" or "오전/오후 N시 M분"
    m = re.search(r"(오전|오후)\s*(\d{1,2})시(?:\s*(\d{1,2})분)?", text)
    if m:
        h = int(m.group(2))
        minute = int(m.group(3)) if m.group(3) else 0
        if m.group(1) == "오후" and h != 12:
            h += 12
        return f"{h:02d}:{minute:02d}"
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


def _is_lawtimes_article_url(href: str) -> bool:
    return bool(
        href
        and "lawtimes.co.kr" in href
        and re.search(r"(idxno=\d+|/\d{4,})", href)
    )


def _try_naver_search(session: requests.Session) -> Optional[str]:
    """네이버 뉴스 검색으로 최신 '이번주 법조 일정' URL을 탐색."""
    naver_headers = {**HEADERS, "Referer": "https://www.naver.com/"}
    try:
        resp = session.get(NAVER_SEARCH_URL, headers=naver_headers, timeout=15)
        print(f"[DEBUG] Naver 검색: HTTP {resp.status_code}", file=sys.stderr)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if _is_lawtimes_article_url(href):
                title = a.get_text(strip=True)
                print(f"[DEBUG] Naver 발견: {href} ({title[:30]})", file=sys.stderr)
                return href

        # data-url 속성도 확인
        for tag in soup.find_all(attrs={"data-url": True}):
            href = tag["data-url"]
            if _is_lawtimes_article_url(href):
                print(f"[DEBUG] Naver data-url 발견: {href}", file=sys.stderr)
                return href

        print("[DEBUG] Naver 결과에 lawtimes.co.kr 링크 없음", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] Naver 검색 실패: {e}", file=sys.stderr)
    return None


def _try_site_rss(session: requests.Session) -> Optional[str]:
    """법률신문 자체 RSS에서 최신 기사 URL 탐색."""
    for rss_url in RSS_CANDIDATES:
        try:
            resp = session.get(rss_url, headers=HEADERS, timeout=10)
            print(f"[DEBUG] RSS {rss_url}: HTTP {resp.status_code}", file=sys.stderr)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title_elem = item.find("title")
                title = ""
                if title_elem is not None:
                    title = (title_elem.text or "").strip()
                    # ET quirk: link URL sometimes in title.tail for RSS 2.0
                    if title_elem.tail and title_elem.tail.strip():
                        link_candidate = title_elem.tail.strip()
                        if "lawtimes.co.kr" in link_candidate and "이번주" in title:
                            print(f"[DEBUG] RSS tail 발견: {link_candidate}", file=sys.stderr)
                            return link_candidate

                if "이번주" not in title:
                    continue

                link_elem = item.find("link")
                link = (link_elem.text or "").strip() if link_elem is not None else ""
                if not link:
                    guid_elem = item.find("guid")
                    link = (guid_elem.text or "").strip() if guid_elem is not None else ""

                if "lawtimes.co.kr" in link:
                    print(f"[DEBUG] RSS 발견: {link}", file=sys.stderr)
                    return link
        except Exception as e:
            print(f"[DEBUG] RSS 실패 {rss_url}: {e}", file=sys.stderr)
    return None


def _try_main_page(session: requests.Session) -> Optional[str]:
    """메인 페이지에서 직접 법조일정 링크 탐색 (쿠키 초기화 겸용)."""
    try:
        resp = session.get(ARTICLE_BASE + "/", headers=HEADERS, timeout=10)
        print(f"[DEBUG] 메인 페이지: HTTP {resp.status_code}", file=sys.stderr)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)
            if _is_lawtimes_article_url(href) and "이번주" in title:
                full = ARTICLE_BASE + href if href.startswith("/") else href
                print(f"[DEBUG] 메인 페이지 발견: {full}", file=sys.stderr)
                return full
    except Exception as e:
        print(f"[DEBUG] 메인 페이지 실패: {e}", file=sys.stderr)
    return None


def _try_google_news_rss(session: requests.Session) -> Optional[str]:
    """Google News RSS에서 최신 기사 URL 탐색."""
    rss_url = (
        "https://news.google.com/rss/search"
        "?q=%EC%9D%B4%EB%B2%88%EC%A3%BC+%EB%B2%95%EC%A1%B0+%EC%9D%BC%EC%A0%95"
        "+site%3Alawtimes.co.kr&hl=ko&gl=KR&ceid=KR%3Ako"
    )
    try:
        resp = session.get(rss_url, timeout=10)
        print(
            f"[DEBUG] Google RSS: HTTP {resp.status_code}, {len(resp.content)}bytes",
            file=sys.stderr,
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.content, "html.parser")
        items = soup.find_all("item")
        print(f"[DEBUG] Google RSS 항목: {len(items)}개", file=sys.stderr)

        for item in items:
            source = item.find("source")
            source_url = source.get("url", "") if source else ""
            if "lawtimes.co.kr" not in source_url:
                continue

            # link 추출 (html.parser는 <link>를 다르게 파싱)
            link = None
            raw = str(item)
            m = re.search(r"<link[^>]*>([^<]+)</link>", raw)
            if m:
                link = m.group(1).strip()
            if not link:
                guid = item.find("guid")
                link = guid.get_text().strip() if guid else None

            if not link:
                continue

            print(f"[DEBUG] Google RSS 링크: {link[:80]}", file=sys.stderr)

            if "lawtimes.co.kr" in link:
                return link

            try:
                r = session.get(link, timeout=10, allow_redirects=True)
                print(f"[DEBUG] Google RSS 리다이렉트: {r.url}", file=sys.stderr)
                if "lawtimes.co.kr" in r.url:
                    return r.url
            except Exception as e:
                print(f"[DEBUG] 리다이렉트 실패: {e}", file=sys.stderr)

    except Exception as e:
        print(f"[DEBUG] Google RSS 실패: {e}", file=sys.stderr)
    return None


def _get_latest_calendar_url(session: requests.Session) -> Optional[str]:
    """최신 '이번주 법조 일정' 기사 URL 반환."""
    print("[DEBUG] 1단계: Naver 뉴스 검색", file=sys.stderr)
    url = _try_naver_search(session)
    if url:
        return url

    print("[DEBUG] 2단계: 법률신문 RSS", file=sys.stderr)
    url = _try_site_rss(session)
    if url:
        return url

    print("[DEBUG] 3단계: 메인 페이지", file=sys.stderr)
    url = _try_main_page(session)
    if url:
        return url

    print("[DEBUG] 4단계: Google News RSS", file=sys.stderr)
    url = _try_google_news_rss(session)
    if url:
        return url

    return None


def _parse_article(soup: BeautifulSoup, url: str) -> list[LegalEvent]:
    events: list[LegalEvent] = []
    year = datetime.now().year

    # Try progressively broader selectors
    body = soup.select_one(
        ".article-body, .news-body, #article-body, .content-body,"
        " #news-view-text, .view-content, #viewContent, .article_body,"
        " .article-view-content, #articleBodyContents, .news_view,"
        " div[class*='article'], div[class*='content'], div[id*='article']"
    )
    if not body:
        body = soup.find("div", {"class": re.compile(r"(article|content|body|view)", re.I)})
    if not body:
        body = soup.body

    # Debug: show which element was found
    if body and body.name:
        cls = body.get("class", [])
        bid = body.get("id", "")
        print(f"[DEBUG] 본문 요소: <{body.name} class='{' '.join(cls)}' id='{bid}'>", file=sys.stderr)

    text = body.get_text(separator="\n") if body else ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    print(f"[DEBUG] 본문 줄 수: {len(lines)}", file=sys.stderr)
    # Show first 20 non-empty lines for diagnosis
    for i, ln in enumerate(lines[:20]):
        print(f"[DEBUG] L{i:02d}: {ln[:80]}", file=sys.stderr)

    current_date: Optional[date] = None

    for line in lines:
        parsed = _parse_date(line, year)
        if parsed and len(line) < 30:
            current_date = parsed
            continue
        if not current_date:
            continue

        # Match "HH:MM event" OR "오전/오후 N시(M분) event"
        time_match = re.match(r"^(\d{1,2}[:.]\d{2})\s+(.+)", line)
        korean_time = re.match(r"^((?:오전|오후)\s*\d{1,2}시(?:\s*\d{1,2}분)?)\s+(.+)", line)
        if not time_match and korean_time:
            time_match = korean_time
        if time_match:
            start_time = _parse_time(time_match.group(1))
            rest = time_match.group(2)
            loc_match = re.search(r"[（(]([^）)]+)[）)]", rest)
            location = loc_match.group(1) if loc_match else None
            title = re.sub(r"\s*[（(][^）)]+[）)]", "", rest).strip()
            end_match = re.search(r"~(\d{1,2}[:.]\d{2})", line)
            end_time = _parse_time(end_match.group(1)) if end_match else None
            if title:
                events.append(
                    LegalEvent(title, current_date, start_time, end_time, location, line, url)
                )
        elif len(line) > 5 and not re.match(r"^[\d\s]+$", line):
            loc_match = re.search(r"[（(]([^）)]+)[）)]", line)
            location = loc_match.group(1) if loc_match else None
            title = re.sub(r"\s*[（(][^）)]+[）)]", "", line).strip()
            if title and len(title) > 3:
                events.append(
                    LegalEvent(title, current_date, None, None, location, line, url)
                )

    print(f"[DEBUG] 파싱 결과: {len(events)}개 일정", file=sys.stderr)
    return events


def fetch_this_week_events() -> list[LegalEvent]:
    """법률신문에서 이번 주 법조일정을 가져온다."""
    session = requests.Session()

    article_url = _get_latest_calendar_url(session)
    if not article_url:
        raise RuntimeError(
            "법률신문에서 법조일정 기사를 찾을 수 없습니다.\n"
            "(Naver 검색, 사이트 RSS, 메인 페이지, Google News RSS 모두 실패)"
        )

    print(f"[INFO] 기사 URL: {article_url}", file=sys.stderr)
    resp = session.get(article_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_article(soup, article_url)
