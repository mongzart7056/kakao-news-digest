"""
main.py
매일 09/12/18/21시(KST)에 GitHub Actions cron으로 실행되는 엔트리포인트.
1) 카테고리별 뉴스 수집
2) 09시 슬롯이면 DART 공시/KOCCA RSS도 포함
3) 카카오톡에는 카테고리별 대표 기사 1건씩만 압축 발송 (메시지 전체가 링크로 동작)
4) 전체 수집 기사는 HTML 리포트(GitHub Pages)로 생성, 카톡 메시지에서 그 링크로 연결
5) [추가] 매 실행의 다이제스트를 docs/archive/*.json 으로 누적 저장하여
   latest.html에서 과거 다이제스트를 드롭다운으로 열람할 수 있게 함
"""
import os
import json
from datetime import datetime, timedelta, timezone

from news_collector import collect_all, collect_institute_rss, collect_affiliate_equity_news
from dart_collector import fetch_recent_disclosures, fetch_company_disclosures
from kakao_sender import send_digest
from html_report import generate_html, generate_archive_json

KST = timezone(timedelta(hours=9))
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "keywords.json")
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")
ARCHIVE_DIR = os.path.join(DOCS_DIR, "archive")

# 슬롯 간 간격(시간) - 09/12/18/21시 실행 기준. 09시는 전날 21시 이후 공백 커버 위해 넉넉히.
SLOT_LOOKBACK_HOURS = {9: 14, 12: 3, 18: 6, 21: 3}

CATEGORY_PRIORITY = [
    "ipo_investment", "policy_fund", "ai_core", "digital_human", "robotics_physical",
    "ai_infra", "ip_kculture", "web3_finance", "ax_dx_policy",
]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _clean_display_title(title):
    import re
    return re.sub(r"\s*-\s*[가-힣A-Za-z0-9]+(뉴스|경제|일보|신문|저널|데일리|타임즈|타임스|투데이)?\s*$", "", title).strip()


def format_kakao_line(item, cat_label):
    """카톡용 압축 한 줄: 카테고리 대표 기사 헤드라인만 (링크는 메시지 전체 클릭으로 처리)."""
    title = _clean_display_title(item["title"])
    date_str = item["published"].strftime("%m.%d %H:%M")
    return f"📌 [{cat_label}] {title}  ({date_str})"


def build_report_sections(conf, collected, affiliate_items, disclosure_items, institute_items):
    """HTML 리포트용: 전체 수집 기사를 카테고리 순서대로 묶기. 관계기업 지분·공시가 최상단."""
    sections = []
    if affiliate_items:
        sections.append((conf.get("affiliate_equity_monitoring", {}).get("label", "관계기업 지분·공시"), affiliate_items))
    if disclosure_items:
        sections.append(("공시", disclosure_items))
    if institute_items:
        sections.append(("기관 자료 (KOCCA 등)", institute_items))
    for cat_key in CATEGORY_PRIORITY:
        label = conf["categories"][cat_key]["label"]
        items = collected.get(cat_key, [])
        if items:
            sections.append((label, items))
    return sections


def build_digest(conf, now_kst):
    hour = now_kst.hour
    lookback = SLOT_LOOKBACK_HOURS.get(hour, 4)

    collected = collect_all(conf, since_hours=lookback)

    # 관계기업(이모션웨이브/리마엔터/엔백스) 지분·공시 - 매 슬롯 최우선 조회
    affiliate_conf = conf.get("affiliate_equity_monitoring", {})
    affiliate_companies = affiliate_conf.get("companies", [])
    affiliate_dart_items = fetch_company_disclosures(affiliate_companies, since_hours=lookback)
    affiliate_news_items = collect_affiliate_equity_news(affiliate_companies, since_hours=lookback)
    affiliate_items = affiliate_dart_items + affiliate_news_items

    disclosure_items, institute_items = [], []
    if hour == 9:
        disclosure_items = fetch_recent_disclosures(since_hours=lookback)
        institute_items = collect_institute_rss(
            conf.get("research_sources", {}).get("verified_rss_feeds", {}), since_hours=lookback
        )

    # --- 카톡용: 섹션별 대표 1건만 (관계기업 지분·공시가 최상단) ---
    kakao_lines = []
    if affiliate_items:
        kakao_lines.append(format_kakao_line(affiliate_items[0], affiliate_conf.get("label", "관계기업 지분·공시")))
    if disclosure_items:
        kakao_lines.append(format_kakao_line(disclosure_items[0], "공시"))
    if institute_items:
        kakao_lines.append(format_kakao_line(institute_items[0], "기관"))
    for cat_key in CATEGORY_PRIORITY:
        items = collected.get(cat_key, [])
        if items:
            cat_label = conf["categories"][cat_key]["label"]
            kakao_lines.append(format_kakao_line(items[0], cat_label))

    # --- HTML용: 전체 목록 ---
    sections = build_report_sections(conf, collected, affiliate_items, disclosure_items, institute_items)

    focus = conf.get("slot_focus", {}).get(f"{hour:02d}:00", "")
    generated_at_str = now_kst.strftime("%Y.%m.%d %H:%M")
    header = f"🗞 AI/딥테크 뉴스 다이제스트 ({generated_at_str} KST)\n{focus}"

    return header, kakao_lines, sections, generated_at_str


def _archive_slug(now_kst):
    """아카이브 파일명에 쓸 타임스탬프 slug. 초 단위까지 넣어 같은 분 내 재실행도 구분."""
    return now_kst.strftime("%Y%m%d_%H%M%S")


def write_archive(sections, generated_at_str, now_kst):
    """이번 실행의 다이제스트를 docs/archive/{slug}.json 으로 저장하고
    docs/archive/index.json 목록 맨 앞에 추가. 기존 항목은 절대 삭제하지 않음
    (과거 내역을 계속 누적 보관)."""
    os.makedirs(ARCHIVE_DIR, exist_ok=True)

    slug = _archive_slug(now_kst)
    fname = f"{slug}.json"
    snapshot_path = os.path.join(ARCHIVE_DIR, fname)
    with open(snapshot_path, "w", encoding="utf-8") as f:
        f.write(generate_archive_json(generated_at_str, sections))

    index_path = os.path.join(ARCHIVE_DIR, "index.json")
    entries = []
    if os.path.exists(index_path):
        try:
            with open(index_path, encoding="utf-8") as f:
                entries = json.load(f)
        except (json.JSONDecodeError, OSError):
            entries = []

    # 혹시 같은 slug로 재실행된 경우 중복 방지 후 맨 앞(최신순)에 추가
    entries = [e for e in entries if e.get("file") != fname]
    entries.insert(0, {"file": fname, "label": generated_at_str})

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def write_html_report(sections, generated_at_str, base_url, now_kst):
    os.makedirs(DOCS_DIR, exist_ok=True)
    html = generate_html(generated_at_str, sections)
    out_path = os.path.join(DOCS_DIR, "latest.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    # 과거 다이제스트 보관용 스냅샷 저장 (latest.html 생성 성공 시에만)
    write_archive(sections, generated_at_str, now_kst)

    return base_url.rstrip("/") + "/latest.html"


def main():
    conf = load_config()
    now_kst = datetime.now(KST)
    header, kakao_lines, sections, generated_at_str = build_digest(conf, now_kst)

    total_items = sum(len(items) for _, items in sections)
    if total_items == 0:
        print("발송할 신규 기사가 없습니다.")
        return

    base_url = conf.get("html_report_base_url", "").strip()
    report_url = write_html_report(sections, generated_at_str, base_url, now_kst) if base_url else None

    if not kakao_lines:
        print("카톡에 담을 대표 기사가 없습니다 (HTML 리포트만 생성됨).")
        return

    footer = f"\n\n📎 전체 {total_items}건 보기: {report_url}" if report_url else ""
    body = header + "\n\n" + "\n".join(kakao_lines) + footer

    ok = send_digest(header="", article_blocks=[body], first_link=report_url)
    print("완료" if ok else "일부 실패 - 로그 확인 필요")


if __name__ == "__main__":
    main()
