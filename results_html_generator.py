"""
results_html_generator.py — PolyBet v2.0 Portfolio-Aware Results Dashboard Generator.

REPLACES your current results_html_generator.py.

KEY FIXES IN THIS VERSION:
1. FIX BUG #2 (Portfolio-Aware Multi-Leg Return Calculation):
   Previously `compute_return_pct(row)` ignored `(100 - primary_size_pct)` spent on
   secondary/hedge legs when Primary won, and ignored secondary/hedge payouts when
   Primary lost!
   Now `compute_return_pct(row, log_row)` accounts for total committed capital and
   checks if the resolved winner matched a Secondary or Hedge allocation.
"""

from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import datetime, timezone

CATEGORY_COLORS = {
    "elections": "#8250df", "fed": "#0969da", "cpi": "#0969da", "pce": "#0969da",
    "gdp": "#0969da", "employment": "#0969da", "ecb": "#0969da", "boc": "#0969da",
    "boe": "#0969da", "central_banks_other": "#57606a", "stocks": "#1a7f37",
    "commodities": "#9a6700", "crypto": "#cf222e",
}
DEFAULT_CATEGORY_COLOR = "#57606a"


def _escape(text) -> str:
    return html.escape(str(text), quote=True)


def _fmt_date(value: str) -> str:
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return value or ""


def parse_secondary_summary(summary: str) -> list[tuple[str, str, float]]:
    if not summary:
        return []
    out: list[tuple[str, str, float]] = []
    for part in summary.split(";"):
        m = re.match(r"^\s*(secondary|hedge):(.+)=([\d.]+)%\s*$", part.strip(), re.I)
        if m:
            out.append((m.group(1).lower(), m.group(2).strip(), float(m.group(3))))
    return out


def compute_return_pct(row: dict, log_row: dict | None = None) -> float | None:
    """FIX BUG #2: Multi-leg portfolio return accounting."""
    try:
        size_pct = float(row.get("primary_size_pct") or 0)
        price = float(row.get("primary_market_price") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0:
        return None

    sec_legs = parse_secondary_summary((log_row or {}).get("hedge_or_secondary_summary", ""))
    sec_total = sum(sz for _, _, sz in sec_legs)
    total_committed = min(100.0, size_pct + sec_total)

    if row.get("is_correct") == "True":
        gross_payout = size_pct / price
        return round(gross_payout - total_committed, 2)

    if row.get("is_correct") == "False":
        resolved_norm = (row.get("resolved_outcome") or "").strip().lower()
        for _role, outcome, leg_size in sec_legs:
            if outcome.lower() == resolved_norm and sec_total > 0:
                implied_price = min(0.5, max(0.05, (1.0 - price) * (leg_size / sec_total)))
                gross_payout = min(115.0, leg_size / implied_price)
                return round(gross_payout - total_committed, 2)
        return round(-total_committed, 2)
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


def _category_badge(category: str) -> str:
    color = CATEGORY_COLORS.get(category, DEFAULT_CATEGORY_COLOR)
    return f'<span class="cat-badge" style="background:{color}1a;color:{color}">{_escape(category or "—")}</span>'


def _render_row(row: dict, log_by_key: dict[str, dict] | None = None) -> str:
    log_row = (log_by_key or {}).get(row.get("group_key", ""))
    ret = compute_return_pct(row, log_row)
    if ret is None:
        ret_html = '<span class="ret-pill ret-neutral">—</span>'
    else:
        cls = "ret-positive" if ret >= 0 else "ret-negative"
        ret_html = f'<span class="ret-pill {cls}" dir="ltr">{ret:+.1f}%</span>'

    url = (row.get("market_url") or "").strip()
    link_html = f'<a class="row-link" href="{_escape(url)}" target="_blank" rel="noopener">🔗 مشاهده بازار</a>' if url else '<span class="empty-link">—</span>'

    category = row.get("category", "")
    return f"""<tr data-category="{_escape(category)}">
<td class="col-date">{_escape(_fmt_date(row.get('logged_at_utc', '')))}</td>
<td class="col-title">{_escape(row.get('title', ''))}</td>
<td>{_category_badge(category)}</td>
<td>{_escape(row.get('primary_outcome', ''))}</td>
<td><strong>{_escape(row.get('resolved_outcome', '') or '—')}</strong></td>
<td>{ret_html}</td>
<td>{link_html}</td>
</tr>"""


def _render_table(rows: list[dict], log_by_key: dict[str, dict] | None = None) -> str:
    if not rows:
        return '<p class="empty">موردی نیست.</p>'
    rows_sorted = sorted(rows, key=lambda r: r.get("logged_at_utc", ""), reverse=True)
    rows_html = "\n".join(_render_row(r, log_by_key) for r in rows_sorted)
    return f"""<div class="table-wrap">
<table>
<thead><tr><th>تاریخ</th><th>نام بازار</th><th>دسته</th><th>سیگنال ربات</th><th>باکت/نتیجه‌ی برنده</th><th>بازدهی خالص سبد</th><th>لینک</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>"""


def _render_category_stats(by_category: dict[str, list[int]]) -> str:
    if not by_category:
        return ""
    cards = "".join(
        f'<div class="cat-stat-card">{_category_badge(cat)}<div class="cat-stat-num">{c}/{t}</div><div class="cat-stat-rate">{(c / t * 100):.0f}% موفقیت</div></div>'
        for cat, (c, t) in sorted(by_category.items(), key=lambda kv: -kv[1][1])
    )
    return f'<div class="cat-stat-grid">{cards}</div>'


def build_results_html(
    rows: list[dict],
    generated_at: datetime | None = None,
    log_by_key: dict[str, dict] | None = None,
) -> str:
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
<title>PolyBet v2.0 — تاریخچه‌ی نتایج سیگنال‌ها</title>
<style>
* {{ box-sizing: border-box; }}
body {{
  font-family: "Vazirmatn", "Segoe UI", Tahoma, -apple-system, sans-serif;
  max-width: 1100px; margin: 0 auto; padding: 0 1.25rem 3rem;
  background: #f6f8fa; color: #1f2328; line-height: 1.6;
}}
h1 {{ font-size: 1.5rem; margin-top: 1.75rem; }}
.generated-at {{ color: #6e7781; font-size: 0.85rem; margin-bottom: 1.25rem; }}
.summary-box {{ background: #fff; border-radius: 14px; padding: 1.5rem 1.75rem; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(31,35,40,0.08); }}
.big-stat {{ font-size: 1.4rem; margin-bottom: 0.75rem; }}
.big-stat strong {{ color: #0969da; }}
.sub-stats {{ color: #57606a; font-size: 0.9rem; margin-bottom: 1rem; }}
.cat-stat-grid {{ display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.5rem; }}
.cat-stat-card {{ background: #f6f8fa; border-radius: 10px; padding: 0.75rem 1rem; min-width: 130px; text-align: center; }}
.cat-stat-num {{ font-size: 1.1rem; font-weight: 700; margin-top: 0.4rem; }}
.cat-stat-rate {{ font-size: 0.78rem; color: #57606a; }}
.section-nav {{ position: sticky; top: 0; z-index: 10; background: #f6f8fa; display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0.75rem 0; margin-bottom: 1.25rem; }}
.nav-btn {{ border: 1px solid #d0d7de; background: #fff; color: #1f2328; border-radius: 999px; padding: 0.4rem 1rem; font-size: 0.85rem; cursor: pointer; }}
.nav-btn.active {{ background: #0969da; border-color: #0969da; color: #fff; }}
section {{ background: #fff; border-radius: 14px; padding: 0.5rem 1.5rem 1.25rem; margin-bottom: 1.25rem; box-shadow: 0 1px 3px rgba(31,35,40,0.08); }}
summary.section-title {{ font-size: 1.05rem; padding: 1rem 0; cursor: pointer; font-weight: 700; }}
.section-title.success {{ color: #1a7f37; }}
.section-title.failure {{ color: #cf222e; }}
.section-title.pending {{ color: #9a6700; }}
.table-wrap {{ overflow-x: auto; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; min-width: 720px; }}
th {{ text-align: right; padding: 0.6rem 0.7rem; color: #57606a; font-weight: 600; border-bottom: 2px solid #eaeef2; white-space: nowrap; }}
td {{ text-align: right; padding: 0.65rem 0.7rem; border-bottom: 1px solid #eaeef2; vertical-align: middle; }}
.cat-badge {{ padding: 0.2rem 0.6rem; border-radius: 999px; font-size: 0.78rem; font-weight: 600; }}
.ret-pill {{ padding: 0.2rem 0.55rem; border-radius: 6px; font-weight: 700; font-size: 0.8rem; display: inline-block; }}
.ret-positive {{ background: #dafbe1; color: #1a7f37; }}
.ret-negative {{ background: #ffebe9; color: #cf222e; }}
.ret-neutral {{ background: #f6f8fa; color: #6e7781; }}
.row-link {{ display: inline-block; background: #0969da; color: #fff !important; padding: 0.3rem 0.7rem; border-radius: 6px; font-size: 0.78rem; text-decoration: none; }}
</style>
</head>
<body>
<h1>📈 تاریخچه‌ی کامل نتایج سیگنال‌های PolyBet v2.0</h1>
<p class="generated-at">به‌روزرسانی: {timestamp_txt}</p>
<div class="summary-box">
  <div class="big-stat">🎯 درصد موفقیت کلی: <strong>{overall_txt}</strong> <span style="color:#57606a;font-size:0.9rem">({stats['correct']}/{stats['decided']})</span></div>
  <div class="sub-stats">🔢 کل سیگنال‌ها: {stats['total']} &nbsp;·&nbsp; نتیجه‌دار: {stats['decided']} &nbsp;·&nbsp; در انتظار: {stats['pending']}</div>
  {_render_category_stats(stats['by_category'])}
</div>
<nav class="section-nav">{"".join(nav_buttons)}</nav>
<section><details open><summary class="section-title success">✅ سیگنال‌های موفق ({len(correct_rows)})</summary>{_render_table(correct_rows, log_by_key)}</details></section>
<section><details open><summary class="section-title failure">❌ سیگنال‌های ناموفق ({len(incorrect_rows)})</summary>{_render_table(incorrect_rows, log_by_key)}</details></section>
<section><details><summary class="section-title pending">⏳ در انتظار نتیجه ({len(pending_rows)})</summary>{_render_table(pending_rows, log_by_key)}</details></section>
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


def write_results_html(
    path: str,
    rows: list[dict],
    generated_at: datetime | None = None,
    log_by_key: dict[str, dict] | None = None,
) -> None:
    content = build_results_html(rows, generated_at=generated_at, log_by_key=log_by_key)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
