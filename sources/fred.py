"""
sources/fred.py — PolyBet v2.0 Unit-Aware FRED Fetcher.

REPLACES your current sources/fred.py.

KEY FIXES IN THIS VERSION:
1. FIX BUG #5 (Raw CPI Index ~315 Compared Against YoY Inflation % ~3.4%):
   Previously `TRANSFORM_DOMAINS = frozenset({"pce"})` omitted `"cpi"` and `"gdp"`.
   That caused `CPIAUCSL` to be fetched without `units="pc1"`, returning the raw
   index level (~315.0) and comparing 315.0 against 3.4% inflation!
   Now `TRANSFORM_DOMAINS = frozenset({"pce", "cpi", "gdp"})`, and `"employment"`
   uses `UNRATE` (Official U-3 Unemployment Rate %) when the question asks about
   unemployment rate %.
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from typing import Any

import requests

from .base import (
    SourceEstimate,
    estimate_bucket_probability,
    estimate_probability_from_signal,
    parse_threshold_from_question,
)

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 1

DOMAIN_SERIES: dict[str, str] = {
    "fed": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "employment": "UNRATE",  # Fixed from PAYEMS (~158,000k) to UNRATE (U-3 Unemployment Rate %)
    "gdp": "GDPC1",
    "pce": "PCEPILFE",
}

# FIX BUG #5: Transform CPI, PCE, and GDP into YoY / MoM / QoQ percentage change!
TRANSFORM_DOMAINS: frozenset[str] = frozenset({"pce", "cpi", "gdp"})

YOY_PATTERN = re.compile(r"\b(yoy|y/y|year[- ]over[- ]year|annual(?:ly)?)\b", re.IGNORECASE)
MOM_PATTERN = re.compile(r"\b(mom|m/m|month[- ]over[- ]month|monthly)\b", re.IGNORECASE)

EQUALITY_PATTERN = re.compile(
    r"(?:\bbe\s+(?:exactly\s+)?|\bequal(?:s|to)?\s+|=\s*)(-?\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

DEFAULT_BUCKET_STD_DEV = 0.12


def _detect_units(question: str, domain: str) -> str:
    if domain == "gdp":
        return "pch"
    if MOM_PATTERN.search(question or ""):
        return "pch"
    return "pc1"


def parse_equality_target(question: str) -> float | None:
    match = EQUALITY_PATTERN.search(question or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except (TypeError, ValueError):
        return None


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _bucket_probability(real_value: float, target: float, std_dev: float = DEFAULT_BUCKET_STD_DEV) -> float:
    half_width = std_dev / 2
    z_lo = (target - half_width - real_value) / std_dev
    z_hi = (target + half_width - real_value) / std_dev
    return max(_normal_cdf(z_hi) - _normal_cdf(z_lo), 1e-6)


def _get_with_retry(params: dict[str, Any]) -> requests.Response | None:
    for attempt in range(MAX_RETRIES + 1):
        try:
            return requests.get(FRED_BASE_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            return None
        except requests.RequestException as exc:
            logger.warning("FRED request failed: %s", exc)
            return None
    return None


def fetch_latest_observation(
    series_id: str, api_key: str | None = None, units: str | None = None
) -> dict[str, Any] | None:
    key = api_key or os.getenv("FRED_API_KEY")
    if not key:
        logger.info("FRED_API_KEY not set; skipping FRED source.")
        return None
    params: dict[str, Any] = {
        "series_id": series_id, "api_key": key, "file_type": "json",
        "sort_order": "desc", "limit": 1,
    }
    if units:
        params["units"] = units

    resp = _get_with_retry(params)
    if resp is None:
        return None
    try:
        resp.raise_for_status()
        data = resp.json()
        obs = data.get("observations") or []
        return obs[0] if obs else None
    except (requests.RequestException, ValueError) as exc:
        logger.warning("FRED response error: %s", exc)
        return None


def get_estimate(question: str, domain: str, api_key: str | None = None) -> SourceEstimate | None:
    series_id = DOMAIN_SERIES.get(domain)
    if series_id is None:
        return None

    units = _detect_units(question, domain) if domain in TRANSFORM_DOMAINS else None

    obs = fetch_latest_observation(series_id, api_key=api_key, units=units)
    if obs is None:
        return None
    try:
        value = float(obs["value"])
    except (KeyError, ValueError, TypeError):
        return None

    parsed = parse_threshold_from_question(question)
    if parsed is not None:
        comparison, threshold = parsed
        probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
        note = f"series={series_id}" + (f" units={units}" if units else "")
        return SourceEstimate(
            source_name="FRED", probability=probability, raw_value=value,
            asof=obs.get("date"), note=note,
        )

    target = parse_equality_target(question)
    if target is not None:
        probability = _bucket_probability(value, target)
        note = f"series={series_id}" + (f" units={units}" if units else "") + f" bucket_target={target}"
        return SourceEstimate(
            source_name="FRED", probability=probability, raw_value=value,
            asof=obs.get("date"), note=note,
        )

    bucket_prob = estimate_bucket_probability(value, question, domain=domain)
    if bucket_prob is not None:
        return SourceEstimate(
            source_name="FRED", probability=bucket_prob, raw_value=value,
            asof=obs.get("date"), note=f"series={series_id} range_bucket",
        )
    return None
