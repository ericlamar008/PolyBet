"""
main.py — orchestration (FIX: only send ONE Telegram message per run — the
daily summary with the dashboard link — instead of one message per market).

REPLACES your current main.py.

WHAT CHANGED vs your last version
----------------------------------
Everything about grouping, resolve_signal_query, contextualize_warning,
HTML writing, and predictions_log.csv is UNCHANGED.

Telegram behavior changed: by default, main.py no longer sends one message
per market/event (which is what was flooding your chat with ~20 messages).
It still WRITES docs/index.html with every card as before, and still logs
every prediction to predictions_log.csv as before -- only the *Telegram
sending* changed. At the end of the run, exactly ONE message is sent: the
daily summary with the event count and the dashboard link.

If you ever want the old per-market messages back (e.g. temporarily, for
debugging), set this in your .env / GitHub secret:
    SEND_PER_MARKET_MESSAGES=true
Default (unset, or "false") = only the one summary message, as requested.
"""

from __future__ import annotations

import csv
import logging
import os
from collections import OrderedDict
from datetime import datetime, timezone

from dotenv import load_dotenv

from html_generator import write_html
from position_logic import build_position_plan, PositionPlan
from scanner import ScannedMarket, scan_markets
from sources.aggregator import build_signal
from telegram_bot import format_signal_message, send_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DOCS_HTML_PATH = os.getenv("HTML_OUTPUT_PATH", "docs/index.html")
PREDICTIONS_LOG_PATH = os.getenv("PREDICTIONS_LOG_PATH", "predictions_log.csv")
DASHBOARD_URL = os.getenv("DASHBOARD_URL", "")
SEND_PER_MARKET_MESSAGES = os.getenv("SEND_PER_MARKET_MESSAGES", "false").lower() == "true"

PREDICTIONS_LOG_FIELDS = [
    "logged_at_utc", "group_key", "title", "category", "days_to_resolve_at_scan",
    "consensus_score", "edge", "num_sources", "primary_outcome", "primary_size_pct",
    "primary_market_price", "hedge_or_secondary_summary", "warning", "market_url",
]

NUMERIC_SIGNAL_DOMAINS: frozenset[str] = frozenset(
    {"fed", "cpi", "pce", "gdp", "employment", "ecb", "boc", "boe"}
)


def group_scanned_markets(markets: list[ScannedMarket]) -> list[list[ScannedMarket]]:
    """Group scanned markets that belong to the same real-world event (same
    public URL — see scanner.py's resolve_public_slug, which already
    resolves grouped candidate-markets to their shared parent event URL).
    Order of first appearance is preserved."""
    groups: "OrderedDict[str, list[ScannedMarket]]" = OrderedDict()
    for m in markets:
        key = m.url or m.market_id
        groups.setdefault(key, []).append(m)
    return list(groups.values())


def extract_yes_price(market: ScannedMarket) -> float:
    """Extract the market-implied probability that THIS candidate/outcome
    wins, from its own Yes/No outcome_prices."""
    if market.outcomes and market.outcome_prices and len(market.outcomes) == len(market.outcome_prices):
        for outcome, price in zip(market.outcomes, market.outcome_prices):
            if outcome.strip().lower() == "yes":
                return price
    return 0.5


def favorite_market(group: list[ScannedMarket]) -> ScannedMarket:
    """The single outcome the market currently prices as most likely — this
    is always what build_position_plan picks as primary."""
    return max(group, key=extract_yes_price)


def resolve_signal_query(group: list[ScannedMarket], representative: ScannedMarket) -> str:
    """Pick the text to feed into build_signal. For standalone markets this
    is just the market's own question. For grouped markets use the event
    title EXCEPT for numeric-data domains, where the favorite outcome's own
    question (which actually contains the number a FRED/BEA/Eurostat/World
    Bank/ECB/BoC/BoE fetcher needs) is used instead."""
    if len(group) == 1 and not representative.is_grouped:
        return representative.question
    if representative.category in NUMERIC_SIGNAL_DOMAINS:
        favorite = favorite_market(group)
        return favorite.question
    return representative.event_title or representative.question


def build_group_plan(group: list[ScannedMarket], signal) -> tuple[PositionPlan, str]:
    """Build ONE PositionPlan for the whole group. For a standalone single,
    ungrouped market this is just the normal binary plan. For a grouped
    multi-candidate event, all candidates become outcomes of one combined
    categorical PositionPlan (primary/secondary/hedge across real
    candidates, not one redundant card per candidate)."""
    representative = group[0]
    if len(group) == 1 and not representative.is_grouped:
        plan = build_position_plan(
            market_id=representative.market_id, question=representative.question,
            outcomes=representative.outcomes, outcome_prices=representative.outcome_prices,
            signal=signal,
        )
        return plan, representative.question

    title = representative.event_title or representative.question
    outcomes = [m.group_label or m.question for m in group]
    outcome_prices = [extract_yes_price(m) for m in group]
    plan = build_position_plan(
        market_id=representative.market_id, question=title,
        outcomes=outcomes, outcome_prices=outcome_prices, signal=signal,
    )
    return plan, title


def contextualize_warning(category: str, warning: str | None) -> str | None:
    """Make the "no independent sources" warning specific to WHY it
    happened, since the reason (and the fix) differs by domain."""
    if not warning:
        return warning
    if category == "elections":
        return warning + " (RACE_PAGE_MAP در sources/polls.py تنظیم نشده است.)"
    return warning + f" ({category} API/.env؟)"


def append_prediction_log(
    group_key: str, title: str, category: str, days_to_resolve: float,
    plan: PositionPlan, market_url: str, path: str = PREDICTIONS_LOG_PATH,
) -> None:
    file_exists = os.path.isfile(path)
    non_primary = [a for a in plan.allocations if a.role != "primary"]
    hedge_summary = "; ".join(f"{a.role}:{a.outcome}={a.size_pct:.1f}%" for a in non_primary)
    row = {
        "logged_at_utc": datetime.now(timezone.utc).isoformat(),
        "group_key": group_key,
        "title": title,
        "category": category,
        "days_to_resolve_at_scan": round(days_to_resolve, 3),
        "consensus_score": plan.consensus_score,
        "edge": plan.edge,
        "num_sources": plan.num_sources,
        "primary_outcome": plan.primary.outcome if plan.primary else "",
        "primary_size_pct": plan.primary.size_pct if plan.primary else "",
        "primary_market_price": plan.primary.market_price if plan.primary else "",
        "hedge_or_secondary_summary": hedge_summary,
        "warning": plan.warning or "",
        "market_url": market_url,
    }
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PREDICTIONS_LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def send_daily_summary(num_events: int, dashboard_url: str) -> None:
    """The ONLY Telegram message sent per run by default: a short summary
    pointing at the live dashboard. Skipped (with a warning log) if
    DASHBOARD_URL isn't configured yet."""
    if not dashboard_url:
        logger.warning("DASHBOARD_URL not set in .env — skipping daily summary message.")
        return
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = (
        f"📊 اسکن روزانه‌ی PolyBet انجام شد.\n\n"
        f"🕒 {generated_at}\n"
        f"🔢 تعداد رویدادهای بررسی‌شده: {num_events}\n\n"
        f"🔗 مشاهده‌ی داشبورد کامل:\n{dashboard_url}"
    )
    ok = send_message(text)
    if not ok:
        logger.warning("Failed to send daily summary message to Telegram.")


def run(window_days: float = 7.0, dry_run: bool | None = None) -> list[str]:
    load_dotenv()
    if dry_run is None:
        dry_run = os.getenv("SEND_LIVE_SIGNALS", "false").lower() != "true"

    markets = scan_markets(window_days=window_days)
    logger.info("Scanned %d markets within %.0f-day resolve window.", len(markets), window_days)

    groups = group_scanned_markets(markets)
    logger.info("Consolidated into %d event sections.", len(groups))

    messages: list[str] = []
    html_results = []

    for group in groups:
        representative = group[0]
        signal_query = resolve_signal_query(group, representative)
        signal = build_signal(signal_query, representative.category)

        plan, title = build_group_plan(group, signal)
        plan.warning = contextualize_warning(representative.category, plan.warning)

        days_to_resolve = min(m.days_to_resolve for m in group)
        html_results.append((representative, title, plan, days_to_resolve))

        try:
            append_prediction_log(
                group_key=representative.url or representative.market_id,
                title=title, category=representative.category,
                days_to_resolve=days_to_resolve, plan=plan,
                market_url=representative.url, path=PREDICTIONS_LOG_PATH,
            )
        except OSError as exc:
            logger.warning("Failed to append prediction log for group %s: %s", title, exc)

        # NOTE: this only builds the text (kept for logging / optional
        # per-market sending below) -- it is NOT sent to Telegram by
        # default anymore. See SEND_PER_MARKET_MESSAGES at the top of the
        # file if you ever want the old one-message-per-market behavior.
        message = format_signal_message(plan, representative.url, days_to_resolve, title=title)
        messages.append(message)

        if dry_run:
            logger.info("DRY RUN — would process message for %s", title)
        elif SEND_PER_MARKET_MESSAGES:
            ok = send_message(message)
            if not ok:
                logger.warning("Failed to send message for %s", title)

    try:
        os.makedirs(os.path.dirname(DOCS_HTML_PATH) or ".", exist_ok=True)
        write_html(DOCS_HTML_PATH, html_results)
        logger.info("Wrote HTML dashboard to %s", DOCS_HTML_PATH)
    except OSError as exc:
        logger.warning("Failed to write HTML dashboard: %s", exc)

    logger.info("Appended %d event predictions to %s", len(groups), PREDICTIONS_LOG_PATH)

    if dry_run:
        logger.info("DRY RUN — would send ONE daily summary linking to %s", DASHBOARD_URL or "(no DASHBOARD_URL set)")
    else:
        send_daily_summary(len(groups), DASHBOARD_URL)

    return messages


if __name__ == "__main__":
    run()
