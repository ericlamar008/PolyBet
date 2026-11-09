"""
html_generator.py — Phase 5 + AI Analysis Layer (Phase 3) + Phase 6
(category sections) + Phase 6.1 (sticky top nav / tab filter).

REPLACES your current html_generator.py.

WHAT CHANGED vs your last version
----------------------------------
Card rendering (signal line, guaranteed-margin line, warning line, full
position-plan table, AI Analysis button/widget) and the section-bucketing
logic (high-confidence / politics / economy / markets / other) are UNCHANGED
from the version you just verified worked correctly.

The only new thing: a sticky nav bar right under the <h1>, with one button
per non-empty section (plus "All"). Clicking a button does NOT scroll the
page — it filters in place, hiding every section except the one you picked
(pure CSS display:none toggling via a tiny inline <script>, no page reload,
no anchor-jump). The nav bar stays pinned to the top (position: sticky) while
you scroll through a section's cards, so you can switch categories again
without scrolling back up.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from position_logic import PositionPlan
from scanner import ScannedMarket

ROLE_LABELS = {"primary": "Primary", "secondary": "Secondary", "hedge": "Hedge"}
ROLE_COLORS = {"primary": "#1a7f37", "secondary": "#0969da", "hedge": "#9a6700"}

# TODO: if you ever redeploy the Worker under a different name/URL,
# update this constant. This is a public URL, not a secret.
AI_WORKER_URL = "https://polybet-ai-research.ericlamar008.workers.dev/"

# ---------------------------------------------------------------------------
# Section definitions for the dashboard. Order here = order of both the nav
# bar buttons and the sections on the page.
# ---------------------------------------------------------------------------

HIGH_CONFIDENCE_PRICE_THRESHOLD = 0.90  # primary market price >= this -> "high confidence" bucket

HIGH_CONFIDENCE_KEY = "high_confidence"
HIGH_CONFIDENCE_LABEL = "⭐ احتمال بالا"
HIGH_CONFIDENCE_ICON = "⭐"

SECTION_DEFS: list[tuple[str, str, str, frozenset[str]]] = [
    # (section_key, nav_label, section_title, categories_in_this_section)
    ("politics", "🗳️ سیاسی", "🗳️ سیاسی و انتخابات (Politics & Elections)", frozenset({"elections"})),
    (
        "economy",
        "📊 اقتصادی",
        "📊 اقتصاد و بانک‌های مرکزی (Economy & Central Banks)",
        frozenset(
            {
                "fed", "cpi", "pce", "gdp", "employment",
                "ecb", "boc", "boe", "central_banks_other",
            }
        ),
    ),
    (
        "markets",
        "💰 بازارهای مالی",
        "💰 بازارهای مالی (Stocks, Commodities & Crypto)",
        frozenset({"stocks", "commodities", "crypto"}),
    ),
]
OTHER_KEY = "other"
OTHER_NAV_LABEL = "🔎 سایر"
OTHER_SECTION_LABEL = "🔎 سایر (Other)"


def _escape(text) -> str:
    return html.escape(str(text), quote=True)


def _render_allocation_row(alloc) -> str:
    color = ROLE_COLORS.get(alloc.role, "#57606a")
    label = ROLE_LABELS.get(alloc.role, alloc.role)
    price_txt = f"{alloc.market_price:.2f}" if alloc.market_price is not None else "—"
    return (
        f'<tr><td style="color:{color};font-weight:600">{label}</td>'
        f"<td>{_escape(alloc.outcome)}</td>"
        f"<td>{alloc.size_pct:.1f}%</td>"
        f"<td>{price_txt}</td></tr>"
    )


def _render_ai_widget(market: ScannedMarket) -> str:
    """Renders the manual "AI Analysis" button + empty result container for
    one market card. Nothing here runs automatically; the Worker is only
    called when the user clicks the button in their browser."""
    payload = {
        "market_id": market.market_id,
        "question": market.question,
        "outcomes": market.outcomes,
        "outcome_prices": market.outcome_prices,
        "end_date": market.end_date.isoformat() if market.end_date else None,
        "category": market.category,
    }
    payload_json = json.dumps(payload)
    payload_attr = _escape(payload_json)
    result_id = f"ai-result-{_escape(market.market_id)}"
    return (
        '<div class="ai-widget">'
        f'<button type="button" class="ai-btn" data-market="{payload_attr}" '
        'onclick="runAiAnalysis(this)">🧠 AI Analysis</button>'
        f'<div class="ai-result" id="{result_id}"></div>'
        "</div>"
    )


def _confidence_badge(market_price: float | None) -> str:
    if market_price is None:
        return ""
    return f'<span class="confidence-badge">⭐ {market_price * 100:.1f}%</span>'


def _render_card(market: ScannedMarket, title: str, plan: PositionPlan, days_to_resolve: float, *, show_confidence_badge: bool = False) -> str:
    warning_html = f'<p class="warning">⚠️ {_escape(plan.warning)}</p>' if plan.warning else ""

    primary = plan.primary
    if primary is not None:
        signal_html = (
            '<p class="signal">🎯 Signal: '
            f"<strong>{_escape(primary.outcome)}</strong> "
            f"— {primary.size_pct:.1f}% "
            f"(market price {primary.market_price:.2f})</p>"
        )
    else:
        signal_html = '<p class="signal">🎯 Signal: unavailable</p>'

    # Guaranteed-margin line, from position_logic.py's floor-sizing fix.
    margin_html = ""
    if plan.guaranteed_margin_pct is not None:
        margin_html = (
            '<p class="margin">✅ Guaranteed net if primary wins: '
            f"<strong>+{plan.guaranteed_margin_pct:.1%}</strong></p>"
        )

    rows_html = "".join(_render_allocation_row(a) for a in plan.allocations)

    badge_html = ""
    if show_confidence_badge and primary is not None:
        badge_html = _confidence_badge(primary.market_price)

    ai_widget_html = _render_ai_widget(market)

    return f"""<article class="market-card">
<h2><a href="{_escape(market.url)}" target="_blank" rel="noopener">{_escape(title)}</a>{badge_html}</h2>
{signal_html}
{margin_html}
{warning_html}
<p class="meta">Category: <strong>{_escape(market.category)}</strong> &middot; Resolves in <strong>{days_to_resolve:.1f}d</strong> &middot; Consensus: <strong>{plan.consensus_score:.0f}</strong> ({plan.num_sources} sources) &middot; Edge: <strong>{plan.edge:.1%}</strong></p>
<details>
<summary>Full position plan ({len(plan.allocations)} outcome(s))</summary>
<table>
<thead><tr><th>Role</th><th>Outcome</th><th>Size</th><th>Mkt price</th></tr></thead>
<tbody>
{rows_html}
</tbody>
</table>
</details>
<hr class="ai-sep">
{ai_widget_html}
</article>"""


def _section_for_category(category: str) -> tuple[str, str]:
    """Returns (section_key, section_title) for a given market category."""
    for key, _nav_label, title, categories in SECTION_DEFS:
        if category in categories:
            return key, title
    return OTHER_KEY, OTHER_SECTION_LABEL


def _bucket_results(results):
    """Splits `results` into (high_confidence_list, {section_key: (title, [items])}).
    Order follows SECTION_DEFS, with "other" appended last. Each item is the
    original (market, title, plan, days) tuple."""
    high_confidence = []
    buckets: dict[str, tuple[str, list]] = {
        key: (title, []) for key, _nav_label, title, _cats in SECTION_DEFS
    }
    buckets[OTHER_KEY] = (OTHER_SECTION_LABEL, [])

    for item in results:
        market, _title, plan, _days = item
        primary = plan.primary
        primary_price = primary.market_price if primary is not None else None
        if primary_price is not None and primary_price >= HIGH_CONFIDENCE_PRICE_THRESHOLD:
            high_confidence.append(item)
            continue
        section_key, _section_title = _section_for_category(market.category)
        buckets[section_key][1].append(item)

    return high_confidence, buckets


def _render_section(section_key: str, title: str, items, *, show_confidence_badge: bool = False) -> str:
    if not items:
        return ""
    cards_html = "\n".join(
        _render_card(market, card_title, plan, days_to_resolve, show_confidence_badge=show_confidence_badge)
        for market, card_title, plan, days_to_resolve in items
    )
    return f"""<section class="market-section" data-section="{section_key}">
<h2 class="section-title">{title} <span class="section-count">({len(items)})</span></h2>
{cards_html}
</section>"""


def _render_nav(section_counts: list[tuple[str, str, int]]) -> str:
    """section_counts: list of (section_key, nav_label, count), already
    filtered down to non-empty sections in display order."""
    total = sum(c for _k, _l, c in section_counts)
    buttons = [
        f'<button type="button" class="nav-btn active" data-target="all" onclick="filterSection(this)">'
        f'همه <span class="nav-count">({total})</span></button>'
    ]
    for key, label, count in section_counts:
        buttons.append(
            f'<button type="button" class="nav-btn" data-target="{key}" onclick="filterSection(this)">'
            f'{label} <span class="nav-count">({count})</span></button>'
        )
    return f'<nav class="section-nav">{"".join(buttons)}</nav>'


def build_html(results, generated_at: datetime | None = None) -> str:
    generated_at = generated_at or datetime.now(timezone.utc)
    timestamp_txt = generated_at.strftime("%Y-%m-%d %H:%M UTC")

    if not results:
        nav_html = ""
        body_html = '<p class="empty">No markets currently within the resolve window.</p>'
    else:
        high_confidence, buckets = _bucket_results(results)

        ordered_sections: list[tuple[str, str, str, list]] = [
            (HIGH_CONFIDENCE_KEY, HIGH_CONFIDENCE_ICON + " احتمال بالا", HIGH_CONFIDENCE_LABEL + " (Market-Implied)", high_confidence)
        ]
        for key, nav_label, title, _cats in SECTION_DEFS:
            ordered_sections.append((key, nav_label, title, buckets[key][1]))
        ordered_sections.append((OTHER_KEY, OTHER_NAV_LABEL, OTHER_SECTION_LABEL, buckets[OTHER_KEY][1]))

        nav_counts = [(key, nav_label, len(items)) for key, nav_label, _title, items in ordered_sections if items]
        nav_html = _render_nav(nav_counts)

        sections_html = [
            _render_section(key, title, items, show_confidence_badge=(key == HIGH_CONFIDENCE_KEY))
            for key, _nav_label, title, items in ordered_sections
        ]
        body_html = "\n".join(s for s in sections_html if s)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polymarket Bot — Latest Scan</title>
<style>
body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 880px; margin: 0 auto; padding: 0 1rem 2rem; color: #1f2328; }}
h1 {{ font-size: 1.5rem; margin-top: 1.5rem; }}
.generated-at {{ color: #57606a; font-size: 0.9rem; margin-bottom: 1rem; }}
.section-nav {{ position: sticky; top: 0; z-index: 10; background: #ffffff; display: flex; flex-wrap: wrap; gap: 0.5rem; padding: 0.6rem 0; border-bottom: 1px solid #d0d7de; margin-bottom: 1rem; }}
.nav-btn {{ border: 1px solid #d0d7de; background: #f6f8fa; color: #1f2328; border-radius: 999px; padding: 0.35rem 0.85rem; font-size: 0.85rem; cursor: pointer; white-space: nowrap; }}
.nav-btn:hover {{ background: #eaeef2; }}
.nav-btn.active {{ background: #0969da; border-color: #0969da; color: #fff; }}
.nav-count {{ opacity: 0.8; }}
.section-title {{ font-size: 1.15rem; margin: 1.5rem 0 0.75rem; padding-bottom: 0.35rem; border-bottom: 2px solid #d0d7de; }}
.section-count {{ color: #57606a; font-weight: 400; font-size: 0.9rem; }}
.market-card {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1rem; }}
.market-card h2 {{ font-size: 1.05rem; margin: 0 0 0.5rem; }}
.market-card h2 a {{ color: #0969da; text-decoration: none; }}
.confidence-badge {{ margin-left: 0.5rem; font-size: 0.75rem; background: #fff8c5; color: #7d4e00; border-radius: 999px; padding: 0.1rem 0.55rem; vertical-align: middle; }}
.signal {{ font-size: 1rem; margin: 0.25rem 0 0.75rem; }}
.margin {{ font-size: 0.9rem; margin: 0 0 0.75rem; color: #1a7f37; }}
.meta {{ color: #57606a; font-size: 0.85rem; margin-bottom: 0.5rem; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; margin-top: 0.5rem; }}
th, td {{ text-align: left; padding: 0.35rem 0.5rem; border-bottom: 1px solid #eaeef2; }}
.warning {{ color: #9a6700; font-size: 0.85rem; }}
.empty {{ color: #57606a; }}
summary {{ cursor: pointer; color: #57606a; font-size: 0.85rem; }}
.ai-sep {{ border: none; border-top: 1px dashed #d0d7de; margin: 0.85rem 0; }}
.ai-widget {{ font-size: 0.9rem; }}
.ai-btn {{ background: #6e40c9; color: #fff; border: none; border-radius: 6px; padding: 0.4rem 0.8rem; font-size: 0.85rem; cursor: pointer; }}
.ai-btn:disabled {{ opacity: 0.6; cursor: default; }}
.ai-result {{ margin-top: 0.6rem; padding: 0.6rem 0.75rem; background: #f6f8fa; border-radius: 6px; font-size: 0.85rem; line-height: 1.5; }}
.ai-result:empty {{ display: none; }}
</style>
</head>
<body>
<h1>Polymarket Bot — Latest Scan</h1>
<p class="generated-at">Generated {timestamp_txt}</p>
{nav_html}
{body_html}
<script>
function filterSection(btn) {{
  const target = btn.getAttribute('data-target');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.market-section').forEach(sec => {{
    sec.style.display = (target === 'all' || sec.getAttribute('data-section') === target) ? '' : 'none';
  }});
}}
const AI_WORKER_URL = "{AI_WORKER_URL}";
async function runAiAnalysis(btn) {{
  const market = JSON.parse(btn.getAttribute('data-market'));
  const resultDiv = document.getElementById('ai-result-' + market.market_id);
  resultDiv.innerHTML = '...';
  btn.disabled = true;
  try {{
    const resp = await fetch(AI_WORKER_URL, {{
      method: 'POST',
      headers: {{'Content-Type': 'application/json'}},
      body: JSON.stringify(market)
    }});
    const data = await resp.json();
    if (data.error) {{ resultDiv.innerHTML = data.error; return; }}
    let out = '';
    out += '<p><strong>Summary:</strong> ' + data.summary + '</p>';
    if (data.sources && data.sources.length) {{
      out += '<p><strong>Sources:</strong></p><ul>';
      for (const s of data.sources) {{
        const label = s.name + (s.date ? ' (' + s.date + ')' : '');
        out += s.url ? ('<li><a href="' + s.url + '" target="_blank" rel="noopener">' + label + '</a></li>') : ('<li>' + label + '</li>');
      }}
      out += '</ul>';
    }}
    out += '<p><strong>Confidence:</strong> ' + data.confidence + '</p>';
    if (data.alternative_signal) {{
      const s = data.alternative_signal;
      out += '<p><strong>Alt signal:</strong> ' + s.primary.outcome + ' ' + s.primary.size_pct + '%</p>';
      if (s.hedge) {{
        out += '<p>Hedge: ' + s.hedge.outcome + ' ' + s.hedge.size_pct + '% (stop-loss ' + s.hedge.stop_loss_pct + '%)</p>';
      }}
      out += '<p>Net if primary wins/loses: ' + s.net_profit_if_primary_wins_pct + '% / ' + s.net_profit_if_primary_loses_pct + '%</p>';
    }}
    if (data.cached) {{ out += '<p style="color:#57606a;font-size:0.8rem">(cached)</p>'; }}
    resultDiv.innerHTML = out;
  }} catch (e) {{
    resultDiv.innerHTML = e.message;
  }} finally {{
    btn.disabled = false;
  }}
}}
</script>
</body>
</html>"""


def write_html(path: str, results, generated_at: datetime | None = None) -> None:
    content = build_html(results, generated_at=generated_at)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
