"""sources/eia.py — EIA fetcher. Covers domain: commodities.
Save this file as sources/eia.py in your repo."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

EIA_BASE_URL = "https://api.eia.gov/v2/petroleum/pri/spt/data/"
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_SERIES_ID = "RWTC"


def fetch_latest_price(series_id: str = DEFAULT_SERIES_ID, api_key: str | None = None) -> dict[str, Any] | None:
    key = api_key or os.getenv("EIA_API_KEY")
    if not key:
        logger.info("EIA_API_KEY not set; skipping EIA source.")
        return None
    params = {
        "api_key": key, "frequency": "daily", "data[0]": "value",
        "facets[series][]": series_id, "sort[0][column]": "period",
        "sort[0][direction]": "desc", "length": 1,
    }
    try:
        resp = requests.get(EIA_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("response", {}).get("data", [])
        return rows[0] if rows else None
    except requests.RequestException as exc:
        logger.warning("EIA request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, api_key: str | None = None) -> SourceEstimate | None:
    if domain != "commodities":
        return None
    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed
    row = fetch_latest_price(api_key=api_key)
    if row is None:
        return None
    try:
        value = float(row["value"])
    except (KeyError, ValueError, TypeError):
        return None
    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(source_name="EIA", probability=probability, raw_value=value, asof=row.get("period"), note=f"series={DEFAULT_SERIES_ID}")
