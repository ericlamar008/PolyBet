"""
weekly_report.py — Phase 7 (calibration) + ONE-TIME diagnostic mode.

THIS IS THE LATEST VERSION. If you already have a file named weekly_report.py
or weekly_report-2.py from earlier in this chat, DELETE it from your repo and
use THIS one instead -- it is NEWER and fixes a real bug the earlier one had.

WHAT THIS VERSION FIXES vs the one you just tested
------------------------------------------------------
Your previous file returned the label of the FIRST closed sub-market it
found, whether that sub-market settled "Yes" OR "No". For multi-threshold
markets (Gold/Oil/SPY/Bitcoin price buckets, where MANY thresholds settle
"No" and only some settle "Yes"), this often grabbed a losing bucket (or
just "No") by accident instead of searching specifically for the one that
actually settled "Yes".

THIS version specifically searches ALL sub-markets for the one that
settled "Yes" (the real winner), and only falls back to "No" for genuinely
standalone (single-market, no real grouping) events.

HOW TO USE THE DIAGNOSTIC (do this once, then we fix it for real if needed)
-------------------------------------------------------------------------------
1. In GitHub, add a new repository secret: DEBUG_RESOLUTION = true
2. In .github/workflows/weekly_report.yml, inside the `env:` block of the
   "Run report" step, add this line:
       DEBUG_RESOLUTION: ${{ secrets.DEBUG_RESOLUTION }}
3. Run "PolyBet Weekly Report" manually once (Actions tab -> Run workflow).
4. Open that run's log, expand "Run report", find the block between
   "===== RAW EVENT JSON (first slug) =====" and
   "===== END RAW EVENT JSON =====", copy it, send it to me.
5. Afterwards, set DEBUG_RESOLUTION back to "false" (or delete the secret).
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from results_html_generator import write_results_html
from telegram_bot import send_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GAMMA_EVENTS_ENDPOINT = "https://gamma-api.polymarket.com/events"
REQUEST_TIMEOUT_SECONDS = 15
RESOLVED_PRICE_THRESHOLD = 0.99  # a price >= this counts as "settled winner"
DEBUG_RESOLUTION = os.getenv("DEBUG_RESOLUTION", "false").lower() == "true"
_debug_already_printed = False  # module-level flag so we only dump ONE example per run

PREDICTIONS_LOG_PATH = os.getenv("PREDICTIONS_LOG_PATH", "predictions_log.csv")
PREDICTIONS_RESOLVED_PATH = os.getenv("PREDICTIONS_RESOLVED_PATH", "predictions_resolved.csv")
RESULTS_HTML_PATH = os.getenv("RESULTS_HTML_PATH", "docs/results.html")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")

RESOLVED_FIELDS = [
    "group_key", "title", "category", "logged_at_utc", "market_url",
    "primary_outcome", "primary_size_pct", "primary_market_price",
    "resolved_outcome", "is_correct", "checked_at_utc",
]

REPORT_TITLES = {
    "scheduled": "📈 *گزارش هفتگی PolyBet*",
    "telegram_button": "🔘 *نتایج نهایی PolyBet (به‌درخواست شما)*",
}


def load_predictions_log(path: str) -> list[dict]:
    if not os.path.isfile(path):
        logger.warning("predictions_log.csv not found at %s -- nothing to report yet.", path)
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_resolved_cache(path: str) -> dict[tuple[str, str], dict]:
    if not os.path.isfile(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {(r["group_key"], r["logged_at_utc"]): r for r in rows}


def slug_from_url(url: str) -> str | None:
    if not url:
        return None
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    return parts[-1] if parts else None


def _parse_json_field(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return []


def _parse_outcomes(market: dict) -> tuple[list[str], list[float]]:
    outcomes = _parse_json_field(market.get("outcomes"))
    prices_raw = _parse_json_field(market.get("outcomePrices"))
    try:
        prices = [float(p) for p in prices_raw]
    except (TypeError, ValueError):
        prices = []
    if not outcomes or not prices or len(outcomes) != len(prices):
        return [], []
    return outcomes, prices


def fetch_event_markets(slug: str, session: requests.Session) -> list[dict] | None:
    global _debug_already_printed
    try:
        resp = session.get(GAMMA_EVENTS_ENDPOINT, params={"slug": slug}, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not fetch event for slug=%s: %s", slug, exc)
        return None

    if DEBUG_RESOLUTION and not _debug_already_printed:
        _debug_already_printed = True
        logger.info("===== RAW EVENT JSON (first slug) =====")
        logger.info("slug=%s", slug)
        logger.info(json.dumps(data, indent=2)[:6000])
        logger.info("===== END RAW EVENT JSON =====")

    events = data if isinstance(data, list) else data.get("data", [])
    if not events:
        return None
    return events[0].get("markets", [])


def resolve_single_prediction(slug: str, primary_outcome: str, session: requests.Session) -> tuple[str | None, bool | None, bool]:
    """Returns (resolved_outcome_label, is_correct, any_closed)."""
    sub_markets = fetch_event_markets(slug, session)
    if not sub_markets:
        return None, None, False

    any_closed = any(m.get("closed") for m in sub_markets)
    if not any_closed:
        return None, None, False

    primary_norm = (primary_outcome or "").strip().lower()

    if len(sub_markets) == 1:
        outcomes, prices = _parse_outcomes(sub_markets[0])
        for outcome, price in zip(outcomes, prices):
            if price >= RESOLVED_PRICE_THRESHOLD:
                settled = outcome.strip()
                return settled, settled.lower() == primary_norm, True
        return None, None, True

    # Search ALL sub-markets specifically for the one that settled "Yes" --
    # do NOT stop at the first closed one regardless of its outcome, since
    # most buckets in a multi-threshold group settle "No".
    for market in sub_markets:
        outcomes, prices = _parse_outcomes(market)
        for outcome, price in zip(outcomes, prices):
            if price >= RESOLVED_PRICE_THRESHOLD and outcome.strip().lower() == "yes":
                label = (market.get("groupItemTitle") or "").strip()
                if not label:
                    question = (market.get("question") or "").lower()
                    if primary_norm and primary_norm in question:
                        label = primary_outcome.strip()
                    else:
                        label = (market.get("question") or "Yes").strip()
                is_correct = label.strip().lower() == primary_norm
                return label, is_correct, True

    return None, None, True


def resolve_predictions(log_rows: list[dict], cache: dict[tuple[str, str], dict]) -> list[dict]:
    session = requests.Session()
    resolved: list[dict] = []

    for row in log_rows:
        key = (row.get("group_key", ""), row.get("logged_at_utc", ""))
        cached = cache.get(key)
        if cached and cached.get("is_correct") in ("True", "False"):
            resolved.append(cached)
            continue

        base = {
            "group_key": row.get("group_key", ""), "title": row.get("title", ""),
            "category": row.get("category", ""), "logged_at_utc": row.get("logged_at_utc", ""),
            "market_url": row.get("market_url", ""),
            "primary_outcome": row.get("primary_outcome", ""),
            "primary_size_pct": row.get("primary_size_pct", ""),
            "primary_market_price": row.get("primary_market_price", ""),
        }

        slug = slug_from_url(row.get("market_url", ""))
        if not slug:
            resolved.append({**base, "resolved_outcome": "", "is_correct": "", "checked_at_utc": datetime.now(timezone.utc).isoformat()})
            continue

        winner, is_correct, _any_closed = resolve_single_prediction(slug, row.get("primary_outcome", ""), session)
        resolved.append({
            **base,
            "resolved_outcome": winner or "",
            "is_correct": "" if is_correct is None else str(is_correct),
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        })

    return resolved


def write_resolved_cache(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESOLVED_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in RESOLVED_FIELDS})


def build_weekly_stats(resolved_rows: list[dict], since: datetime) -> dict:
    this_week = [r for r in resolved_rows if _parse_ts(r["logged_at_utc"]) and _parse_ts(r["logged_at_utc"]) >= since]
    total = len(this_week)
    decided = [r for r in this_week if r["is_correct"] in ("True", "False")]
    correct = [r for r in decided if r["is_correct"] == "True"]
    pending = total - len(decided)

    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in decided:
        by_category[r["category"]][1] += 1
        if r["is_correct"] == "True":
            by_category[r["category"]][0] += 1

    return {
        "total": total, "decided": len(decided), "correct": len(correct), "pending": pending,
        "success_rate": (len(correct) / len(decided) * 100.0) if decided else None,
        "by_category": dict(by_category),
    }


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def format_weekly_report(stats: dict, trigger_source: str = "scheduled", results_url: str = "") -> str:
    header = REPORT_TITLES.get(trigger_source, REPORT_TITLES["scheduled"])
    lines = [header, ""]
    lines.append(f"🔢 سیگنال‌های تولیدشده در ۷ روز اخیر: {stats['total']}")
    lines.append(f"✅ نتیجه‌ی نهایی مشخص شده: {stats['decided']}")
    lines.append(f"⏳ هنوز در انتظار نتیجه: {stats['pending']}")
    if stats["success_rate"] is not None:
        lines.append(f"🎯 درصد موفقیت (از میان نتیجه‌دارها): *{stats['success_rate']:.1f}%* ({stats['correct']}/{stats['decided']})")
    else:
        lines.append("🎯 هنوز هیچ سیگنالی نتیجه‌ی نهایی نگرفته -- بعداً دوباره چک می‌شود.")

    if stats["by_category"]:
        lines.append("")
        lines.append("📊 تفکیک بر اساس دسته (۷ روز اخیر):")
        for category, (correct, total) in sorted(stats["by_category"].items(), key=lambda kv: -kv[1][1]):
            rate = (correct / total * 100.0) if total else 0.0
            lines.append(f"  • {category}: {correct}/{total} ({rate:.0f}%)")

    if results_url:
        lines.append("")
        lines.append(f"📄 جدول کامل تاریخچه (همه‌ی سیگنال‌ها، همیشه):\n{results_url}")

    return "\n".join(lines)


def run(dry_run: bool = False) -> str:
    load_dotenv()
    trigger_source = os.getenv("TRIGGER_SOURCE", "scheduled")

    log_rows = load_predictions_log(PREDICTIONS_LOG_PATH)
    if not log_rows:
        message = "📈 گزارش PolyBet: هنوز هیچ سیگنالی در predictions_log.csv ثبت نشده."
        if not dry_run:
            send_message(message)
        else:
            print(message)
        return message

    cache = load_resolved_cache(PREDICTIONS_RESOLVED_PATH)
    resolved_rows = resolve_predictions(log_rows, cache)
    write_resolved_cache(PREDICTIONS_RESOLVED_PATH, resolved_rows)

    try:
        os.makedirs(os.path.dirname(RESULTS_HTML_PATH) or ".", exist_ok=True)
        write_results_html(RESULTS_HTML_PATH, resolved_rows)
        logger.info("Wrote results dashboard to %s", RESULTS_HTML_PATH)
    except OSError as exc:
        logger.warning("Failed to write results dashboard: %s", exc)

    since = datetime.now(timezone.utc) - timedelta(days=7)
    stats = build_weekly_stats(resolved_rows, since)
    results_url = f"{DASHBOARD_URL.rstrip('/')}/results.html" if DASHBOARD_URL else ""
    report = format_weekly_report(stats, trigger_source=trigger_source, results_url=results_url)

    if dry_run:
        print(report)
    else:
        ok = send_message(report)
        if not ok:
            logger.warning("Failed to send report to Telegram.")
    return report


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
