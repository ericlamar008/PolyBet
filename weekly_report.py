"""
weekly_report.py — PolyBet v2.0 Resolution & Self-Healing Cache Auditor.

REPLACES your current weekly_report.py.

KEY FIXES IN THIS VERSION:
1. FIX BUG #1 (Self-Healing for Single-Market Binary Events):
   Previously, single binary markets (like all 35 stock earnings markets: PANW,
   AVGO, SNOW, LULU, etc.) had `primary_outcome` logged as the full question
   title (`"Will Broadcom (AVGO) beat quarterly earnings?"`) while Polymarket
   resolved them as `"Yes"` or `"No"`. `resolve_single_prediction` compared
   `"yes" == "will broadcom..."` -> `False`!
   Worse, `resolve_predictions` cached those false negatives forever in
   `predictions_resolved.csv`!
   Now `resolve_predictions` automatically detects and repairs any cached row
   where `primary_outcome.lower() == title.lower()` and `resolved_outcome in ("Yes", "No")`!
2. FIX BUG #7 (Cumulative "By Date" Multi-Market Resolution):
   In markets like "US reissues Iran oil sales sanction relief by...?", if the
   specific sub-market matching `primary_outcome` (e.g. "August 31") has closed
   and settled `"No"`, it immediately resolves as `False` instead of hanging
   forever waiting for some future date to settle `"Yes"`.
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
RESOLVED_PRICE_THRESHOLD = 0.99
DEBUG_RESOLUTION = os.getenv("DEBUG_RESOLUTION", "false").lower() == "true"
REBUILD_RESOLVED_CACHE = os.getenv("REBUILD_RESOLVED_CACHE", "false").lower() == "true"

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
    "scheduled": "📈 *گزارش هفتگی PolyBet v2.0*",
    "telegram_button": "🔘 *نتایج نهایی PolyBet v2.0 (به‌درخواست شما)*",
}


def load_predictions_log(path: str) -> list[dict]:
    if not os.path.isfile(path):
        logger.warning("predictions_log.csv not found at %s -- nothing to report yet.", path)
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def dedupe_by_market(log_rows: list[dict]) -> list[dict]:
    earliest: dict[str, dict] = {}
    for row in log_rows:
        key = row.get("group_key", "")
        if not key:
            continue
        existing = earliest.get(key)
        if existing is None or (row.get("logged_at_utc", "") < existing.get("logged_at_utc", "")):
            earliest[key] = row
    return list(earliest.values())


def _repair_binary_cache_row(row: dict) -> dict:
    """Self-heal cached rows in predictions_resolved.csv affected by Bug #1."""
    title = (row.get("title") or "").strip()
    primary = (row.get("primary_outcome") or "").strip()
    resolved = (row.get("resolved_outcome") or "").strip()
    if title and primary.lower() == title.lower():
        row["primary_outcome"] = "Yes"
        if resolved.lower() in ("yes", "no"):
            row["is_correct"] = str(resolved.lower() == "yes")
    return row


def load_resolved_cache(path: str) -> dict[str, dict]:
    if REBUILD_RESOLVED_CACHE or not os.path.isfile(path):
        return {}
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cache: dict[str, dict] = {}
    for r in rows:
        key = r.get("group_key", "")
        if key:
            cache[key] = _repair_binary_cache_row(r)
    return cache


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
    try:
        resp = session.get(GAMMA_EVENTS_ENDPOINT, params={"slug": slug}, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Could not fetch event for slug=%s: %s", slug, exc)
        return None

    events = data if isinstance(data, list) else data.get("data", [])
    if not events:
        return None
    return events[0].get("markets", [])


def resolve_single_prediction(
    slug: str, primary_outcome: str, title: str, session: requests.Session
) -> tuple[str | None, bool | None, bool]:
    sub_markets = fetch_event_markets(slug, session)
    if not sub_markets:
        return None, None, False

    any_closed = any(m.get("closed") for m in sub_markets)
    if not any_closed:
        return None, None, False

    primary_norm = (primary_outcome or "").strip().lower()
    title_norm = (title or "").strip().lower()

    # FIX BUG #1: Single binary market
    if len(sub_markets) == 1:
        effective_primary = "yes" if primary_norm == title_norm else primary_norm
        outcomes, prices = _parse_outcomes(sub_markets[0])
        for outcome, price in zip(outcomes, prices):
            if price >= RESOLVED_PRICE_THRESHOLD:
                settled = outcome.strip()
                return settled, settled.lower() == effective_primary, True
        return None, None, True

    # Multi-candidate / Multi-date event
    for market in sub_markets:
        outcomes, prices = _parse_outcomes(market)
        label = (market.get("groupItemTitle") or market.get("question") or "").strip()
        for outcome, price in zip(outcomes, prices):
            if price >= RESOLVED_PRICE_THRESHOLD and outcome.strip().lower() == "yes":
                if not label:
                    label = primary_outcome.strip()
                is_correct = label.strip().lower() == primary_norm
                return label, is_correct, True
            # FIX BUG #7: If the specific date sub-market we bet on settled "No", resolve as False!
            if (
                market.get("closed")
                and price >= RESOLVED_PRICE_THRESHOLD
                and outcome.strip().lower() == "no"
                and label.strip().lower() == primary_norm
            ):
                return f"Not {label}", False, True

    return None, None, True


def resolve_predictions(log_rows: list[dict], cache: dict[str, dict]) -> list[dict]:
    session = requests.Session()
    resolved: list[dict] = []

    for row in log_rows:
        key = row.get("group_key", "")
        cached = cache.get(key)
        if cached and cached.get("is_correct") in ("True", "False"):
            resolved.append(_repair_binary_cache_row(cached))
            continue

        title = row.get("title", "")
        raw_primary = row.get("primary_outcome", "")
        clean_primary = "Yes" if raw_primary.strip().lower() == title.strip().lower() else raw_primary

        base = {
            "group_key": key,
            "title": title,
            "category": row.get("category", ""),
            "logged_at_utc": row.get("logged_at_utc", ""),
            "market_url": row.get("market_url", ""),
            "primary_outcome": clean_primary,
            "primary_size_pct": row.get("primary_size_pct", ""),
            "primary_market_price": row.get("primary_market_price", ""),
        }

        slug = slug_from_url(row.get("market_url", ""))
        if not slug:
            resolved.append({**base, "resolved_outcome": "", "is_correct": "", "checked_at_utc": datetime.now(timezone.utc).isoformat()})
            continue

        winner, is_correct, _any_closed = resolve_single_prediction(slug, clean_primary, title, session)
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


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


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
        "total": total,
        "decided": len(decided),
        "correct": len(correct),
        "pending": pending,
        "success_rate": (len(correct) / len(decided) * 100.0) if decided else None,
        "by_category": dict(by_category),
    }


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

    raw_log_rows = load_predictions_log(PREDICTIONS_LOG_PATH)
    if not raw_log_rows:
        message = "📈 گزارش PolyBet: هنوز هیچ سیگنالی در predictions_log.csv ثبت نشده."
        if not dry_run:
            send_message(message)
        else:
            print(message)
        return message

    log_rows = dedupe_by_market(raw_log_rows)
    log_by_key = {r.get("group_key", ""): r for r in log_rows if r.get("group_key")}
    logger.info("Deduped %d logged rows down to %d unique markets.", len(raw_log_rows), len(log_rows))

    cache = load_resolved_cache(PREDICTIONS_RESOLVED_PATH)
    resolved_rows = resolve_predictions(log_rows, cache)
    write_resolved_cache(PREDICTIONS_RESOLVED_PATH, resolved_rows)

    try:
        os.makedirs(os.path.dirname(RESULTS_HTML_PATH) or ".", exist_ok=True)
        write_results_html(RESULTS_HTML_PATH, resolved_rows, log_by_key=log_by_key)
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
