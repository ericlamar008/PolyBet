"""sources/bea.py — BEA fetcher. Covers domain: gdp.
Save this file as sources/bea.py in your repo."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

BEA_BASE_URL = "https://apps.bea.gov/api/data/"
REQUEST_TIMEOUT_SECONDS = 10


def fetch_latest_gdp_growth(api_key: str | None = None) -> dict[str, Any] | None:
    key = api_key or os.getenv("BEA_API_KEY")
    if not key:
        logger.info("BEA_API_KEY not set; skipping BEA source.")
        return None
    params = {
        "UserID": key, "method": "GetData", "datasetname": "NIPA",
        "TableName": "T10101", "Frequency": "Q", "Year": "X", "ResultFormat": "JSON",
    }
    try:
        resp = requests.get(BEA_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("BEAAPI", {}).get("Results", {}).get("Data", [])
        gdp_rows = [r for r in rows if r.get("LineNumber") == "1"]
        if not gdp_rows:
            return None
        gdp_rows.sort(key=lambda r: r.get("TimePeriod", ""))
        return gdp_rows[-1]
    except requests.RequestException as exc:
        logger.warning("BEA request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, api_key: str | None = None) -> SourceEstimate | None:
    if domain != "gdp":
        return None
    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed
    row = fetch_latest_gdp_growth(api_key=api_key)
    if row is None:
        return None
    try:
        value = float(str(row["DataValue"]).replace(",", ""))
    except (KeyError, ValueError, TypeError):
        return None
    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(source_name="BEA", probability=probability, raw_value=value, asof=row.get("TimePeriod"), note="table=T10101 line=1")
