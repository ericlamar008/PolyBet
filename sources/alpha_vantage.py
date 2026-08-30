"""
sources/alpha_vantage.py — Alpha Vantage fetcher (FIX: uses the actual
company/index mentioned in the question via ticker_map.py, instead of
always checking SPY regardless of what the market is about). REPLACES
your current sources/alpha_vantage.py.

Covers domains: stocks, commodities, crypto.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question
from .ticker_map import detect_ticker

logger = logging.getLogger(__name__)

ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT_SECONDS = 10

# Commodities/crypto still use a fixed representative instrument, since
# "which specific commodity/coin" is usually unambiguous per-domain
# already (oil, gold, BTC). Only "stocks" needed per-question detection.
DOMAIN_SYMBOL: dict[str, str] = {"commodities": "WTI", "crypto": "BTC"}


def fetch_quote(symbol: str, api_key: str | None = None) -> dict[str, Any] | None:
    key = api_key or os.getenv("ALPHA_VANTAGE_API_KEY")
    if not key:
        logger.info("ALPHA_VANTAGE_API_KEY not set; skipping Alpha Vantage source.")
        return None
    params = {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key}
    try:
        resp = requests.get(ALPHA_VANTAGE_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        quote = data.get("Global Quote") or {}
        return quote if quote else None
    except requests.RequestException as exc:
        logger.warning("Alpha Vantage request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, api_key: str | None = None) -> SourceEstimate | None:
    if domain == "stocks":
        symbol = detect_ticker(question)
    else:
        symbol = DOMAIN_SYMBOL.get(domain)
    if symbol is None:
        return None

    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    quote = fetch_quote(symbol, api_key=api_key)
    if quote is None:
        return None
    try:
        value = float(quote.get("05. price", ""))
    except (ValueError, TypeError):
        return None

    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(
        source_name="Alpha Vantage", probability=probability, raw_value=value,
        asof=quote.get("07. latest trading day"), note=f"symbol={symbol}",
    )
