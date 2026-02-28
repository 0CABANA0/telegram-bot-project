"""
weather_scheduler.py - 통합 스케줄러 (날씨 + 뉴스)
백그라운드에서 상주하며 지정 시간에 날씨/뉴스 알림을 발송합니다.

Railway 배포 시 이 파일이 메인 프로세스로 실행됩니다.

스케줄:
  - 날씨 알림: 매일 WEATHER_SCHEDULE_TIME (기본 07:30)
  - 뉴스 브리핑: 매일 NEWS_SCHEDULE_TIMES (기본 08:00, 18:00)

텔레그램 명령 수신:
  봇이 /날씨, /뉴스, /위치, /설정, /도움 명령을 실시간으로 수신합니다.

기능:
  - 실패 시 자동 재시도 (5분 후, 10분 후)
  - 컨테이너 재시작 시 중복 발송 방지 (당일 발송 이력 추적)
  - 놓친 스케줄 자동 보충 (시작 시 당일 미발송분 확인)

사용법:
    python weather_scheduler.py          # 포그라운드 실행
    python weather_scheduler.py --now    # 즉시 1회 실행 후 스케줄 시작
    python weather_scheduler.py --test   # 즉시 1회만 실행 후 종료
"""

import json
import os
import sys
import time
import signal
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import schedule

# 한국 표준시 (KST, UTC+9)
KST = ZoneInfo("Asia/Seoul")

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from config import TELEGRAM_BOT_TOKEN, WEATHER_SCHEDULE_TIME, NEWS_SCHEDULE_TIMES
from weather_alert import main as send_weather
from news_bot import send_news
from bot_commands import start_command_listener

STATE_FILE = Path(__file__).parent / "scheduler_state.json"

# 재시도 설정: (대기분, 대기분)
RETRY_DELAYS_MIN = [5, 10]


# ──────────────────────────────────────────────
# 상태 추적 (당일 발송 이력)
# ──────────────────────────────────────────────

def _load_state() -> dict:
    """스케줄러 상태 파일 로드"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _save_state(state: dict):
    """스케줄러 상태 파일 저장"""
    STATE_FILE.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _now() -> datetime:
    """한국 시간(KST) 기준 현재 시각을 반환합니다."""
    return datetime.now(KST)


def _mark_done(job_key: str):
    """작업 완료를 기록 (날짜+시간 키)"""
    state = _load_state()
    today = _now().strftime("%Y-%m-%d")
    state[job_key] = today
    state["_last_heartbeat"] = _now().isoformat()
    _save_state(state)


def _was_done_today(job_key: str) -> bool:
    """오늘 이미 완료된 작업인지 확인"""
    state = _load_state()
    today = _now().strftime("%Y-%m-%d")
    return state.get(job_key) == today


# ──────────────────────────────────────────────
# 작업 실행 (재시도 포함)
# ──────────────────────────────────────────────

def weather_job():
    """스케줄 작업: 날씨 알림 발송 (실패 시 자동 재시도)"""
    job_key = "weather"

    if _was_done_today(job_key):
        print(f"[스케줄] 날씨 알림: 오늘 이미 발송됨, 건너뜀", flush=True)
        return

    now_str = _now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}", flush=True)
    print(f"[{now_str}] 날씨 알림 작업 시작", flush=True)
    print(f"{'='*50}", flush=True)

    # 첫 시도
    try:
        result = send_weather()
        if result and result.get("ok"):
            _mark_done(job_key)
            return
        print(f"[날씨] 발송 실패: {result}", flush=True)
    except Exception as e:
        print(f"[ERROR] 날씨 작업 오류: {e}", flush=True)

    # 재시도 (별도 스레드에서 대기 후 실행)
    def _retry():
        for i, delay_min in enumerate(RETRY_DELAYS_MIN, 1):
            if _was_done_today(job_key):
                return
            print(f"[날씨] 재시도 {i}/{len(RETRY_DELAYS_MIN)} ({delay_min}분 후)", flush=True)
            time.sleep(delay_min * 60)
            if _was_done_today(job_key):
                return
            try:
                result = send_weather()
                if result and result.get("ok"):
                    _mark_done(job_key)
                    print(f"[날씨] 재시도 {i} 성공!", flush=True)
                    return
            except Exception as e:
                print(f"[ERROR] 날씨 재시도 {i} 오류: {e}", flush=True)
        print("[날씨] 모든 재시도 실패", flush=True)

    threading.Thread(target=_retry, daemon=True, name="WeatherRetry").start()


def news_job(period_override: str | None = None):
    """스케줄 작업: 뉴스 브리핑 발송 (실패 시 자동 재시도)

    Args:
        period_override: "am" 또는 "pm" (None이면 현재 시각으로 자동 결정)
    """
    now = _now()
    # 뉴스는 오전/오후 구분 (같은 날 여러 번 발송하므로 시간대별 키)
    period = period_override if period_override else ("am" if now.hour < 12 else "pm")
    job_key = f"news_{period}"

    if _was_done_today(job_key):
        print(f"[스케줄] 뉴스 브리핑({period}): 오늘 이미 발송됨, 건너뜀", flush=True)
        return

    now_str = now.strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*50}", flush=True)
    print(f"[{now_str}] 뉴스 브리핑 작업 시작 ({period})", flush=True)
    print(f"{'='*50}", flush=True)

    time_label = "오전" if period == "am" else "오후"

    try:
        result = send_news(time_label=time_label)
        if result and result.get("ok"):
            _mark_done(job_key)
            return
        # total=0 (새 뉴스 없음)도 정상 완료로 처리
        if result and result.get("total", -1) == 0:
            _mark_done(job_key)
            return
        print(f"[뉴스] 발송 실패: {result}", flush=True)
    except Exception as e:
        print(f"[ERROR] 뉴스 작업 오류: {e}", flush=True)

    # 재시도
    def _retry():
        for i, delay_min in enumerate(RETRY_DELAYS_MIN, 1):
            if _was_done_today(job_key):
                return
            print(f"[뉴스] 재시도 {i}/{len(RETRY_DELAYS_MIN)} ({delay_min}분 후)", flush=True)
            time.sleep(delay_min * 60)
            if _was_done_today(job_key):
                return
            try:
                result = send_news(time_label=time_label)
                if result and (result.get("ok") or result.get("total", -1) == 0):
                    _mark_done(job_key)
                    print(f"[뉴스] 재시도 {i} 성공!", flush=True)
                    return
            except Exception as e:
                print(f"[ERROR] 뉴스 재시도 {i} 오류: {e}", flush=True)
        print("[뉴스] 모든 재시도 실패", flush=True)

    threading.Thread(target=_retry, daemon=True, name="NewsRetry").start()


def graceful_shutdown(signum, frame):
    """종료 시그널 처리 (Railway 재시작/종료 대응)"""
    print(f"\n[{_now().strftime('%H:%M:%S')}] 스케줄러 종료 중...", flush=True)
    sys.exit(0)


def _recover_missed_jobs():
    """
    시작 시 놓친 스케줄 보충.
    현재 시각이 예정 시간을 지났는데 오늘 미발송이면 즉시 실행.
    """
    now = _now()
    current_time = now.strftime("%H:%M")

    # 날씨: 예정 시간이 지났고 오늘 미발송이면
    if current_time > WEATHER_SCHEDULE_TIME and not _was_done_today("weather"):
        print(f"[보충] 날씨 알림 미발송 감지 (예정 {WEATHER_SCHEDULE_TIME}), 즉시 발송", flush=True)
        weather_job()

    # 뉴스: 각 예정 시간 확인
    for news_time in NEWS_SCHEDULE_TIMES:
        if current_time > news_time:
            hour = int(news_time.split(":")[0])
            period = "am" if hour < 12 else "pm"
            if not _was_done_today(f"news_{period}"):
                print(f"[보충] 뉴스 브리핑({period}) 미발송 감지 (예정 {news_time}), 즉시 발송", flush=True)
                news_job(period_override=period)


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

    # 날씨 스케줄 (KST 명시 — schedule 라이브러리는 문자열/pytz만 허용)
    weather_time = WEATHER_SCHEDULE_TIME
    schedule.every().day.at(weather_time, tz="Asia/Seoul").do(weather_job)
    print(f"  [스케줄] 날씨 알림: 매일 {weather_time} KST", flush=True)

    # 뉴스 스케줄 (여러 시간 지원, KST 명시)
    for news_time in NEWS_SCHEDULE_TIMES:
        schedule.every().day.at(news_time, tz="Asia/Seoul").do(news_job)
        print(f"  [스케줄] 뉴스 브리핑: 매일 {news_time} KST", flush=True)

    # === 텔레그램 커맨드 리스너 시작 (별도 스레드) ===
    start_command_listener(TELEGRAM_BOT_TOKEN)

    print(f"\n{'='*50}", flush=True)
    print(f"  통합 스케줄러 시작 (날씨 + 뉴스 + 명령수신)", flush=True)
    print(f"  타임존: Asia/Seoul (KST, UTC+9)", flush=True)
    print(f"  시작 시각: {_now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"{'='*50}", flush=True)

    # --now: 즉시 1회 실행 (중복 방지 포함)
    if "--now" in args:
        print("\n[즉시 실행] 미발송분 확인 후 발송...", flush=True)
        _recover_missed_jobs()
    else:
        # --now 없어도 놓친 작업 자동 보충
        _recover_missed_jobs()

    # 다음 실행 시간 표시
    jobs = schedule.get_jobs()
    if jobs:
        print(f"\n[등록된 작업: {len(jobs)}개]", flush=True)
        for j in sorted(jobs, key=lambda x: x.next_run):
            print(f"  다음 실행: {j.next_run.strftime('%Y-%m-%d %H:%M:%S')} - {j.job_func.__name__}", flush=True)

    # 스케줄 루프 (하트비트 포함)
    heartbeat_interval = 3600  # 1시간마다 하트비트
    last_heartbeat = time.time()

    while True:
        schedule.run_pending()

        # 하트비트 로그 (1시간마다)
        if time.time() - last_heartbeat >= heartbeat_interval:
            state = _load_state()
            state["_last_heartbeat"] = _now().isoformat()
            _save_state(state)
            print(f"[하트비트] {_now().strftime('%H:%M')} 스케줄러 정상 동작 중", flush=True)
            last_heartbeat = time.time()

        time.sleep(5)  # 5초 간격으로 체크 (정확한 스케줄 실행)


if __name__ == "__main__":
    main()
