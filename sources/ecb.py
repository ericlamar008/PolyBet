"""
sources/ecb.py — European Central Bank (ECB SDW) fetcher. REPLACES your
current sources/ecb.py — the trend-based fallback added earlier has been
REMOVED per your instruction; back to numeric-threshold-only.

Covers domain: ecb.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

ECB_SDW_BASE_URL = "https://data-api.ecb.europa.eu/service/data"
DEFAULT_SERIES_KEY = "FM/D.U2.EUR.4F.KR.MRR_FR.LEV"
REQUEST_TIMEOUT_SECONDS = 15


def fetch_latest_rate(series_key: str = DEFAULT_SERIES_KEY) -> dict[str, Any] | None:
    """Fetch the most recent observation for an ECB SDW series. No key
    needed. Returns None on any failure so callers can gracefully skip."""
    url = f"{ECB_SDW_BASE_URL}/{series_key}"
    params = {"format": "jsondata", "lastNObservations": 1}
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        series = data.get("dataSets", [{}])[0].get("series", {})
        if not series:
            return None
        first_series = next(iter(series.values()))
        observations = first_series.get("observations", {})
        if not observations:
            return None
        last_key = sorted(observations.keys(), key=lambda k: int(k))[-1]
        value = observations[last_key][0]

        time_dim = data.get("structure", {}).get("dimensions", {}).get("observation", [{}])[0]
        periods = [v.get("id") for v in time_dim.get("values", [])]
        period = periods[int(last_key)] if periods and int(last_key) < len(periods) else None
        return {"value": value, "period": period}
    except (requests.RequestException, ValueError, KeyError, IndexError, StopIteration) as exc:
        logger.warning("ECB SDW request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, series_key: str = DEFAULT_SERIES_KEY) -> SourceEstimate | None:
    """Only handles questions with an explicit numeric threshold. Binary
    questions with no number return None — no heuristic fallback."""
    if domain != "ecb":
        return None
    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    obs = fetch_latest_rate(series_key=series_key)
    if obs is None:
        return None
    try:
        value = float(obs["value"])
    except (KeyError, ValueError, TypeError):
        return None

    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(source_name="ECB SDW", probability=probability, raw_value=value, asof=obs.get("period"), note=f"series={series_key}")
