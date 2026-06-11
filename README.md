# 법률신문 법조일정 → Google Calendar 자동 동기화

법률신문(lawtimes.co.kr)의 **이주의 법조일정** 기사를 매주 자동으로 스크래핑하여 Google Calendar에 등록하는 도구입니다.

## 기능

- 법률신문 이주의 법조일정 기사 자동 수집 (Naver/Daum 검색, RSS, 메인 페이지 등 다단계 폴백)
- Google Calendar API를 통한 일정 자동 등록
- 중복 이벤트 방지 (같은 날짜+제목이면 스킵)
- 시간 정보가 있는 일정은 시간대 포함 등록 (KST), 없는 경우 종일 이벤트로 등록
- GitHub Actions로 **매주 일요일 오후 4시(KST)** 자동 실행

## 실행 결과 예시

```
법률신문 법조일정 수집 중...
총 32개 일정 발견:
  2026-05-26 10:00  서울중앙지법, '...' 28차 공판
  2026-05-27 10:00  서울중앙지법, '...' 10차 공판
  ...

Google Calendar 동기화 중...
  [ADD]  2026-05-26 서울중앙지법, '...' 28차 공판
  ...

완료: 32개 추가, 0개 중복 스킵
```

---

## 설정 방법

### 1. Google Cloud 서비스 계정 생성

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 선택 또는 새 프로젝트 생성
3. **API 및 서비스 → 라이브러리**에서 **Google Calendar API** 활성화
4. **API 및 서비스 → 사용자 인증 정보** → **서비스 계정 만들기**
5. 생성된 서비스 계정 클릭 → **키 탭** → **키 추가 → 새 키 만들기 → JSON**
6. 다운로드된 JSON 파일의 내용 전체를 복사

### 2. Google Calendar 공유 설정

1. [Google Calendar](https://calendar.google.com/) 접속
2. 일정을 등록할 캘린더 → **설정 및 공유**
3. **특정 사용자 또는 그룹과 공유** → 서비스 계정 이메일 추가 (권한: **이벤트 변경**)
4. **캘린더 통합** 섹션에서 **캘린더 ID** 복사

### 3. GitHub Secrets 등록

저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 아래 두 가지를 등록합니다:

| Secret 이름 | 값 |
|---|---|
| `GOOGLE_SERVICE_ACCOUNT_JSON` | 서비스 계정 JSON 파일 내용 전체 |
| `GOOGLE_CALENDAR_ID` | Google Calendar ID (예: `xxx@group.calendar.google.com`) |

> **주의:** JSON 키나 Calendar ID를 코드나 워크플로 파일에 직접 입력하지 마세요. 반드시 GitHub Secrets를 사용하세요.

---

## 로컬 실행

```bash
# 의존성 설치
pip install -r legal_calendar/requirements.txt

# 실제 등록 없이 파싱 결과만 확인 (dry-run)
python -m legal_calendar.main --dry-run

# 실제 Google Calendar 동기화 (서비스 계정 JSON 환경변수 필요)
export GOOGLE_SERVICE_ACCOUNT_JSON='{ ... }'
export GOOGLE_CALENDAR_ID='your-calendar-id@group.calendar.google.com'
python -m legal_calendar.main
```

### 로컬에서 OAuth2 인증으로 실행하기

서비스 계정 대신 개인 Google 계정을 사용하려면:

1. Google Cloud Console에서 **OAuth 2.0 클라이언트 ID** 발급 후 `credentials.json`으로 저장
2. 처음 실행 시 브라우저에서 인증 후 `token.pickle` 자동 생성

```bash
python -m legal_calendar.main --dry-run
```

---

## 프로젝트 구조

```
.
├── .github/
│   └── workflows/
│       └── legal-calendar-sync.yml   # GitHub Actions 워크플로
├── legal_calendar/
│   ├── __init__.py
│   ├── main.py                       # 진입점 (--dry-run 지원)
│   ├── scraper.py                    # 법률신문 스크래퍼
│   ├── calendar_sync.py              # Google Calendar API 연동
│   └── requirements.txt
├── .gitignore
└── README.md
```

## 자동 실행 스케줄

GitHub Actions 워크플로(`.github/workflows/legal-calendar-sync.yml`)가 다음 일정으로 자동 실행됩니다:

- **매주 일요일 오후 4시 (KST)** — 다음 주 법조일정 수집 및 등록
- **수동 실행** — GitHub Actions 탭 → Legal Calendar Sync → Run workflow

## 기사 발견 방식 (폴백 순서)

스크래퍼는 아래 순서로 최신 이주의 법조일정 기사 URL을 탐색합니다:

1. **Naver 뉴스 검색** — 가장 빠르고 정확
2. **Daum 뉴스 검색** — Naver 차단 시 대안
3. **법률신문 RSS** — `allArticle.xml` 등
4. **법률신문 메인 페이지** — 홈에 노출된 기사 링크
5. **Google News RSS** — 최후 폴백
