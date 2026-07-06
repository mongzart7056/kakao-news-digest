"""
dart_collector.py
전자공시(DART) OpenAPI로 지정 기업의 정기보고서(사업/반기/분기)를 가져옵니다.
"""
import io
import json
import os
import re
import urllib.parse
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
DART_API_KEY = os.environ.get("DART_API_KEY", "")

CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DISCLOSURE_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
PERIOD_RE = re.compile(r"\((\d{4}\.\d{2})\)")

DEFAULT_REPORT_TYPES = ["반기보고서", "분기보고서", "사업보고서"]


def _http_get(url):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read()


def _normalize_name(name):
    """DART 회사명 매칭용 정규화."""
    text = (name or "").lower()
    for token in ["주식회사", "(주)", "㈜", "주)", "(주", "co.,ltd.", "co,ltd", "ltd.", "ltd"]:
        text = text.replace(token, "")
    return re.sub(r"[^0-9a-z가-힣]", "", text)


def _parse_date(date_text):
    try:
        return datetime.strptime(date_text, "%Y%m%d").replace(tzinfo=KST)
    except (TypeError, ValueError):
        return datetime.now(KST)


def _report_type(report_name, report_types):
    for report_type in report_types:
        if report_type in report_name:
            return report_type
    return None


def _report_period(report_name):
    match = PERIOD_RE.search(report_name or "")
    return match.group(1) if match else ""


def _dart_link(receipt_no):
    return f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}"


def fetch_corp_codes():
    """DART 고유번호 ZIP을 내려받아 회사명 매칭용 목록으로 반환."""
    if not DART_API_KEY:
        return []

    url = CORP_CODE_URL + "?" + urllib.parse.urlencode({"crtfc_key": DART_API_KEY})
    try:
        raw = _http_get(url)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            xml_name = zf.namelist()[0]
            xml_raw = zf.read(xml_name)
        root = ET.fromstring(xml_raw)
    except Exception as e:
        print(f"[dart] corpCode 조회 실패: {e}")
        return []

    records = []
    for item in root.findall("list"):
        corp_name = (item.findtext("corp_name") or "").strip()
        if not corp_name:
            continue
        records.append({
            "corp_code": (item.findtext("corp_code") or "").strip(),
            "corp_name": corp_name,
            "stock_code": (item.findtext("stock_code") or "").strip(),
            "modify_date": (item.findtext("modify_date") or "").strip(),
        })
    return records


def _company_aliases(name, alias_map):
    aliases = [name]
    aliases.extend(alias_map.get(name, []))
    return aliases


def resolve_companies(company_names, alias_map=None):
    """설정 회사명을 DART corp_code로 해석. 상장사(stock_code 존재)를 우선합니다."""
    alias_map = alias_map or {}
    corp_codes = fetch_corp_codes()
    by_name = {}
    for record in corp_codes:
        by_name.setdefault(_normalize_name(record["corp_name"]), []).append(record)

    resolved, unresolved = [], []
    seen_codes = set()
    for name in company_names:
        candidates = []
        for alias in _company_aliases(name, alias_map):
            candidates.extend(by_name.get(_normalize_name(alias), []))

        if not candidates:
            unresolved.append(name)
            continue

        candidates.sort(key=lambda r: (0 if r.get("stock_code") else 1, r.get("corp_name", "")))
        picked = candidates[0]
        if picked["corp_code"] in seen_codes:
            continue
        seen_codes.add(picked["corp_code"])
        resolved.append({
            "input_name": name,
            "corp_code": picked["corp_code"],
            "corp_name": picked["corp_name"],
            "stock_code": picked.get("stock_code", ""),
        })

    if unresolved:
        print("[dart] DART 회사명 미매칭: " + ", ".join(unresolved))
    return resolved


def fetch_periodic_reports_for_company(company, start_date, end_date, report_types, target_periods, page_count=100):
    """한 회사의 정기공시 중 대상 보고서/기간만 반환."""
    reports = []
    page_no = 1
    while True:
        params = {
            "crtfc_key": DART_API_KEY,
            "corp_code": company["corp_code"],
            "bgn_de": start_date,
            "end_de": end_date,
            "pblntf_ty": "A",
            "page_no": page_no,
            "page_count": page_count,
        }
        url = DISCLOSURE_LIST_URL + "?" + urllib.parse.urlencode(params)
        try:
            data = json.loads(_http_get(url))
        except Exception as e:
            print(f"[dart] {company['corp_name']} 정기공시 조회 실패: {e}")
            return reports

        status = data.get("status")
        if status == "013":
            return reports
        if status != "000":
            message = data.get("message", "unknown")
            print(f"[dart] {company['corp_name']} 정기공시 응답 오류: {status} {message}")
            return reports

        reports.extend(data.get("list", []))
        total_page = int(data.get("total_page") or 1)
        if page_no >= total_page:
            break
        page_no += 1

    selected = {}
    for report in reports:
        report_name = report.get("report_nm", "")
        report_type = _report_type(report_name, report_types)
        period = _report_period(report_name)
        if not report_type or (target_periods and period not in target_periods):
            continue

        key = (company["corp_code"], report_type, period)
        current = selected.get(key)
        if current is None or (report.get("rcept_dt", ""), report.get("rcept_no", "")) > (
            current.get("rcept_dt", ""), current.get("rcept_no", "")
        ):
            selected[key] = report

    return list(selected.values())


def fetch_target_periodic_reports(disclosure_conf):
    """설정된 회사들의 사업/반기/분기보고서를 공시 섹션용 item 리스트로 반환."""
    if not DART_API_KEY:
        return []

    disclosure_conf = disclosure_conf or {}
    company_names = disclosure_conf.get("companies", [])
    if not company_names:
        return []

    now_kst = datetime.now(KST)
    start_date = disclosure_conf.get("start_date", "20250101")
    end_date = disclosure_conf.get("end_date") or now_kst.strftime("%Y%m%d")
    report_types = disclosure_conf.get("report_types", DEFAULT_REPORT_TYPES)
    target_periods = disclosure_conf.get("target_periods", [])
    alias_map = disclosure_conf.get("company_aliases", {})

    companies = resolve_companies(company_names, alias_map=alias_map)
    company_order = {company["corp_code"]: idx for idx, company in enumerate(companies)}
    period_order = {period: idx for idx, period in enumerate(target_periods)}
    report_type_order = {report_type: idx for idx, report_type in enumerate(report_types)}

    selected_reports = []
    for company in companies:
        reports = fetch_periodic_reports_for_company(
            company, start_date, end_date, report_types, target_periods
        )
        for report in reports:
            report_name = report.get("report_nm", "")
            report_type = _report_type(report_name, report_types) or ""
            period = _report_period(report_name)
            receipt_no = report.get("rcept_no", "")
            published = _parse_date(report.get("rcept_dt", ""))
            corp_name = report.get("corp_name") or company["corp_name"]
            selected_reports.append({
                "title": f"[정기공시] {corp_name} - {report_name}",
                "summary": f"보고기간: {period or '확인 필요'} | 접수일: {published.strftime('%Y.%m.%d')} | 구분: {report_type}",
                "link": _dart_link(receipt_no),
                "published": published,
                "source": "DART 정기공시",
                "query": "정기공시",
                "_sort": (
                    period_order.get(period, len(period_order)),
                    company_order.get(company["corp_code"], len(company_order)),
                    report_type_order.get(report_type, len(report_type_order)),
                    report_name,
                ),
            })

    selected_reports.sort(key=lambda item: item["_sort"])
    for item in selected_reports:
        item.pop("_sort", None)
    return selected_reports
