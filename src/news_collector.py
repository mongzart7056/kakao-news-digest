"""
news_collector.py
국내(네이버 뉴스 검색 API) + 해외(Google News RSS) 기사를 키워드 기준으로 수집.
카테고리별 noise filter(콘텐츠 IP/저작권 등)도 여기서 적용합니다.
"""
import os
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")


def _http_get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def search_naver_news(query, display=10):
    """네이버 뉴스 검색 API. 무료지만 NAVER_CLIENT_ID/SECRET 필요."""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []
    url = (
        "https://openapi.naver.com/v1/search/news.json?"
        + urllib.parse.urlencode({"query": query, "display": display, "sort": "date"})
    )
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    try:
        raw = _http_get(url, headers)
        data = json.loads(raw)
    except Exception as e:
        print(f"[naver] {query} 검색 실패: {e}")
        return []

    items = []
    for it in data.get("items", []):
        title = _strip_html(it.get("title", ""))
        desc = _strip_html(it.get("description", ""))
        link = it.get("originallink") or it.get("link")
        pub = it.get("pubDate")
        try:
            pub_dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %z").astimezone(KST)
        except Exception:
            pub_dt = datetime.now(KST)
        items.append({
            "title": title, "summary": desc, "link": link,
            "published": pub_dt, "source": "네이버뉴스", "query": query,
        })
    return items


def search_google_news_rss(query, lang="ko", country="KR"):
    """Google News RSS. 키 불필요. 해외 커버리지는 lang=en, country=US 사용."""
    ceid = f"{country}:{lang if lang!='en' else 'en'}"
    url = (
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode({"q": query, "hl": lang, "gl": country, "ceid": ceid})
    )
    try:
        raw = _http_get(url)
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[google-rss] {query} 검색 실패: {e}")
        return []

    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", "")
        link = item.findtext("link", "")
        pub = item.findtext("pubDate", "")
        source_el = item.find("source")
        source = source_el.text if source_el is not None else "Google News"
        try:
            pub_dt = datetime.strptime(pub, "%a, %d %b %Y %H:%M:%S %Z").replace(
                tzinfo=timezone.utc
            ).astimezone(KST)
        except Exception:
            pub_dt = datetime.now(KST)
        items.append({
            "title": title, "summary": "", "link": link,
            "published": pub_dt, "source": source, "query": query,
        })
    return items


def _strip_html(text):
    import re
    return re.sub("<[^<]+?>", "", text).replace("&quot;", '"').replace("&amp;", "&")


def apply_noise_filter(items, category_conf):
    nf = category_conf.get("noise_filter")
    if not nf:
        return items
    require = nf.get("require_combo_with", [])
    exclude = nf.get("exclude_terms", [])
    filtered = []
    for it in items:
        text = (it["title"] + " " + it["summary"]).lower()
        if any(x.lower() in text for x in exclude):
            continue
        if require and not any(r.lower() in text for r in require):
            continue
        filtered.append(it)
    return filtered


def _normalize_title(title):
    """중복 판별용 제목 정규화: 언론사 접미사(- OO뉴스, - OO경제 등) 제거, 공백/기호 정리."""
    import re
    t = re.sub(r"\s*-\s*[가-힣A-Za-z0-9]+(뉴스|경제|일보|신문|저널|데일리|타임즈|타임스|투데이)?\s*$", "", title)
    t = re.sub(r"[^\w가-힣]", "", t)  # 공백/특수문자 제거
    return t.strip().lower()


def dedupe(items):
    seen = set()
    out = []
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        key = _normalize_title(it["title"])[:25]
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def collect_for_category(cat_key, cat_conf, since_hours=4, global_coverage=True):
    all_items = []
    for kw in cat_conf["keywords"]:
        all_items += search_naver_news(kw, display=5)
        all_items += search_google_news_rss(kw, lang="ko", country="KR")
        if global_coverage:
            all_items += search_google_news_rss(kw, lang="en", country="US")
        time.sleep(0.2)  # 과도한 호출 방지

    all_items = apply_noise_filter(all_items, cat_conf)

    cutoff = datetime.now(KST) - timedelta(hours=since_hours)
    recent = [it for it in all_items if it["published"] >= cutoff]
    return dedupe(recent)


def collect_all(keywords_conf, since_hours=4):
    results = {}
    for cat_key, cat_conf in keywords_conf["categories"].items():
        results[cat_key] = collect_for_category(cat_key, cat_conf, since_hours=since_hours)
    return results


def fetch_generic_rss(url, source_label):
    """표준 RSS 2.0 파서 (KOCCA 등 직접 확인된 기관 RSS용)."""
    try:
        raw = _http_get(url)
        root = ET.fromstring(raw)
    except Exception as e:
        print(f"[rss:{source_label}] {url} 조회 실패: {e}")
        return []

    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub = item.findtext("pubDate", "")
        desc = _strip_html(item.findtext("description", "") or "")
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
            try:
                pub_dt = datetime.strptime(pub, fmt)
                pub_dt = pub_dt.astimezone(KST) if pub_dt.tzinfo else pub_dt.replace(tzinfo=KST)
                break
            except Exception:
                pub_dt = None
        if pub_dt is None:
            pub_dt = datetime.now(KST)
        items.append({
            "title": title, "summary": desc[:80], "link": link,
            "published": pub_dt, "source": source_label, "query": source_label,
        })
    return items


def collect_affiliate_equity_news(company_names, since_hours=24):
    """관계기업(비상장 포함) 지분 변동 관련 뉴스. DART에 안 걸리는 비상장사 대비 백업 채널."""
    EQUITY_TERMS = ["지분", "최대주주", "매각", "인수", "증자", "지분매입", "지분율"]
    all_items = []
    for name in company_names:
        for term in EQUITY_TERMS:
            query = f"{name} {term}"
            all_items += search_naver_news(query, display=3)
        time.sleep(0.2)

    filtered = []
    for it in all_items:
        text = it["title"] + " " + it["summary"]
        if not any(name in text for name in company_names):
            continue
        filtered.append(it)

    cutoff = datetime.now(KST) - timedelta(hours=since_hours)
    recent = [it for it in filtered if it["published"] >= cutoff]
    return dedupe(recent)


def collect_institute_rss(verified_rss_conf, since_hours=14):
    """검증된 기관 RSS(KOCCA 등)에서 최근 항목만 수집. 09시 슬롯 위주로 사용."""
    all_items = []
    kocca_feeds = verified_rss_conf.get("kocca", {})
    for label, url in kocca_feeds.items():
        all_items += fetch_generic_rss(url, f"KOCCA·{label}")
        time.sleep(0.2)
    cutoff = datetime.now(KST) - timedelta(hours=since_hours)
    recent = [it for it in all_items if it["published"] >= cutoff]
    return dedupe(recent)
