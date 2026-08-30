"""
sources/finnhub.py — Finnhub fetcher (FIX: uses the actual company/index
mentioned in the question via ticker_map.py, instead of always checking
SPY regardless of what the market is about). REPLACES your current
sources/finnhub.py.

Covers domains: stocks, crypto, commodities (via ETF proxy).
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question
from .ticker_map import detect_ticker

logger = logging.getLogger(__name__)

FINNHUB_BASE_URL = "https://finnhub.io/api/v1/quote"
REQUEST_TIMEOUT_SECONDS = 10

DOMAIN_SYMBOL: dict[str, str] = {"commodities": "USO", "crypto": "BINANCE:BTCUSDT"}


def fetch_quote(symbol: str, api_key: str | None = None) -> dict[str, Any] | None:
    key = api_key or os.getenv("FINNHUB_API_KEY")
    if not key:
        logger.info("FINNHUB_API_KEY not set; skipping Finnhub source.")
        return None
    params = {"symbol": symbol, "token": key}
    try:
        resp = requests.get(FINNHUB_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        return data if data.get("c") else None
    except requests.RequestException as exc:
        logger.warning("Finnhub request failed: %s", exc)
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
    value = quote.get("c")
    if value is None:
        return None

    probability = estimate_probability_from_signal(float(value), threshold, comparison, domain=domain)
    return SourceEstimate(
        source_name="Finnhub", probability=probability, raw_value=float(value),
        asof=str(quote.get("t")), note=f"symbol={symbol}",
    )
