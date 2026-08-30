"""
sources/boe.py — Bank of England Interactive Statistical Database (IADB)
fetcher (FIX: added browser-like User-Agent header, since a live test
showed the IADB endpoint returns 403 Forbidden without one — a common
anti-bot measure on legacy government endpoints).

Covers domain: boe (UK policy rate — "Bank Rate").
Free, no API key required.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

BOE_IADB_BASE_URL = "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
DEFAULT_SERIES = "IUDBEDR"  # Bank Rate
REQUEST_TIMEOUT_SECONDS = 15

# The IADB endpoint returns 403 Forbidden to requests without a
# browser-like User-Agent (confirmed via live testing) — Python's default
# "python-requests/X.Y" is blocked.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def fetch_latest_rate(series: str = DEFAULT_SERIES) -> dict[str, Any] | None:
    """Fetch the most recent Bank Rate observation via the IADB CSV
    export. Returns None on any failure so callers can gracefully skip."""
    now = datetime.now(timezone.utc)
    params = {
        "csv.x": "yes",
        "SeriesCodes": series,
        "UsingCodes": "Y",
        "CSVF": "TT",
        "Datefrom": "01/Jan/2020",
        "Dateto": now.strftime("%d/%b/%Y"),
    }
    try:
        resp = requests.get(
            BOE_IADB_BASE_URL, params=params, headers=_HEADERS, timeout=REQUEST_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        lines = [l for l in resp.text.strip().splitlines() if l.strip()]
        if len(lines) < 2:
            return None
        last_line = lines[-1]
        parts = [p.strip().strip('"') for p in last_line.split(",")]
        if len(parts) < 2:
            return None
        date_str, value_str = parts[0], parts[1]
        return {"value": value_str, "date": date_str}
    except (requests.RequestException, ValueError, IndexError) as exc:
        logger.warning("Bank of England IADB request failed: %s", exc)
        return None


def get_estimate(question: str, domain: str, series: str = DEFAULT_SERIES) -> SourceEstimate | None:
    if domain != "boe":
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
        source_name="Bank of England", probability=probability, raw_value=value,
        asof=obs.get("date"), note=f"series={series}",
    )
