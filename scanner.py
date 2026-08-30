"""
scanner.py — Phase 1 (FIX round 2: state-name false-positive + ambiguous
"gold" keyword + new Trump-behavior exclusion filter).

REPLACES your current scanner.py.

WHAT CHANGED vs your last version
----------------------------------
1. BUG FIX — "Georgia Tree" / candidate-name-collides-with-US-state-name:
   `Secret Harbour State By-Election Winner` (a non-US, non-American race)
   was being classified as a US election because one of the CANDIDATES is
   named "Georgia Tree" — the word "Georgia" matched the US_STATE_NAMES
   list, which was checked against the full candidate question text.
   FIX: state names are now only checked against the EVENT-level context
   (event_title + tags), never against an individual candidate's own
   question. Real US races always carry the state name in the event title
   itself (e.g. "Massachusetts Governor Republican Primary Winner"); a
   candidate's personal name coincidentally matching a state should never
   count. All other US-ness signals (u.s., electoral college, "democratic
   nominee", senate/governor/congress, etc.) are unaffected and still
   checked against the full text, since those are legitimate anywhere they
   appear.

2. BUG FIX — ambiguous "gold" keyword: `Trump-named things Trump will
   mention` (containing the phrase "Trump Gold Card") was pulled into
   `commodities` purely because the word "gold" appears in a product name,
   the same class of bug as the already-fixed "Olympic gold medal" case,
   just a different false-positive source (product name, not sport).
   FIX: "gold" and "silver" (the only ambiguous, non-sport commodity
   keywords) now additionally require a price-context word nearby (price,
   xau, xag, ounce, $, "hit high/low") before they count as `commodities`.
   Unambiguous commodity keywords (oil, crude, opec, natural gas, wti) are
   untouched.

3. NEW — Trump personal-behavior markets are now excluded entirely (return
   to DEFAULT_CATEGORY -> dropped by filter_to_roadmap_domains), per user
   request: these are inherently unpredictable (whims of what someone says
   or does on a given day) and no independent data source could ever model
   them. Guard checked BEFORE any economic/political keyword, same pattern
   as SPORTS_SIGNALS. Catches things like "Will Trump publicly insult X",
   "Will Trump try to fire Powell", "What Trump-named things will Trump
   mention", "What will Karoline Leavitt say...". Legitimate Trump POLICY
   markets (elections, bills, tariffs, appointments announced through
   normal channels) are NOT caught by this -- only speech-act / personal-
   whim verbs (insult, mention, tweet, post, say, name, fire, call,
   publicly). If you spot another Trump-behavior market slipping through,
   just add its verb to TRUMP_BEHAVIOR_VERBS below.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests

logger = logging.getLogger(__name__)

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
MARKETS_ENDPOINT = f"{GAMMA_API_BASE}/markets"
DEFAULT_RESOLVE_WINDOW_DAYS = 7
DEFAULT_PAGE_LIMIT = 100
DEFAULT_MAX_PAGES = 300
REQUEST_TIMEOUT_SECONDS = 15

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fed": ("fed", "federal reserve", "fomc", "powell"),
    "cpi": ("cpi", "inflation", "consumer price index"),
    "pce": ("pce", "personal consumption expenditures", "core pce"),
    "employment": ("unemployment", "nonfarm", "payroll", "jobs report", "jobless"),
    "gdp": ("gdp", "gross domestic product", "recession"),
    "ecb": ("ecb", "european central bank", "lagarde", "eurozone rate"),
    "boc": ("bank of canada", "boc rate", "macklem"),
    "boe": ("bank of england", "boe rate", "bailey"),
    "central_banks_other": (
        "bank of korea", "boj", "bank of japan", "reserve bank of australia",
        "rba rate", "reserve bank of new zealand", "rbnz", "snb",
        "swiss national bank", "pboc", "people's bank of china",
        "bank of mexico", "banxico", "sarb", "south african reserve bank",
    ),
    "stocks": ("s&p", "nasdaq", "dow jones", "stock", "equity", "earnings"),
    "commodities": ("oil", "gold", "silver", "crude", "opec", "commodity", "natural gas"),
    "elections": ("election", "president", "senate", "congress", "governor", "vote", "primary"),
    "crypto": ("bitcoin", "btc", "ethereum", "eth", "crypto", "altcoin"),
}
DEFAULT_CATEGORY = "other"
ROADMAP_DOMAINS: frozenset[str] = frozenset(CATEGORY_KEYWORDS.keys())

US_STATE_NAMES: tuple[str, ...] = (
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
)

# Generic STRONG signals -- legitimate anywhere they appear (candidate
# question, event title, tags). State names are handled SEPARATELY (see
# is_us_election) because they falsely match candidate personal names.
US_STRONG_SIGNALS: tuple[str, ...] = (
    "united states", "u.s.", "usa", "electoral college", "midterm",
    "white house", "democratic nominee", "republican nominee",
    "house of representatives",
)
# WEAK signals: safe to trust on their own since nothing else uses them.
US_WEAK_SIGNALS: tuple[str, ...] = ("senate", "governor", "congress")

NON_US_COUNTRY_SIGNALS: tuple[str, ...] = (
    "japan", "korea", "china", "brazil", "argentina", "chile", "peru",
    "mexico", "france", "germany", "italy", "spain", "uk", "united kingdom",
    "britain", "india", "australia", "philippines", "indonesia", "canada",
    "taiwan", "poland", "portugal", "netherlands", "sweden", "norway",
    "turkey", "israel", "egypt", "nigeria", "kenya", "colombia",
    "venezuela", "ireland", "greece", "austria", "switzerland", "belgium",
    "romania",
)

SPORTS_SIGNALS: tuple[str, ...] = (
    "medal", "olympic", "olympics", "tournament", "championship",
    "playoffs", "playoff", "world cup", "super bowl", "grand slam",
    "final four", "world series", "stanley cup", "nba", "nfl", "mlb",
    "nhl", "ufc", "boxing", "wrestlemania", "grand prix", "match",
    "vs.", "vs ", "wins the game", "wins the match", "fight card",
)

# Ambiguous commodity keywords that also show up in unrelated product
# names / slang ("Trump Gold Card", "gold medal" -- the latter is already
# caught by SPORTS_SIGNALS). Require one of these price-context words
# nearby before "gold"/"silver" count toward the commodities category.
AMBIGUOUS_COMMODITY_KEYWORDS: frozenset[str] = frozenset({"gold", "silver"})
PRICE_CONTEXT_SIGNALS: tuple[str, ...] = (
    "price", "xau", "xag", "ounce", "$", "hit high", "hit low", "per ounce",
)

# Trump / WH-press-secretary personal-behavior markets: inherently
# unpredictable speech-acts, not modelable by any economic/political data
# source. Excluded entirely regardless of what else the question mentions.
TRUMP_BEHAVIOR_VERBS: tuple[str, ...] = (
    "insult", "mention", "tweet", "post", "say", "says", "said", "name",
    "named", "fire", "call", "publicly",
)


def word_in_text(keyword: str, text: str) -> bool:
    pattern = r"\b" + re.escape(keyword) + r"\b"
    return re.search(pattern, text) is not None


def is_sports_market(haystack: str) -> bool:
    for sig in SPORTS_SIGNALS:
        stripped = sig.strip()
        if "." in stripped:
            if stripped in haystack:
                return True
        elif word_in_text(stripped, haystack):
            return True
    return False


def is_trump_behavior_market(haystack: str) -> bool:
    if "leavitt" in haystack:
        return True
    if "trump" not in haystack:
        return False
    return any(word_in_text(verb, haystack) for verb in TRUMP_BEHAVIOR_VERBS)


def is_us_election(haystack: str, context_haystack: str) -> bool:
    """`haystack` = full text (question + tags + event_title), used for
    every US-ness signal EXCEPT state names. `context_haystack` = event-level
    text only (event_title + tags, never the individual candidate question)
    -- this is the only text state names are allowed to match against, so a
    candidate whose personal name happens to be a US state (e.g. "Georgia
    Tree") can never single-handedly make a foreign race look American."""
    if any(word_in_text(sig, haystack) for sig in NON_US_COUNTRY_SIGNALS):
        return False
    if any(word_in_text(sig, haystack) for sig in US_STRONG_SIGNALS):
        return True
    if any(word_in_text(state, context_haystack) for state in US_STATE_NAMES):
        return True
    return any(word_in_text(sig, haystack) for sig in US_WEAK_SIGNALS)


def categorize_market(question: str, tags: Iterable[str], event_title: str = "") -> str:
    """`tags` may include event-level metadata; `event_title` is passed
    separately so the US-state-name check can use event-only context (see
    is_us_election) while every other signal still sees the full text."""
    haystack = " ".join([question or ""] + [t or "" for t in tags] + [event_title or ""]).lower()
    context_haystack = " ".join([event_title or ""] + [t or "" for t in tags]).lower()

    if is_trump_behavior_market(haystack):
        return DEFAULT_CATEGORY
    if is_sports_market(haystack):
        return DEFAULT_CATEGORY

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if not word_in_text(kw, haystack):
                continue
            if category == "commodities" and kw in AMBIGUOUS_COMMODITY_KEYWORDS:
                if not any(ctx in haystack for ctx in PRICE_CONTEXT_SIGNALS):
                    continue
            if category == "elections" and not is_us_election(haystack, context_haystack):
                continue
            return category
    return DEFAULT_CATEGORY


@dataclass
class ScannedMarket:
    market_id: str
    question: str
    slug: str
    end_date: datetime
    category: str
    tags: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    outcome_prices: list[float] = field(default_factory=list)
    volume: float = 0.0
    liquidity: float = 0.0
    url: str = ""
    group_label: str = ""
    event_title: str = ""

    @property
    def days_to_resolve(self) -> float:
        now = datetime.now(timezone.utc)
        return (self.end_date - now).total_seconds() / 86400.0

    @property
    def is_grouped(self) -> bool:
        return bool(self.event_title)


def parse_end_date(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        text = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        logger.warning("Could not parse end date %r", raw)
        return None


def parse_float_list(raw: Any) -> list[float]:
    if raw is None:
        return []
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, list):
        out = []
        for v in raw:
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
        return out
    return []


def parse_str_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        import json
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except json.JSONDecodeError:
            return [raw] if raw else []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return []


def resolve_public_slug(raw_market: dict[str, Any]) -> str:
    events = raw_market.get("events")
    if isinstance(events, list) and events:
        event_slug = events[0].get("slug") if isinstance(events[0], dict) else None
        if event_slug:
            return event_slug
    return raw_market.get("slug") or ""


def resolve_group_metadata(raw_market: dict[str, Any], question: str) -> tuple[str, str]:
    group_label = raw_market.get("groupItemTitle") or ""
    events = raw_market.get("events")
    event_title = ""
    if isinstance(events, list) and events and isinstance(events[0], dict):
        event_title = events[0].get("title") or ""
    if not group_label and event_title:
        group_label = question
    return group_label, event_title


def parse_market(raw_market: dict[str, Any]) -> ScannedMarket | None:
    end_date = parse_end_date(raw_market.get("endDate"))
    if end_date is None:
        return None

    market_id = str(raw_market.get("id") or raw_market.get("conditionId") or "")
    question = raw_market.get("question") or raw_market.get("title") or ""
    slug = raw_market.get("slug") or ""
    if not market_id or not question:
        return None

    tags_field = raw_market.get("tags")
    if isinstance(tags_field, list) and tags_field and isinstance(tags_field[0], dict):
        tags = [t.get("label") or t.get("slug") or "" for t in tags_field]
    else:
        tags = parse_str_list(tags_field)

    group_label, event_title = resolve_group_metadata(raw_market, question)
    category = categorize_market(question, tags, event_title)

    outcomes = parse_str_list(raw_market.get("outcomes"))
    outcome_prices = parse_float_list(raw_market.get("outcomePrices"))
    volume = float(raw_market.get("volume") or raw_market.get("volumeNum") or 0.0)
    liquidity = float(raw_market.get("liquidity") or raw_market.get("liquidityNum") or 0.0)

    public_slug = resolve_public_slug(raw_market)
    url = f"https://polymarket.com/event/{public_slug}" if public_slug else ""

    return ScannedMarket(
        market_id=market_id,
        question=question,
        slug=slug,
        end_date=end_date,
        category=category,
        tags=[t for t in tags if t],
        outcomes=outcomes,
        outcome_prices=outcome_prices,
        volume=volume,
        liquidity=liquidity,
        url=url,
        group_label=group_label,
        event_title=event_title,
    )


def filter_by_resolve_window(
    markets: Iterable[ScannedMarket],
    window_days: float = DEFAULT_RESOLVE_WINDOW_DAYS,
    now: datetime | None = None,
) -> list[ScannedMarket]:
    now = now or datetime.now(timezone.utc)
    cutoff = now + timedelta(days=window_days)
    return [m for m in markets if now <= m.end_date <= cutoff]


def filter_to_roadmap_domains(markets: Iterable[ScannedMarket]) -> list[ScannedMarket]:
    return [m for m in markets if m.category in ROADMAP_DOMAINS]


def fetch_raw_markets_page(
    limit: int = DEFAULT_PAGE_LIMIT,
    offset: int = 0,
    active: bool = True,
    closed: bool = False,
    end_date_min: str | None = None,
    end_date_max: str | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    params: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "active": str(active).lower(),
        "closed": str(closed).lower(),
    }
    if end_date_min:
        params["end_date_min"] = end_date_min
    if end_date_max:
        params["end_date_max"] = end_date_max
    resp = sess.get(MARKETS_ENDPOINT, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict) and "data" in data:
        return data["data"]
    if isinstance(data, list):
        return data
    logger.warning("Unexpected Gamma API response shape: %s", type(data))
    return []


def fetch_raw_markets(
    limit: int = DEFAULT_PAGE_LIMIT,
    active: bool = True,
    closed: bool = False,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    return fetch_raw_markets_page(limit=limit, offset=0, active=active, closed=closed, session=session)


def fetch_all_raw_markets(
    page_limit: int = DEFAULT_PAGE_LIMIT,
    active: bool = True,
    closed: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
    end_date_min: str | None = None,
    end_date_max: str | None = None,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    sess = session or requests.Session()
    all_markets: list[dict[str, Any]] = []
    offset = 0
    for _ in range(max_pages):
        try:
            page = fetch_raw_markets_page(
                limit=page_limit, offset=offset, active=active, closed=closed,
                end_date_min=end_date_min, end_date_max=end_date_max, session=sess,
            )
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 422:
                logger.info(
                    "Gamma API returned 422 at offset=%d (pagination depth limit); "
                    "stopping pagination with %d markets collected so far.",
                    offset, len(all_markets),
                )
                break
            raise
        if not page:
            break
        all_markets.extend(page)
        offset += len(page)
    else:
        logger.warning("Hit max_pages=%d while paginating Gamma API; results may be incomplete.", max_pages)
    return all_markets


def scan_markets(
    window_days: float = DEFAULT_RESOLVE_WINDOW_DAYS,
    raw_markets: list[dict[str, Any]] | None = None,
    exclude_other: bool = True,
) -> list[ScannedMarket]:
    if raw_markets is not None:
        raw = raw_markets
    else:
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=window_days)
        raw = fetch_all_raw_markets(
            end_date_min=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_date_max=cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    parsed = [m for m in (parse_market(r) for r in raw) if m is not None]
    filtered = filter_by_resolve_window(parsed, window_days=window_days)
    if exclude_other:
        filtered = filter_to_roadmap_domains(filtered)
    filtered.sort(key=lambda m: m.end_date)
    return filtered


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    results = scan_markets()
    for m in results:
        print(f"[{m.category}] {m.question} (resolves in {m.days_to_resolve:.1f}d) {m.url}")
