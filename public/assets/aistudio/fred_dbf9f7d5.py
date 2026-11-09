"""
sources/fred.py — FRED fetcher (FIX: added equality/"bucket" question
support, on top of the earlier "pce" domain fix).

Confirmed via live testing:
  - FRED_API_KEY works fine; fetch_latest_observation('PCEPILFE',
    units='pc1') correctly returns e.g. {'value': '3.28653', ...}.
  - parse_threshold_from_question() returns None for questions phrased
    as "Will Core PCE YoY - July 2026 be 3.2%?" -- this is an EQUALITY
    / bucket-style question (each Polymarket outcome is a narrow 0.1pp
    bucket: 3.0, 3.1, 3.2, 3.3...), not a threshold comparison ("above
    X%"), which is the only pattern the existing base.py parser and the
    old get_estimate() here supported.

Fix: get_estimate() now tries the normal threshold parser FIRST (so
fed/cpi/gdp/employment "above/below X" questions are unaffected), and
if that returns None, falls back to a new equality parser that matches
"be X%" / "be exactly X%" / "= X%" phrasing. For an equality-style
target, probability is computed directly here (NOT via
estimate_probability_from_signal, whose signature is threshold/
comparison-based) using a Gaussian centered on the real FRED value,
with a std_dev sized to roughly one bucket-width -- so the bucket
containing (or nearest to) the real print gets the most mass, and
neighbouring buckets get a realistic tail instead of a hard 0/1 cutoff.

Covers domains: fed, cpi, employment, gdp, pce (all FRED series — U.S.
only).
"""

from __future__ import annotations

import logging
import math
import os
import re
import time
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 1

DOMAIN_SERIES: dict[str, str] = {
    "fed": "FEDFUNDS",
    "cpi": "CPIAUCSL",
    "employment": "PAYEMS",
    "gdp": "GDP",
    "pce": "PCEPILFE",  # Core PCE price index (excl. food & energy)
}

TRANSFORM_DOMAINS: frozenset[str] = frozenset({"pce"})

YOY_PATTERN = re.compile(r"\b(yoy|y/y|year[- ]over[- ]year|annual(?:ly)?)\b", re.IGNORECASE)
MOM_PATTERN = re.compile(r"\b(mom|m/m|month[- ]over[- ]month|monthly)\b", re.IGNORECASE)

# Matches "be 3.2%", "be exactly 3.2%", "= 3.2%", "equal 3.2%"
EQUALITY_PATTERN = re.compile(
    r"(?:\bbe\s+(?:exactly\s+)?|\bequal(?:s|to)?\s+|=\s*)(-?\d+(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

# Default bucket half-width (percentage points) used as the Gaussian
# std_dev when no better estimate of Polymarket's bucket spacing is
# known. Most PCE/CPI bucket markets on Polymarket use 0.1pp-wide
# buckets, so a std_dev of ~0.12 spreads most mass onto the correct and
# immediately adjacent buckets, which matches how these markets tend to
# price historically.
DEFAULT_BUCKET_STD_DEV = 0.12


def _detect_units(question: str) -> str:
    if MOM_PATTERN.search(question or ""):
        return "pch"
    return "pc1"


def parse_equality_target(question: str) -> float | None:
    """Extract a single numeric target from an equality-style question
    like "Will Core PCE YoY be 3.2%?". Returns None if no match."""
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
    """Probability mass that the true value falls in the bucket centered
    on `target` (± half a bucket width), given a Gaussian centered on
    `real_value`. Assumes bucket width == std_dev (one bucket each side)."""
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
                logger.info("FRED request timed out, retrying (attempt %d)...", attempt + 1)
                time.sleep(1)
                continue
            logger.warning("FRED request timed out after %d attempt(s).", attempt + 1)
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

    units = _detect_units(question) if domain in TRANSFORM_DOMAINS else None

    parsed = parse_threshold_from_question(question)
    if parsed is not None:
        comparison, threshold = parsed
        obs = fetch_latest_observation(series_id, api_key=api_key, units=units)
        if obs is None:
            return None
        try:
            value = float(obs["value"])
        except (KeyError, ValueError, TypeError):
            return None
        probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
        note = f"series={series_id}" + (f" units={units}" if units else "")
        return SourceEstimate(
            source_name="FRED", probability=probability, raw_value=value,
            asof=obs.get("date"), note=note,
        )

    # Fallback: equality/bucket-style question (e.g. "be 3.2%?"), common
    # for Polymarket's narrow-bucket economic-data markets.
    target = parse_equality_target(question)
    if target is None:
        return None

    obs = fetch_latest_observation(series_id, api_key=api_key, units=units)
    if obs is None:
        return None
    try:
        value = float(obs["value"])
    except (KeyError, ValueError, TypeError):
        return None

    probability = _bucket_probability(value, target)
    note = f"series={series_id}" + (f" units={units}" if units else "") + f" bucket_target={target}"
    return SourceEstimate(
        source_name="FRED", probability=probability, raw_value=value,
        asof=obs.get("date"), note=note,
    )
