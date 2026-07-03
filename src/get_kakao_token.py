"""
get_kakao_token.py
최초 1회만 로컬에서 실행하여 refresh_token을 발급받는 헬퍼 스크립트.
발급받은 refresh_token은 GitHub Secrets(KAKAO_REFRESH_TOKEN)에 등록하세요.

사용법:
1) https://developers.kakao.com 에서 앱 생성 후 REST API 키 확인
2) [카카오 로그인] 활성화, Redirect URI에 아래 REDIRECT_URI 등록 (예: http://localhost:5000)
3) [동의항목]에서 "카카오톡 메시지 전송(talk_message)" 필수 동의로 설정
4) 아래 REST_API_KEY, REDIRECT_URI 채운 뒤 이 스크립트 실행
5) 브라우저에서 인가 코드 받은 뒤 터미널에 붙여넣기
"""
import json
import urllib.parse
import urllib.request

REST_API_KEY = "bacf4f4658d35634f1a076d9b6393608"
REDIRECT_URI = "http://localhost:5000"

AUTH_URL = (
    "https://kauth.kakao.com/oauth/authorize?"
    + urllib.parse.urlencode({
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "talk_message",
    })
)

TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def main():
    print("아래 URL을 브라우저에서 열고 로그인/동의 후, 리디렉션된 주소의 'code=' 값을 복사하세요.\n")
    print(AUTH_URL, "\n")
    code = input("인가 코드(code) 입력: ").strip()

    payload = urllib.parse.urlencode({
        "grant_type": "authorization_code",
        "client_id": REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    print("\n=== 발급 결과 (안전하게 보관하세요) ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    print("\nGitHub Secrets에 KAKAO_REFRESH_TOKEN으로 아래 값을 등록하세요:")
    print(data.get("refresh_token"))


if __name__ == "__main__":
    main()
