"""
main.py
매일 09/12/18/21시(KST)에 GitHub Actions cron으로 실행되는 엔트리포인트.
1) 카테고리별 뉴스 수집
2) 09시 슬롯이면 DART 공시도 포함
3) 상위 항목 선별 및 포맷팅
4) 카카오톡 "나에게 보내기"로 발송
"""
import os
import json
from datetime import datetime, timedelta, timezone

from news_collector import collect_all, collect_company_watchlist, collect_institute_rss
from dart_collector import fetch_recent_disclosures
from kakao_sender import send_digest

KST = timezone(timedelta(hours=9))
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "keywords.json")

# 슬롯 간 간격(시간) - 09/12/18/21시 실행 기준. 09시는 전날 21시 이후 공백(간밤+주말 등) 커버 위해 넉넉히.
SLOT_LOOKBACK_HOURS = {9: 14, 12: 3, 18: 6, 21: 3}

# 카테고리 우선순위 (메시지 길이 제한 있으므로 중요한 카테고리부터 채움)
CATEGORY_PRIORITY = [
    "ipo_investment", "policy_fund", "ai_core", "robotics_physical",
    "ai_infra", "ip_kculture", "web3_finance", "ax_dx_policy",
]


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def format_article(item, cat_label):
    date_str = item["published"].strftime("%m.%d %H:%M")
    summary = item["summary"][:60] + ("…" if len(item["summary"]) > 60 else "")
    line = f"📌 [{cat_label}] {item['title']}"
    if summary:
        line += f"\n· 요약: {summary}"
    line += f"\n· 출처: {item['source']} | {date_str}"
    line += f"\n🔗 {item['link']}"
    return line


def build_digest(conf, now_kst):
    hour = now_kst.hour
    lookback = SLOT_LOOKBACK_HOURS.get(hour, 4)
    max_items = conf.get("max_items_per_send", 7)

    collected = collect_all(conf, since_hours=lookback)

    # 경쟁사/유사기업 워치리스트 (예: 갤럭시코퍼레이션) - 항상 최우선
    watchlist_conf = conf.get("company_watchlist", {})
    watchlist_items = collect_company_watchlist(
        watchlist_conf.get("companies", []), since_hours=lookback
    )

    # 09시 슬롯: 정책보고서/공시/KOCCA RSS 우선 포함
    disclosure_items = []
    institute_items = []
    if hour == 9:
        disclosure_items = fetch_recent_disclosures(since_hours=lookback)
        institute_items = collect_institute_rss(
            conf.get("research_sources", {}).get("verified_rss_feeds", {}), since_hours=lookback
        )

    blocks = []
    used = 0

    # 1순위: 경쟁사/유사기업 워치리스트 (최대 3건)
    for it in watchlist_items[:3]:
        blocks.append(format_article(it, "워치리스트"))
        used += 1

    # 2순위: 공시 (최대 2건)
    for it in disclosure_items[:2]:
        blocks.append(format_article(it, "공시"))
        used += 1

    # 3순위: KOCCA 등 검증된 기관 RSS (최대 2건, 09시만)
    for it in institute_items[:2]:
        blocks.append(format_article(it, "기관"))
        used += 1

    for cat_key in CATEGORY_PRIORITY:
        if used >= max_items:
            break
        cat_label = conf["categories"][cat_key]["label"]
        items = collected.get(cat_key, [])
        for it in items:
            if used >= max_items:
                break
            blocks.append(format_article(it, cat_label))
            used += 1

    focus = conf.get("slot_focus", {}).get(f"{hour:02d}:00", "")
    header = f"🗞 AI/딥테크 뉴스 다이제스트 ({now_kst.strftime('%Y.%m.%d %H:%M')} KST)\n{focus}"

    first_link = blocks[0].split("🔗 ")[1].split("\n")[0] if blocks else None
    return header, blocks, first_link


def main():
    conf = load_config()
    now_kst = datetime.now(KST)
    header, blocks, first_link = build_digest(conf, now_kst)

    if not blocks:
        print("발송할 신규 기사가 없습니다.")
        return

    ok = send_digest(header, blocks, first_link=first_link)
    print("완료" if ok else "일부 실패 - 로그 확인 필요")


if __name__ == "__main__":
    main()
