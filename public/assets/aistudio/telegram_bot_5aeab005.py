"""telegram_bot.py — Phase 4 (FIX: shows the new guaranteed-margin figure
from position_logic.py's floor-sizing fix in the Telegram message too).

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment only
(.env via python-dotenv). Never logs or prints the actual token value.
"""

from __future__ import annotations

import logging
import os

import requests

from position_logic import PositionPlan

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 10
WARNING_EMOJI = "\u26a0\ufe0f"
SIGNAL_EMOJI = "\U0001F3AF"  # 🎯
MARGIN_EMOJI = "\u2705"  # ✅


def format_signal_message(plan: PositionPlan, market_url: str, days_to_resolve: float, title: str | None = None) -> str:
    heading = title or plan.question
    primary = plan.primary
    signal_line = (
        f"{SIGNAL_EMOJI} پیشنهاد: *{primary.outcome}* — {primary.size_pct:.1f}% (قیمت بازار {primary.market_price:.2f})"
        if primary else f"{SIGNAL_EMOJI} پیشنهاد: نامعلوم"
    )

    lines = [
        f"*{heading}*", "",
        signal_line,
    ]

    # NEW: guaranteed-margin line, from position_logic.py's floor-sizing
    # fix. Shows the net profit locked in if the primary outcome wins,
    # regardless of how the rest of the budget is spent on hedges.
    if plan.guaranteed_margin_pct is not None:
        lines.append(f"{MARGIN_EMOJI} سود تضمینی اگر Primary ببرد: +{plan.guaranteed_margin_pct:.1%}")

    lines += [
        "",
        f"\u23f3 Resolves in: {days_to_resolve:.1f} days",
        f"\U0001F4CA Consensus: {plan.consensus_score:.0f}% ({plan.num_sources} sources) | Edge: {plan.edge:.1%}",
        "", "*Full position plan:*",
    ]

    role_labels = {"primary": "\U0001F7E2 Primary", "secondary": "\U0001F535 Secondary", "hedge": "\U0001F6E1 Hedge"}
    for alloc in plan.allocations:
        label = role_labels.get(alloc.role, alloc.role)
        price_txt = f" (mkt {alloc.market_price:.2f})" if alloc.market_price is not None else ""
        lines.append(f"  {label}: *{alloc.outcome}* — {alloc.size_pct:.1f}%{price_txt}")

    if plan.warning:
        lines.append("")
        lines.append(f"{WARNING_EMOJI} {plan.warning}")

    lines.append("")
    lines.append(f"[View market]({market_url})")
    return "\n".join(lines)


def send_message(text: str, bot_token: str | None = None, chat_id: str | None = None) -> bool:
    """Send a Markdown-formatted message via the Telegram Bot API. Returns
    True on success, False on any failure. Never logs the resolved
    token/chat_id values."""
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        logger.error("Telegram not configured: missing bot token or chat id (check .env).")
        return False
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {"chat_id": chat, "text": text, "parse_mode": "Markdown", "disable_web_page_preview": False}
    try:
        resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Telegram send failed: %s", exc)
        return False
