"""main.py — orchestration (FIX: build the signal from the market's
current FAVORITE outcome's own question text for numeric/data-driven
domains, instead of always using the group's generic event title).

Root cause this fixes: for grouped "bucket" markets (e.g. "Core PCE
YoY - July 2026" with outcomes "3.0", "3.1", "3.2"...), the event_title
("Core PCE YoY - July 2026") has NO number in it -- only each
individual candidate/outcome's own question ("...be 3.2%?") does.
build_signal() was always called with the event_title for grouped
markets, so parse_threshold_from_question()/parse_equality_target()
never had a number to work with, and every numeric-data source
correctly (but uselessly) returned None -> "no independent sources".

Since build_position_plan() (position_logic.py) already always picks
the market's highest-priced outcome as "primary" regardless of the
model signal, the only thing that actually needs a real per-market
number is THAT outcome's own signal. So for domains backed by
numeric-threshold/equality data sources (fed/cpi/pce/gdp/employment/
ecb/boc/boe), we now build the signal from the favorite outcome's own
question text. Elections keep using the event_title (unchanged),
since sources/polls.py's race lookup is keyed by the race/event level,
not by an individual candidate's question text.

Still writes docs/index.html (Phase 5) and appends predictions_log.csv
(Phase 7 groundwork) every run.
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

PREDICTIONS_LOG_FIELDS = [
    "logged_at_utc", "group_key", "title", "category", "days_to_resolve_at_scan",
    "consensus_score", "edge", "num_sources", "primary_outcome", "primary_size_pct",
    "primary_market_price", "hedge_or_secondary_summary", "warning", "market_url",
]

# Domains whose independent sources (FRED/BEA/Eurostat/World Bank/ECB/
# BoC/BoE) key off an EXPLICIT NUMBER in the question text (a threshold
# like "above X" or an equality/bucket target like "be X%"). For groups
# in these domains, the per-outcome question (not the generic event
# title) is what actually carries that number.
NUMERIC_SIGNAL_DOMAINS: frozenset[str] = frozenset({
    "fed", "cpi", "pce", "gdp", "employment", "ecb", "boc", "boe",
})


def group_scanned_markets(markets: list[ScannedMarket]) -> list[list[ScannedMarket]]:
    """Group scanned markets that belong to the same real-world event
    (same public URL — see scanner.py's `_resolve_public_slug`, which
    already resolves grouped candidate-markets to their shared parent
    event URL). Order of first appearance is preserved."""
    groups: "OrderedDict[str, list[ScannedMarket]]" = OrderedDict()
    for m in markets:
        key = m.url or m.market_id
        groups.setdefault(key, []).append(m)
    return list(groups.values())


def _extract_yes_price(market: ScannedMarket) -> float:
    """Extract the market-implied probability that THIS candidate/outcome
    wins, from its own Yes/No outcome_prices."""
    if market.outcomes and market.outcome_prices and len(market.outcomes) == len(market.outcome_prices):
        for outcome, price in zip(market.outcomes, market.outcome_prices):
            if outcome.strip().lower() == "yes":
                return price
    return 0.5


def _favorite_market(group: list[ScannedMarket]) -> ScannedMarket:
    """The single outcome the market currently prices as most likely --
    this is always what build_position_plan() picks as 'primary'."""
    return max(group, key=_extract_yes_price)


def resolve_signal_query(group: list[ScannedMarket], representative: ScannedMarket) -> str:
    """Pick the text to feed into build_signal(). For standalone markets
    this is just the market's own question. For grouped markets: use the
    event title EXCEPT for numeric-data domains, where the favorite
    outcome's own question (which actually contains the number a FRED/
    BEA/Eurostat/World Bank/ECB/BoC/BoE fetcher needs) is used instead."""
    if len(group) == 1 and not representative.is_grouped:
        return representative.question
    if representative.category in NUMERIC_SIGNAL_DOMAINS:
        favorite = _favorite_market(group)
        return favorite.question
    return representative.event_title or representative.question


def build_group_plan(group: list[ScannedMarket], signal) -> tuple[PositionPlan, str]:
    """Build ONE PositionPlan for the whole group. For a standalone
    (single, ungrouped) market this is just the normal binary plan. For a
    grouped multi-candidate event, all candidates become outcomes of one
    combined categorical PositionPlan (primary/secondary/hedge across
    real candidates, not one redundant card per candidate)."""
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
    outcome_prices = [_extract_yes_price(m) for m in group]
    plan = build_position_plan(
        market_id=representative.market_id, question=title,
        outcomes=outcomes, outcome_prices=outcome_prices, signal=signal,
    )
    return plan, title


def contextualize_warning(category: str, warning: str | None) -> str | None:
    """Make the 'no independent sources' warning specific to WHY it
    happened, since the reason (and the fix) differs by domain:
    - elections: documented limitation, needs manual RACE_PAGE_MAP entry.
    - economic/financial domains: usually missing API keys in .env,
      OR the market question has no explicit numeric threshold the
      current sigmoid-based model can use at all (a modeling gap, not
      just a missing key) — flagged for Phase 7 calibration."""
    if not warning:
        return warning
    if category == "elections":
        return warning + " (برای این رقابت، RACE_PAGE_MAP در sources/polls.py تنظیم نشده است.)"
    return (
        warning
        + " (برای دسته‌ی "
        + category
        + ": یا کلید API مربوطه در .env خالی است، یا سؤال این بازار آستانه‌ی عددی صریح ندارد که "
        "مدل فعلی بتواند از آن تخمین بزند — این محدودیت مدل است، نه فقط کلید، و دقیقاً موضوع کالیبراسیون فاز ۷ است.)"
    )


def append_prediction_log(group_key: str, title: str, category: str, days_to_resolve: float,
                           plan: PositionPlan, market_url: str, path: str = PREDICTIONS_LOG_PATH) -> None:
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


def run(window_days: float = 7.0, dry_run: bool | None = None) -> list[str]:
    load_dotenv()
    if dry_run is None:
        dry_run = os.getenv("SEND_LIVE_SIGNALS", "false").lower() != "true"

    markets = scan_markets(window_days=window_days)
    logger.info("Scanned %d markets within %.0f-day resolve window.", len(markets), window_days)

    groups = group_scanned_markets(markets)
    logger.info("Consolidated into %d event section(s).", len(groups))

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

        message = format_signal_message(plan, representative.url, days_to_resolve, title=title)
        messages.append(message)
        if dry_run:
            logger.info("[DRY RUN] Would send message for: %s", title)
            print(message)
            print("-" * 60)
        else:
            ok = send_message(message)
            if not ok:
                logger.warning("Failed to send message for: %s", title)

    try:
        os.makedirs(os.path.dirname(DOCS_HTML_PATH) or ".", exist_ok=True)
        write_html(DOCS_HTML_PATH, html_results)
        logger.info("Wrote HTML dashboard to %s", DOCS_HTML_PATH)
    except OSError as exc:
        logger.warning("Failed to write HTML dashboard: %s", exc)

    logger.info("Appended %d event predictions to %s", len(groups), PREDICTIONS_LOG_PATH)
    return messages


if __name__ == "__main__":
    run()
