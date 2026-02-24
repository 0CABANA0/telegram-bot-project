"""
weather_scheduler.py - 매일 오전 8시 날씨 알림 정기 자동실행
백그라운드에서 상주하며 매일 지정 시간에 weather_alert.py를 실행합니다.

Railway 배포 시 이 파일이 메인 프로세스로 실행됩니다.

사용법:
    python weather_scheduler.py          # 포그라운드 실행
    python weather_scheduler.py --now    # 즉시 1회 실행 후 스케줄 시작
    python weather_scheduler.py --test   # 즉시 1회만 실행 후 종료
"""

import os
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

import schedule

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config import SCHEDULE_TIME
from weather_alert import main as send_weather


def job():
    """스케줄 작업: 날씨 알림 발송"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}", flush=True)
    print(f"[{now}] 날씨 알림 작업 시작", flush=True)
    print(f"{'='*50}", flush=True)
    try:
        send_weather()
    except Exception as e:
        print(f"[ERROR] 작업 실행 중 오류: {e}", flush=True)


def graceful_shutdown(signum, frame):
    """종료 시그널 처리 (Railway 재시작/종료 대응)"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 스케줄러 종료 중...", flush=True)
    sys.exit(0)


def main():
    # 종료 시그널 핸들러 등록
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    # 환경변수에서 스케줄 시간 읽기 (기본: 08:00)
    schedule_time = SCHEDULE_TIME

    args = sys.argv[1:]

    # --test: 즉시 1회 실행 후 종료
    if "--test" in args:
        print("[테스트 모드] 즉시 1회 실행", flush=True)
        job()
        return

    # 매일 지정 시간에 스케줄 등록
    schedule.every().day.at(schedule_time).do(job)

    tz = os.getenv("TZ", "시스템 기본")
    print(f"{'='*50}", flush=True)
    print(f"  날씨 알림 스케줄러 시작", flush=True)
    print(f"  실행 시간: 매일 {schedule_time}", flush=True)
    print(f"  타임존: {tz}", flush=True)
    print(f"  시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"{'='*50}", flush=True)

    # --now: 즉시 1회 실행 후 스케줄 시작
    if "--now" in args:
        print("[즉시 실행] 첫 발송 시작...", flush=True)
        job()

    # 다음 실행 시간 표시
    next_run = schedule.next_run()
    if next_run:
        print(f"\n[대기 중] 다음 실행: {next_run.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

    # 스케줄 루프
    while True:
        schedule.run_pending()
        time.sleep(30)  # 30초 간격으로 체크


if __name__ == "__main__":
    main()
