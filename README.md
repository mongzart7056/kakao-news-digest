# 카카오톡 뉴스 다이제스트 자동 발송

매일 한국시간 09:00 / 12:00 / 15:00 / 18:00 / 21:00 / 00:00, 지정한 키워드(AI, 로보틱스, 정책자금, IPO, IP/K-Culture, 공연/뮤지컬/음악/디지털콘텐츠 등) 관련
국내외 뉴스 + 기업 공시를 요약해 카카오톡("나에게 보내기")으로 자동 발송합니다.

## 구조
```
config/keywords.json      # 카테고리별 키워드, noise filter, 슬롯별 포커스
src/news_collector.py     # 네이버 뉴스 API + Google News RSS(한/영) 수집
src/dart_collector.py     # DART 전자공시 API (지정 기업 정기보고서)
src/kakao_sender.py       # 카카오 "나에게 보내기" 발송 (토큰 자동 갱신)
src/main.py               # 전체 파이프라인 실행 (엔트리포인트)
src/get_kakao_token.py    # 최초 1회 refresh_token 발급용 헬퍼
.github/workflows/        # GitHub Actions cron 스케줄 (무료, 서버 불필요)
```

## 설정 순서

### 1) 카카오 개발자 앱 등록
1. https://developers.kakao.com → 애플리케이션 추가
2. [앱 설정] > [요약 정보]에서 **REST API 키** 확인
3. [카카오 로그인] 활성화, Redirect URI 등록 (예: `http://localhost:5000`)
4. [카카오 로그인] > [동의항목]에서 **"카카오톡 메시지 전송(talk_message)"** 를 필수 동의로 설정
   - 본인 계정으로만 쓰는 "나에게 보내기"는 별도 카카오 심사 없이 사용 가능합니다.

### 2) refresh_token 최초 발급 (로컬에서 1회만)
```bash
cd src
python get_kakao_token.py
```
`get_kakao_token.py` 상단의 `REST_API_KEY`, `REDIRECT_URI`를 먼저 채워넣으세요.
안내에 따라 브라우저 인증 후 나온 `refresh_token`을 복사해둡니다.

### 3) 뉴스 소스 API 키 발급 (선택이지만 권장)
- **네이버 뉴스 검색 API** (무료): https://developers.naver.com/apps → 애플리케이션 등록 → 검색 API 사용 설정
  → `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 발급
- **Google News RSS**: 키 불필요, 바로 사용 가능 (한국어/영어 모두 커버)
- **DART 전자공시 API** (무료): https://opendart.fss.or.kr → 인증키 신청 → `DART_API_KEY`

### 4) GitHub 리포지토리에 코드 업로드
이 폴더를 새 GitHub 리포지토리로 push 합니다 (private 권장 — API 키가 로그에 노출되지 않도록 유의).

### 5) GitHub Secrets 등록
리포지토리 → Settings → Secrets and variables → Actions → New repository secret

| Secret 이름 | 값 |
|---|---|
| `KAKAO_REST_API_KEY` | 1)에서 확인한 REST API 키 |
| `KAKAO_REFRESH_TOKEN` | 2)에서 발급받은 refresh_token |
| `NAVER_CLIENT_ID` | 3)의 네이버 Client ID |
| `NAVER_CLIENT_SECRET` | 3)의 네이버 Client Secret |
| `DART_API_KEY` | 3)의 DART 인증키 |

### 6) 테스트 실행
Actions 탭 → "Kakao News Digest" → Run workflow (workflow_dispatch)로 수동 1회 실행해보고,
본인 카카오톡에 메시지가 오는지 확인합니다.

이후로는 매일 09/12/15/18/21/00시(KST)에 자동으로 실행됩니다.

## 알아두실 점 / 한계
- **토큰 만료**: refresh_token도 유효기간이 있어 장기간 미사용 시 재발급이 필요할 수 있습니다.
  실행 로그에 새 refresh_token이 찍히면(`::warning::`) Secret을 갱신해주세요.
- **카카오 메시지 길이 제한**: 텍스트 템플릿 길이 제한 때문에 기사가 많으면 메시지가 여러 개로 나뉘어 발송됩니다.
- **noise filter는 규칙 기반**: "저작권/특허/상표" 같은 단독 키워드는 콘텐츠/IP 관련 결합어가 있을 때만,
  그리고 소송/판결 관련 단어가 없을 때만 채택합니다. 완벽하지 않으니 며칠 운영해보고
  `config/keywords.json`의 `exclude_terms`/`require_combo_with`를 튜닝하는 걸 추천드립니다.
- **HTML 아카이브**: 매 실행 결과는 `docs/archive/*.json`으로 저장되며, `latest.html` 드롭다운에서 최근 3일 내역을 조회할 수 있습니다.
- **공시**: 지정 기업들의 DART 사업보고서, 반기보고서, 분기보고서를 한 섹션으로 노출합니다.
- **정책자금/지원사업**: 일반 뉴스보다 지원사업 공고, 정부과제 공고, 용역/입찰 공고, RFP 중심으로 필터링합니다.
- **API 무료 쿼터**: 네이버 뉴스 API, DART API 모두 일일 호출 한도가 있어 키워드 수가 많으면
  하루 6회 실행 시 한도에 근접할 수 있습니다. 실제 운영 중 초과 시 카테고리별 실행 주기를 조정하는 게 좋습니다.
