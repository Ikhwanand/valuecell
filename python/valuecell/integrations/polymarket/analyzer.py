"""Market analysis pipeline — orchestrates data collection and scoring.

This module ties together all the individual scorers, the CLOB client,
the probability history store, and the news agent into a single
``analyze_market`` coroutine that returns a comprehensive ``MarketAnalysis``.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Literal

from loguru import logger
from pydantic import BaseModel, Field

from .cache import get_news_cache
from .clob import OrderbookSummary, fetch_orderbook
from .history import ProbabilitySnapshot, get_history_store
from .models import PolymarketMarket
from .scoring import (
    EdgeResult,
    MarketQualityResult,
    MomentumResult,
    NewsImpactResult,
    OrderbookHealthResult,
    compute_composite,
    kelly_fraction,
    recommendation_from_composite,
    score_edge,
    score_market_quality,
    score_momentum,
    score_news_impact,
    score_orderbook_health,
    score_relevance,
)


# ---------------------------------------------------------------------------
# Output Schema
# ---------------------------------------------------------------------------


class MarketAnalysis(BaseModel):
    """Comprehensive analysis result for a Polymarket market."""

    # Market identity
    condition_id: str
    question: str
    category: str | None = None

    # Current market snapshot
    yes_price: float | None = None
    no_price: float | None = None
    volume: float = 0.0
    liquidity: float = 0.0

    # Signal scores (all 0.0–1.0)
    market_quality_score: float = 0.0
    momentum_score: float = 0.0
    news_impact_score: float = 0.5
    edge_score: float = 0.0
    orderbook_health_score: float = 0.0
    relevance_score: float = 0.0
    composite_score: float = 0.0

    # Decision
    recommendation: Literal["SKIP", "WATCH", "CONSIDER", "RECOMMEND", "HIGH_CONVICTION"] = "SKIP"
    recommended_side: Literal["YES", "NO", "NONE"] = "NONE"
    kelly_fraction: float = 0.0
    suggested_allocation_pct: float = 0.0

    # Context for UI / LLM narrative
    signal_breakdown: dict = Field(default_factory=dict)
    momentum_context: dict = Field(default_factory=dict)
    news_summary: str = ""
    risk_factors: list[str] = Field(default_factory=list)
    ai_narrative: str = ""


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


async def analyze_market(
    market: PolymarketMarket,
    *,
    news_text: str | None = None,
    news_impact: NewsImpactResult | None = None,
    trading_symbols: list[str] | None = None,
    bankroll_usd: float = 1000.0,
    target_size_usd: float = 100.0,
) -> MarketAnalysis:
    """Run the full multi-signal analysis pipeline on a single market.

    Stages:
    1. Record current probability snapshot
    2. Score market quality (from Gamma API data already on the model)
    3. Score momentum (from probability history)
    4. Score news impact (if provided)
    5. Score edge + orderbook health (from CLOB, best-effort)
    6. Score relevance (keyword matching)
    7. Compute composite + Kelly sizing
    """

    yes_price = market.yes_price or 0.5
    no_price = market.no_price or (1.0 - yes_price)

    # -- 1. Record current snapshot ---
    history_store = get_history_store()
    now_ms = int(time.time() * 1000)
    history_store.record(
        ProbabilitySnapshot(
            condition_id=market.condition_id,
            timestamp_ms=now_ms,
            yes_prob=yes_price,
            no_prob=no_price,
            volume_24h=market.volume,
            liquidity=market.liquidity,
        )
    )

    # -- 2. Market Quality ---
    # Estimate days to end
    days_to_end: float | None = None
    if market.end_date_iso:
        try:
            end_dt = datetime.fromisoformat(market.end_date_iso.replace("Z", "+00:00"))
            delta = end_dt - datetime.now(timezone.utc)
            days_to_end = max(delta.total_seconds() / 86400, 0)
        except (ValueError, TypeError):
            pass

    # We don't have spread data from Gamma, estimate from price complement
    estimated_spread = abs(1.0 - yes_price - no_price) if no_price else 0.02
    mq = score_market_quality(
        volume_24h=market.volume,
        liquidity=market.liquidity,
        spread=estimated_spread,
        days_to_end=days_to_end,
    )

    # -- 3. Momentum ---
    prob_history = history_store.get_history(market.condition_id, hours=48)
    mom = score_momentum(prob_history)

    # -- 4. News Impact ---
    if news_impact is not None:
        news_score = score_news_impact(news_impact)
        news_impact_result = news_impact
    else:
        news_score = 0.5
        news_impact_result = NewsImpactResult()

    # -- 5. Edge + Orderbook Health (best-effort via CLOB) ---
    edge_result = EdgeResult(score=0.0, edge_type="NONE")
    ob_result = OrderbookHealthResult(score=0.0)

    yes_token_id = _extract_yes_token_id(market)
    if yes_token_id:
        try:
            ob_yes = await fetch_orderbook(yes_token_id)
            if ob_yes.bids or ob_yes.asks:
                ob_result = score_orderbook_health(
                    bids=ob_yes.bids,
                    asks=ob_yes.asks,
                    target_size_usd=target_size_usd,
                )
                # For edge: use best bid/ask from YES side + complement for NO
                edge_result = score_edge(
                    yes_ask=ob_yes.best_ask,
                    no_ask=1.0 - ob_yes.best_bid if ob_yes.best_bid > 0 else 1.0,
                    yes_bid=ob_yes.best_bid,
                    no_bid=1.0 - ob_yes.best_ask if ob_yes.best_ask < 1 else 0.0,
                )
        except Exception as exc:
            logger.warning("CLOB analysis skipped for {cid}: {err}", cid=market.condition_id, err=str(exc))

    # -- 6. Relevance ---
    rel_score = score_relevance(
        question=market.question,
        description=market.description,
        trading_symbols=trading_symbols,
    )

    # -- 7. Composite ---
    scores = {
        "market_quality": mq.score,
        "momentum": mom.score,
        "news_impact": news_score,
        "edge": edge_result.score,
        "orderbook_health": ob_result.score,
        "relevance": rel_score,
    }
    composite = compute_composite(scores)
    rec = recommendation_from_composite(composite)

    # -- 8. Side + Kelly ---
    if news_score > 0.55:
        side: Literal["YES", "NO", "NONE"] = "YES"
        estimated_prob = min(yes_price + (news_score - 0.5) * 0.4, 0.95)
    elif news_score < 0.45:
        side = "NO"
        estimated_prob = min(no_price + (0.5 - news_score) * 0.4, 0.95)
    else:
        # Lean towards the market consensus when news is neutral
        if yes_price > 0.6:
            side = "YES"
            estimated_prob = yes_price
        elif yes_price < 0.4:
            side = "NO"
            estimated_prob = no_price
        else:
            side = "NONE"
            estimated_prob = 0.5

    market_price = yes_price if side == "YES" else no_price
    kf = kelly_fraction(
        estimated_prob=estimated_prob,
        market_price=market_price,
        confidence=composite,
    )
    suggested_pct = round(kf * 100, 2)

    # -- 9. Risk factors ---
    risks: list[str] = []
    if mq.score < 0.3:
        risks.append("Low market quality — thin liquidity or low volume")
    if not ob_result.fillable:
        risks.append("Orderbook too thin to fill target size without slippage")
    if mom.direction != "FLAT" and not mom.consistent:
        risks.append("Momentum direction inconsistent across timeframes")
    if days_to_end is not None and days_to_end < 1:
        risks.append("Market resolves within 24h — high uncertainty")
    if len(news_impact_result.contradictions) > 0:
        risks.append(f"{len(news_impact_result.contradictions)} contradictory news sources detected")

    return MarketAnalysis(
        condition_id=market.condition_id,
        question=market.question,
        category=market.category,
        yes_price=yes_price,
        no_price=no_price,
        volume=market.volume,
        liquidity=market.liquidity,
        market_quality_score=mq.score,
        momentum_score=mom.score,
        news_impact_score=news_score,
        edge_score=edge_result.score,
        orderbook_health_score=ob_result.score,
        relevance_score=rel_score,
        composite_score=composite,
        recommendation=rec,
        recommended_side=side,
        kelly_fraction=kf,
        suggested_allocation_pct=suggested_pct,
        signal_breakdown={
            "market_quality": mq.model_dump(),
            "momentum": mom.model_dump(),
            "news_impact": news_impact_result.model_dump(),
            "edge": edge_result.model_dump(),
            "orderbook_health": ob_result.model_dump(),
            "relevance": rel_score,
        },
        momentum_context=mom.model_dump(),
        news_summary=news_text or "",
        risk_factors=risks,
    )


def _extract_yes_token_id(market: PolymarketMarket) -> str | None:
    """Extract the YES token ID from a market's token list."""
    for token in market.tokens:
        if token.outcome.lower() == "yes" and token.token_id:
            return token.token_id
    return None
