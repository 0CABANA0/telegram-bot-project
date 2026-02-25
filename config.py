"""
config.py - 중앙 설정
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
    "뉴스 채널": os.getenv("NEWS_CHANNEL_ID", "-1003854343800"),
}

# === 날씨 설정 ===
WEATHER_CITY = os.getenv("WEATHER_CITY", "Seoul")
WEATHER_CITY_KR = os.getenv("WEATHER_CITY_KR", "서울")

# === 스케줄 설정 ===
WEATHER_SCHEDULE_TIME = os.getenv("WEATHER_SCHEDULE_TIME", "07:30")

# === 네이버 뉴스 설정 ===
# 핵심 키워드 17개 (쉼표 구분, 환경변수로 변경 가능)
# AI → 인공지능 (조류인플루엔자 AI 혼용 방지)
# 대통령/국회/탄핵/전쟁 → 정치 통합
_default_keywords = (
    "인공지능,주식,반도체,긴급속보,기준금리,"
    "환율,코스피,나스닥,미중무역,삼성전자,"
    "엔비디아,ETF,속보,정치,수출규제,"
    "관세,금값"
)
NEWS_KEYWORDS = [
    k.strip() for k in os.getenv("NEWS_KEYWORDS", _default_keywords).split(",") if k.strip()
]
NEWS_COUNT_PER_KEYWORD = int(os.getenv("NEWS_COUNT_PER_KEYWORD", "3"))

# 뉴스 스케줄: 쉼표로 구분된 시간 (환경변수로 변경 가능)
_default_news_times = "08:00,18:00"
NEWS_SCHEDULE_TIMES = [
    t.strip() for t in os.getenv("NEWS_SCHEDULE_TIMES", _default_news_times).split(",") if t.strip()
]

# 뉴스 중복 필터링용 해시 파일
NEWS_HASH_FILE = "news_sent_hashes.json"

# === 한국 주요 도시 매핑 ===
CITY_MAP = {
    "서울": "Seoul", "부산": "Busan", "대구": "Daegu", "인천": "Incheon",
    "광주": "Gwangju", "대전": "Daejeon", "울산": "Ulsan", "세종": "Sejong",
    "수원": "Suwon", "성남": "Seongnam", "고양": "Goyang", "용인": "Yongin",
    "창원": "Changwon", "청주": "Cheongju", "전주": "Jeonju", "천안": "Cheonan",
    "제주": "Jeju", "김해": "Gimhae", "포항": "Pohang", "평택": "Pyeongtaek",
}
CITY_MAP_REV = {v.lower(): k for k, v in CITY_MAP.items()}
