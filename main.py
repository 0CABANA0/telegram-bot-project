"""
main.py - GUI 메인 프로그램
tkinter 기반 텔레그램 봇 발송 GUI 애플리케이션입니다.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

from telegram_sender import send_message, _load_history
from news_scraper import scrape_naver_news, format_news_for_telegram
from config import TELEGRAM_CHAT_ID


class TelegramBotApp:
    """텔레그램 봇 GUI 애플리케이션"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("텔레그램 봇 발송기")
        self.root.geometry("600x500")

        self._create_widgets()

    def _create_widgets(self):
        """GUI 위젯을 생성합니다."""
        # === 메시지 전송 영역 ===
        msg_frame = ttk.LabelFrame(self.root, text="메시지 전송", padding=10)
        msg_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(msg_frame, text="메시지:").pack(anchor="w")
        self.msg_text = scrolledtext.ScrolledText(msg_frame, height=5)
        self.msg_text.pack(fill="x", pady=5)

        ttk.Button(msg_frame, text="전송", command=self._send_message).pack(anchor="e")

        # === 뉴스 스크래핑 영역 ===
        news_frame = ttk.LabelFrame(self.root, text="네이버 뉴스 스크래핑", padding=10)
        news_frame.pack(fill="x", padx=10, pady=5)

        keyword_row = ttk.Frame(news_frame)
        keyword_row.pack(fill="x")

        ttk.Label(keyword_row, text="키워드:").pack(side="left")
        self.keyword_entry = ttk.Entry(keyword_row)
        self.keyword_entry.pack(side="left", fill="x", expand=True, padx=5)

        ttk.Button(keyword_row, text="검색 & 전송", command=self._scrape_and_send).pack(side="right")

        # === 로그 영역 ===
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _log(self, message: str):
        """로그 메시지를 출력합니다."""
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _send_message(self):
        """텍스트 메시지를 전송합니다."""
        text = self.msg_text.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("경고", "메시지를 입력해주세요.")
            return

        self._log(f"[발송 중] {text[:50]}...")
        result = send_message(text)

        if result.get("ok"):
            self._log("[성공] 메시지 전송 완료")
            self.msg_text.delete("1.0", "end")
        else:
            self._log(f"[실패] {result.get('error', '알 수 없는 오류')}")

    def _scrape_and_send(self):
        """뉴스를 스크래핑하여 텔레그램으로 전송합니다."""
        keyword = self.keyword_entry.get().strip()
        if not keyword:
            messagebox.showwarning("경고", "키워드를 입력해주세요.")
            return

        self._log(f"[스크래핑] '{keyword}' 검색 중...")
        news_list = scrape_naver_news(keyword)

        if not news_list:
            self._log("[결과 없음] 뉴스를 찾지 못했습니다.")
            return

        self._log(f"[완료] {len(news_list)}건의 뉴스 수집")

        formatted = format_news_for_telegram(news_list)
        result = send_message(formatted)

        if result.get("ok"):
            self._log("[성공] 뉴스 전송 완료")
        else:
            self._log(f"[실패] {result.get('error', '알 수 없는 오류')}")


def main():
    root = tk.Tk()
    app = TelegramBotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
