"""텔레그램 메시지 발송 핵심 모듈"""
import requests
import json
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path(__file__).parent / "send_history.json"


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> dict:
    """
    텔레그램 메시지 발송
    Args:
        token: 봇 API 토큰
        chat_id: 대상 Chat ID
        text: 메시지 내용 (HTML 포맷 지원)
        parse_mode: "HTML" 또는 "Markdown"
    Returns:
        dict: API 응답 (ok, result 포함)
    """
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False,
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        result = response.json()
        # 발송 이력 저장
        _save_history(chat_id, text, result.get("ok", False))
        return result
    except requests.RequestException as e:
        return {"ok": False, "description": str(e)}


def send_photo(token: str, chat_id: str, photo_path: str, caption: str = "") -> dict:
    """이미지 발송"""
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(photo_path, "rb") as photo:
        files = {"photo": photo}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        response = requests.post(url, data=data, files=files, timeout=30)
    return response.json()


def send_document(token: str, chat_id: str, doc_path: str, caption: str = "") -> dict:
    """파일 발송"""
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(doc_path, "rb") as doc:
        files = {"document": doc}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        response = requests.post(url, data=data, files=files, timeout=30)
    return response.json()


def send_video(token: str, chat_id: str, video_path: str, caption: str = "") -> dict:
    """동영상 발송 (최대 50MB)"""
    url = f"https://api.telegram.org/bot{token}/sendVideo"
    with open(video_path, "rb") as video:
        files = {"video": video}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        response = requests.post(url, data=data, files=files, timeout=60)
    return response.json()


def send_animation(token: str, chat_id: str, gif_path: str, caption: str = "") -> dict:
    """GIF 애니메이션 발송"""
    url = f"https://api.telegram.org/bot{token}/sendAnimation"
    with open(gif_path, "rb") as animation:
        files = {"animation": animation}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        response = requests.post(url, data=data, files=files, timeout=30)
    return response.json()


def send_voice(token: str, chat_id: str, voice_path: str, caption: str = "") -> dict:
    """음성 메시지 발송 (.ogg 권장)"""
    url = f"https://api.telegram.org/bot{token}/sendVoice"
    with open(voice_path, "rb") as voice:
        files = {"voice": voice}
        data = {"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"}
        response = requests.post(url, data=data, files=files, timeout=30)
    return response.json()


def send_location(token: str, chat_id: str, latitude: float, longitude: float) -> dict:
    """위치 공유"""
    url = f"https://api.telegram.org/bot{token}/sendLocation"
    payload = {"chat_id": chat_id, "latitude": latitude, "longitude": longitude}
    return requests.post(url, json=payload, timeout=10).json()


def send_poll(token: str, chat_id: str, question: str, options: list[str],
              is_anonymous: bool = True, poll_type: str = "regular") -> dict:
    """
    투표 생성
    Args:
        question: 질문 (1~300자)
        options: 선택지 리스트 (2~10개)
        is_anonymous: 익명 투표 여부
        poll_type: "regular" (일반) 또는 "quiz" (퀴즈)
    """
    url = f"https://api.telegram.org/bot{token}/sendPoll"
    payload = {
        "chat_id": chat_id,
        "question": question,
        "options": options,
        "is_anonymous": is_anonymous,
        "type": poll_type,
    }
    return requests.post(url, json=payload, timeout=10).json()


def forward_message(token: str, chat_id: str, from_chat_id: str, message_id: int) -> dict:
    """메시지 전달 (원본 발신자 표시)"""
    url = f"https://api.telegram.org/bot{token}/forwardMessage"
    payload = {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id}
    return requests.post(url, json=payload, timeout=10).json()


def copy_message(token: str, chat_id: str, from_chat_id: str, message_id: int) -> dict:
    """메시지 복사 (원본 발신자 숨김)"""
    url = f"https://api.telegram.org/bot{token}/copyMessage"
    payload = {"chat_id": chat_id, "from_chat_id": from_chat_id, "message_id": message_id}
    return requests.post(url, json=payload, timeout=10).json()


def edit_message(token: str, chat_id: str, message_id: int, new_text: str,
                 parse_mode: str = "HTML") -> dict:
    """발송된 메시지 내용 수정"""
    url = f"https://api.telegram.org/bot{token}/editMessageText"
    payload = {
        "chat_id": chat_id, "message_id": message_id,
        "text": new_text, "parse_mode": parse_mode,
    }
    return requests.post(url, json=payload, timeout=10).json()


def delete_message(token: str, chat_id: str, message_id: int) -> dict:
    """메시지 삭제 (48시간 이내만 가능)"""
    url = f"https://api.telegram.org/bot{token}/deleteMessage"
    payload = {"chat_id": chat_id, "message_id": message_id}
    return requests.post(url, json=payload, timeout=10).json()


def pin_message(token: str, chat_id: str, message_id: int,
                disable_notification: bool = False) -> dict:
    """메시지 고정"""
    url = f"https://api.telegram.org/bot{token}/pinChatMessage"
    payload = {
        "chat_id": chat_id, "message_id": message_id,
        "disable_notification": disable_notification,
    }
    return requests.post(url, json=payload, timeout=10).json()


def get_me(token: str) -> dict:
    """봇 정보 조회 (이름, 사용자명, 권한 등)"""
    url = f"https://api.telegram.org/bot{token}/getMe"
    return requests.get(url, timeout=10).json()


def get_chat(token: str, chat_id: str) -> dict:
    """채팅/채널/그룹 정보 조회"""
    url = f"https://api.telegram.org/bot{token}/getChat"
    return requests.post(url, json={"chat_id": chat_id}, timeout=10).json()


def get_chat_member_count(token: str, chat_id: str) -> dict:
    """그룹/채널 멤버 수 조회"""
    url = f"https://api.telegram.org/bot{token}/getChatMemberCount"
    return requests.post(url, json={"chat_id": chat_id}, timeout=10).json()


def answer_callback_query(token: str, callback_query_id: str,
                          text: str = "", show_alert: bool = False) -> dict:
    """인라인 버튼 클릭 응답 처리"""
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    payload = {
        "callback_query_id": callback_query_id,
        "text": text, "show_alert": show_alert,
    }
    return requests.post(url, json=payload, timeout=10).json()


def broadcast(token: str, chat_ids: list[str], text: str) -> dict:
    """
    다채널 동시 발송
    Returns:
        dict: {"success": [...], "failed": [...]}
    """
    results = {"success": [], "failed": []}
    for chat_id in chat_ids:
        result = send_message(token, chat_id, text)
        if result.get("ok"):
            results["success"].append(chat_id)
        else:
            results["failed"].append({
                "chat_id": chat_id,
                "error": result.get("description", "Unknown error")
            })
    return results


def _save_history(chat_id: str, text: str, success: bool):
    """발송 이력을 JSON 파일에 저장"""
    history = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []

    history.append({
        "timestamp": datetime.now().isoformat(),
        "chat_id": chat_id,
        "text": text[:100] + "..." if len(text) > 100 else text,
        "success": success,
    })

    # 최근 500건만 보관
    history = history[-500:]
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def get_history(limit: int = 50) -> list:
    """발송 이력 조회"""
    if not HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return history[-limit:]
    except json.JSONDecodeError:
        return []
