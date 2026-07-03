"""
html_report.py
카카오톡 메시지에는 카테고리별 대표 기사 1건만 담고,
전체 수집 기사는 이 모듈이 생성하는 HTML 리포트에서 확인합니다.
GitHub Pages(docs/latest.html)로 발행되어 카카오 메시지에서 링크로 연결됩니다.
"""
import html as html_lib


def _escape(text):
    return html_lib.escape(text or "")


def _article_html(item):
    title = _escape(item["title"])
    summary = _escape(item.get("summary", ""))
    date_str = item["published"].strftime("%m.%d %H:%M")
    source = _escape(item["source"])
    link = _escape(item["link"])
    summary_html = f'<p class="summary">{summary}</p>' if summary else ""
    return f"""
    <a class="card" href="{link}" target="_blank" rel="noopener">
      <p class="title">{title}</p>
      {summary_html}
      <p class="meta">{source} · {date_str}</p>
    </a>
    """


def _section_html(label, items):
    if not items:
        return ""
    cards = "\n".join(_article_html(it) for it in items)
    return f"""
    <section>
      <h2>{_escape(label)} <span class="count">{len(items)}</span></h2>
      {cards}
    </section>
    """


def generate_html(generated_at_str, sections):
    """sections: [(label, [item, ...]), ...] 순서대로 렌더링"""
    body = "\n".join(_section_html(label, items) for label, items in sections)
    total = sum(len(items) for _, items in sections)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI/딥테크 뉴스 다이제스트 — {_escape(generated_at_str)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 16px;
    font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
    background: #f5f5f7; color: #1c1c1e; line-height: 1.5;
  }}
  header {{ margin-bottom: 20px; }}
  header h1 {{ font-size: 20px; margin: 0 0 4px; }}
  header p {{ font-size: 13px; color: #6e6e73; margin: 0; }}
  section {{ margin-bottom: 28px; }}
  h2 {{
    font-size: 15px; font-weight: 700; color: #444;
    border-left: 4px solid #4a7cff; padding-left: 8px;
    margin: 0 0 10px; display: flex; align-items: center; gap: 6px;
  }}
  .count {{
    font-size: 11px; font-weight: 500; color: #fff; background: #4a7cff;
    border-radius: 10px; padding: 1px 7px;
  }}
  .card {{
    display: block; background: #fff; border-radius: 12px;
    padding: 12px 14px; margin-bottom: 8px; text-decoration: none; color: inherit;
    box-shadow: 0 1px 2px rgba(0,0,0,0.06);
  }}
  .card:active {{ background: #eee; }}
  .title {{ font-size: 14.5px; font-weight: 600; margin: 0 0 4px; color: #111; }}
  .summary {{ font-size: 13px; color: #555; margin: 0 0 6px; }}
  .meta {{ font-size: 11.5px; color: #999; margin: 0; }}
  footer {{ text-align: center; font-size: 11px; color: #aaa; padding: 20px 0 8px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #000; color: #f2f2f2; }}
    .card {{ background: #1c1c1e; box-shadow: none; }}
    .title {{ color: #fff; }}
    .summary {{ color: #bbb; }}
    h2 {{ color: #ddd; }}
  }}
</style>
</head>
<body>
<header>
  <h1>🗞 AI/딥테크 뉴스 다이제스트</h1>
  <p>{_escape(generated_at_str)} KST · 총 {total}건</p>
</header>
{body}
<footer>자동 생성 · 리마엔터테인먼트 / 이모션웨이브 개인용</footer>
</body>
</html>"""
