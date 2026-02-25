"""
news_bot.py - 네이버 뉴스 텔레그램 자동 발송 모듈
키워드별 뉴스를 수집하여 텔레그램 뉴스 채널로 발송합니다.
4096자 초과 시 자동 분할 발송 지원.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import (
    TELEGRAM_BOT_TOKEN,
    CHAT_IDS,
    NEWS_KEYWORDS,
    NEWS_COUNT_PER_KEYWORD,
)
from news_scraper import scrape_all_keywords, format_news_for_telegram
from telegram_sender import send_message

# 텔레그램 메시지 최대 길이
MAX_MSG_LEN = 4096


def _split_message(text: str, max_len: int = MAX_MSG_LEN) -> list[str]:
    """
    텔레그램 메시지 길이 제한(4096자) 초과 시 줄 단위로 분할합니다.
    HTML 태그가 깨지지 않도록 줄 단위로 분리합니다.
    """
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""

    for line in text.split("\n"):
        candidate = current + "\n" + line if current else line
        if len(candidate) <= max_len:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = line

    if current:
        chunks.append(current)

    return chunks


def send_news():
    """
    네이버 뉴스를 수집하여 텔레그램 뉴스 채널로 발송합니다.

    Returns:
        dict: {"ok": bool, "total": int, "message": str}
    """
    token = TELEGRAM_BOT_TOKEN
    channel_id = CHAT_IDS.get("뉴스 채널", "")

    if not token:
        print("[뉴스봇] ERROR: TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        return {"ok": False, "total": 0, "message": "토큰 미설정"}

    if not channel_id:
        print("[뉴스봇] ERROR: NEWS_CHANNEL_ID가 설정되지 않았습니다.")
        return {"ok": False, "total": 0, "message": "채널 ID 미설정"}

    keywords = NEWS_KEYWORDS
    count_per = NEWS_COUNT_PER_KEYWORD

    print(f"[뉴스봇] 키워드: {keywords} (각 {count_per}건)")
    print(f"[뉴스봇] 뉴스 수집 시작...")

    # 뉴스 수집
    all_news = scrape_all_keywords(keywords, count_per)

    # 전체 수집 건수
    total = sum(len(arts) for arts in all_news.values())
    if total == 0:
        msg = "새로운 뉴스가 없습니다."
        print(f"[뉴스봇] {msg}")
        return {"ok": True, "total": 0, "message": msg}

    print(f"[뉴스봇] 총 {total}건 수집 완료, 메시지 생성 중...")

    # 메시지 포맷
    message = format_news_for_telegram(all_news)
    print(f"[뉴스봇] 메시지 길이: {len(message)}자")

    # 분할 발송
    chunks = _split_message(message)
    success_count = 0

    for i, chunk in enumerate(chunks):
        result = send_message(token, channel_id, chunk)
        if result.get("ok"):
            success_count += 1
            if len(chunks) > 1:
                print(f"[뉴스봇] 파트 {i + 1}/{len(chunks)} 발송 성공")
        else:
            desc = result.get("description", "Unknown error")
            print(f"[뉴스봇] 파트 {i + 1}/{len(chunks)} 발송 실패: {desc}")

    if success_count == len(chunks):
        print(f"[뉴스봇] 뉴스 {total}건 발송 완료!")
        return {"ok": True, "total": total, "message": "발송 완료"}
    else:
        msg = f"{success_count}/{len(chunks)} 파트만 발송됨"
        print(f"[뉴스봇] {msg}")
        return {"ok": False, "total": total, "message": msg}


if __name__ == "__main__":
    result = send_news()
    print(f"\n결과: {result}")
