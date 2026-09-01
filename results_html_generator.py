"""
results_html_generator.py — builds docs/results.html: the FULL historical
signal-performance dashboard (every prediction ever logged, not just the
trailing 7 days used in the Telegram summary).

NEW FILE. Imported and called by weekly_report.py at the end of every run
(scheduled or button-triggered) so the page is always current.

WHAT'S ON THE PAGE
--------------------
- Overall success rate + a per-category success-rate table, right at the top.
- A sticky filter bar (same click-to-filter pattern as the main dashboard's
  html_generator.py) so you can isolate one category without scrolling.
- Three collapsible sections: ✅ successful signals, ❌ unsuccessful signals,
  ⏳ still pending -- each a full table (date, market name/link, category,
  bot's signal, final resolved outcome, approximate return).

ABOUT THE "RETURN" (بازدهی) COLUMN
-------------------------------------
This is computed ONLY from the PRIMARY allocation (size_pct at market_price),
not the full hedged portfolio -- predictions_log.csv doesn't store enough
detail about secondary/hedge allocations to reconstruct exact total P&L, so
this is intentionally a simplified "what if you only took the primary bet"
number:
  - if correct:   return_pct = primary_size_pct * (1/primary_market_price - 1)
  - if incorrect: return_pct = -primary_size_pct   (entire primary stake lost)
Both expressed as a percent of your total position budget. Good enough to
see directional accuracy and rough magnitude; not a substitute for real P&L
accounting if you started actually trading these.
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime, timezone


def _escape(text) -> str:
    return html.escape(str(text), quote=True)


def _fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value or ""


def compute_return_pct(row: dict) -> float | None:
    try:
        size_pct = float(row.get("primary_size_pct") or 0)
        price = float(row.get("primary_market_price") or 0)
    except (TypeError, ValueError):
        return None
    if row.get("is_correct") == "True":
        if price <= 0:
            return None
        return round(size_pct * (1.0 / price - 1.0), 2)
    if row.get("is_correct") == "False":
        return round(-size_pct, 2)
    return None


def build_stats(rows: list[dict]) -> dict:
    decided = [r for r in rows if r.get("is_correct") in ("True", "False")]
    correct = [r for r in decided if r["is_correct"] == "True"]
    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in decided:
        cat = r.get("category") or "other"
        by_category[cat][1] += 1
        if r["is_correct"] == "True":
            by_category[cat][0] += 1
    return {
        "total": len(rows), "decided": len(decided), "correct": len(correct),
        "pending": len(rows) - len(decided),
        "overall_rate": (len(correct) / len(decided) * 100.0) if decided else None,
        "by_category": dict(by_category),
    }


def _render_row(row: dict) -> str:
    ret = compute_return_pct(row)
    ret_txt = f"{ret:+.1f}%" if ret is not None else "—"
    ret_color = "#57606a"
    if ret is not None:
        ret_color = "#1a7f37" if ret >= 0 else "#cf222e"
    url = row.get("market_url", "")
    title = row.get("title", "")
    name_html = f'<a href="{_escape(url)}" target="_blank" rel="noopener">{_escape(title)}</a>' if url else _escape(title)
    category = row.get("category", "")
    return f"""<tr data-category="{_escape(category)}">
<td>{_escape(_fmt_date(row.get('logged_at_utc', '')))}</td>
<td>{name_html}</td>
<td>{_escape(category)}</td>
<td>{_escape(row.get('primary_outcome', ''))}</td>
<td>{_escape(row.get('resolved_outcome', '') or '—')}</td>
<td style="color:{ret_color};font-weight:600">{ret_txt}</td>
</tr>"""


def _render_table(rows: list[dict]) -> str:
    if not rows:
        return '<p class="empty">موردی نیست.</p>'
    rows_sorted = sorted(rows, key=lambda r: r.get("logged_at_utc", ""), reverse=True)
    rows_html = "\n".join(_render_row(r) for r in rows_sorted)
    return f"""<table>
<thead><tr><th>تاریخ</th><th>نام بازار</th><th>دسته</th><th>سیگنال ربات</th><th>نتیجه‌ی نهایی</th><th>بازدهی (Primary)</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>"""


def _render_category_stats(by_category: dict[str, list[int]]) -> str:
    if not by_category:
        return ""
    rows = "".join(
        f"<tr><td>{_escape(cat)}</td><td>{c}/{t}</td><td>{(c / t * 100):.0f}%</td></tr>"
        for cat, (c, t) in sorted(by_category.items(), key=lambda kv: -kv[1][1])
    )
    return f"""<table class="category-stats">
<thead><tr><th>دسته</th><th>تعداد نتیجه‌دار</th><th>درصد موفقیت</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""


def build_results_html(rows: list[dict], generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    timestamp_txt = generated_at.strftime("%Y-%m-%d %H:%M UTC")
    stats = build_stats(rows)

    decided_rows = [r for r in rows if r.get("is_correct") in ("True", "False")]
    correct_rows = [r for r in decided_rows if r["is_correct"] == "True"]
    incorrect_rows = [r for r in decided_rows if r["is_correct"] == "False"]
    pending_rows = [r for r in rows if r.get("is_correct") not in ("True", "False")]

    categories = sorted({r.get("category", "") for r in rows if r.get("category")})
    nav_buttons = ['<button type="button" class="nav-btn active" data-target="all" onclick="filterCategory(this)">همه</button>']
    for cat in categories:
        nav_buttons.append(
            f'<button type="button" class="nav-btn" data-target="{_escape(cat)}" onclick="filterCategory(this)">{_escape(cat)}</button>'
        )

    overall_txt = f"{stats['overall_rate']:.1f}%" if stats["overall_rate"] is not None else "—"

    return f"""<!DOCTYPE html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PolyBet — تاریخچه‌ی نتایج سیگنال‌ها</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", Tahoma, sans-serif; max-width: 960px; margin: 0 auto; padding: 0 1rem 2rem; color: #1f2328; }}
h1 {{ font-size: 1.4rem; margin-top: 1.5rem; }}
.generated-at {{ color: #57606a; font-size: 0.85rem; margin-bottom: 1rem; }}
.summary-box {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem; background: #f6f8fa; }}
.big-stat {{ font-size: 1.2rem; margin-bottom: 0.5rem; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.88rem; margin-top: 0.6rem; }}
th, td {{ text-align: right; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eaeef2; }}
table.category-stats {{ max-width: 420px; }}
.section-nav {{ position: sticky; top: 0; z-index: 10; background: #fff; display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0.6rem 0; border-bottom: 1px solid #d0d7de; margin-bottom: 1rem; }}
.nav-btn {{ border: 1px solid #d0d7de; background: #f6f8fa; color: #1f2328; border-radius: 999px; padding: 0.35rem 0.85rem; font-size: 0.82rem; cursor: pointer; }}
.nav-btn.active {{ background: #0969da; border-color: #0969da; color: #fff; }}
.section-title {{ font-size: 1.05rem; padding: 0.6rem 0; cursor: pointer; }}
.section-title.success {{ color: #1a7f37; }}
.section-title.failure {{ color: #cf222e; }}
.section-title.pending {{ color: #9a6700; }}
.empty {{ color: #57606a; font-size: 0.85rem; }}
a {{ color: #0969da; text-decoration: none; }}
</style>
</head>
<body>
<h1>📈 تاریخچه‌ی کامل نتایج سیگنال‌های PolyBet</h1>
<p class="generated-at">به‌روزرسانی: {timestamp_txt}</p>

<div class="summary-box">
  <div class="big-stat">🎯 درصد موفقیت کلی: <strong>{overall_txt}</strong> ({stats['correct']}/{stats['decided']})</div>
  <div>🔢 کل سیگنال‌های ثبت‌شده: {stats['total']} &middot; نتیجه‌دار: {stats['decided']} &middot; در انتظار: {stats['pending']}</div>
  {_render_category_stats(stats['by_category'])}
</div>

<nav class="section-nav">{"".join(nav_buttons)}</nav>

<section>
<details open>
<summary class="section-title success">✅ سیگنال‌های موفق ({len(correct_rows)})</summary>
{_render_table(correct_rows)}
</details>
</section>

<section>
<details open>
<summary class="section-title failure">❌ سیگنال‌های ناموفق ({len(incorrect_rows)})</summary>
{_render_table(incorrect_rows)}
</details>
</section>

<section>
<details>
<summary class="section-title pending">⏳ در انتظار نتیجه ({len(pending_rows)})</summary>
{_render_table(pending_rows)}
</details>
</section>

<script>
function filterCategory(btn) {{
  const target = btn.getAttribute('data-target');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('tbody tr').forEach(tr => {{
    tr.style.display = (target === 'all' || tr.getAttribute('data-category') === target) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""


def write_results_html(path: str, rows: list[dict], generated_at: datetime | None = None) -> None:
    content = build_results_html(rows, generated_at=generated_at)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
