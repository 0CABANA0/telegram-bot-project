"""
bot_commands.py - 텔레그램 봇 커맨드 핸들러
사용자 명령을 수신하여 날씨 위치 설정 등을 처리합니다.

지원 명령 (띄어쓰기/붙여쓰기 모두 인식):
  /날씨        — 현재 설정으로 즉시 날씨 확인
  /뉴스        — 즉시 뉴스 브리핑 발송
  /위치 <도시>  — 날씨 도시 수동 설정 (예: /위치 부산)
  /위치 자동    — IP 기반 자동 위치 감지
  /설정        — 현재 설정 확인
  /도움        — 명령어 도움말
"""

import json
import threading
import time
from datetime import datetime
from pathlib import Path

import requests

from config import (
    TELEGRAM_BOT_TOKEN, CHAT_IDS, WEATHER_SCHEDULE_TIME, NEWS_SCHEDULE_TIMES,
    NEWS_KEYWORDS, NEWS_COUNT_PER_KEYWORD,
    CITY_MAP, CITY_MAP_REV,
)
from telegram_sender import send_message

LOCATION_FILE = Path(__file__).parent / "weather_location.json"


# ──────────────────────────────────────────────
# 위치 설정 저장/로드
# ──────────────────────────────────────────────

def load_location() -> dict:
    """저장된 위치 설정을 로드합니다."""
    if LOCATION_FILE.exists():
        try:
            return json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            pass
    return {"mode": "manual", "city": "Seoul", "city_kr": "서울"}


def save_location(data: dict):
    """위치 설정을 저장합니다."""
    data["updated"] = datetime.now().isoformat()
    LOCATION_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def detect_location_by_ip() -> dict | None:
    """IP 기반으로 현재 위치를 감지합니다."""
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=10)
        resp.raise_for_status()
        info = resp.json()
        return {
            "city": info.get("city", "Seoul"),
            "region": info.get("region", ""),
            "loc": info.get("loc", ""),
        }
    except Exception as e:
        print(f"[위치감지] IP 위치 감지 실패: {e}", flush=True)
        return None


def _reverse_geocode(lat: float, lon: float) -> dict | None:
    """
    좌표 → 주소 상세 변환 (Nominatim 무료 API).
    Returns: {"city": "서울특별시", "district": "마포구", "display": "서울 마포구"}
    """
    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat, "lon": lon,
                "format": "json",
                "zoom": 14,  # 구/동 단위
                "accept-language": "ko",
            },
            headers={"User-Agent": "TelegramWeatherBot/1.0"},
            timeout=10,
        )
        resp.raise_for_status()
        addr = resp.json().get("address", {})

        city = (
            addr.get("city")
            or addr.get("town")
            or addr.get("county")
            or addr.get("state")
            or ""
        )
        # 구 단위
        district = (
            addr.get("city_district")
            or addr.get("suburb")
            or addr.get("borough")
            or addr.get("quarter")
            or ""
        )
        # 동 단위
        dong = (
            addr.get("neighbourhood")
            or addr.get("village")
            or addr.get("town")
            or ""
        )
        # 동 이름이 시/구와 겹치면 제외
        if dong and (dong == city or dong == district):
            dong = ""

        # "서울특별시" → "서울"
        city_short = city.replace("특별시", "").replace("광역시", "").replace("특별자치시", "").replace("특별자치도", "")

        parts = [p for p in [city_short, district, dong] if p]
        display = " ".join(parts)

        return {"city": city, "district": district, "dong": dong, "display": display}
    except Exception:
        return None


# ──────────────────────────────────────────────
# 텔레그램 업데이트 수신
# ──────────────────────────────────────────────

def _clear_webhook(token: str):
    """기존 웹훅/폴링 세션을 정리하여 getUpdates 충돌을 방지합니다."""
    url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    try:
        resp = requests.post(url, json={"drop_pending_updates": False}, timeout=10)
        data = resp.json()
        if data.get("ok"):
            print("[커맨드] 웹훅/이전 폴링 세션 정리 완료", flush=True)
        else:
            print(f"[커맨드] 웹훅 정리 실패: {data.get('description', '')}", flush=True)
    except Exception as e:
        print(f"[커맨드] 웹훅 정리 예외: {e}", flush=True)


def _get_updates(token: str, offset: int = 0, timeout: int = 30) -> list | None:
    """텔레그램 업데이트(메시지+채널포스트)를 가져옵니다. (Long Polling)

    Returns:
        list: 업데이트 목록
        None: 409 Conflict 발생 시 (재초기화 필요 신호)
    """
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {
        "offset": offset,
        "timeout": timeout,
        "allowed_updates": ["message", "channel_post"],
    }
    try:
        resp = requests.get(url, params=params, timeout=timeout + 10)
        data = resp.json()
        if data.get("ok"):
            return data.get("result", [])

        # 409 Conflict: 다른 인스턴스가 동시에 getUpdates 호출 중
        if resp.status_code == 409:
            print("[커맨드] 409 Conflict 감지 — 다른 인스턴스와 충돌", flush=True)
            return None

        print(f"[커맨드] getUpdates 오류: {data.get('description', '')}", flush=True)
    except Exception as e:
        print(f"[커맨드] getUpdates 예외: {e}", flush=True)
    return []


# ──────────────────────────────────────────────
# 명령 처리
# ──────────────────────────────────────────────

def handle_message(token: str, message: dict):
    """수신된 메시지를 분석하고 별도 스레드에서 처리합니다."""
    chat_id = str(message["chat"]["id"])

    # 텔레그램 위치 공유 메시지 처리 (📎 → 위치)
    location = message.get("location")
    if location:
        _run_in_thread(_handle_gps_location, token, chat_id, location)
        return

    text = message.get("text", "").strip()
    if not text.startswith("/"):
        return

    print(f"[커맨드] 수신: {text} (chat_id: {chat_id})", flush=True)

    # 공백 제거한 정규화 명령 (띄어쓰기/붙여쓰기 모두 인식)
    cmd = text.replace(" ", "")

    if cmd.startswith("/위치자동"):
        _run_in_thread(_cmd_auto_location, token, chat_id)
    elif cmd.startswith("/위치"):
        _run_in_thread(_cmd_set_location, token, chat_id, text)
    elif cmd.startswith("/날씨"):
        _run_in_thread(_cmd_weather_now, token, chat_id)
    elif cmd.startswith("/뉴스"):
        _run_in_thread(_cmd_news_now, token, chat_id)
    elif cmd.startswith("/설정"):
        _run_in_thread(_cmd_show_settings, token, chat_id)
    elif cmd.startswith("/도움") or cmd.startswith("/help"):
        _run_in_thread(_cmd_help, token, chat_id)


def _run_in_thread(func, *args):
    """명령 핸들러를 별도 스레드에서 실행 (리스너 블로킹 방지)"""
    t = threading.Thread(target=_safe_run, args=(func, *args), daemon=True)
    t.start()


def _safe_run(func, *args):
    """예외를 잡아서 로그로 출력"""
    try:
        func(*args)
    except Exception as e:
        print(f"[커맨드] 오류 ({func.__name__}): {e}", flush=True)


def _handle_gps_location(token: str, chat_id: str, location: dict):
    """텔레그램 GPS 위치 공유를 처리합니다."""
    lat = location["latitude"]
    lon = location["longitude"]

    # 좌표 → 구/동 단위 변환
    geo = _reverse_geocode(lat, lon)
    display_name = geo["display"] if geo and geo.get("display") else f"{lat:.2f},{lon:.2f}"

    save_location({
        "mode": "gps",
        "city": f"{lat},{lon}",
        "city_kr": display_name,
        "lat": lat,
        "lon": lon,
    })

    reply = (
        f"📍 <b>GPS 위치 저장 완료!</b>\n\n"
        f"위치: {display_name}\n"
        f"좌표: {lat:.4f}, {lon:.4f}\n"
        f"모드: GPS"
    )
    send_message(token, chat_id, reply)


def _cmd_auto_location(token: str, chat_id: str):
    """IP 기반 자동 위치 감지 (구 단위까지)"""
    loc = detect_location_by_ip()
    if not loc:
        send_message(token, chat_id, "❌ 위치 자동 감지에 실패했습니다.\n/위치 <도시> 로 수동 설정해주세요.")
        return

    city = loc["city"]
    city_kr = CITY_MAP_REV.get(city.lower(), city)

    save_location({
        "mode": "auto",
        "city": city,
        "city_kr": city_kr,
    })

    reply = (
        f"📍 <b>자동 위치 감지 완료!</b>\n\n"
        f"위치: {city_kr}\n"
        f"모드: 자동 (IP 기반)"
    )
    send_message(token, chat_id, reply)


def _cmd_set_location(token: str, chat_id: str, text: str):
    """수동 위치 설정: /위치 <도시>"""
    # 공백 유무 모두 지원: "/위치 부산", "/위치부산"
    parts = text.split(maxsplit=1)
    if len(parts) >= 2:
        arg = parts[1].strip()
    else:
        # "/위치부산" 처럼 붙여쓴 경우 → "/위치" 접두사 제거
        arg = text.lstrip("/").replace("위치", "", 1).strip()

    # "자동" / "auto" → 자동 감지로 전환
    if arg in ("자동", "auto"):
        _cmd_auto_location(token, chat_id)
        return

    if not arg:
        cities = "  ".join(list(CITY_MAP.keys())[:10])
        reply = (
            "📍 <b>위치 설정 방법</b>\n\n"
            "1️⃣ <b>수동 설정</b>\n"
            "   /위치 부산\n"
            "   /위치 Seoul\n\n"
            "2️⃣ <b>자동 감지</b>\n"
            "   /위치 자동\n\n"
            f"🏙️ 주요 도시: {cities} ..."
        )
        send_message(token, chat_id, reply)
        return

    city_input = arg

    # 한글 도시명 확인
    if city_input in CITY_MAP:
        city_en = CITY_MAP[city_input]
        city_kr = city_input
    else:
        city_en = city_input
        city_kr = CITY_MAP_REV.get(city_input.lower(), city_input)

    save_location({"mode": "manual", "city": city_en, "city_kr": city_kr})

    reply = (
        f"✅ <b>날씨 위치가 변경되었습니다!</b>\n\n"
        f"도시: {city_kr} ({city_en})\n"
        f"모드: 수동 설정"
    )
    send_message(token, chat_id, reply)


def _cmd_weather_now(token: str, chat_id: str):
    """즉시 날씨 확인: /날씨"""
    from weather_alert import load_location as wa_load, get_weather_message

    city, city_kr = wa_load()
    print(f"[커맨드] /날씨 처리: {city_kr}({city})", flush=True)
    try:
        msg = get_weather_message(city, city_kr)
        result = send_message(token, chat_id, msg)
        print(f"[커맨드] /날씨 발송: {'성공' if result.get('ok') else '실패'}", flush=True)
    except Exception as e:
        print(f"[커맨드] /날씨 오류: {e}", flush=True)
        send_message(token, chat_id, f"❌ 날씨 조회 실패: {e}")


def _cmd_news_now(token: str, chat_id: str):
    """즉시 뉴스 발송: /뉴스"""
    from news_bot import send_news

    print(f"[커맨드] /뉴스 처리 시작", flush=True)
    send_message(token, chat_id, "📰 뉴스 수집 중... 잠시만 기다려주세요.")
    try:
        result = send_news()
        if result.get("ok") and result.get("total", 0) > 0:
            print(f"[커맨드] /뉴스 발송: {result['total']}건 완료", flush=True)
        elif result.get("total", 0) == 0:
            send_message(token, chat_id, "📭 새로운 뉴스가 없습니다.")
            print("[커맨드] /뉴스: 새 뉴스 없음", flush=True)
        else:
            send_message(token, chat_id, f"❌ 뉴스 발송 실패: {result.get('message', '')}")
            print(f"[커맨드] /뉴스 실패: {result.get('message', '')}", flush=True)
    except Exception as e:
        print(f"[커맨드] /뉴스 오류: {e}", flush=True)
        send_message(token, chat_id, f"❌ 뉴스 조회 실패: {e}")


def _cmd_show_settings(token: str, chat_id: str):
    """현재 설정 확인: /설정"""
    loc = load_location()
    mode_map = {"manual": "수동 설정", "auto": "자동 (IP)", "gps": "GPS 위치"}
    mode_str = mode_map.get(loc.get("mode", "manual"), "수동 설정")

    news_times = ", ".join(NEWS_SCHEDULE_TIMES)

    reply = (
        f"⚙️ <b>현재 설정</b>\n\n"
        f"📍 위치: {loc.get('city_kr', '서울')} ({loc.get('city', 'Seoul')})\n"
        f"🔧 모드: {mode_str}\n"
        f"🌤️ 날씨: 매일 {WEATHER_SCHEDULE_TIME}\n"
        f"📰 뉴스: 매일 {news_times}\n\n"
        f"💡 /도움 — 전체 명령 목록"
    )
    send_message(token, chat_id, reply)


def _cmd_help(token: str, chat_id: str):
    """도움말: /도움"""
    news_times = ", ".join(NEWS_SCHEDULE_TIMES)

    kw_count = len(NEWS_KEYWORDS)
    kw_list = ", ".join(NEWS_KEYWORDS)

    reply = (
        "🤖 <b>텔레그램 봇 명령어</b>\n\n"
        "🌤️ <b>날씨</b>\n"
        f"  /날씨 — 현재 날씨 즉시 확인 (매일 {WEATHER_SCHEDULE_TIME} 자동)\n\n"
        "📰 <b>뉴스</b>\n"
        f"  /뉴스 — 뉴스 브리핑 즉시 발송 (매일 {news_times} 자동)\n"
        f"  • 키워드 {kw_count}개, 키워드당 {NEWS_COUNT_PER_KEYWORD}건\n"
        f"  • 추적 키워드: {kw_list}\n"
        "  • 중복 기사 자동 필터링\n\n"
        "📍 <b>위치 설정</b>\n"
        "  /위치 서울 — 도시 직접 설정 (한글/영문)\n"
        "  /위치 자동 — IP 기반 자동 감지\n"
        "  • 예시: /위치 부산, /위치 대전, /위치 제주\n"
        f"  • 지원 도시: {', '.join(list(CITY_MAP.keys()))}\n\n"
        "⚙️ <b>설정</b>\n"
        "  /설정 — 현재 설정 확인\n"
        "  /도움 — 이 도움말"
    )
    send_message(token, chat_id, reply)


# ──────────────────────────────────────────────
# 커맨드 리스너 (별도 스레드)
# ──────────────────────────────────────────────

def start_command_listener(token: str | None = None):
    """
    별도 스레드에서 텔레그램 명령 수신을 시작합니다.
    Long Polling으로 메시지를 실시간 수신합니다.
    시작 시 deleteWebhook으로 이전 세션을 정리하고,
    409 Conflict 발생 시 자동 재초기화합니다.
    """
    if token is None:
        token = TELEGRAM_BOT_TOKEN

    if not token:
        print("[커맨드] BOT_TOKEN이 없어 커맨드 리스너를 시작할 수 없습니다.", flush=True)
        return None

    def listener():
        # 시작 시 이전 폴링 세션 정리 (충돌 방지)
        _clear_webhook(token)

        print("[커맨드] 텔레그램 명령 수신 대기 중...", flush=True)
        print(
            "[커맨드] 지원 명령: /날씨, /뉴스, /위치, /위치 자동, /설정, /도움",
            flush=True,
        )
        offset = 0
        conflict_count = 0

        while True:
            try:
                updates = _get_updates(token, offset=offset, timeout=30)

                # 409 Conflict → 백오프 후 재초기화
                if updates is None:
                    conflict_count += 1
                    backoff = min(conflict_count * 5, 30)
                    print(f"[커맨드] 충돌 복구 대기 {backoff}초 (#{conflict_count})", flush=True)
                    time.sleep(backoff)
                    _clear_webhook(token)
                    continue

                conflict_count = 0  # 정상 응답 시 카운터 초기화

                for update in updates:
                    offset = update["update_id"] + 1

                    # 개인/그룹 메시지
                    message = update.get("message")
                    # 채널 포스트
                    if not message:
                        message = update.get("channel_post")
                    if message:
                        handle_message(token, message)
            except Exception as e:
                print(f"[커맨드] 리스너 오류: {e}", flush=True)
                time.sleep(5)

    thread = threading.Thread(target=listener, daemon=True, name="CommandListener")
    thread.start()
    return thread
