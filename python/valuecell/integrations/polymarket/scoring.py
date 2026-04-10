"""Multi-signal scoring engine for Polymarket market analysis.

Each scorer produces a normalized score (0.0–1.0) from raw market data.
The composite score is a weighted average of all signal scores.
"""

from __future__ import annotations

import json
import math
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS: dict[str, float] = {
    "market_quality": 0.15,
    "momentum": 0.20,
    "news_impact": 0.25,
    "edge": 0.15,
    "orderbook_health": 0.10,
    "relevance": 0.15,
}

KEYWORD_MAP: dict[str, list[str]] = {
    "BTC": ["bitcoin", "btc", "crypto", "digital asset", "halving", "satoshi"],
    "ETH": ["ethereum", "eth", "defi", "smart contract", "vitalik", "layer 2"],
    "SOL": ["solana", "sol"],
    "XRP": ["xrp", "ripple"],
    "DOGE": ["doge", "dogecoin"],
    "_MACRO": ["fed", "interest rate", "inflation", "recession", "sec", "etf", "tariff", "treasury"],
}

# ---------------------------------------------------------------------------
# Signal Result Models
# ---------------------------------------------------------------------------


class MarketQualityResult(BaseModel):
    """Result from market quality scoring."""

    score: float = Field(ge=0, le=1)
    liquidity_score: float = Field(ge=0, le=1)
    volume_score: float = Field(ge=0, le=1)
    spread_score: float = Field(ge=0, le=1)
    time_score: float = Field(ge=0, le=1)


class MomentumResult(BaseModel):
    """Result from momentum scoring."""

    score: float = Field(ge=0, le=1)
    direction: Literal["UP", "DOWN", "FLAT"] = "FLAT"
    delta_1h: float = 0.0
    delta_6h: float = 0.0
    delta_24h: float = 0.0
    velocity: float = 0.0
    consistent: bool = False


class NewsImpactResult(BaseModel):
    """Structured output from news analysis."""

    impact_direction: Literal["supports_yes", "supports_no", "neutral", "mixed"] = "neutral"
    confidence: float = Field(default=0.5, ge=0, le=1)
    recency_hours: float = 24.0
    source_quality: Literal["tier1", "tier2", "unverified"] = "unverified"
    key_facts: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    score: float = Field(default=0.5, ge=0, le=1)


class EdgeResult(BaseModel):
    """Result from edge/mispricing detection."""

    score: float = Field(ge=0, le=1)
    raw_edge_cents: float = 0.0
    edge_type: Literal["UNDERPRICED", "OVERPRICED", "NONE"] = "NONE"
    mid_divergence: float = 0.0


class OrderbookHealthResult(BaseModel):
    """Result from orderbook health scoring."""

    score: float = Field(ge=0, le=1)
    spread_cents: float = 0.0
    total_depth_usd: float = 0.0
    imbalance_ratio: float = 0.0
    fillable: bool = True


# ---------------------------------------------------------------------------
# Scorers
# ---------------------------------------------------------------------------


def score_market_quality(
    volume_24h: float,
    liquidity: float,
    spread: float,
    days_to_end: float | None,
) -> MarketQualityResult:
    """Score whether a market is worth betting on.

    High liquidity, healthy volume, tight spread, and reasonable time
    to resolution all increase the quality score.
    """
    liq_score = min(liquidity / 200_000, 1.0) if liquidity > 0 else 0.0
    vol_score = min(volume_24h / 50_000, 1.0) if volume_24h > 0 else 0.0
    spread_score = max(0.0, 1.0 - (spread / 0.10)) if spread >= 0 else 0.0

    if days_to_end is not None and days_to_end > 0:
        time_score = 1.0 if 2 < days_to_end < 60 else 0.5
    else:
        time_score = 0.5

    composite = (
        liq_score * 0.30
        + vol_score * 0.30
        + spread_score * 0.25
        + time_score * 0.15
    )

    return MarketQualityResult(
        score=round(composite, 4),
        liquidity_score=round(liq_score, 4),
        volume_score=round(vol_score, 4),
        spread_score=round(spread_score, 4),
        time_score=round(time_score, 4),
    )


def score_momentum(
    prob_history: list[tuple[int, float]],
) -> MomentumResult:
    """Score price momentum from probability timeseries.

    ``prob_history`` is a list of ``(timestamp_ms, yes_prob)`` sorted ascending
    by time.  The function computes deltas at 1h, 6h, and 24h look-backs to
    gauge velocity and directional consistency.
    """
    if len(prob_history) < 3:
        return MomentumResult(score=0.0, direction="FLAT")

    current_ts, current = prob_history[-1]

    def _find_nearest(hours: int) -> float | None:
        target = current_ts - (hours * 3_600_000)
        best: tuple[int, float] | None = None
        for ts, prob in prob_history:
            if best is None or abs(ts - target) < abs(best[0] - target):
                best = (ts, prob)
        # Consider valid only if within 50% of the look-back window
        if best is not None and abs(best[0] - target) < (hours * 1_800_000):
            return best[1]
        return None

    prob_1h = _find_nearest(1)
    prob_6h = _find_nearest(6)
    prob_24h = _find_nearest(24)

    delta_1h = (current - prob_1h) if prob_1h is not None else 0.0
    delta_6h = (current - prob_6h) if prob_6h is not None else 0.0
    delta_24h = (current - prob_24h) if prob_24h is not None else 0.0

    velocity = abs(delta_1h) * 3 + abs(delta_6h) * 2 + abs(delta_24h) * 1
    signs = [s for s in [delta_1h, delta_6h, delta_24h] if s != 0]
    consistent = bool(signs) and (all(s > 0 for s in signs) or all(s < 0 for s in signs))

    if delta_1h > 0:
        direction: Literal["UP", "DOWN", "FLAT"] = "UP"
    elif delta_1h < 0:
        direction = "DOWN"
    else:
        direction = "FLAT"

    score = min(velocity / 0.30, 1.0)

    return MomentumResult(
        score=round(score, 4),
        direction=direction,
        delta_1h=round(delta_1h, 6),
        delta_6h=round(delta_6h, 6),
        delta_24h=round(delta_24h, 6),
        velocity=round(velocity, 6),
        consistent=consistent,
    )


def score_news_impact(result: NewsImpactResult) -> float:
    """Convert structured news analysis into a probabilistic adjustment score.

    Returns a value 0.0–1.0 where 0.5 means neutral.  Values >0.5 support
    YES, <0.5 support NO.
    """
    direction_map = {
        "supports_yes": +1,
        "supports_no": -1,
        "neutral": 0,
        "mixed": 0,
    }
    d = direction_map[result.impact_direction]

    recency_factor = max(0.0, 1.0 - (result.recency_hours / 48))
    quality_mult = {"tier1": 1.0, "tier2": 0.7, "unverified": 0.3}[result.source_quality]
    contradiction_penalty = min(len(result.contradictions) * 0.15, 0.5)

    adjustment = d * result.confidence * recency_factor * quality_mult
    adjustment *= (1 - contradiction_penalty)

    score = 0.5 + (adjustment * 0.3)
    return round(max(0.0, min(1.0, score)), 4)


def score_edge(
    yes_ask: float,
    no_ask: float,
    yes_bid: float,
    no_bid: float,
) -> EdgeResult:
    """Detect mispricing from orderbook best-of-book prices.

    An *underpriced* edge exists when buying both YES + NO costs < $1.
    An *overpriced* edge exists when selling both yields > $1.
    """
    buy_sum = yes_ask + no_ask
    underpriced_edge = max(0.0, 1.0 - buy_sum)

    sell_sum = yes_bid + no_bid
    overpriced_edge = max(0.0, sell_sum - 1.0)

    mid_yes = (yes_bid + yes_ask) / 2.0 if (yes_bid + yes_ask) > 0 else 0.0
    divergence = abs(mid_yes - yes_ask)

    raw_edge = max(underpriced_edge, overpriced_edge)
    score = min(raw_edge / 0.05, 1.0)

    if raw_edge <= 0:
        edge_type: Literal["UNDERPRICED", "OVERPRICED", "NONE"] = "NONE"
    elif underpriced_edge > overpriced_edge:
        edge_type = "UNDERPRICED"
    else:
        edge_type = "OVERPRICED"

    return EdgeResult(
        score=round(score, 4),
        raw_edge_cents=round(raw_edge * 100, 2),
        edge_type=edge_type,
        mid_divergence=round(divergence, 6),
    )


def score_orderbook_health(
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    target_size_usd: float = 100.0,
) -> OrderbookHealthResult:
    """Evaluate whether a trade can execute with reasonable slippage."""
    if not bids or not asks:
        return OrderbookHealthResult(score=0.0, fillable=False)

    spread = asks[0][0] - bids[0][0]
    spread_score = max(0.0, 1.0 - (spread / 0.05))

    depth_bid = sum(p * s for p, s in bids[:5])
    depth_ask = sum(p * s for p, s in asks[:5])
    total_depth = depth_bid + depth_ask
    depth_score = min(total_depth / 5_000, 1.0) if total_depth > 0 else 0.0

    if total_depth > 0:
        imbalance = abs(depth_bid - depth_ask) / total_depth
    else:
        imbalance = 1.0
    balance_score = 1.0 - imbalance

    fill_score = 1.0 if depth_ask >= target_size_usd else (depth_ask / target_size_usd if target_size_usd > 0 else 0)

    composite = (
        spread_score * 0.30
        + depth_score * 0.30
        + balance_score * 0.20
        + fill_score * 0.20
    )

    return OrderbookHealthResult(
        score=round(composite, 4),
        spread_cents=round(spread * 100, 2),
        total_depth_usd=round(total_depth, 2),
        imbalance_ratio=round(imbalance, 4),
        fillable=depth_ask >= target_size_usd,
    )


def score_relevance(
    question: str,
    description: str | None,
    trading_symbols: list[str] | None = None,
) -> float:
    """Score how relevant a market is to the user's trading portfolio.

    Uses keyword matching against known crypto/macro terms.
    """
    if trading_symbols is None:
        trading_symbols = ["BTC", "ETH"]

    text = f"{question} {description or ''}".lower()

    max_score = 0.0
    for symbol in trading_symbols:
        base = symbol.split("/")[0].split("-")[0].upper()
        keywords = KEYWORD_MAP.get(base, []) + KEYWORD_MAP.get("_MACRO", [])
        hits = sum(1 for kw in keywords if kw in text)
        score = min(hits / 3, 1.0)
        max_score = max(max_score, score)

    return round(max_score, 4)


# ---------------------------------------------------------------------------
# Composite Scoring
# ---------------------------------------------------------------------------


def compute_composite(scores: dict[str, float]) -> float:
    """Weighted average of all signal scores."""
    total = sum(
        SIGNAL_WEIGHTS.get(key, 0.0) * value
        for key, value in scores.items()
        if key in SIGNAL_WEIGHTS
    )
    return round(total, 4)


def recommendation_from_composite(
    composite: float,
) -> Literal["SKIP", "WATCH", "CONSIDER", "RECOMMEND", "HIGH_CONVICTION"]:
    """Map composite score to a human-readable recommendation tier."""
    if composite >= 0.80:
        return "HIGH_CONVICTION"
    if composite >= 0.60:
        return "RECOMMEND"
    if composite >= 0.40:
        return "CONSIDER"
    if composite >= 0.25:
        return "WATCH"
    return "SKIP"


# ---------------------------------------------------------------------------
# Kelly Criterion Sizing
# ---------------------------------------------------------------------------


def kelly_fraction(
    estimated_prob: float,
    market_price: float,
    confidence: float = 1.0,
    max_fraction: float = 0.05,
) -> float:
    """Fractional Kelly sizing for prediction market bets.

    Uses half-Kelly (industry standard) scaled by confidence, with a hard cap
    to prevent over-concentration in a single market.

    Args:
        estimated_prob: Our estimated probability of YES outcome (0–1).
        market_price: Current market price for YES (= implied prob).
        confidence: Confidence in our probability estimate (0–1).
        max_fraction: Hard cap on fraction of bankroll (default 5%).

    Returns:
        Fraction of bankroll to bet (0–max_fraction).
    """
    if estimated_prob <= market_price or market_price <= 0 or market_price >= 1:
        return 0.0

    # Kelly formula for binary outcomes: f* = (p*(b+1) - 1) / b
    # where b = (1 - price) / price  (payout odds)
    b = (1.0 - market_price) / market_price
    if b <= 0:
        return 0.0

    f_star = (estimated_prob * (b + 1) - 1) / b

    # Half-Kelly for safety
    f_half = f_star * 0.5

    # Scale by confidence
    f_adjusted = f_half * confidence

    return round(max(0.0, min(f_adjusted, max_fraction)), 6)
