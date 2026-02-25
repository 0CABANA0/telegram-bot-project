"""
news_scraper.py - 네이버 뉴스 스크래퍼
네이버 뉴스 검색에서 키워드 기반으로 뉴스를 수집합니다.
2025~ 네이버 SDS 디자인 시스템 대응 + 레거시 폴백 지원.
MD5 해시 기반 중복 필터링 포함.
"""

import hashlib
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import NEWS_HASH_FILE

HASH_FILE = Path(NEWS_HASH_FILE)

# 조류인플루엔자(AI) 관련 제외 키워드
_AVIAN_FLU_KEYWORDS = [
    "조류인플루엔자", "조류독감", "고병원성", "AI 방역", "AI 발생",
    "AI 확산", "살처분", "가금류", "닭·오리", "AI 의심",
    "AI 확진", "조류 인플루엔자", "H5N1", "H5N6", "H5N8",
    "AI 양성", "철새", "AI 역학", "구제역",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://search.naver.com/",
}


def _article_hash(title: str, link: str) -> str:
    """기사 제목+링크의 MD5 해시 생성 (중복 판별용)"""
    raw = f"{title.strip()}|{link.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _load_sent_hashes() -> set:
    """이전에 발송한 기사 해시 목록 로드"""
    if not HASH_FILE.exists():
        return set()
    try:
        data = json.loads(HASH_FILE.read_text(encoding="utf-8"))
        return set(data.get("hashes", []))
    except (json.JSONDecodeError, KeyError):
        return set()


def _save_sent_hashes(hashes: set):
    """발송한 기사 해시 저장 (최근 2000개만 유지)"""
    hash_list = list(hashes)[-2000:]
    HASH_FILE.write_text(
        json.dumps({"updated": datetime.now().isoformat(), "hashes": hash_list},
                    ensure_ascii=False),
        encoding="utf-8",
    )


def _is_avian_flu(article: dict) -> bool:
    """조류인플루엔자 관련 기사인지 판별"""
    text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
    return any(kw in text for kw in _AVIAN_FLU_KEYWORDS)


def scrape_naver_news(keyword: str, count: int = 5) -> list[dict]:
    """
    네이버 뉴스에서 키워드로 뉴스를 검색합니다.
    여러 전략(SDS 신규 디자인 / 레거시)을 시도하여 안정적으로 추출합니다.
    인공지능/AI 키워드 검색 시 조류인플루엔자 기사를 자동 제외합니다.

    Returns:
        list[dict]: [{"title", "link", "press", "summary"}, ...]
    """
    url = "https://search.naver.com/search.naver"
    params = {"where": "news", "query": keyword, "sort": "1"}  # sort=1: 최신순

    # 최대 2회 재시도 (403 차단 대응)
    soup = None
    resp = None
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            break
        except requests.RequestException as e:
            if resp is not None and resp.status_code == 403 and attempt < 2:
                wait = random.uniform(3.0, 6.0)
                print(f"    [{keyword}] 403 차단 → {wait:.1f}초 대기 후 재시도 ({attempt+1}/2)")
                time.sleep(wait)
                continue
            print(f"[ERROR] '{keyword}' 뉴스 요청 실패: {e}")
            return []

    if soup is None:
        return []

    # 여유분 확보 (필터링으로 감소할 수 있으므로)
    fetch_count = count + 5

    # 전략 1: SDS 디자인 시스템 (2025~)
    articles = _parse_sds(soup, fetch_count)

    # 전략 2: 레거시 디자인 (div.news_area)
    if not articles:
        articles = _parse_legacy(soup, fetch_count)

    # 전략 3: 범용 링크 기반 추출
    if not articles:
        articles = _parse_generic(soup, fetch_count)

    # 조류인플루엔자 필터: AI/인공지능 관련 키워드일 때 적용
    ai_keywords = {"ai", "인공지능", "생성ai", "생성형ai", "ai반도체"}
    if keyword.lower().replace(" ", "") in ai_keywords:
        filtered = [a for a in articles if not _is_avian_flu(a)]
        removed = len(articles) - len(filtered)
        if removed > 0:
            print(f"    [필터] 조류인플루엔자 기사 {removed}건 제외")
        articles = filtered

    return articles[:count]


def _parse_sds(soup: BeautifulSoup, count: int) -> list[dict]:
    """
    SDS 디자인 시스템 파서 (2025~ 네이버 검색 UI).
    Profile 요소([data-sds-comp="Profile"])를 기사 경계로 사용하여
    각 기사의 언론사/제목/요약/링크를 추출합니다.
    """
    results = []

    # 뉴스 카드 컨테이너 찾기
    container = soup.select_one("div.fds-news-item-list-tab")
    if not container:
        container = soup.select_one("ul.list_news")
    if not container:
        return results

    all_links = container.select("a[href]")
    if not all_links:
        return results

    # Profile 요소의 위치를 기준으로 기사 경계 설정
    # 각 Profile은 기사 시작을 의미함
    profiles = container.select('[data-sds-comp="Profile"]')
    if not profiles:
        return results

    # Profile의 부모에서 언론사 이름이 포함된 텍스트 링크 찾기
    # 각 Profile 요소를 기준으로 기사 단위 파싱
    _SKIP = {"keep.naver.com", "#", ""}

    for profile in profiles:
        if len(results) >= count:
            break

        # Profile의 바로 위 부모가 기사 컨테이너 (sds-comps-full-layout)
        article_el = profile.parent
        if not article_el or not article_el.name:
            continue

        links = article_el.select("a[href]")

        press = ""
        title = ""
        link = ""
        summary = ""

        for a in links:
            href = a.get("href", "").strip()
            text = a.get_text(strip=True)

            # Keep / 빈 href 스킵
            if href in _SKIP or "keep.naver.com" in href:
                continue

            # 빈 텍스트 스킵
            if not text:
                continue

            # "네이버뉴스" 보조 링크 스킵
            if text == "네이버뉴스":
                continue

            # 언론사명: media.naver.com/press 링크 또는 언론사 자체 도메인 링크
            # (제목보다 먼저 나오는 짧은 텍스트 링크)
            if not press and not title:
                # 언론사명은 보통 짧고 (15자 이하), 제목/요약보다 먼저 나옴
                if "media.naver.com/press" in href or len(text) <= 15:
                    press = text
                    continue

            # 제목: 첫 번째 콘텐츠 링크 (5자 이상)
            if not title and len(text) >= 5:
                title = text
                link = href
                continue

            # 요약: 두 번째 콘텐츠 링크 (20자 이상)
            if title and not summary and len(text) >= 10:
                summary = text
                continue

        if title and link:
            results.append({
                "title": title,
                "link": link,
                "press": press,
                "summary": summary[:120] if summary else "",
            })

    return results


def _parse_legacy(soup: BeautifulSoup, count: int) -> list[dict]:
    """레거시 디자인 파서 (div.news_area 기반)"""
    results = []
    articles = soup.select("div.news_area")[:count]

    for article in articles:
        title_tag = article.select_one("a.news_tit")
        if not title_tag:
            continue

        title = title_tag.get_text(strip=True)
        link = title_tag.get("href", "")

        press_tag = article.select_one("a.info.press")
        press = press_tag.get_text(strip=True) if press_tag else ""

        summary_tag = article.select_one("div.news_dsc")
        summary = summary_tag.get_text(strip=True)[:120] if summary_tag else ""

        results.append({
            "title": title,
            "link": link,
            "press": press,
            "summary": summary,
        })

    return results


def _parse_generic(soup: BeautifulSoup, count: int) -> list[dict]:
    """범용 폴백 파서: news.naver.com 링크를 직접 탐색"""
    results = []
    seen_links = set()

    for a_tag in soup.select('a[href*="news.naver.com"]'):
        href = a_tag.get("href", "")
        text = a_tag.get_text(strip=True)

        if not text or len(text) < 5 or href in seen_links:
            continue

        # 기사 링크 패턴만 허용
        if "/article/" not in href and "/read" not in href:
            continue

        seen_links.add(href)
        results.append({
            "title": text,
            "link": href,
            "press": "",
            "summary": "",
        })

        if len(results) >= count:
            break

    return results


def scrape_all_keywords(keywords: list[str], count_per: int = 5) -> dict[str, list[dict]]:
    """
    여러 키워드를 한 번에 스크래핑합니다.
    중복 기사를 MD5 해시로 필터링합니다.
    네이버 차단 방지를 위해 요청 간 랜덤 딜레이를 적용합니다.

    Returns:
        dict: {키워드: [기사 목록], ...}
    """
    sent_hashes = _load_sent_hashes()
    all_results = {}
    new_hashes = set()

    for idx, keyword in enumerate(keywords):
        # 네이버 403 차단 방지: 요청 간 1~3초 랜덤 딜레이
        if idx > 0:
            delay = random.uniform(1.0, 3.0)
            time.sleep(delay)
        raw_articles = scrape_naver_news(keyword, count=count_per + 3)  # 여유분
        filtered = []

        for article in raw_articles:
            h = _article_hash(article["title"], article["link"])
            if h not in sent_hashes and h not in new_hashes:
                filtered.append(article)
                new_hashes.add(h)

            if len(filtered) >= count_per:
                break

        all_results[keyword] = filtered
        total = len(filtered)
        print(f"  [{keyword}] {total}건 수집 (원본 {len(raw_articles)}건)")

    # 해시 저장
    sent_hashes.update(new_hashes)
    _save_sent_hashes(sent_hashes)

    return all_results


def format_news_for_telegram(all_news: dict[str, list[dict]]) -> str:
    """
    키워드별 뉴스를 텔레그램 HTML 메시지로 변환합니다.

    Args:
        all_news: scrape_all_keywords()의 반환값

    Returns:
        str: HTML 형식의 텔레그램 메시지
    """
    now = datetime.now()
    time_label = "오전" if now.hour < 12 else "오후"
    date_str = now.strftime("%Y-%m-%d")

    lines = [
        f"<b>📰 네이버 뉴스 브리핑</b>  ({date_str} {time_label})",
        "",
    ]

    total_count = 0

    for keyword, articles in all_news.items():
        if not articles:
            lines.append(f"🔹 <b>{keyword}</b> — 새로운 뉴스 없음")
            lines.append("")
            continue

        lines.append(f"🔹 <b>{keyword}</b>")

        for i, art in enumerate(articles, 1):
            press_str = f" [{art['press']}]" if art.get("press") else ""
            title_escaped = _escape_html(art["title"])
            lines.append(
                f'  {i}. <a href="{art["link"]}">{title_escaped}</a>{press_str}'
            )
            if art.get("summary"):
                summary_escaped = _escape_html(art["summary"][:80])
                lines.append(f"     {summary_escaped}")

        lines.append("")
        total_count += len(articles)

    lines.append(f"📊 총 {total_count}건")

    return "\n".join(lines)


def _escape_html(text: str) -> str:
    """텔레그램 HTML에서 특수문자 이스케이프"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
