"""
sources/polls.py — polling-average fetcher. Covers domain: elections.
Save this file as sources/polls.py in your repo.

Unlike the other Phase-2 sources, there is no single free, structured
polling API that works for an arbitrary election question. Per the
roadmap's own file structure (`polls_scrape.py`), this is inherently a
per-race, best-effort scraper: you map keywords from the market question
to a Wikipedia "opinion polling" article, and this module extracts the
leading candidate's polling percentage from that page's prose.

This is intentionally conservative: if no mapping matches the question,
or the page structure doesn't match the expected pattern, it returns
None and the market falls back to `position_logic`'s "no independent
sources — market-favorite at floor size" behavior, exactly as for any
other domain with no available data. Extend RACE_PAGE_MAP with your own
races as needed — this is meant to be edited by you per the roadmap's
"non-generalizable, per-race" nature of election forecasting.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

from .base import SourceEstimate, estimate_probability_from_signal, parse_threshold_from_question

logger = logging.getLogger(__name__)

WIKIPEDIA_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"
REQUEST_TIMEOUT_SECONDS = 10

# keyword (lowercase, matched against the market question) -> Wikipedia
# article title for that race's polling-average page. Extend this dict
# per race; this is a placeholder mapping, not a generalized solution.
RACE_PAGE_MAP: dict[str, str] = {
    # "special election": "Opinion_polling_for_the_2026_XX_special_election",
}

# Matches patterns like "leads with 52%" or "at 47.5% support" in prose.
_LEAD_PERCENT_PATTERN = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def _find_race_page(question: str) -> str | None:
    q = (question or "").lower()
    for keyword, page_title in RACE_PAGE_MAP.items():
        if keyword in q:
            return page_title
    return None


def fetch_page_summary(page_title: str) -> dict[str, Any] | None:
    url = f"{WIKIPEDIA_REST_BASE}/{page_title}"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning("Wikipedia summary request failed: %s", exc)
        return None


def extract_leading_percentage(summary_text: str) -> float | None:
    """Best-effort extraction of the first percentage mentioned in the
    page summary prose, treated as the leading candidate's polling share.
    This is a coarse heuristic — verify manually for any race you rely on."""
    match = _LEAD_PERCENT_PATTERN.search(summary_text or "")
    if not match:
        return None
    return float(match.group(1))


def get_estimate(question: str, domain: str) -> SourceEstimate | None:
    if domain != "elections":
        return None
    page_title = _find_race_page(question)
    if page_title is None:
        logger.info("No RACE_PAGE_MAP entry matches this question; skipping polls source.")
        return None
    parsed = parse_threshold_from_question(question)
    if parsed is None:
        return None
    comparison, threshold = parsed

    summary = fetch_page_summary(page_title)
    if summary is None:
        return None
    value = extract_leading_percentage(summary.get("extract", ""))
    if value is None:
        return None

    probability = estimate_probability_from_signal(value, threshold, comparison, domain=domain)
    return SourceEstimate(source_name="Polls (Wikipedia)", probability=probability, raw_value=value, asof=summary.get("timestamp"), note=f"page={page_title}")
