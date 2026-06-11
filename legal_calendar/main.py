"""법률신문 이주의 법조일정 → Google Calendar 자동 동기화 진입점."""

import argparse
import sys

from .scraper import fetch_this_week_events
from .calendar_sync import sync_events


def main():
    parser = argparse.ArgumentParser(
        description="법률신문 이주의 법조일정을 Google Calendar에 자동 등록합니다."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 캘린더 등록 없이 파싱된 일정만 출력합니다.",
    )
    args = parser.parse_args()

    print("법률신문 법조일정 수집 중...")
    try:
        events = fetch_this_week_events()
    except Exception as e:
        print(f"[ERROR] 스크래핑 실패: {e}", file=sys.stderr)
        sys.exit(1)

    if not events:
        print("이번 주 법조일정을 찾지 못했습니다.")
        sys.exit(0)

    print(f"총 {len(events)}개 일정 발견:")
    for ev in events:
        time_str = f" {ev.start_time}" if ev.start_time else ""
        loc_str = f" ({ev.location})" if ev.location else ""
        print(f"  {ev.date}{time_str}  {ev.title}{loc_str}")

    if args.dry_run:
        print("\n[dry-run] 캘린더 등록을 건너뜁니다.")
        return

    print("\nGoogle Calendar 동기화 중...")
    try:
        added, skipped = sync_events(events)
    except Exception as e:
        print(f"[ERROR] 캘린더 동기화 실패: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n완료: {added}개 추가, {skipped}개 중복 스킵")


if __name__ == "__main__":
    main()
