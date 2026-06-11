"""Google Calendar API 연동 — 법조일정 이벤트 등록 및 중복 방지."""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import pathlib

from .scraper import LegalEvent

SCOPES = ["https://www.googleapis.com/auth/calendar"]
KST = timezone(timedelta(hours=9))

# 캘린더 ID (환경변수로 오버라이드 가능, 기본값 primary)
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

# 인증 파일 경로
TOKEN_PATH = pathlib.Path(os.environ.get("GOOGLE_TOKEN_PATH", "token.pickle"))
CREDENTIALS_PATH = pathlib.Path(
    os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
)
SERVICE_ACCOUNT_PATH = pathlib.Path(
    os.environ.get("GOOGLE_SERVICE_ACCOUNT_PATH", "service_account.json")
)


def _build_service():
    """인증 방식 우선순위: 서비스 계정 → OAuth2 토큰 → 브라우저 OAuth2."""
    creds = None

    # 1. 서비스 계정 (GitHub Actions / 서버 환경)
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=SCOPES
        )
        return build("calendar", "v3", credentials=creds)

    if SERVICE_ACCOUNT_PATH.exists():
        creds = service_account.Credentials.from_service_account_file(
            str(SERVICE_ACCOUNT_PATH), scopes=SCOPES
        )
        return build("calendar", "v3", credentials=creds)

    # 2. 저장된 OAuth2 토큰
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "wb") as f:
            pickle.dump(creds, f)

    if creds and creds.valid:
        return build("calendar", "v3", credentials=creds)

    # 3. 브라우저 OAuth2 (최초 로컬 실행 시)
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"인증 파일이 없습니다. {CREDENTIALS_PATH} 또는 "
            "GOOGLE_SERVICE_ACCOUNT_JSON 환경변수를 설정하세요."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)

    return build("calendar", "v3", credentials=creds)


def _event_to_google(event: LegalEvent) -> dict:
    """LegalEvent → Google Calendar API 이벤트 딕셔너리."""
    if event.start_time:
        start_dt = datetime(
            event.date.year, event.date.month, event.date.day,
            int(event.start_time[:2]), int(event.start_time[3:]),
            tzinfo=KST,
        )
        if event.end_time:
            end_dt = datetime(
                event.date.year, event.date.month, event.date.day,
                int(event.end_time[:2]), int(event.end_time[3:]),
                tzinfo=KST,
            )
        else:
            end_dt = start_dt + timedelta(hours=1)

        start = {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Seoul"}
        end = {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Seoul"}
    else:
        # 종일 이벤트
        start = {"date": event.date.isoformat()}
        end = {"date": event.date.isoformat()}

    description_parts = []
    if event.description:
        description_parts.append(event.description)
    description_parts.append(f"\n출처: {event.source_url}")

    body = {
        "summary": event.title,
        "description": "\n".join(description_parts),
        "start": start,
        "end": end,
    }
    if event.location:
        body["location"] = event.location

    return body


def _already_exists(service, calendar_id: str, event: LegalEvent) -> bool:
    """같은 날짜+제목의 이벤트가 이미 있으면 True."""
    time_min = datetime(
        event.date.year, event.date.month, event.date.day, 0, 0, tzinfo=KST
    ).isoformat()
    time_max = datetime(
        event.date.year, event.date.month, event.date.day, 23, 59, tzinfo=KST
    ).isoformat()

    result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            q=event.title,
            singleEvents=True,
        )
        .execute()
    )
    existing = result.get("items", [])
    return any(
        e.get("summary", "") == event.title for e in existing
    )


def sync_events(events: list[LegalEvent]) -> tuple[int, int]:
    """
    이벤트 목록을 Google Calendar에 동기화한다.
    Returns (added, skipped) 카운트.
    """
    if not events:
        print("등록할 일정이 없습니다.")
        return 0, 0

    service = _build_service()
    added = 0
    skipped = 0

    for event in events:
        if _already_exists(service, CALENDAR_ID, event):
            print(f"  [SKIP] {event.date} {event.title}")
            skipped += 1
            continue

        body = _event_to_google(event)
        created = (
            service.events()
            .insert(calendarId=CALENDAR_ID, body=body)
            .execute()
        )
        print(f"  [ADD]  {event.date} {event.title}  → {created.get('htmlLink', '')}")
        added += 1

    return added, skipped
