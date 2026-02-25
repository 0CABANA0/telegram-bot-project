"""
weather_alert.py - 매일 오전 날씨 알림 발송 스크립트
Open-Meteo(기본) + wttr.in(fallback) 이중 API로 안정적 날씨 조회.
위치 설정: weather_location.json (텔레그램 /위치 명령으로 변경 가능)
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

import requests
from config import TELEGRAM_BOT_TOKEN, CHAT_IDS, WEATHER_CITY, WEATHER_CITY_KR, CITY_MAP
from telegram_sender import send_message

LOCATION_FILE = Path(__file__).parent / "weather_location.json"

# WMO 날씨 코드 → 설명
_WMO = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with hail",
}


# ──────────────────────────────────────────────
# 위치 로드
# ──────────────────────────────────────────────

def load_location() -> tuple[str, str]:
    """
    위치 설정 로드 → (city_query, city_kr)
    weather_location.json이 있으면 그 값을, 없으면 config 기본값 사용.
    """
    if LOCATION_FILE.exists():
        try:
            data = json.loads(LOCATION_FILE.read_text(encoding="utf-8"))
            mode = data.get("mode", "manual")

            if mode == "auto":
                loc = _detect_by_ip()
                if loc:
                    city = loc["city"]
                    city_kr = next(
                        (kr for kr, en in CITY_MAP.items()
                         if en.lower() == city.lower()),
                        city,
                    )
                    return city, city_kr

            if mode == "gps":
                lat = data.get("lat")
                lon = data.get("lon")
                if lat and lon:
                    return f"{lat},{lon}", data.get("city_kr", f"{lat},{lon}")

            return data.get("city", WEATHER_CITY), data.get("city_kr", WEATHER_CITY_KR)
        except Exception:
            pass
    return WEATHER_CITY, WEATHER_CITY_KR


def _detect_by_ip() -> dict | None:
    """IP 기반 위치 감지"""
    try:
        resp = requests.get("https://ipinfo.io/json", timeout=10)
        resp.raise_for_status()
        info = resp.json()
        return {"city": info.get("city", "Seoul"), "region": info.get("region", "")}
    except Exception:
        return None


# ──────────────────────────────────────────────
# 날씨 API: Open-Meteo (기본, 빠름, 무료)
# ──────────────────────────────────────────────

def _geocode_city(city: str) -> tuple[float, float, str]:
    """도시명 → (위도, 경도, 표시이름). 좌표 형식이면 그대로 파싱."""
    # "37.5,126.9" 형식 (GPS 모드)
    if "," in city:
        parts = city.split(",")
        try:
            return float(parts[0]), float(parts[1]), city
        except ValueError:
            pass

    resp = requests.get(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1, "language": "ko"},
        timeout=10,
    )
    resp.raise_for_status()
    results = resp.json().get("results")
    if not results:
        raise ValueError(f"도시 '{city}'를 찾을 수 없습니다")
    loc = results[0]
    return loc["latitude"], loc["longitude"], loc.get("name", city)


def get_weather_openmeteo(city: str) -> dict:
    """
    Open-Meteo API에서 날씨를 가져옵니다.
    무료, API 키 불필요, 응답 빠름 (~1초).
    """
    lat, lon, _ = _geocode_city(city)

    resp = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                       "weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,sunrise,sunset",
            "hourly": "precipitation_probability",
            "timezone": "Asia/Seoul",
            "forecast_days": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def format_weather_openmeteo(data: dict, city_kr: str) -> str:
    """Open-Meteo 데이터를 텔레그램 HTML 메시지로 포맷합니다."""
    cur = data["current"]
    daily = data["daily"]
    hourly_precip = data.get("hourly", {}).get("precipitation_probability", [])

    temp = round(cur["temperature_2m"])
    feels = round(cur["apparent_temperature"])
    humidity = cur["relative_humidity_2m"]
    wind = round(cur["wind_speed_10m"])
    code = cur.get("weather_code", 0)
    desc = _WMO.get(code, "Unknown")

    max_temp = round(daily["temperature_2m_max"][0])
    min_temp = round(daily["temperature_2m_min"][0])
    sunrise = daily["sunrise"][0].split("T")[1]  # "07:05"
    sunset = daily["sunset"][0].split("T")[1]

    # 시간대별 강수확률 (오전9시/오후15시/저녁21시)
    rain_morning = hourly_precip[9] if len(hourly_precip) > 9 else 0
    rain_afternoon = hourly_precip[15] if len(hourly_precip) > 15 else 0
    rain_evening = hourly_precip[21] if len(hourly_precip) > 21 else 0
    max_rain = max(rain_morning, rain_afternoon, rain_evening)

    emoji = weather_emoji(desc)
    warning = rain_warning(max_rain)
    date_str = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"{emoji} <b>{city_kr} 오늘의 날씨</b>  ({date_str})",
        "",
        f"🌡️ 현재 <b>{temp}°C</b> (체감 {feels}°C)",
        f"📊 최고 <b>{max_temp}°C</b> / 최저 <b>{min_temp}°C</b>",
        f"💧 습도 {humidity}%  |  💨 풍속 {wind}km/h",
        "",
        "🌧️ <b>강수확률</b>",
        f"   오전 {rain_morning}%  |  오후 {rain_afternoon}%  |  저녁 {rain_evening}%",
    ]

    if warning:
        lines.append("")
        lines.append(warning)

    lines.extend([
        "",
        f"🌅 일출 {sunrise}  |  🌇 일몰 {sunset}",
    ])

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 날씨 API: wttr.in (fallback, 느리지만 데이터 풍부)
# ──────────────────────────────────────────────

def get_weather_wttr(city: str, max_retries: int = 3) -> dict:
    """wttr.in API (재시도 포함)"""
    url = f"https://wttr.in/{city}?format=j1"
    headers = {"User-Agent": "curl/7.68.0", "Accept": "application/json"}

    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=20)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                print(
                    f"[날씨] wttr.in 재시도 {attempt + 1}/{max_retries} "
                    f"({wait}초 대기): {e}",
                    flush=True,
                )
                time.sleep(wait)
            else:
                raise


def format_weather_wttr(data: dict, city_kr: str) -> str:
    """wttr.in 데이터를 텔레그램 HTML 메시지로 포맷합니다."""
    current = data["current_condition"][0]
    today = data["weather"][0]
    astro = today["astronomy"][0]

    temp = current["temp_C"]
    feels = current["FeelsLikeC"]
    desc = current["weatherDesc"][0]["value"]
    humidity = current["humidity"]
    wind = current["windspeedKmph"]
    max_temp = today["maxtempC"]
    min_temp = today["mintempC"]
    sunrise = astro["sunrise"]
    sunset = astro["sunset"]

    hourly = today["hourly"]
    rain_morning = int(hourly[3]["chanceofrain"])
    rain_afternoon = int(hourly[5]["chanceofrain"])
    rain_evening = int(hourly[7]["chanceofrain"])
    max_rain = max(rain_morning, rain_afternoon, rain_evening)

    emoji = weather_emoji(desc)
    warning = rain_warning(max_rain)
    date_str = today["date"]

    lines = [
        f"{emoji} <b>{city_kr} 오늘의 날씨</b>  ({date_str})",
        "",
        f"🌡️ 현재 <b>{temp}°C</b> (체감 {feels}°C)",
        f"📊 최고 <b>{max_temp}°C</b> / 최저 <b>{min_temp}°C</b>",
        f"💧 습도 {humidity}%  |  💨 풍속 {wind}km/h",
        "",
        "🌧️ <b>강수확률</b>",
        f"   오전 {rain_morning}%  |  오후 {rain_afternoon}%  |  저녁 {rain_evening}%",
    ]

    if warning:
        lines.append("")
        lines.append(warning)

    lines.extend([
        "",
        f"🌅 일출 {sunrise}  |  🌇 일몰 {sunset}",
    ])

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 통합 날씨 조회 (Open-Meteo 우선 → wttr.in fallback)
# ──────────────────────────────────────────────

def get_weather_message(city: str, city_kr: str) -> str:
    """
    Open-Meteo를 먼저 시도하고, 실패 시 wttr.in으로 fallback.
    최종 포맷된 메시지 문자열을 반환합니다.
    """
    # 1차: Open-Meteo (빠름, ~1초)
    try:
        data = get_weather_openmeteo(city)
        return format_weather_openmeteo(data, city_kr)
    except Exception as e:
        print(f"[날씨] Open-Meteo 실패, wttr.in 시도: {e}", flush=True)

    # 2차: wttr.in (느림, fallback)
    data = get_weather_wttr(city)
    return format_weather_wttr(data, city_kr)


# ──────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────

def weather_emoji(desc: str) -> str:
    """날씨 설명에 맞는 이모지를 반환합니다."""
    desc_lower = desc.lower()
    if "clear" in desc_lower or "sunny" in desc_lower:
        return "☀️"
    elif "partly" in desc_lower:
        return "⛅"
    elif "cloud" in desc_lower or "overcast" in desc_lower:
        return "☁️"
    elif "rain" in desc_lower or "drizzle" in desc_lower or "shower" in desc_lower:
        return "🌧️"
    elif "snow" in desc_lower:
        return "❄️"
    elif "thunder" in desc_lower or "storm" in desc_lower:
        return "⛈️"
    elif "fog" in desc_lower or "mist" in desc_lower or "rime" in desc_lower:
        return "🌫️"
    elif "wind" in desc_lower:
        return "💨"
    return "🌤️"


def rain_warning(chance: int) -> str:
    """강수확률에 따른 우산 안내 메시지"""
    if chance >= 70:
        return "☂️ <b>우산 꼭 챙기세요!</b>"
    elif chance >= 40:
        return "🌂 우산 챙기는 게 좋겠어요"
    return ""


# ──────────────────────────────────────────────
# 메인 (스케줄 작업용)
# ──────────────────────────────────────────────

def main():
    """날씨 정보를 가져와서 텔레그램 날씨 알림 채널로 발송합니다."""
    token = TELEGRAM_BOT_TOKEN
    channel_id = CHAT_IDS["날씨 알림 채널"]
    city, city_kr = load_location()

    result = {"ok": False, "description": "실행되지 않음"}

    try:
        print(f"[날씨 알림] {city_kr}({city}) 날씨 데이터 조회 중...", flush=True)
        message = get_weather_message(city, city_kr)
        print("[날씨 알림] 메시지 생성 완료, 발송 중...", flush=True)

        result = send_message(token, channel_id, message)

        if result.get("ok"):
            print("[날씨 알림] ✅ 발송 성공!", flush=True)
        else:
            print(f"[날씨 알림] ❌ 발송 실패: {result.get('description', 'Unknown error')}", flush=True)

    except Exception as e:
        print(f"[날씨 알림] ❌ 오류 발생: {e}", flush=True)
        result = {"ok": False, "description": str(e)}
        try:
            personal_id = CHAT_IDS["내 개인"]
            send_message(token, personal_id, f"⚠️ 날씨 알림 오류: {str(e)}")
        except Exception:
            pass

    return result


if __name__ == "__main__":
    main()
