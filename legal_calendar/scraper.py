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
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
    "Referer": "https://www.lawtimes.co.kr/",
}

# 기사 제목 키워드 (RSS/검색 결과 필터용)
SCHEDULE_KEYWORDS = ["법조일정", "이번주", "이주의", "법조 일정"]

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
    # q=이번주 법조 일정 법률신문, 최신순
    url = (
        "https://search.naver.com/search.naver?where=news"
        "&query=%EC%9D%B4%EB%B2%88%EC%A3%BC+%EB%B2%95%EC%A1%B0+%EC%9D%BC%EC%A0%95+%EB%B2%95%EB%A5%A0%EC%8B%A0%EB%AC%B8"
        "&sort=1&nso=so:dd,p:1m"
    )
    headers = {
        **HEADERS,
        "Referer": "https://www.naver.com/",
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
    }
    try:
        resp = session.get(url, headers=headers, timeout=15)
        print(f"[DEBUG] Naver 검색: HTTP {resp.status_code}", file=sys.stderr)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        # Check direct href and various data attributes
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if _is_lawtimes_article_url(href):
                title = a.get_text(strip=True)
                print(f"[DEBUG] Naver href 발견: {href} ({title[:40]})", file=sys.stderr)
                return href

        for attr in ("data-url", "data-link", "data-news-url"):
            for tag in soup.find_all(attrs={attr: True}):
                href = tag[attr]
                if _is_lawtimes_article_url(href):
                    print(f"[DEBUG] Naver {attr} 발견: {href}", file=sys.stderr)
                    return href

        print("[DEBUG] Naver 결과에 lawtimes.co.kr 링크 없음", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] Naver 검색 실패: {e}", file=sys.stderr)
    return None


def _try_daum_search(session: requests.Session) -> Optional[str]:
    """Daum 뉴스 검색으로 최신 '이번주 법조 일정' URL을 탐색."""
    # q=이번주 법조일정 법률신문
    url = (
        "https://search.daum.net/search"
        "?w=news"
        "&q=%EC%9D%B4%EB%B2%88%EC%A3%BC+%EB%B2%95%EC%A1%B0%EC%9D%BC%EC%A0%95+%EB%B2%95%EB%A5%A0%EC%8B%A0%EB%AC%B8"
        "&sort=recency"
    )
    headers = {**HEADERS, "Referer": "https://www.daum.net/"}
    try:
        resp = session.get(url, headers=headers, timeout=15)
        print(f"[DEBUG] Daum 검색: HTTP {resp.status_code}", file=sys.stderr)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if _is_lawtimes_article_url(href):
                title = a.get_text(strip=True)
                print(f"[DEBUG] Daum href 발견: {href} ({title[:40]})", file=sys.stderr)
                return href

        for attr in ("data-url", "data-link"):
            for tag in soup.find_all(attrs={attr: True}):
                href = tag[attr]
                if _is_lawtimes_article_url(href):
                    print(f"[DEBUG] Daum {attr} 발견: {href}", file=sys.stderr)
                    return href

        print("[DEBUG] Daum 결과에 lawtimes.co.kr 링크 없음", file=sys.stderr)
    except Exception as e:
        print(f"[DEBUG] Daum 검색 실패: {e}", file=sys.stderr)
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
            items = list(root.iter("item"))
            print(f"[DEBUG] RSS 항목 수: {len(items)}", file=sys.stderr)

            # Log first 10 titles for diagnosis
            for i, item in enumerate(items[:10]):
                t = item.find("title")
                t_text = (t.text or "").strip() if t is not None else "(no title)"
                print(f"[DEBUG] RSS 제목[{i}]: {t_text[:70]}", file=sys.stderr)

            for item in items:
                title_elem = item.find("title")
                title = (title_elem.text or "").strip() if title_elem is not None else ""

                if not any(kw in title for kw in SCHEDULE_KEYWORDS):
                    continue

                # Extract link from <link> or <guid>
                link = ""
                link_elem = item.find("link")
                if link_elem is not None:
                    link = (link_elem.text or "").strip()
                    # RSS 2.0: <link> is sometimes empty text with tail
                    if not link and link_elem.tail:
                        link = link_elem.tail.strip()
                if not link:
                    guid_elem = item.find("guid")
                    if guid_elem is not None:
                        link = (guid_elem.text or "").strip()

                print(f"[DEBUG] RSS 일치: '{title[:50]}' → {link[:60]}", file=sys.stderr)
                if link and "lawtimes.co.kr" in link:
                    return link
        except Exception as e:
            print(f"[DEBUG] RSS 실패 {rss_url}: {e}", file=sys.stderr)
    return None


def _try_main_page(session: requests.Session) -> Optional[str]:
    """메인 페이지에서 직접 법조일정 링크 탐색."""
    try:
        resp = session.get(ARTICLE_BASE + "/", headers=HEADERS, timeout=10)
        print(f"[DEBUG] 메인 페이지: HTTP {resp.status_code}", file=sys.stderr)
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)
            if _is_lawtimes_article_url(href) and any(kw in title for kw in SCHEDULE_KEYWORDS):
                full = ARTICLE_BASE + href if href.startswith("/") else href
                print(f"[DEBUG] 메인 페이지 발견: {full} ({title[:30]})", file=sys.stderr)
                return full
    except Exception as e:
        print(f"[DEBUG] 메인 페이지 실패: {e}", file=sys.stderr)
    return None


def _try_google_news_rss(session: requests.Session) -> Optional[str]:
    """Google News RSS에서 최신 기사 URL 탐색."""
    rss_url = (
        "https://news.google.com/rss/search"
        "?q=%EB%B2%95%EC%A1%B0%EC%9D%BC%EC%A0%95"
        "+site%3Alawtimes.co.kr&hl=ko&gl=KR&ceid=KR%3Ako"
    )
    try:
        resp = session.get(rss_url, timeout=15)
        print(
            f"[DEBUG] Google RSS: HTTP {resp.status_code}, {len(resp.content)}bytes",
            file=sys.stderr,
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.content, "html.parser")
        items = soup.find_all("item")
        print(f"[DEBUG] Google RSS 항목: {len(items)}개", file=sys.stderr)

        for item in items[:5]:
            # Title check
            title_tag = item.find("title")
            item_title = title_tag.get_text(strip=True) if title_tag else ""
            print(f"[DEBUG] Google RSS 제목: {item_title[:60]}", file=sys.stderr)

            source = item.find("source")
            source_url = source.get("url", "") if source else ""

            # Extract link
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

            # Prefix CBMi... encoded Google article IDs
            if not link.startswith("http"):
                link = f"https://news.google.com/articles/{link}"

            print(f"[DEBUG] Google RSS 링크: {link[:80]}", file=sys.stderr)

            if "lawtimes.co.kr" in link:
                return link

            # Follow Google redirect → actual article URL
            try:
                r = session.get(link, timeout=10, allow_redirects=True)
                print(f"[DEBUG] Google RSS 최종 URL: {r.url[:80]}", file=sys.stderr)
                if "lawtimes.co.kr" in r.url:
                    return r.url
            except Exception as e:
                print(f"[DEBUG] 리다이렉트 실패: {e}", file=sys.stderr)

    except Exception as e:
        print(f"[DEBUG] Google RSS 실패: {e}", file=sys.stderr)
    return None


def _get_latest_calendar_url(session: requests.Session) -> Optional[str]:
    """최신 '이번주 법조 일정' 기사 URL 반환 (4단계 폴백)."""
    print("[DEBUG] 1단계: Naver 뉴스 검색", file=sys.stderr)
    url = _try_naver_search(session)
    if url:
        return url

    print("[DEBUG] 2단계: Daum 뉴스 검색", file=sys.stderr)
    url = _try_daum_search(session)
    if url:
        return url

    print("[DEBUG] 3단계: 법률신문 RSS", file=sys.stderr)
    url = _try_site_rss(session)
    if url:
        return url

    print("[DEBUG] 4단계: 메인 페이지", file=sys.stderr)
    url = _try_main_page(session)
    if url:
        return url

    print("[DEBUG] 5단계: Google News RSS", file=sys.stderr)
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

    if body and body.name:
        cls = body.get("class", [])
        bid = body.get("id", "")
        print(f"[DEBUG] 본문 요소: <{body.name} class='{' '.join(cls)}' id='{bid}'>", file=sys.stderr)

    text = body.get_text(separator="\n") if body else ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    print(f"[DEBUG] 본문 줄 수: {len(lines)}", file=sys.stderr)
    for i, ln in enumerate(lines[:20]):
        print(f"[DEBUG] L{i:02d}: {ln[:80]}", file=sys.stderr)

    current_date: Optional[date] = None

    for line in lines:
        parsed = _parse_date(line, year)
        if parsed and len(line) < 40:
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
            "(Naver, Daum, RSS, 메인 페이지, Google News RSS 모두 실패)"
        )

    print(f"[INFO] 기사 URL: {article_url}", file=sys.stderr)
    resp = session.get(article_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_article(soup, article_url)
