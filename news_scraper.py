"""
news_scraper.py - 네이버 뉴스 스크래퍼
네이버 뉴스에서 키워드 기반으로 뉴스를 수집합니다.
"""

import requests
from bs4 import BeautifulSoup


def scrape_naver_news(keyword: str, count: int = 5) -> list[dict]:
    """
    네이버 뉴스에서 키워드로 뉴스를 검색합니다.

    Args:
        keyword: 검색 키워드
        count: 가져올 뉴스 수 (기본값: 5)

    Returns:
        list[dict]: 뉴스 목록 [{"title": ..., "link": ..., "summary": ...}, ...]
    """
    url = "https://search.naver.com/search.naver"
    params = {
        "where": "news",
        "query": keyword,
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        news_list = []
        articles = soup.select("div.news_area")[:count]

        for article in articles:
            title_tag = article.select_one("a.news_tit")
            summary_tag = article.select_one("div.news_dsc")

            if title_tag:
                news_list.append({
                    "title": title_tag.get_text(strip=True),
                    "link": title_tag.get("href", ""),
                    "summary": summary_tag.get_text(strip=True) if summary_tag else "",
                })

        return news_list
    except requests.RequestException as e:
        print(f"[ERROR] 뉴스 스크래핑 실패: {e}")
        return []


def format_news_for_telegram(news_list: list[dict]) -> str:
    """
    뉴스 목록을 텔레그램 메시지 형식(HTML)으로 변환합니다.

    Args:
        news_list: scrape_naver_news()의 반환값

    Returns:
        str: HTML 형식의 텔레그램 메시지
    """
    if not news_list:
        return "검색 결과가 없습니다."

    lines = ["📰 <b>네이버 뉴스 요약</b>\n"]
    for i, news in enumerate(news_list, 1):
        lines.append(
            f'{i}. <a href="{news["link"]}">{news["title"]}</a>\n'
            f'   {news["summary"][:80]}...\n'
        )

    return "\n".join(lines)
