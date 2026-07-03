"""
kakao_sender.py
카카오 "나에게 보내기" API로 뉴스 다이제스트를 전송합니다.
access token은 refresh token으로 매 실행 시 새로 발급받습니다 (만료 대응).
"""
import os
import json
import time
import urllib.parse
import urllib.request

KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY", "")
KAKAO_REFRESH_TOKEN = os.environ.get("KAKAO_REFRESH_TOKEN", "")

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

# 카카오 기본 텍스트 템플릿의 text 필드 안전 길이 (여유있게 설정, 초과 시 분할 발송)
MAX_TEXT_LEN = 900


def refresh_access_token():
    payload = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": KAKAO_REST_API_KEY,
        "refresh_token": KAKAO_REFRESH_TOKEN,
    }).encode()
    req = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
    access_token = data["access_token"]
    new_refresh = data.get("refresh_token")  # 카카오가 갱신된 refresh_token을 줄 수도 있음
    if new_refresh:
        print("::warning::새 refresh_token이 발급되었습니다. GitHub Secret을 업데이트하세요:")
        print(f"::warning::{new_refresh}")
    return access_token


def _send_text(access_token, text, link_url=None):
    template_object = {
        "object_type": "text",
        "text": text,
        "link": {
            "web_url": link_url or "https://news.google.com",
            "mobile_web_url": link_url or "https://news.google.com",
        },
    }
    payload = urllib.parse.urlencode({
        "template_object": json.dumps(template_object, ensure_ascii=False)
    }).encode()
    req = urllib.request.Request(
        SEND_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            print(f"[kakao] 발송 성공: {result}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[kakao] 발송 실패 ({e.code}): {e.read()}")
        return False


def _chunk_text_blocks(blocks, max_len=MAX_TEXT_LEN):
    """블록(기사 단위 문자열) 리스트를 max_len 이내로 묶어서 여러 메시지로 분할."""
    chunks, current = [], ""
    for b in blocks:
        candidate = (current + "\n\n" + b) if current else b
        if len(candidate) > max_len and current:
            chunks.append(current)
            current = b
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_digest(header, article_blocks, first_link=None):
    """header + 기사 블록들을 카카오톡으로 발송 (여러 메시지로 분할될 수 있음)."""
    access_token = refresh_access_token()
    chunks = _chunk_text_blocks(article_blocks)
    ok = True
    for i, chunk in enumerate(chunks):
        if i == 0 and header:
            text = f"{header}\n\n{chunk}"
        else:
            text = chunk
        ok = _send_text(access_token, text, link_url=first_link) and ok
        time.sleep(0.5)
    return ok
