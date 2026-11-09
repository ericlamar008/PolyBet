"""
sources/base.py — shared data types + consensus scoring. REPLACES your
current sources/base.py. Adds the "boe" domain's volatility scale for
the new Bank of England source.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Literal

Comparison = Literal["above", "below"]


@dataclass
class SourceEstimate:
    source_name: str
    probability: float
    raw_value: float | None = None
    asof: str | None = None
    note: str = ""


DOMAIN_VOLATILITY_SCALE: dict[str, float] = {
    "cpi": 0.25,
    "employment": 60.0,
    "gdp": 0.5,
    "fed": 0.25,
    "ecb": 0.25,
    "boc": 0.25,
    "boe": 0.25,  # Bank of England policy rate — same scale as fed/ecb/boc (percentage points)
    "stocks": 0.02,
    "commodities": 0.03,
    "crypto": 0.05,
    "elections": 0.15,
}
DEFAULT_VOLATILITY_SCALE = 0.3

PRICE_LEVEL_DOMAINS = {"stocks", "commodities", "crypto"}

_THRESHOLD_PATTERN = re.compile(
    r"(above|below|over|under|exceed[s]?|more than|less than)\s*\$?([\d,]+\.?\d*)\s*%?",
    re.IGNORECASE,
)
_ABOVE_WORDS = {"above", "over", "exceed", "exceeds", "more than"}


def parse_threshold_from_question(question: str) -> tuple[Comparison, float] | None:
    match = _THRESHOLD_PATTERN.search(question or "")
    if not match:
        return None
    direction_word = match.group(1).lower()
    value = float(match.group(2).replace(",", ""))
    comparison: Comparison = "above" if direction_word in _ABOVE_WORDS else "below"
    return comparison, value


def estimate_probability_from_signal(
    current_value: float,
    threshold: float,
    comparison: Comparison,
    domain: str = "",
) -> float:
    scale = DOMAIN_VOLATILITY_SCALE.get(domain, DEFAULT_VOLATILITY_SCALE)
    if scale <= 0:
        scale = DEFAULT_VOLATILITY_SCALE
    if domain in PRICE_LEVEL_DOMAINS and threshold != 0:
        effective_scale = abs(threshold) * scale
    else:
        effective_scale = scale
    if effective_scale <= 0:
        effective_scale = scale
    z = (current_value - threshold) / effective_scale
    prob_above = 1.0 / (1.0 + math.exp(-z))
    return prob_above if comparison == "above" else 1.0 - prob_above


def compute_consensus_score(estimates: Iterable[SourceEstimate]) -> float:
    ests = list(estimates)
    if not ests:
        return 0.0
    yes_votes = sum(1 for e in ests if e.probability >= 0.5)
    no_votes = len(ests) - yes_votes
    agreeing = max(yes_votes, no_votes)
    return 100.0 * agreeing / len(ests)


def compute_mean_probability(estimates: Iterable[SourceEstimate]) -> float:
    ests = list(estimates)
    if not ests:
        return 0.5
    return sum(e.probability for e in ests) / len(ests)
