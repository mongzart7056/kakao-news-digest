"""
html_report.py
카카오톡 메시지에는 카테고리별 대표 기사 1건만 담고,
전체 수집 기사는 이 모듈이 생성하는 HTML 리포트에서 확인합니다.
GitHub Pages(docs/latest.html)로 발행되어 카카오 메시지에서 링크로 연결됩니다.

[변경 사항]
- 카테고리 레일(건수 뱃지) + 검색 + 카드 필터링 UI
- 매 실행마다의 다이제스트를 docs/archive/*.json 으로 누적 저장하고,
  latest.html에서 드롭다운으로 과거 다이제스트를 선택해 볼 수 있음
  (아카이브 파일 저장/인덱스 갱신은 main.py 쪽에서 처리, 여기서는
  JSON 스냅샷 문자열만 생성)
- 푸터를 저작권 표기로 변경

generate_html(generated_at_str, sections)의 시그니처와 반환값(완성 HTML 문자열)은
기존과 동일합니다.
"""
import html as html_lib
import json


def _escape(text):
    return html_lib.escape(text or "")


def _articles_list(sections):
    """sections: [(label, [item, ...]), ...] -> 평탄화된 dict 리스트.

    item 필드: title, summary(optional), published(datetime), source, link
    """
    articles = []
    for label, items in sections:
        for item in items:
            articles.append({
                "c": label,
                "t": item["title"] or "",
                "d": item.get("summary", "") or "",
                "s": item["source"] or "",
                "tm": item["published"].strftime("%m.%d %H:%M"),
                "link": item["link"] or "",
            })
    return articles


def _category_list(sections):
    """sections 순서를 유지한 카테고리 목록. 빈 섹션도 count 0으로 포함."""
    return [{"c": label, "count": len(items)} for label, items in sections]


def _articles_json_for_script(sections):
    """<script> 태그 안에 안전하게 주입할 수 있도록 이스케이프된 JSON 문자열."""
    return json.dumps(_articles_list(sections), ensure_ascii=False).replace("</script>", "<\\/script>")


def _categories_json_for_script(sections):
    """<script> 태그 안에 안전하게 주입할 수 있도록 이스케이프된 카테고리 JSON 문자열."""
    return json.dumps(_category_list(sections), ensure_ascii=False).replace("</script>", "<\\/script>")


def generate_archive_json(generated_at_str, sections):
    """아카이브 스냅샷용 순수 JSON 문자열 (별도 .json 파일로 저장됨).

    latest.html의 렌더링 로직이 그대로 재사용할 수 있도록
    {"generated_at": ..., "total": ..., "articles": [...]} 형태로 저장.
    """
    total = sum(len(items) for _, items in sections)
    payload = {
        "generated_at": generated_at_str,
        "total": total,
        "categories": _category_list(sections),
        "articles": _articles_list(sections),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_html(generated_at_str, sections):
    """sections: [(label, [item, ...]), ...] 순서대로 카테고리 레일에 표시"""
    total = sum(len(items) for _, items in sections)
    articles_json = _articles_json_for_script(sections)
    categories_json = _categories_json_for_script(sections)
    gen_str = _escape(generated_at_str)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI/딥테크 뉴스 다이제스트 — {gen_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root{{
    --ink:#14171f; --ink-2:#1b1f29; --panel:#1e2330; --panel-2:#242a38;
    --line:#2e3444; --gold:#c9a24b; --gold-dim:#8a7638; --teal:#5ec8bd;
    --text:#e9e8e2; --text-dim:#9aa0ad; --text-faint:#5f6572;
  }}
  *{{box-sizing:border-box;}}
  html,body{{margin:0;padding:0;}}
  body{{background:var(--ink);color:var(--text);font-family:'Inter',sans-serif;-webkit-font-smoothing:antialiased;}}
  a{{color:inherit;text-decoration:none;}}

  header{{padding:22px 24px 18px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:flex-end;flex-wrap:wrap;gap:14px;}}
  .brand-eyebrow{{font-family:'IBM Plex Mono',monospace;font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--gold);margin:0 0 6px;}}
  h1{{font-family:'Source Serif 4',serif;font-weight:700;font-size:22px;margin:0;color:var(--text);letter-spacing:-.01em;}}
  .meta-line{{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--text-dim);margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;}}
  .meta-line select{{
    background:var(--ink-2);color:var(--text);border:1px solid var(--line);
    border-radius:4px;font-family:'IBM Plex Mono',monospace;font-size:11px;
    padding:3px 6px;outline:none;cursor:pointer;
  }}
  .totalboard{{display:flex;align-items:baseline;gap:10px;font-family:'IBM Plex Mono',monospace;}}
  .totalboard .digits{{font-size:28px;font-weight:600;color:var(--gold);background:var(--ink-2);border:1px solid var(--line);border-radius:4px;padding:3px 10px;}}
  .totalboard .label{{font-size:10.5px;color:var(--text-faint);text-transform:uppercase;letter-spacing:.1em;}}

  .layout{{display:grid;grid-template-columns:220px 1fr;min-height:calc(100vh - 90px);}}
  @media (max-width:820px){{
    .layout{{grid-template-columns:1fr;}}
    nav.rail{{position:sticky;top:0;z-index:5;display:flex;overflow-x:auto;border-right:none;border-bottom:1px solid var(--line);padding:8px;gap:4px;background:var(--ink);}}
    nav.rail .cat{{border-left:none;border-bottom:2px solid transparent;white-space:nowrap;padding:7px 10px;}}
    nav.rail .cat.active{{border-bottom-color:var(--gold);border-left:none;background:transparent;}}
  }}
  nav.rail{{border-right:1px solid var(--line);padding:14px 0;background:var(--ink-2);}}
  nav.rail .cat{{display:flex;justify-content:space-between;align-items:center;padding:9px 16px;border-left:3px solid transparent;cursor:pointer;font-size:13px;color:var(--text-dim);transition:background .15s,color .15s;}}
  nav.rail .cat:hover{{background:var(--panel);color:var(--text);}}
  nav.rail .cat.active{{border-left-color:var(--gold);background:var(--panel);color:var(--text);font-weight:600;}}
  nav.rail .cat .count{{font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--text-faint);background:var(--ink);border:1px solid var(--line);border-radius:3px;padding:1px 6px;min-width:26px;text-align:center;}}
  nav.rail .cat.active .count{{color:var(--gold);border-color:var(--gold-dim);}}

  main{{padding:18px 22px 50px;}}
  .toolbar{{display:flex;gap:12px;align-items:center;margin-bottom:14px;flex-wrap:wrap;}}
  .toolbar input{{flex:1;min-width:160px;max-width:380px;background:var(--panel);border:1px solid var(--line);color:var(--text);font-family:'Inter',sans-serif;font-size:13px;padding:8px 12px;border-radius:6px;outline:none;}}
  .toolbar input:focus{{border-color:var(--gold-dim);}}
  .toolbar .current-cat{{font-family:'Source Serif 4',serif;font-size:17px;font-weight:600;color:var(--text);}}
  .toolbar .current-count{{font-family:'IBM Plex Mono',monospace;font-size:11.5px;color:var(--text-faint);}}

  .cards{{display:flex;flex-direction:column;gap:2px;}}
  .card{{display:grid;grid-template-columns:1fr auto;gap:5px 16px;padding:12px 14px;border-radius:6px;background:var(--panel);border:1px solid transparent;}}
  .card:hover{{border-color:var(--line);background:var(--panel-2);}}
  .card h3{{grid-column:1/2;font-family:'Source Serif 4',serif;font-weight:600;font-size:14.5px;margin:0;color:var(--text);line-height:1.4;}}
  .card p{{grid-column:1/2;margin:2px 0 0;font-size:12.5px;color:var(--text-dim);line-height:1.55;}}
  .card .meta{{grid-column:2/3;grid-row:1/3;display:flex;flex-direction:column;align-items:flex-end;justify-content:flex-start;gap:4px;font-family:'IBM Plex Mono',monospace;font-size:10.5px;color:var(--text-faint);white-space:nowrap;padding-top:2px;}}
  .card .meta .src{{color:var(--teal);}}

  .empty{{padding:50px 0;text-align:center;color:var(--text-faint);font-family:'IBM Plex Mono',monospace;font-size:12.5px;}}
  footer{{padding:16px 22px 36px;border-top:1px solid var(--line);font-family:'IBM Plex Mono',monospace;font-size:11px;color:var(--text-faint);}}
</style>
</head>
<body>

<header>
  <div>
    <p class="brand-eyebrow">RIMA / EmotionWave · Internal Wire</p>
    <h1>AI/딥테크 뉴스 다이제스트</h1>
    <p class="meta-line">
      <span id="meta-gen">{gen_str} KST 기준 자동 생성</span>
      <select id="archive-select" style="display:none;"></select>
    </p>
  </div>
  <div class="totalboard">
    <span class="digits" id="total-digits">{total}</span>
    <span class="label">건 수집</span>
  </div>
</header>

<div class="layout">
  <nav class="rail" id="rail"></nav>
  <main>
    <div class="toolbar">
      <span class="current-cat" id="current-cat">전체</span>
      <span class="current-count" id="current-count"></span>
      <input type="text" id="search" placeholder="제목·내용 검색…">
    </div>
    <div class="cards" id="cards"></div>
    <div class="empty" id="empty" style="display:none;">검색 결과가 없습니다.</div>
  </main>
</div>

<footer>(C) Copyright Saint Seonghyeon Park</footer>

<script>
const CURRENT_ARTICLES = {articles_json};
const CURRENT_CATEGORIES = {categories_json};
const CURRENT_TOTAL = {total};
const CURRENT_GEN = "{gen_str}";

let ARTICLES = CURRENT_ARTICLES;
let CATEGORIES = CURRENT_CATEGORIES;
let active = "전체";

function categoriesFromArticles(articles){{
  const counts = new Map();
  articles.forEach(a => counts.set(a.c, (counts.get(a.c) || 0) + 1));
  return [...counts.entries()].map(([c, count]) => ({{ c, count }}));
}}

function renderRail(){{
  const rail = document.getElementById('rail');
  rail.innerHTML = "";
  rail.appendChild(makeRow("전체", ARTICLES.length));
  CATEGORIES.forEach(cat => rail.appendChild(makeRow(cat.c, cat.count)));
}}
function makeRow(name, count){{
  const el = document.createElement('div');
  el.className = 'cat' + (name === active ? ' active' : '');
  el.innerHTML = `<span>${{name}}</span><span class="count">${{count}}</span>`;
  el.onclick = () => {{ active = name; renderRail(); renderCards(); }};
  return el;
}}
function renderCards(){{
  const q = document.getElementById('search').value.trim().toLowerCase();
  let list = active === "전체" ? ARTICLES : ARTICLES.filter(a => a.c === active);
  if (q) list = list.filter(a => (a.t + a.d).toLowerCase().includes(q));

  document.getElementById('current-cat').textContent = active;
  document.getElementById('current-count').textContent = list.length + "건";

  const wrap = document.getElementById('cards');
  const empty = document.getElementById('empty');
  wrap.innerHTML = "";
  if (list.length === 0) {{ empty.style.display = 'block'; return; }}
  empty.style.display = 'none';

  list.forEach(a => {{
    const card = document.createElement('a');
    card.className = 'card';
    card.href = a.link;
    card.target = '_blank';
    card.rel = 'noopener';
    card.innerHTML = `
      <h3>${{a.t}}</h3>
      ${{a.d ? `<p>${{a.d}}</p>` : ''}}
      <div class="meta"><span class="src">${{a.s}}</span><span>${{a.tm}}</span></div>
    `;
    wrap.appendChild(card);
  }});
}}

// ---- 과거 다이제스트 아카이브 ----
async function loadArchiveList(){{
  const sel = document.getElementById('archive-select');
  try {{
    const res = await fetch('archive/index.json', {{ cache: 'no-store' }});
    if (!res.ok) return;
    const list = await res.json();
    if (!Array.isArray(list) || list.length === 0) return;

    sel.innerHTML = '<option value="__current__">최신 (' + CURRENT_GEN + ')</option>' +
      list.map(e => `<option value="${{e.file}}">${{e.label}}</option>`).join('');
    sel.style.display = 'inline-block';
    sel.onchange = onArchiveChange;
  }} catch (e) {{
    // 아카이브가 아직 없거나 fetch 실패 시 드롭다운 없이 현재 화면 그대로 유지
  }}
}}
async function onArchiveChange(e){{
  const val = e.target.value;
  if (val === '__current__') {{
    ARTICLES = CURRENT_ARTICLES;
    CATEGORIES = CURRENT_CATEGORIES;
    document.getElementById('meta-gen').textContent = CURRENT_GEN + ' KST 기준 자동 생성';
    document.getElementById('total-digits').textContent = CURRENT_TOTAL;
  }} else {{
    try {{
      const res = await fetch('archive/' + val, {{ cache: 'no-store' }});
      const data = await res.json();
      ARTICLES = data.articles || [];
      CATEGORIES = data.categories || categoriesFromArticles(ARTICLES);
      document.getElementById('meta-gen').textContent = data.generated_at + ' KST 기준 (지난 다이제스트)';
      document.getElementById('total-digits').textContent = data.total;
    }} catch (err) {{
      return;
    }}
  }}
  active = "전체";
  renderRail();
  renderCards();
}}

document.getElementById('search').addEventListener('input', renderCards);
renderRail();
renderCards();
loadArchiveList();
</script>
</body>
</html>"""
