"""
config.py - 설정 (토큰, Chat ID)
환경변수에서 Telegram Bot 설정값을 로드합니다.
"""

import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# Telegram Bot 설정
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === 채널/채팅 목록 ===
CHAT_IDS = {
    "내 개인": os.getenv("PERSONAL_CHAT_ID", "7447207979"),
    "날씨 알림 채널": os.getenv("WEATHER_CHANNEL_ID", "-1003854343800"),
}

# === 날씨 설정 ===
WEATHER_CITY = os.getenv("WEATHER_CITY", "Seoul")
WEATHER_CITY_KR = os.getenv("WEATHER_CITY_KR", "서울")

# === 스케줄 설정 ===
SCHEDULE_TIME = os.getenv("SCHEDULE_TIME", "08:00")

# === 네이버 뉴스 설정 ===
NEWS_KEYWORDS = ["날씨"]
NEWS_COUNT = 5

# 발송 이력 파일 경로
SEND_HISTORY_FILE = "send_history.json"
