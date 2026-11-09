"""
sources/bls.py — PolyBet v2.0 Fixed BLS Fetcher (Unemployment Rate LNS14000000 & CPI YoY %).

REPLACES your current sources/bls.py.

KEY FIXES IN THIS VERSION:
1. FIX BUG #9 (BLS Nonfarm Payroll Level 158,000k Compared Against 4.1% Unemployment Rate):
   Previously `DOMAIN_SERIES["employment"] = "CES0000000001"` fetched total nonfarm
   employees (~158,000 thousand) and compared 158,000 directly against `4.1%`
   unemployment rate, yielding Z = +2633 -> probability = 1.0 (100%)!
   Now uses `"LNS14000000"` (Official U-3 Unemployment Rate %) for unemployment
   questions, and computes 12-month YoY % change for `"CUUR0000SA0"` (CPI-U).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import requests

from .base import (
    SourceEstimate,
    estimate_bucket_probability,
    estimate_probability_from_signal,
    parse_threshold_from_question,
)
from .fred import parse_equality_target, _bucket_probability

logger = logging.getLogger(__name__)

BLS_BASE_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/"
REQUEST_TIMEOUT_SECONDS = 12

DOMAIN_SERIES: dict[str, str] = {
    "cpi": "CUUR0000SA0",
    "employment": "LNS14000000",  # Official U-3 Unemployment Rate (%)
}


def fetch_series_observations(series_id: str, api_key: str | None = None) -> list[dict[str, Any]]:
    key = api_key or os.getenv("BLS_API_KEY")
    payload: dict[str, Any] = {"seriesid": [series_id]}
    if key:
        payload["registrationkey"] = key
    try:
        resp = requests.post(BLS_BASE_URL, json=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        series_list = data.get("Results", {}).get("series", [])
        if not series_list:
            return []
        return series_list[0].get("data", []) or []
    except requests.RequestException as exc:
        logger.warning("BLS request failed: %s", exc)
        return []


def _extract_effective_metric(obs_list: list[dict[str, Any]], domain: str, question: str) -> tuple[float | None, str]:
    if not obs_list:
        return None, ""
    latest = obs_list[0]
    period = f"{latest.get('year', '')}-{latest.get('period', '')}"
    try:
        latest_val = float(latest["value"])
    except (KeyError, ValueError, TypeError):
        return None, period

    if domain == "cpi":
        # Convert raw CPI index (~315) into YoY % or MoM % change!
        is_mom = bool(re.search(r"\b(mom|m/m|monthly|month[- ]over[- ]month)\b", question or "", re.I))
        lag_idx = 1 if is_mom else 12
        if len(obs_list) > lag_idx:
            try:
                base_val = float(obs_list[lag_idx]["value"])
                if base_val > 0:
                    pct_change = ((latest_val - base_val) / base_val) * 100.0
                    return round(pct_change, 3), period
            except (KeyError, ValueError, TypeError):
                pass
        return None, period

    return latest_val, period


def get_estimate(question: str, domain: str, api_key: str | None = None) -> SourceEstimate | None:
    series_id = DOMAIN_SERIES.get(domain)
    if series_id is None:
        return None

    obs_list = fetch_series_observations(series_id, api_key=api_key)
    value, period = _extract_effective_metric(obs_list, domain, question)
    if value is None:
        return None

    parsed = parse_threshold_from_question(question)
    if parsed is not None:
        comparison, threshold = parsed
        probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
        return SourceEstimate(
            source_name="BLS", probability=probability, raw_value=value,
            asof=period, note=f"series={series_id}",
        )

    target = parse_equality_target(question)
    if target is not None:
        probability = _bucket_probability(value, target)
        return SourceEstimate(
            source_name="BLS", probability=probability, raw_value=value,
            asof=period, note=f"series={series_id} target={target}",
        )

    bucket_prob = estimate_bucket_probability(value, question, domain=domain)
    if bucket_prob is not None:
        return SourceEstimate(
            source_name="BLS", probability=bucket_prob, raw_value=value,
            asof=period, note=f"series={series_id} range_bucket",
        )
    return None
