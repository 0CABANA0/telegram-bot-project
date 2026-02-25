"""
weather_scheduler.py - 통합 스케줄러 (날씨 + 뉴스)
백그라운드에서 상주하며 지정 시간에 날씨/뉴스 알림을 발송합니다.

Railway 배포 시 이 파일이 메인 프로세스로 실행됩니다.

스케줄:
  - 날씨 알림: 매일 WEATHER_SCHEDULE_TIME (기본 07:30)
  - 뉴스 브리핑: 매일 NEWS_SCHEDULE_TIMES (기본 08:00, 18:00)

텔레그램 명령 수신:
  봇이 /위치, /날씨 등의 명령을 실시간으로 수신합니다.

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

from config import TELEGRAM_BOT_TOKEN, WEATHER_SCHEDULE_TIME, NEWS_SCHEDULE_TIMES
from weather_alert import main as send_weather
from news_bot import send_news
from bot_commands import start_command_listener


def weather_job():
    """스케줄 작업: 날씨 알림 발송"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}", flush=True)
    print(f"[{now}] 날씨 알림 작업 시작", flush=True)
    print(f"{'='*50}", flush=True)
    try:
        send_weather()
    except Exception as e:
        print(f"[ERROR] 날씨 작업 실행 중 오류: {e}", flush=True)


def news_job():
    """스케줄 작업: 뉴스 브리핑 발송"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}", flush=True)
    print(f"[{now}] 뉴스 브리핑 작업 시작", flush=True)
    print(f"{'='*50}", flush=True)
    try:
        send_news()
    except Exception as e:
        print(f"[ERROR] 뉴스 작업 실행 중 오류: {e}", flush=True)


def graceful_shutdown(signum, frame):
    """종료 시그널 처리 (Railway 재시작/종료 대응)"""
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 스케줄러 종료 중...", flush=True)
    sys.exit(0)


def main():
    # 종료 시그널 핸들러 등록
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    args = sys.argv[1:]

    # --test: 즉시 1회 실행 후 종료
    if "--test" in args:
        print("[테스트 모드] 날씨 + 뉴스 즉시 1회 실행", flush=True)
        weather_job()
        news_job()
        return

    # === 스케줄 등록 ===

    # 날씨 스케줄
    weather_time = WEATHER_SCHEDULE_TIME
    schedule.every().day.at(weather_time).do(weather_job)
    print(f"  [스케줄] 날씨 알림: 매일 {weather_time}", flush=True)

    # 뉴스 스케줄 (여러 시간 지원)
    for news_time in NEWS_SCHEDULE_TIMES:
        schedule.every().day.at(news_time).do(news_job)
        print(f"  [스케줄] 뉴스 브리핑: 매일 {news_time}", flush=True)

    # === 텔레그램 커맨드 리스너 시작 (별도 스레드) ===
    start_command_listener(TELEGRAM_BOT_TOKEN)

    tz = os.getenv("TZ", "시스템 기본")
    print(f"\n{'='*50}", flush=True)
    print(f"  통합 스케줄러 시작 (날씨 + 뉴스 + 명령수신)", flush=True)
    print(f"  타임존: {tz}", flush=True)
    print(f"  시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"{'='*50}", flush=True)

    # --now: 즉시 1회 실행 후 스케줄 시작
    if "--now" in args:
        print("\n[즉시 실행] 날씨 + 뉴스 첫 발송 시작...", flush=True)
        weather_job()
        news_job()

    # 다음 실행 시간 표시
    jobs = schedule.get_jobs()
    if jobs:
        print(f"\n[등록된 작업: {len(jobs)}개]", flush=True)
        for j in sorted(jobs, key=lambda x: x.next_run):
            print(f"  다음 실행: {j.next_run.strftime('%Y-%m-%d %H:%M:%S')} - {j.job_func.__name__}", flush=True)

    # 스케줄 루프
    while True:
        schedule.run_pending()
        time.sleep(30)  # 30초 간격으로 체크


if __name__ == "__main__":
    main()
