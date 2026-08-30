"""sources/bls.py — BLS fetcher. Covers domains: cpi, employment.
Save this file as sources/bls.py in your repo."""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

BLS_BASE_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
REQUEST_TIMEOUT_SECONDS = 10

DOMAIN_SERIES: dict[str, str] = {
    "cpi": "CUUR0000SA0",
    "employment": "CES0000000001",
}


def fetch_latest_observation(series_id: str, api_key: str | None = None) -> dict[str, Any] | None:
    key = api_key or os.getenv("BLS_API_KEY")
    payload: dict[str, Any] = {"seriesid": [series_id]}
    if key:
        payload["registrationkey"] = key
    else:
        logger.info("BLS_API_KEY not set; using unauthenticated (rate-limited) BLS access.")
    try:
        resp = requests.post(BLS_BASE_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        series_list = data.get("Results", {}).get("series", [])
        if not series_list:
            return None
        obs_list = series_list[0].get("data", [])
        return obs_list[0] if obs_list else None
    except requests.RequestException as exc:
        logger.warning("BLS request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, api_key: str | None = None) -> SourceEstimate | None:
    series_id = DOMAIN_SERIES.get(domain)
    if series_id is None:
        return None
    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed
    obs = fetch_latest_observation(series_id, api_key=api_key)
    if obs is None:
        return None
    try:
        value = float(obs["value"])
    except (KeyError, ValueError, TypeError):
        return None
    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    period = f"{obs.get('year', '')}-{obs.get('period', '')}"
    return SourceEstimate(source_name="BLS", probability=probability, raw_value=value, asof=period, note=f"series={series_id}")
