"""
news_collector.py
국내(네이버 뉴스 검색 API) + 해외(Google News RSS) 기사를 키워드 기준으로 수집.
카테고리별 noise filter(콘텐츠 IP/저작권 등)도 여기서 적용합니다.
"""
import os
import json
import html as html_lib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

NAVER_CLIENT_ID = os.environ.get("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.environ.get("NAVER_CLIENT_SECRET", "")

DEFAULT_POLICY_NOTICE_TERMS = [
    "공고", "모집", "공모", "지원사업", "사업공고", "과제공고", "정부과제",
    "R&D", "연구개발", "입찰", "용역", "제안요청서", "RFP", "수행기관", "참여기업",
]


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
    text = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    return re.sub("<[^<]+?>", "", text).replace("&quot;", '"').replace("&amp;", "&")


def _clean_text(text):
    text = html_lib.unescape(_strip_html(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def apply_noise_filter(items, category_conf):
    nf = category_conf.get("noise_filter")
    if not nf:
        return items
    require = nf.get("require_combo_with", [])
    require_any = nf.get("require_any_terms", [])
    exclude = nf.get("exclude_terms", [])
    include_query = nf.get("include_query_in_filter", False)
    filtered = []
    for it in items:
        text_parts = [it["title"], it["summary"]]
        if include_query:
            text_parts.append(it.get("query", ""))
        text = " ".join(text_parts).lower()
        if any(x.lower() in text for x in exclude):
            continue
        if require_any and not any(r.lower() in text for r in require_any):
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


def _has_any(text, terms):
    haystack = (text or "").lower()
    return any((term or "").lower() in haystack for term in terms)


def _absolute_url(url, base_url):
    if not url or url.startswith("#") or url.startswith("javascript:"):
        return base_url
    return urllib.parse.urljoin(base_url, html_lib.unescape(url))


def _row_dates_text(text):
    dates = []
    for m in re.finditer(r"20\d{2}\s*[.\-]\s*\d{1,2}\s*[.\-]\s*\d{1,2}\.?", text):
        date_text = re.sub(r"\s+", "", m.group(0)).rstrip(".")
        if date_text not in dates:
            dates.append(date_text)
    return dates


def _is_closed_notice_block(text):
    compact = _clean_text(text)
    closed_terms = ["종료", "(마감)", "접수마감", "모집마감", "마감완료"]
    return any(term in compact for term in closed_terms)


def _policy_notice_item(title, summary, link, source, query, force_notice=False):
    return {
        "title": title,
        "summary": summary,
        "link": link,
        "published": datetime.now(KST),
        "source": source,
        "query": query,
        "force_policy_notice": force_notice,
    }


def _source_max_items(source_conf):
    try:
        return max(1, int(source_conf.get("max_items", 10)))
    except (TypeError, ValueError):
        return 10


def _source_include_ok(title, summary, source_conf):
    include_terms = source_conf.get("include_terms", [])
    exclude_terms = source_conf.get("exclude_terms", [])
    text = f"{title} {summary}"
    if include_terms and not _has_any(text, include_terms):
        return False
    if exclude_terms and _has_any(text, exclude_terms):
        return False
    return True


def _extract_mss_board_link(row, base_url):
    m = re.search(
        r"doBbsFView\('([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']+)'\)",
        row,
    )
    if not m:
        return base_url
    cb_idx, bc_idx, _, parent_seq = m.groups()
    return urllib.parse.urljoin(
        base_url,
        f"/site/smba/ex/bbs/View.do?cbIdx={cb_idx}&bcIdx={bc_idx}&parentSeq={parent_seq}",
    )


def _anchor_title_and_link(anchor, row, source_conf):
    attrs_match = re.match(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", anchor, re.S | re.I)
    if not attrs_match:
        return "", source_conf.get("base_url", source_conf.get("url", ""))

    attrs = attrs_match.group("attrs")
    body = attrs_match.group("body")
    title_attr = re.search(r'title\s*=\s*["\']([^"\']+)["\']', attrs, re.S | re.I)
    href_attr = re.search(r'href\s*=\s*["\']([^"\']*)["\']', attrs, re.S | re.I)
    title = _clean_text(title_attr.group(1) if title_attr else body)
    title = re.sub(r"\s*(페이지 이동|새 창 열림|상세보기)\s*$", "", title).strip()

    href = href_attr.group(1) if href_attr else ""
    base_url = source_conf.get("base_url", source_conf.get("url", ""))
    if source_conf.get("parser") == "mss_board" and (not href or href.startswith("#")):
        link = _extract_mss_board_link(row, base_url)
    else:
        link = _absolute_url(href, base_url)
    return title, link


def _parse_table_link_notices(html_text, source_conf):
    items = []
    max_items = _source_max_items(source_conf)
    source_label = source_conf.get("label", "공식 공고")
    force_notice = bool(source_conf.get("force_notice", False))
    rows = re.findall(r"<tr\b.*?</tr>", html_text, flags=re.S | re.I)

    for row in rows:
        if len(items) >= max_items:
            break
        if _is_closed_notice_block(row):
            continue

        anchors = re.findall(r"<a\b[^>]*>.*?</a>", row, flags=re.S | re.I)
        for anchor in anchors:
            title, link = _anchor_title_and_link(anchor, row, source_conf)
            if not title or title in {"사업공고", "입찰공고", "모집중", "공지", "지원사업 공고"}:
                continue

            row_text = _clean_text(row)
            dates = _row_dates_text(row_text)
            summary_parts = []
            if dates:
                summary_parts.append("일정: " + " ~ ".join(dates[:2]))
            if source_conf.get("summary_prefix"):
                summary_parts.insert(0, source_conf["summary_prefix"])
            summary = " | ".join(summary_parts) or source_label
            if not _source_include_ok(title, summary + " " + row_text, source_conf):
                continue

            items.append(_policy_notice_item(
                title=title,
                summary=summary,
                link=link,
                source=source_label,
                query=source_label,
                force_notice=force_notice,
            ))
            break
    return items


def _parse_iris_main_notices(html_text, source_conf):
    items = []
    max_items = _source_max_items(source_conf)
    source_label = source_conf.get("label", "IRIS·사업공고")
    list_url = source_conf.get("list_url") or source_conf.get("url")
    base_url = source_conf.get("base_url", source_conf.get("url", ""))

    for match in re.finditer(
        r"<a\b(?=[^>]*f_bsnsAncmBtinSituListForm_view)[^>]*>(?P<body>.*?)</a>",
        html_text,
        flags=re.S | re.I,
    ):
        if len(items) >= max_items:
            break
        block = match.group(0)
        if _is_closed_notice_block(block):
            continue

        title_match = re.search(r'<strong[^>]*class="title"[^>]*>(.*?)</strong>', block, re.S | re.I)
        if not title_match:
            continue
        title = _clean_text(title_match.group(1))
        status_match = re.search(r'<span[^>]*class="status[^"]*"[^>]*>(.*?)</span>', block, re.S | re.I)
        departments = [
            _clean_text(v)
            for v in re.findall(r'<p[^>]*class="department"[^>]*>(.*?)</p>', block, re.S | re.I)
        ]
        period_match = re.search(r'<p[^>]*class="period"[^>]*>(.*?)</p>', block, re.S | re.I)

        summary_parts = []
        if status_match:
            summary_parts.append("상태: " + _clean_text(status_match.group(1)))
        if departments:
            summary_parts.append("기관: " + " / ".join(departments[:2]))
        if period_match:
            summary_parts.append("기간: " + _clean_text(period_match.group(1)))
        summary = " | ".join(summary_parts) or source_label
        if not _source_include_ok(title, summary, source_conf):
            continue

        items.append(_policy_notice_item(
            title=title,
            summary=summary,
            link=_absolute_url(list_url, base_url),
            source=source_label,
            query=source_label,
            force_notice=True,
        ))
    return items


def fetch_html_notice_source(source_conf):
    """RSS가 없는 공식 공고 목록 페이지를 직접 파싱."""
    url = source_conf.get("url", "")
    if not url:
        return []

    try:
        raw = _http_get(url, headers={"User-Agent": "Mozilla/5.0"})
        html_text = raw.decode(source_conf.get("encoding", "utf-8"), errors="ignore")
    except Exception as e:
        print(f"[notice:{source_conf.get('label', url)}] {url} 조회 실패: {e}")
        return []

    parser = source_conf.get("parser", "table_links")
    if parser == "iris_main":
        return _parse_iris_main_notices(html_text, source_conf)
    return _parse_table_link_notices(html_text, source_conf)


def _is_policy_notice_item(item, category_conf):
    """정책자금/지원사업은 일반 뉴스보다 실제 공고성 항목만 통과."""
    text = " ".join([
        item.get("title", ""),
        item.get("summary", ""),
        item.get("link", ""),
    ])
    notice_terms = category_conf.get("notice_terms", DEFAULT_POLICY_NOTICE_TERMS)
    exclude_terms = category_conf.get("exclude_terms", [])
    if exclude_terms and _has_any(text, exclude_terms):
        return False
    if item.get("force_policy_notice"):
        return True
    return _has_any(text, notice_terms)


def collect_policy_notices(category_conf, since_hours=4):
    """지원사업/정부과제/용역공고성 항목 전용 수집."""
    all_items = []
    effective_since = max(since_hours, int(category_conf.get("min_lookback_hours", since_hours)))

    for label, url in category_conf.get("rss_feeds", {}).items():
        all_items += fetch_generic_rss(url, label)
        time.sleep(0.2)

    for source_conf in category_conf.get("html_notice_sources", []):
        all_items += fetch_html_notice_source(source_conf)
        time.sleep(0.2)

    for query in category_conf.get("notice_searches", category_conf.get("keywords", [])):
        all_items += search_google_news_rss(query, lang="ko", country="KR")
        time.sleep(0.2)

    if category_conf.get("include_naver_news_backup", False):
        for query in category_conf.get("notice_searches", category_conf.get("keywords", [])):
            all_items += search_naver_news(query, display=3)
            time.sleep(0.2)

    cutoff = datetime.now(KST) - timedelta(hours=effective_since)
    recent = [
        it for it in all_items
        if it["published"] >= cutoff and _is_policy_notice_item(it, category_conf)
    ]
    return dedupe(recent)


def collect_for_category(cat_key, cat_conf, since_hours=4, global_coverage=True):
    if cat_conf.get("source_type") == "policy_notices":
        return collect_policy_notices(cat_conf, since_hours=since_hours)

    effective_since = max(since_hours, int(cat_conf.get("min_lookback_hours", since_hours)))
    all_items = []
    for kw in cat_conf["keywords"]:
        all_items += search_naver_news(kw, display=5)
        all_items += search_google_news_rss(kw, lang="ko", country="KR")
        if global_coverage:
            all_items += search_google_news_rss(kw, lang="en", country="US")
        time.sleep(0.2)  # 과도한 호출 방지

    all_items = apply_noise_filter(all_items, cat_conf)

    cutoff = datetime.now(KST) - timedelta(hours=effective_since)
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
