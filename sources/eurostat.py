"""
sources/eurostat.py — Eurostat REST API fetcher (FIX: corrected the CPI
unit code — live testing showed GDP worked but CPI returned no data with
unit="RCH_A_AVG"; switched to "RCH_A", the standard Eurostat code for
"annual rate of change" used by the prc_hicp_manr dataset). REPLACES your
current sources/eurostat.py.

Covers domains: cpi, gdp — for Eurozone/EU countries, with MONTHLY
(CPI/HICP) or QUARTERLY (GDP) data.
Free, no API key required.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

EUROSTAT_BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
REQUEST_TIMEOUT_SECONDS = 15

DOMAIN_DATASET: dict[str, str] = {
    "cpi": "prc_hicp_manr",
    "gdp": "namq_10_gdp",
}

COUNTRY_CODES: dict[str, str] = {
    "eurozone": "EA20", "euro area": "EA20", "european union": "EU27_2020",
    "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES",
    "netherlands": "NL", "belgium": "BE", "austria": "AT", "portugal": "PT",
    "greece": "EL", "ireland": "IE", "finland": "FI",
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


def fetch_latest_value(dataset: str, country_code: str, domain: str) -> dict[str, Any] | None:
    """Fetch the most recent observation for a Eurostat dataset+country.
    Returns None on any failure so callers can gracefully skip."""
    params: dict[str, Any] = {"format": "JSON", "lang": "EN", "geo": country_code, "sinceTimePeriod": "2023"}
    if domain == "cpi":
        params["coicop"] = "CP00"
        params["unit"] = "RCH_A"  # was "RCH_A_AVG" — live test showed no data with that code
    elif domain == "gdp":
        params["na_item"] = "B1GQ"
        params["unit"] = "CLV_PCH_SM"
        params["s_adj"] = "SCA"

    url = f"{EUROSTAT_BASE_URL}/{dataset}"
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        values = data.get("value", {})
        if not values:
            return None
        time_categories = data.get("dimension", {}).get("time", {}).get("category", {}).get("label", {})
        latest_key = str(max(int(k) for k in values.keys()))
        value = values.get(latest_key)
        if value is None:
            return None
        period_labels = list(time_categories.values())
        period = period_labels[-1] if period_labels else None
        return {"value": value, "period": period}
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Eurostat request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str) -> SourceEstimate | None:
    dataset = DOMAIN_DATASET.get(domain)
    if dataset is None:
        return None

    country_code = detect_country_code(question)
    if country_code is None:
        return None

    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    row = fetch_latest_value(dataset, country_code, domain)
    if row is None:
        return None
    try:
        value = float(row["value"])
    except (KeyError, ValueError, TypeError):
        return None

    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(
        source_name="Eurostat", probability=probability, raw_value=value,
        asof=row.get("period"), note=f"country={country_code}, dataset={dataset}",
    )
