"""
sources/worldbank.py — World Bank Open Data API fetcher (NEW). Save as
sources/worldbank.py in your repo.

Covers domains: gdp, cpi, employment — for NON-US countries mentioned in
the market question (complements FRED/BLS which are U.S.-only).

Free, no API key required. Data is ANNUAL and typically lags 6-12+
months behind the current date — this makes it a reasonable background
check for longer-horizon questions, but weak for near-term (7-day)
resolve windows. This limitation is inherent to the World Bank's own
publishing cadence, not a bug here.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

WORLD_BANK_BASE_URL = "https://api.worldbank.org/v2"
REQUEST_TIMEOUT_SECONDS = 15

# Standard World Bank indicator codes (stable, well-documented).
DOMAIN_INDICATOR: dict[str, str] = {
    "gdp": "NY.GDP.MKTP.KD.ZG",       # GDP growth (annual %)
    "cpi": "FP.CPI.TOTL.ZG",          # Inflation, consumer prices (annual %)
    "employment": "SL.UEM.TOTL.ZS",  # Unemployment, total (% of labor force)
}

# ISO 3166-1 alpha-3 codes for countries we might see referenced in
# Polymarket questions. Extend this as needed.
COUNTRY_CODES: dict[str, str] = {
    "canada": "CAN",
    "united kingdom": "GBR",
    "uk": "GBR",
    "britain": "GBR",
    "japan": "JPN",
    "australia": "AUS",
    "germany": "DEU",
    "france": "FRA",
    "china": "CHN",
    "india": "IND",
    "brazil": "BRA",
    "mexico": "MEX",
    "south korea": "KOR",
    "italy": "ITA",
    "spain": "ESP",
    "switzerland": "CHE",
    "eurozone": "EMU",
    "euro area": "EMU",
}

# Words that signal a question is specifically about the U.S. — if
# present, we defer entirely to FRED/BLS and do NOT also fire World Bank,
# to avoid a redundant/conflicting "second US source" under a different
# methodology.
US_EXCLUSION_WORDS = ("united states", "u.s.", "usa", " us ")


def detect_country_code(question: str) -> str | None:
    q = f" {(question or '').lower()} "
    if any(w in q for w in US_EXCLUSION_WORDS):
        return None
    for name, code in COUNTRY_CODES.items():
        if name in q:
            return code
    return None


def fetch_latest_indicator_value(country_code: str, indicator_code: str) -> dict[str, Any] | None:
    """Fetch the most recent non-null annual value for a World Bank
    indicator. Returns None on any failure or if no data is available."""
    url = f"{WORLD_BANK_BASE_URL}/country/{country_code}/indicator/{indicator_code}"
    params = {"format": "json", "per_page": 10, "mrnev": 1}  # most recent non-empty value
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list) or len(data) < 2:
            return None
        rows = data[1]
        for row in rows or []:
            if row.get("value") is not None:
                return row
        return None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("World Bank request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str) -> SourceEstimate | None:
    """Only fires for non-US countries explicitly named in the question,
    for the gdp/cpi/employment domains, and only when the question has an
    explicit numeric threshold (same convention as FRED/BLS/BEA)."""
    indicator_code = DOMAIN_INDICATOR.get(domain)
    if indicator_code is None:
        return None

    country_code = detect_country_code(question)
    if country_code is None:
        return None  # no recognized non-US country mentioned -> defer to FRED/BLS

    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    row = fetch_latest_indicator_value(country_code, indicator_code)
    if row is None:
        return None
    try:
        value = float(row["value"])
    except (KeyError, ValueError, TypeError):
        return None

    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(
        source_name="World Bank", probability=probability, raw_value=value,
        asof=row.get("date"), note=f"country={country_code}, indicator={indicator_code} (ANNUAL data — may lag current period)",
    )
