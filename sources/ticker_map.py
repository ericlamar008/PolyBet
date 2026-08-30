"""
sources/ticker_map.py — shared ticker-detection utility (NEW). Save as
sources/ticker_map.py in your repo.

Used by alpha_vantage.py and finnhub.py so stock/index questions are
matched to the ACTUAL company/index mentioned, instead of always
defaulting to SPY regardless of what the question is about.

Covers the major indices and large-cap stocks commonly seen on
Polymarket's stock-market category. Extend TICKER_NAMES as needed —
this is an explicit, editable mapping rather than a general NLP entity
extractor, matching the project's existing keyword-based design.
"""

from __future__ import annotations

import re

# name (lowercase, matched as a whole word/phrase) -> ticker symbol.
TICKER_NAMES: dict[str, str] = {
    # Major indices (as liquid ETF proxies — same instruments Alpha
    # Vantage/Finnhub can actually quote on free tiers).
    "s&p 500": "SPY", "s&p500": "SPY", "s&p": "SPY",
    "nasdaq 100": "QQQ", "nasdaq": "QQQ",
    "dow jones": "DIA", "dow": "DIA",
    "russell 2000": "IWM", "russell": "IWM",
    "vix": "VIXY",
    # Large-cap individual stocks frequently referenced in prediction markets.
    "tesla": "TSLA", "apple": "AAPL", "nvidia": "NVDA", "amazon": "AMZN",
    "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL", "meta": "META",
    "netflix": "NFLX", "palantir": "PLTR", "amd": "AMD", "intel": "INTC",
    "coinbase": "COIN", "robinhood": "HOOD", "gamestop": "GME",
    "berkshire": "BRK.B", "jpmorgan": "JPM", "disney": "DIS", "boeing": "BA",
}

DEFAULT_TICKER = "SPY"  # fallback when no specific name is recognized


def detect_ticker(question: str) -> str:
    """Return the ticker symbol for the company/index actually mentioned
    in the question, or DEFAULT_TICKER (SPY) if none is recognized."""
    q = (question or "").lower()
    for name, ticker in TICKER_NAMES.items():
        pattern = r"\b" + re.escape(name) + r"\b"
        if re.search(pattern, q):
            return ticker
    return DEFAULT_TICKER
