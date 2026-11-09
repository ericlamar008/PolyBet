"""
sources/imf.py — IMF International Financial Statistics (IFS) fetcher
(FIX: switched from http:// to https://, since a live test showed the
http:// base URL returning 502 Bad Gateway — likely due to a redirect/
security-policy issue on IMF's side that https avoids).

Covers domains: gdp, cpi — for non-US countries, with QUARTERLY data
(YoY %, computed from the raw index/level series).
Free, no API key required.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

IMF_BASE_URL = "https://dataservices.imf.org/REST/SDMX_JSON.svc/CompactData"  # was http:// — caused 502 in live testing
REQUEST_TIMEOUT_SECONDS = 15

DOMAIN_INDICATOR: dict[str, str] = {
    "cpi": "PCPI_IX",  # Consumer Price Index, all items (index level)
    "gdp": "NGDP_R",   # Real GDP (national currency, level)
}

COUNTRY_CODES: dict[str, str] = {
    "canada": "CA", "united kingdom": "GB", "uk": "GB", "britain": "GB",
    "japan": "JP", "australia": "AU", "germany": "DE", "france": "FR",
    "china": "CN", "india": "IN", "brazil": "BR", "mexico": "MX",
    "south korea": "KR", "italy": "IT", "spain": "ES", "switzerland": "CH",
}

US_EXCLUSION_WORDS = ("united states", "u.s.", "usa", " us ")


def detect_country_code(question: str) -> str | None:
    q = f" {(question or '').lower()} "
    if any(w in q for w in US_EXCLUSION_WORDS):
        return None
    for name, code in COUNTRY_CODES.items():
        if name in q:
            return code
    return None


def fetch_recent_quarterly_series(country_code: str, indicator_code: str, periods: int = 8) -> list[dict[str, Any]]:
    """Fetch the most recent `periods` quarterly observations (oldest
    first, as IMF returns them). Returns [] on any failure."""
    key = f"Q.{country_code}.{indicator_code}"
    url = f"{IMF_BASE_URL}/IFS/{key}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        series = data.get("CompactData", {}).get("DataSet", {}).get("Series", {})
        if isinstance(series, list):
            series = series[0] if series else {}
        obs = series.get("Obs", [])
        if isinstance(obs, dict):
            obs = [obs]
        rows = []
        for o in obs:
            period = o.get("@TIME_PERIOD")
            value = o.get("@OBS_VALUE")
            if period and value is not None:
                rows.append({"period": period, "value": value})
        return rows[-periods:] if rows else []
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        logger.warning("IMF IFS request failed: %s", exc)
        return []


def compute_yoy_change(rows: list[dict[str, Any]]) -> tuple[float, str] | None:
    """Given quarterly rows (oldest first), compute year-over-year %
    change between the latest quarter and the same quarter one year
    (4 quarters) earlier. Returns (yoy_pct, latest_period) or None if
    there isn't enough history."""
    if len(rows) < 5:
        return None
    try:
        latest = float(rows[-1]["value"])
        year_ago = float(rows[-5]["value"])
    except (KeyError, ValueError, TypeError):
        return None
    if year_ago == 0:
        return None
    yoy_pct = (latest - year_ago) / abs(year_ago) * 100.0
    return yoy_pct, rows[-1]["period"]


def get_estimate(question: str, domain: str) -> SourceEstimate | None:
    indicator_code = DOMAIN_INDICATOR.get(domain)
    if indicator_code is None:
        return None

    country_code = detect_country_code(question)
    if country_code is None:
        return None

    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    rows = fetch_recent_quarterly_series(country_code, indicator_code)
    result = compute_yoy_change(rows)
    if result is None:
        return None
    yoy_pct, period = result

    probability = estimate_probability_from_signal(yoy_pct, threshold, comparison, domain=domain)
    return SourceEstimate(
        source_name="IMF IFS", probability=probability, raw_value=yoy_pct,
        asof=period, note=f"country={country_code}, indicator={indicator_code}, YoY% (quarterly)",
    )
