"""
sources/aggregator.py — PolyBet v2.0 Multi-Source Signal Aggregator.

REPLACES your current sources/aggregator.py.
"""

from __future__ import annotations

import logging
from typing import Callable

from . import alpha_vantage, bea, bls, boc, boe, ecb, eia, eurostat, finnhub, fred, polls, worldbank
from .base import SourceEstimate, compute_consensus_score, compute_mean_probability

logger = logging.getLogger(__name__)

GetEstimateFn = Callable[[str, str], "SourceEstimate | None"]

DOMAIN_SOURCES: dict[str, list[GetEstimateFn]] = {
    "fed": [fred.get_estimate],
    "cpi": [fred.get_estimate, bls.get_estimate, eurostat.get_estimate, worldbank.get_estimate],
    "pce": [fred.get_estimate, bea.get_estimate],
    "employment": [fred.get_estimate, bls.get_estimate, worldbank.get_estimate],
    "gdp": [fred.get_estimate, bea.get_estimate, eurostat.get_estimate, worldbank.get_estimate],
    "ecb": [ecb.get_estimate],
    "boc": [boc.get_estimate],
    "boe": [boe.get_estimate],
    "stocks": [alpha_vantage.get_estimate, finnhub.get_estimate],
    "commodities": [alpha_vantage.get_estimate, finnhub.get_estimate, eia.get_estimate],
    "crypto": [alpha_vantage.get_estimate, finnhub.get_estimate],
    "elections": [polls.get_estimate],
}


def collect_estimates(question: str, domain: str) -> list[SourceEstimate]:
    fns = DOMAIN_SOURCES.get(domain, [])
    estimates: list[SourceEstimate] = []
    for fn in fns:
        try:
            est = fn(question, domain)
        except Exception as exc:
            logger.warning("Source fetcher %s raised: %s", getattr(fn, "__module__", fn), exc)
            est = None
        if est is not None:
            estimates.append(est)
    return estimates


class MarketSignal:
    """Aggregated multi-source signal for one market, with Bayesian consensus."""

    def __init__(self, estimates: list[SourceEstimate]):
        self.estimates = estimates
        self.consensus_score = compute_consensus_score(estimates)
        self.mean_probability = compute_mean_probability(estimates)
        self.num_sources = len(estimates)

    def __repr__(self) -> str:
        return f"MarketSignal(n={self.num_sources}, consensus={self.consensus_score:.1f}, mean_p={self.mean_probability:.2f})"


def build_signal(question: str, domain: str) -> MarketSignal:
    estimates = collect_estimates(question, domain)
    return MarketSignal(estimates)
