"""
sources/boc.py — Bank of Canada Valet API fetcher (NEW). Save as
sources/boc.py in your repo.

Covers domain: boc (Canada's central bank policy rate), mirroring the
ecb.py pattern. Free, no API key required.
Docs: https://www.bankofcanada.ca/valet/docs
Series V39079 = the overnight rate target, daily.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

BOC_VALET_BASE_URL = "https://www.bankofcanada.ca/valet/observations"
DEFAULT_SERIES = "V39079"  # overnight rate target
REQUEST_TIMEOUT_SECONDS = 15


def fetch_latest_rate(series: str = DEFAULT_SERIES) -> dict[str, Any] | None:
    """Fetch the most recent observation for a Bank of Canada Valet
    series. Returns None on any failure so callers can gracefully skip."""
    url = f"{BOC_VALET_BASE_URL}/{series}/json"
    params = {"recent": 1}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        obs = data.get("observations") or []
        if not obs:
            return None
        latest = obs[-1]
        value = latest.get(series, {}).get("v")
        if value is None:
            return None
        return {"value": value, "date": latest.get("d")}
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Bank of Canada Valet request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, series: str = DEFAULT_SERIES) -> SourceEstimate | None:
    if domain != "boc":
        return None
    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    obs = fetch_latest_rate(series=series)
    if obs is None:
        return None
    try:
        value = float(obs["value"])
    except (KeyError, ValueError, TypeError):
        return None

    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(
        source_name="Bank of Canada", probability=probability, raw_value=value,
        asof=obs.get("date"), note=f"series={series}",
    )
