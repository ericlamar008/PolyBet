"""
position_logic.py — PolyBet v2.0 Position Sizing & Multi-Leg Hedge Engine.

REPLACES your current position_logic.py.

KEY FIXES IN THIS VERSION:
1. FIX BUG #6 (Barrier Option Longshot Guard):
   Detects "What price will X hit?" / arrow barrier options (`↑ $4,700`) with
   `primary_price < 0.15` and caps their risk at 5% instead of dumping 35% into
   primary and 65% into non-exclusive barrier options.
2. FIX BUG #2 (True Net Scenario ROI Accounting):
   Computes `net_roi_if_wins_pct = (size_pct / market_price) - total_allocated_pct`
   for EVERY leg (Primary, Secondary, Hedge) so you can see the exact net profit/loss
   on total capital under every possible resolution scenario.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sources.aggregator import MarketSignal


@dataclass
class PositionConfig:
    min_x_pct: float = 35.0
    max_x_pct: float = 70.0
    weight_consensus: float = 0.5
    weight_edge: float = 0.5
    edge_cap: float = 0.5
    secondary_cumulative_cap_pct: float = 90.0
    guaranteed_margin_pct: float = 0.05
    barrier_trap_max_pct: float = 5.0


DEFAULT_CONFIG = PositionConfig()


@dataclass
class PositionAllocation:
    outcome: str
    size_pct: float
    role: str
    market_price: float | None = None
    net_roi_if_wins_pct: float | None = None


@dataclass
class PositionPlan:
    market_id: str
    question: str
    consensus_score: float
    edge: float
    num_sources: int
    allocations: list[PositionAllocation] = field(default_factory=list)
    warning: str | None = None
    guaranteed_margin_pct: float | None = None

    @property
    def primary(self) -> PositionAllocation | None:
        return next((a for a in self.allocations if a.role == "primary"), None)

    @property
    def total_allocated_pct(self) -> float:
        return sum(a.size_pct for a in self.allocations)


def _normalized_prices(outcomes: list[str], prices: list[float]) -> dict[str, float]:
    if not outcomes:
        outcomes = ["Yes", "No"]
    if len(prices) < len(outcomes):
        remaining = max(0.0, 1.0 - sum(prices))
        fill = remaining / max(1, (len(outcomes) - len(prices)))
        prices = list(prices) + [fill] * (len(outcomes) - len(prices))
    return dict(zip(outcomes, prices[: len(outcomes)]))


def compute_edge(model_probability: float, market_price: float) -> float:
    return abs(model_probability - market_price)


def compute_position_size(consensus_score: float, edge: float, config: PositionConfig = DEFAULT_CONFIG) -> float:
    consensus_component = max(0.0, min(1.0, consensus_score / 100.0))
    edge_component = max(0.0, min(1.0, edge / config.edge_cap)) if config.edge_cap > 0 else 0.0
    raw_score = config.weight_consensus * consensus_component + config.weight_edge * edge_component
    raw_score = max(0.0, min(1.0, raw_score))
    return config.min_x_pct + raw_score * (config.max_x_pct - config.min_x_pct)


def compute_guaranteed_floor_pct(primary_price: float, margin: float) -> tuple[float, float]:
    if primary_price <= 0:
        return 0.0, margin
    floor_fraction = primary_price * (1 + margin)
    if floor_fraction >= 1.0:
        achieved_margin = (1.0 / primary_price) - 1.0
        return 100.0, achieved_margin
    return floor_fraction * 100.0, margin


def is_barrier_option_trap(question: str, primary_outcome: str, primary_price: float) -> bool:
    """Detect non-exclusive 'What price will X hit?' barrier traps with <15c price."""
    hit_q = bool(re.search(r"\bwhat (?:price )?will .* hit\b", (question or "").lower()))
    arrow_o = bool(re.match(r"^[↑↓]\s*\$?[\d,.]+", (primary_outcome or "").strip()))
    return (hit_q or arrow_o) and primary_price < 0.15


def _attach_net_roi(allocations: list[PositionAllocation]) -> None:
    total_committed = sum(a.size_pct for a in allocations)
    for a in allocations:
        if a.market_price and a.market_price > 0:
            gross = a.size_pct / a.market_price
            a.net_roi_if_wins_pct = round(gross - total_committed, 2)


def build_position_plan(
    market_id: str, question: str, outcomes: list[str], outcome_prices: list[float],
    signal: MarketSignal, config: PositionConfig = DEFAULT_CONFIG,
) -> PositionPlan:
    price_by_outcome = _normalized_prices(outcomes, outcome_prices)
    ordered_outcomes = list(price_by_outcome.keys())
    warning = None

    if signal.num_sources == 0:
        primary_outcome = max(price_by_outcome, key=price_by_outcome.get)
        consensus_score = 0.0
        edge = 0.0
        x_pct = config.min_x_pct
        warning = "no independent sources available — sized at floor, using market-implied favorite"
    else:
        model_probability = signal.mean_probability
        if len(ordered_outcomes) == 2 and "Yes" in price_by_outcome and "No" in price_by_outcome:
            primary_outcome = "Yes" if model_probability >= 0.5 else "No"
            model_prob_for_side = model_probability if primary_outcome == "Yes" else 1 - model_probability
        else:
            primary_outcome = max(price_by_outcome, key=price_by_outcome.get)
            model_prob_for_side = model_probability
        market_price = price_by_outcome[primary_outcome]
        consensus_score = signal.consensus_score
        edge = compute_edge(model_prob_for_side, market_price)
        x_pct = compute_position_size(consensus_score, edge, config)

    primary_price = price_by_outcome.get(primary_outcome, 0.0)

    # Guard against non-exclusive Barrier Option Traps (Bug #6 Fix)
    if is_barrier_option_trap(question, primary_outcome, primary_price):
        capped_size = round(min(config.barrier_trap_max_pct, max(1.0, primary_price * 200.0)), 2)
        allocations = [
            PositionAllocation(
                outcome=primary_outcome,
                size_pct=capped_size,
                role="primary",
                market_price=primary_price,
            )
        ]
        _attach_net_roi(allocations)
        return PositionPlan(
            market_id=market_id,
            question=question,
            consensus_score=consensus_score,
            edge=edge,
            num_sources=signal.num_sources,
            allocations=allocations,
            warning="Barrier option longshot detected — capped allocation at 5% without non-exclusive hedges.",
            guaranteed_margin_pct=None,
        )

    floor_pct, achieved_margin = compute_guaranteed_floor_pct(primary_price, config.guaranteed_margin_pct)
    if floor_pct > x_pct:
        x_pct = floor_pct
    x_pct = min(x_pct, 100.0)

    allocations = [
        PositionAllocation(
            outcome=primary_outcome,
            size_pct=round(x_pct, 2),
            role="primary",
            market_price=primary_price,
        )
    ]

    remaining_pct = 100.0 - x_pct
    remaining_outcomes = [o for o in ordered_outcomes if o != primary_outcome]

    if remaining_pct <= 0 or not remaining_outcomes:
        pass
    elif len(remaining_outcomes) <= 1:
        allocations.append(
            PositionAllocation(
                outcome=remaining_outcomes[0],
                size_pct=round(remaining_pct, 2),
                role="hedge",
                market_price=price_by_outcome.get(remaining_outcomes[0]),
            )
        )
    else:
        cumulative_pct = primary_price * 100.0
        remaining_sorted = sorted(remaining_outcomes, key=lambda o: price_by_outcome[o], reverse=True)
        secondary_selected = []
        for outcome in remaining_sorted:
            if cumulative_pct >= config.secondary_cumulative_cap_pct:
                break
            secondary_selected.append(outcome)
            cumulative_pct += price_by_outcome[outcome] * 100.0

        secondary_weight_total = sum(price_by_outcome[o] for o in secondary_selected) or 1.0
        secondary_budget = remaining_pct * 0.6
        hedge_budget = remaining_pct - secondary_budget

        for outcome in secondary_selected:
            share = price_by_outcome[outcome] / secondary_weight_total
            allocations.append(
                PositionAllocation(
                    outcome=outcome,
                    size_pct=round(secondary_budget * share, 2),
                    role="secondary",
                    market_price=price_by_outcome[outcome],
                )
            )

        hedge_candidates = [o for o in remaining_outcomes if o not in secondary_selected]
        if hedge_candidates:
            hedge_weight_total = sum(price_by_outcome[o] for o in hedge_candidates) or 1.0
            for outcome in hedge_candidates:
                share = price_by_outcome[outcome] / hedge_weight_total
                allocations.append(
                    PositionAllocation(
                        outcome=outcome,
                        size_pct=round(hedge_budget * share, 2),
                        role="hedge",
                        market_price=price_by_outcome[outcome],
                    )
                )
        elif secondary_selected:
            allocations[-1].size_pct = round(allocations[-1].size_pct + hedge_budget, 2)

    _attach_net_roi(allocations)
    return PositionPlan(
        market_id=market_id,
        question=question,
        consensus_score=consensus_score,
        edge=edge,
        num_sources=signal.num_sources,
        allocations=allocations,
        warning=warning,
        guaranteed_margin_pct=round(achieved_margin, 4) if primary_price > 0 else None,
    )
