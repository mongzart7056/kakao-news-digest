"""
dart_collector.py
전자공시(DART) OpenAPI로 최근 공시를 가져옵니다. (무료, DART_API_KEY 필요 - opendart.fss.or.kr에서 발급)
IPO/투자/증자 등 관련 공시 유형만 필터링합니다.
"""
import os
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
DART_API_KEY = os.environ.get("DART_API_KEY", "")

# 관심 공시 유형 키워드 (report_nm에 포함되는 경우만 채택)
RELEVANT_REPORT_KEYWORDS = [
    "증권신고서", "투자설명서", "주요사항보고서", "유상증자", "무상증자",
    "전환사채", "신주인수권부사채", "합병", "분할", "최대주주변경",
    "기술평가", "상장예비심사", "공모가",
]


def _http_get(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read()


def fetch_recent_disclosures(since_hours=4, page_count=100):
    """DART 공시검색 API - 최근 N시간 내 공시 중 관심 유형만 반환."""
    if not DART_API_KEY:
        return []

    end_dt = datetime.now(KST)
    begin_dt = end_dt - timedelta(hours=since_hours)

    params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de": begin_dt.strftime("%Y%m%d"),
        "end_de": end_dt.strftime("%Y%m%d"),
        "page_no": 1,
        "page_count": page_count,
    }
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode(params)

    try:
        raw = _http_get(url)
        data = json.loads(raw)
    except Exception as e:
        print(f"[dart] 조회 실패: {e}")
        return []

    if data.get("status") != "000":
        return []

    items = []
    for it in data.get("list", []):
        report_nm = it.get("report_nm", "")
        if not any(k in report_nm for k in RELEVANT_REPORT_KEYWORDS):
            continue
        rcept_no = it.get("rcept_no")
        link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        items.append({
            "title": f"[공시] {it.get('corp_name', '')} - {report_nm}",
            "summary": f"제출인: {it.get('flr_nm', '')}",
            "link": link,
            "published": datetime.strptime(it.get("rcept_dt", ""), "%Y%m%d").replace(tzinfo=KST),
            "source": "DART 전자공시",
            "query": "공시",
        })
    return items


def fetch_company_disclosures(company_names, since_hours=24, page_count=100):
    """특정 회사명(관계기업) 공시만 필터링 - 지분 변동 등 놓치지 않기 위해 report_nm 유형 제한 없이 전체 공시 포함."""
    if not DART_API_KEY or not company_names:
        return []

    end_dt = datetime.now(KST)
    begin_dt = end_dt - timedelta(hours=since_hours)

    params = {
        "crtfc_key": DART_API_KEY,
        "bgn_de": begin_dt.strftime("%Y%m%d"),
        "end_de": end_dt.strftime("%Y%m%d"),
        "page_no": 1,
        "page_count": page_count,
    }
    url = "https://opendart.fss.or.kr/api/list.json?" + urllib.parse.urlencode(params)

    try:
        raw = _http_get(url)
        data = json.loads(raw)
    except Exception as e:
        print(f"[dart] 관계기업 공시 조회 실패: {e}")
        return []

    if data.get("status") != "000":
        return []

    items = []
    for it in data.get("list", []):
        corp_name = it.get("corp_name", "")
        if not any(name in corp_name for name in company_names):
            continue
        report_nm = it.get("report_nm", "")
        rcept_no = it.get("rcept_no")
        link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"
        items.append({
            "title": f"[관계기업 공시] {corp_name} - {report_nm}",
            "summary": f"제출인: {it.get('flr_nm', '')}",
            "link": link,
            "published": datetime.strptime(it.get("rcept_dt", ""), "%Y%m%d").replace(tzinfo=KST),
            "source": "DART 전자공시",
            "query": "관계기업공시",
        })
    return items
