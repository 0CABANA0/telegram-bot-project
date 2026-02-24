"""
weather_alert.py - 매일 오전 날씨 알림 발송 스크립트
wttr.in API를 사용하여 날씨를 텔레그램 채널로 전송합니다.
"""

import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

import requests
from config import TELEGRAM_BOT_TOKEN, CHAT_IDS, WEATHER_CITY, WEATHER_CITY_KR
from telegram_sender import send_message


def get_weather(city: str) -> dict:
    """wttr.in API에서 날씨 데이터를 가져옵니다."""
    url = f"https://wttr.in/{city}?format=j1"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def weather_emoji(desc: str) -> str:
    """날씨 설명에 맞는 이모지를 반환합니다."""
    desc_lower = desc.lower()
    if "clear" in desc_lower or "sunny" in desc_lower:
        return "☀️"
    elif "partly" in desc_lower:
        return "⛅"
    elif "cloud" in desc_lower or "overcast" in desc_lower:
        return "☁️"
    elif "rain" in desc_lower or "drizzle" in desc_lower:
        return "🌧️"
    elif "snow" in desc_lower:
        return "❄️"
    elif "thunder" in desc_lower or "storm" in desc_lower:
        return "⛈️"
    elif "fog" in desc_lower or "mist" in desc_lower:
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


def format_weather_message(data: dict, city_kr: str) -> str:
    """날씨 데이터를 텔레그램 HTML 메시지로 포맷합니다."""
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

    # 시간대별 강수확률 (오전/오후/저녁)
    hourly = today["hourly"]
    rain_morning = int(hourly[3]["chanceofrain"])   # 09시
    rain_afternoon = int(hourly[5]["chanceofrain"])  # 15시
    rain_evening = int(hourly[7]["chanceofrain"])    # 21시
    max_rain = max(rain_morning, rain_afternoon, rain_evening)

    emoji = weather_emoji(desc)
    warning = rain_warning(max_rain)

    date_str = today["date"]  # YYYY-MM-DD

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


def main():
    """날씨 정보를 가져와서 텔레그램 날씨 알림 채널로 발송합니다."""
    token = TELEGRAM_BOT_TOKEN
    channel_id = CHAT_IDS["날씨 알림 채널"]
    city = WEATHER_CITY
    city_kr = WEATHER_CITY_KR

    try:
        print(f"[날씨 알림] {city_kr} 날씨 데이터 조회 중...")
        data = get_weather(city)

        message = format_weather_message(data, city_kr)
        print(f"[날씨 알림] 메시지 생성 완료, '{channel_id}' 채널로 발송 중...")

        result = send_message(token, channel_id, message)

        if result.get("ok"):
            print(f"[날씨 알림] ✅ 채널 발송 성공!")
        else:
            print(f"[날씨 알림] ❌ 발송 실패: {result.get('description', 'Unknown error')}")
            return result

    except Exception as e:
        print(f"[날씨 알림] ❌ 오류 발생: {e}")
        # 오류 시 개인 채팅으로 알림
        try:
            personal_id = CHAT_IDS["내 개인"]
            send_message(token, personal_id, f"⚠️ 날씨 알림 오류: {str(e)}")
        except Exception:
            pass

    return result


if __name__ == "__main__":
    main()
