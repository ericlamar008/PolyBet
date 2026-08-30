"""
weekly_report.py — Phase 7 (calibration): checks which past signals actually
resolved correctly, and sends a weekly Telegram report with the real
success rate.

Place this file in the ROOT of your repo, next to main.py (NOT inside any
subfolder). It reads predictions_log.csv (written every day by main.py) and
writes predictions_resolved.csv next to it.

HOW RESOLUTION IS CHECKED
--------------------------
For each logged prediction, we already stored `market_url` (the public
Polymarket event URL). We hit Polymarket's own Gamma API for that event's
slug and look at its sub-markets:
  - a sub-market counts as resolved once it's `closed` and one of its
    outcome prices has settled near 1.0 (winner) or 0.0 (loser)
  - the winning outcome's label (`groupItemTitle` for grouped/categorical
    events, or "Yes"/"No" for a plain binary market) is compared against
    the `primary_outcome` we logged at scan time
  - if it matches -> the signal was CORRECT; if not -> INCORRECT; if the
    event hasn't closed yet -> PENDING (skipped from the success-rate math,
    checked again next run)

This is intentionally a plain string/price comparison, no ML, so you can
audit any single row by hand against the Polymarket page if a number looks
off.

WEEKLY NUMBERS REPORTED
-------------------------
Over the trailing 7 days (by `logged_at_utc`):
  - how many signals were generated
  - how many have resolved by now vs. still pending
  - overall success rate (resolved-correct / resolved-total)
  - a per-category breakdown (elections / fed / commodities / etc.)

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

from telegram_bot import send_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

GAMMA_EVENTS_ENDPOINT = "https://gamma-api.polymarket.com/events"
REQUEST_TIMEOUT_SECONDS = 15
RESOLVED_PRICE_THRESHOLD = 0.99  # a price >= this counts as "settled winner"

PREDICTIONS_LOG_PATH = os.getenv("PREDICTIONS_LOG_PATH", "predictions_log.csv")
PREDICTIONS_RESOLVED_PATH = os.getenv("PREDICTIONS_RESOLVED_PATH", "predictions_resolved.csv")

RESOLVED_FIELDS = [
    "group_key", "title", "category", "logged_at_utc", "primary_outcome",
    "resolved_outcome", "is_correct", "checked_at_utc",
]


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
    """Returns (winning_outcome_label_or_None, any_market_closed). If the
    event can't be found or nothing has closed yet, returns (None, False)."""
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
        for outcome, price in zip(outcomes, prices):
            if price >= RESOLVED_PRICE_THRESHOLD:
                # A "Yes" win on a per-candidate sub-market means THAT
                # candidate/bucket (its groupItemTitle) is the real winner.
                if outcome.strip().lower() == "yes":
                    return (market.get("groupItemTitle") or market.get("question") or "").strip(), True
                # A plain binary market resolving "No" as the settled
                # outcome (e.g. "Will X happen?" -> No) is itself the answer.
                if outcome.strip().lower() == "no" and len(outcomes) == 2:
                    return "No", True
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

        if winner is None:
            resolved.append({
                "group_key": row.get("group_key", ""), "title": row.get("title", ""),
                "category": row.get("category", ""), "logged_at_utc": row.get("logged_at_utc", ""),
                "primary_outcome": row.get("primary_outcome", ""), "resolved_outcome": "",
                "is_correct": "", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
            })
            continue

        primary = (row.get("primary_outcome") or "").strip().lower()
        is_correct = winner.strip().lower() == primary
        resolved.append({
            "group_key": row.get("group_key", ""), "title": row.get("title", ""),
            "category": row.get("category", ""), "logged_at_utc": row.get("logged_at_utc", ""),
            "primary_outcome": row.get("primary_outcome", ""), "resolved_outcome": winner,
            "is_correct": str(is_correct), "checked_at_utc": datetime.now(timezone.utc).isoformat(),
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

    by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # [correct, total_decided]
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


def format_weekly_report(stats: dict) -> str:
    lines = ["📈 *گزارش هفتگی PolyBet*", ""]
    lines.append(f"🔢 سیگنال‌های تولیدشده در ۷ روز اخیر: {stats['total']}")
    lines.append(f"✅ نتیجه‌ی نهایی مشخص شده: {stats['decided']}")
    lines.append(f"⏳ هنوز در انتظار نتیجه: {stats['pending']}")
    if stats["success_rate"] is not None:
        lines.append(f"🎯 درصد موفقیت (از میان نتیجه‌دارها): *{stats['success_rate']:.1f}%* ({stats['correct']}/{stats['decided']})")
    else:
        lines.append("🎯 هنوز هیچ سیگنالی نتیجه‌ی نهایی نگرفته -- هفته‌ی بعد دوباره چک می‌شود.")

    if stats["by_category"]:
        lines.append("")
        lines.append("📊 تفکیک بر اساس دسته:")
        for category, (correct, total) in sorted(stats["by_category"].items(), key=lambda kv: -kv[1][1]):
            rate = (correct / total * 100.0) if total else 0.0
            lines.append(f"  • {category}: {correct}/{total} ({rate:.0f}%)")

    return "\n".join(lines)


def run(dry_run: bool = False) -> str:
    load_dotenv()
    log_rows = load_predictions_log(PREDICTIONS_LOG_PATH)
    if not log_rows:
        message = "📈 گزارش هفتگی PolyBet: هنوز هیچ سیگنالی در predictions_log.csv ثبت نشده."
        if not dry_run:
            send_message(message)
        else:
            print(message)
        return message

    cache = load_resolved_cache(PREDICTIONS_RESOLVED_PATH)
    resolved_rows = resolve_predictions(log_rows, cache)
    write_resolved_cache(PREDICTIONS_RESOLVED_PATH, resolved_rows)

    since = datetime.now(timezone.utc) - timedelta(days=7)
    stats = build_weekly_stats(resolved_rows, since)
    report = format_weekly_report(stats)

    if dry_run:
        print(report)
    else:
        ok = send_message(report)
        if not ok:
            logger.warning("Failed to send weekly report to Telegram.")
    return report


if __name__ == "__main__":
    run(dry_run="--dry-run" in sys.argv)
