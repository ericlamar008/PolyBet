"""
position_logic.py — Phase 3: position sizing & hedge decision engine
(FIX: guaranteed-floor sizing on the primary outcome).

Problem this fixes: the old sizing computed x_pct purely from consensus/
edge (clamped to [35, 70]), then split the REMAINING budget across
secondary/hedge outcomes with no constraint tying the two together. If
enough budget leaked into cheap "hedge" outcomes, the total amount spent
across ALL outcomes could exceed the payout you'd get back even when the
PRIMARY (most likely / model-favorite) outcome actually won -- i.e. you
could correctly call the outcome and still lose money, because too much
capital evaporated into hedges that didn't pay off.

Fix: before splitting the remaining budget into secondary/hedge, we now
compute the MINIMUM fraction of the budget that must go to primary so
that, if it wins, the payout guarantees at least `guaranteed_margin_pct`
net profit on the ENTIRE budget -- regardless of how the rest is spent
on hedges. Only the budget left over after satisfying that floor is
free to spend on secondary/hedge outcomes.

Math: if you spend `spend` on an outcome priced at `price` (cost per $1
of payout) and it wins, you get back `spend / price`. For the whole
100% budget B to net at least `margin` when primary (priced `p`) wins:

    spend_primary / p >= B * (1 + margin)
    spend_primary >= B * p * (1 + margin)

So the minimum primary fraction is `p * (1 + margin)`. Whatever remains
(1 - that fraction) is free to spend on secondary/hedge outcomes without
ever violating the guarantee, because those outcomes pay nothing when
primary wins anyway -- they only matter for the OTHER scenarios.

If `p * (1 + margin) > 1` (i.e. the market has already priced primary
so expensively that no margin is mathematically achievable without
spending literally everything on it), the floor is capped at 100% and
the achieved margin is reported as whatever `1/p - 1` actually is
(still guaranteed non-negative, just less than the requested target).

X = f(consensus score, edge) is STILL used as before to decide how much
extra conviction to add beyond the guaranteed floor (e.g. a strong edge
can push spend on primary well above the floor), but it can never push
the primary allocation BELOW the floor needed for the guarantee.

Secondary positions for categorical markets are selected by market price
until cumulative probability covered reaches 90% (roadmap spec); the
remaining budget becomes the hedge -- this part of the logic is
unchanged, it just now operates on the post-floor remaining budget.
"""

from __future__ import annotations

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
    # NEW: minimum guaranteed net profit (as a fraction of the total
    # budget) if the primary outcome wins, e.g. 0.05 = guarantee at
    # least +5% net regardless of how hedges are split.
    guaranteed_margin_pct: float = 0.05


DEFAULT_CONFIG = PositionConfig()


@dataclass
class PositionAllocation:
    outcome: str
    size_pct: float
    role: str
    market_price: float | None = None


@dataclass
class PositionPlan:
    market_id: str
    question: str
    consensus_score: float
    edge: float
    num_sources: int
    allocations: list[PositionAllocation] = field(default_factory=list)
    warning: str | None = None
    guaranteed_margin_pct: float | None = None  # NEW: what margin is actually locked in if primary wins

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
    """Minimum % of the budget that must go to primary to guarantee
    `margin` net profit if it wins. Returns (floor_pct, achieved_margin).
    If the requested margin is unreachable (primary too expensive),
    floor is capped at 100% and achieved_margin is whatever is actually
    possible (still >= 0, just less than requested)."""
    if primary_price <= 0:
        return 0.0, margin  # no price info -- can't compute, don't force a floor
    floor_fraction = primary_price * (1 + margin)
    if floor_fraction >= 1.0:
        achieved_margin = (1.0 / primary_price) - 1.0
        return 100.0, achieved_margin
    return floor_fraction * 100.0, margin


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

    # NEW: enforce the guaranteed-floor on primary regardless of how
    # confident the model was. The consensus/edge-driven x_pct can only
    # push spend ABOVE the floor, never below it.
    primary_price = price_by_outcome.get(primary_outcome, 0.0)
    floor_pct, achieved_margin = compute_guaranteed_floor_pct(primary_price, config.guaranteed_margin_pct)
    if floor_pct > x_pct:
        x_pct = floor_pct
    x_pct = min(x_pct, 100.0)

    allocations = [PositionAllocation(outcome=primary_outcome, size_pct=round(x_pct, 2), role="primary", market_price=price_by_outcome.get(primary_outcome))]

    remaining_pct = 100.0 - x_pct
    remaining_outcomes = [o for o in ordered_outcomes if o != primary_outcome]

    if remaining_pct <= 0 or not remaining_outcomes:
        pass  # entire budget already committed to primary to satisfy the guarantee
    elif len(remaining_outcomes) <= 1:
        allocations.append(PositionAllocation(outcome=remaining_outcomes[0], size_pct=round(remaining_pct, 2), role="hedge", market_price=price_by_outcome.get(remaining_outcomes[0])))
    else:
        primary_price_for_cumulative = price_by_outcome[primary_outcome]
        cumulative_pct = primary_price_for_cumulative * 100.0
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
            allocations.append(PositionAllocation(outcome=outcome, size_pct=round(secondary_budget * share, 2), role="secondary", market_price=price_by_outcome[outcome]))

        hedge_candidates = [o for o in remaining_outcomes if o not in secondary_selected]
        if hedge_candidates:
            hedge_weight_total = sum(price_by_outcome[o] for o in hedge_candidates) or 1.0
            for outcome in hedge_candidates:
                share = price_by_outcome[outcome] / hedge_weight_total
                allocations.append(PositionAllocation(outcome=outcome, size_pct=round(hedge_budget * share, 2), role="hedge", market_price=price_by_outcome[outcome]))
        elif secondary_selected:
            allocations[-1].size_pct = round(allocations[-1].size_pct + hedge_budget, 2)

    return PositionPlan(
        market_id=market_id, question=question, consensus_score=consensus_score, edge=edge,
        num_sources=signal.num_sources, allocations=allocations, warning=warning,
        guaranteed_margin_pct=round(achieved_margin, 4) if primary_price > 0 else None,
    )
