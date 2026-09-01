"""
weekly_report.py — Phase 7 (calibration): checks which past signals actually
resolved correctly, sends a Telegram summary, and writes the full historical
docs/results.html dashboard.

Place this file in the ROOT of your repo, next to main.py.

BUG FIX in this version
-------------------------
The resolution-matching logic had a real bug: when a STANDALONE binary
(Yes/No) market resolved "Yes", the code returned the market's QUESTION TEXT
as the "winner" instead of the literal word "Yes" -- but predictions_log.csv
always logs "Yes"/"No" as primary_outcome for standalone markets. Comparing
"Yes" against a whole sentence always failed, so almost every non-election
signal was scored as incorrect regardless of whether it actually was.
FIXED: the winner label is now `groupItemTitle` ONLY when the market
actually has one (i.e. it's part of a grouped/categorical event, like an
election with multiple candidates); otherwise it's the raw outcome text
("Yes"/"No"), which is exactly what's logged for standalone markets.

NEW: after resolving predictions, writes docs/results.html (full history,
every prediction ever logged -- not just the trailing 7 days used in the
Telegram message) via results_html_generator.py. The Telegram report now
also includes a link to that page if DASHBOARD_URL is set.

USAGE
------
    python weekly_report.py                # normal run, sends Telegram msg
    python weekly_report.py --dry-run      # prints the report, doesn't send
"""

from __future__ import annotations

import csv
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


def fetch_event_resolution(slug: str, session: requests.Session) -> tuple[str | None, bool]:
    """Returns (winning_outcome_label_or_None, any_market_closed).

    The winner label is:
      - the sub-market's `groupItemTitle`, IF it has one (grouped /
        categorical event -- an election with multiple candidates, a
        multi-bucket economic release, etc.) -- that's the real-world
        "thing that won" (a candidate name, a price bucket, ...).
      - otherwise, the raw settled outcome text ("Yes" or "No") -- this is
        a plain standalone binary market, and "Yes"/"No" is exactly what
        predictions_log.csv logs as primary_outcome for those.
    """
    try:
        resp = session.get(GAMMA_EVENTS_ENDPOINT, params={"slug": slug}, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not fetch resolution for slug=%s: %s", slug, exc)
        return None, False

    events = data if isinstance(data, list) else data.get("data", [])
    if not events:
        return None, False
    event = events[0]
    sub_markets = event.get("markets", [])
    any_closed = False

    for market in sub_markets:
        if not market.get("closed"):
            continue
        any_closed = True
        outcomes = market.get("outcomes")
        prices = market.get("outcomePrices")
        if isinstance(outcomes, str):
            import json
            try:
                outcomes = json.loads(outcomes)
            except json.JSONDecodeError:
                outcomes = []
        if isinstance(prices, str):
            import json
            try:
                prices = json.loads(prices)
            except json.JSONDecodeError:
                prices = []
        prices = [float(p) for p in (prices or [])]
        if not outcomes or not prices or len(outcomes) != len(prices):
            continue

        group_item_title = (market.get("groupItemTitle") or "").strip()
        for outcome, price in zip(outcomes, prices):
            if price >= RESOLVED_PRICE_THRESHOLD:
                if group_item_title:
                    return group_item_title, True
                return outcome.strip(), True

    return None, any_closed


def resolve_predictions(log_rows: list[dict], cache: dict[tuple[str, str], dict]) -> list[dict]:
    session = requests.Session()
    resolved: list[dict] = []

    for row in log_rows:
        key = (row.get("group_key", ""), row.get("logged_at_utc", ""))
        cached = cache.get(key)
        if cached and cached.get("is_correct") in ("True", "False"):
            resolved.append(cached)
            continue

        slug = slug_from_url(row.get("market_url", ""))
        winner, any_closed = (None, False) if not slug else fetch_event_resolution(slug, session)

        base = {
            "group_key": row.get("group_key", ""), "title": row.get("title", ""),
            "category": row.get("category", ""), "logged_at_utc": row.get("logged_at_utc", ""),
            "market_url": row.get("market_url", ""),
            "primary_outcome": row.get("primary_outcome", ""),
            "primary_size_pct": row.get("primary_size_pct", ""),
            "primary_market_price": row.get("primary_market_price", ""),
        }

        if winner is None:
            resolved.append({
                **base, "resolved_outcome": "", "is_correct": "",
                "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            continue

        primary = (row.get("primary_outcome") or "").strip().lower()
        is_correct = winner.strip().lower() == primary
        resolved.append({
            **base, "resolved_outcome": winner, "is_correct": str(is_correct),
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
