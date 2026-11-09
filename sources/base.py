"""
sources/base.py — PolyBet v2.0 Shared Data Types, Range-Bucket Integration & Bayesian Consensus.

REPLACES your current sources/base.py.

KEY FIXES IN THIS VERSION:
1. FIX BUG #10 (Single-Source 100% Consensus Illusion):
   Previously `compute_consensus_score` returned `100.0 * agreeing / len(ests)`,
   which ALWAYS returned `100.0%` when `len(ests) == 1` (`1/1 = 100%`).
   Now applies Empirical Bayes shrinkage (`n / (n + 1.5)`) so a single uncorroborated
   source achieves at most 40.0% consensus confidence, scaling toward 80%+ only
   when >= 3 independent sources agree.
2. FIX BUG #4 (Wired `range_bucket.py` into `parse_bucket_or_threshold`):
   Allows any source fetcher to evaluate narrow bucket/range questions (`0.3%–0.5%`,
   `≤3.8%`, `<0.0%`) using Gaussian CDF integration.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Iterable, Literal

from .range_bucket import parse_bucket_label

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
    "pce": 0.20,
    "employment": 0.20,  # Unemployment rate % std_dev (fixed from 60.0 payrolls!)
    "gdp": 0.5,
    "fed": 0.25,
    "ecb": 0.25,
    "boc": 0.25,
    "boe": 0.25,
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


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def estimate_bucket_probability(current_value: float, label_or_question: str, domain: str = "") -> float | None:
    """FIX BUG #4: Evaluate probability that `current_value` falls in a range bucket."""
    bucket = parse_bucket_label(label_or_question)
    if bucket is None:
        return None
    std = DOMAIN_VOLATILITY_SCALE.get(domain, 0.20)
    lo = -10.0 if math.isinf(bucket.low) else bucket.low - 0.05
    hi = 10.0 if math.isinf(bucket.high) else bucket.high + 0.05
    z_lo = (lo - current_value) / max(std, 0.05)
    z_hi = (hi - current_value) / max(std, 0.05)
    return max(1e-4, min(0.999, _normal_cdf(z_hi) - _normal_cdf(z_lo)))


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
    prob_above = 1.0 / (1.0 + math.exp(-max(-20.0, min(20.0, z))))
    return prob_above if comparison == "above" else 1.0 - prob_above


def compute_consensus_score(estimates: Iterable[SourceEstimate], prior_k: float = 1.5) -> float:
    """FIX BUG #10: Empirical Bayes shrinkage prevents n=1 from returning 100.0%."""
    ests = list(estimates)
    n = len(ests)
    if n == 0:
        return 0.0
    yes_votes = sum(1 for e in ests if e.probability >= 0.5)
    no_votes = n - yes_votes
    raw_agreement = max(yes_votes, no_votes) / n
    credibility_weight = n / (n + prior_k)
    return round(100.0 * raw_agreement * credibility_weight, 1)


def compute_mean_probability(estimates: Iterable[SourceEstimate]) -> float:
    ests = list(estimates)
    if not ests:
        return 0.5
    return sum(e.probability for e in ests) / len(ests)
