"""
sources/range_bucket.py - Generic handler for "bucket/range" prediction
markets (e.g. Polymarket's "Canada GDP: June 2026 (MoM)" with outcomes
like "<0.0%", "0.0-0.1%", "0.2-0.3%", "0.8%+").

Root cause this fixes: markets like this have NO numeric threshold in the
event title (the group_title) -- the numbers live in the individual
outcome/candidate labels. The existing parse_threshold_from_question()
only ever looks at the title, so it always returns None here and every
source silently no-ops, falling back to "floor + market-implied favorite".

This module:
  1. Detects whether a group's outcome labels are numeric ranges.
  2. Parses each label into (low, high) bounds (open-ended on either side).
  3. Given one real "point estimate" for the underlying quantity (e.g. a
     real MoM GDP print), spreads a probability mass across the buckets
     using a Gaussian centered on that point estimate, so buckets near
     the real value get most of the mass and neighbours get a realistic
     tail instead of one bucket getting artificially 100%.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_RANGE_RE = re.compile(
    r"^\s*(?:<\s*(?P<lt>-?\d+(?:\.\d+)?))"
    r"|^\s*(?P<gt>-?\d+(?:\.\d+)?)\s*%?\s*\+\s*$"
    r"|^\s*(?P<lo>-?\d+(?:\.\d+)?)\s*(?:-|to)\s*(?P<hi>-?\d+(?:\.\d+)?)\s*%?\s*$"
)


@dataclass
class Bucket:
    label: str
    low: float
    high: float


def parse_bucket_label(label: str) -> Bucket | None:
    cleaned = label.strip()
    m = _RANGE_RE.match(cleaned)
    if not m:
        return None
    if m.group("lt") is not None:
        return Bucket(label=label, low=-math.inf, high=float(m.group("lt")))
    if m.group("gt") is not None:
        return Bucket(label=label, low=float(m.group("gt")), high=math.inf)
    if m.group("lo") is not None and m.group("hi") is not None:
        lo, hi = float(m.group("lo")), float(m.group("hi"))
        return Bucket(label=label, low=min(lo, hi), high=max(lo, hi))
    return None


def try_parse_all_buckets(labels: list[str]) -> list[Bucket | None] | None:
    parsed = [parse_bucket_label(lbl) for lbl in labels]
    n_ok = sum(1 for p in parsed if p is not None)
    if n_ok < 3 or n_ok < 0.75 * len(labels):
        return None
    return parsed


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def distribute_probability(
    real_value: float,
    buckets: list[Bucket | None],
    std_dev: float,
) -> list[float | None]:
    masses: list[float | None] = []
    for b in buckets:
        if b is None:
            masses.append(None)
            continue
        lo = -10.0 if math.isinf(b.low) else b.low
        hi = 10.0 if math.isinf(b.high) else b.high
        z_lo = (lo - real_value) / std_dev
        z_hi = (hi - real_value) / std_dev
        mass = _normal_cdf(z_hi) - _normal_cdf(z_lo)
        masses.append(max(mass, 1e-6))
    total = sum(m for m in masses if m is not None)
    if total <= 0:
        return masses
    return [(m / total if m is not None else None) for m in masses]
