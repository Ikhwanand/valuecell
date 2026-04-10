"""Polymarket prediction market API routes.

Provides endpoints for browsing markets and running multi-signal analysis
powered by the scoring engine.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from agno.agent import Agent as AgnoAgent

from ....agents.news_agent.core import NewsAgent
from ....integrations.polymarket.analyzer import MarketAnalysis, analyze_market
from ....integrations.polymarket.cache import get_news_cache
from ....integrations.polymarket.client import (
    get_crypto_relevant_markets,
    get_market_by_id,
    get_markets,
)
from ....integrations.polymarket.models import PolymarketMarket
from ....integrations.polymarket.scoring import NewsImpactResult
from ....utils import model as model_utils
from ..schemas import SuccessResponse


# ---------------------------------------------------------------------------
# Response Schemas
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    token_id: str
    outcome: str
    price: float


class MarketData(BaseModel):
    condition_id: str
    question: str
    description: Optional[str] = None
    category: Optional[str] = None
    end_date_iso: Optional[str] = None
    volume: float
    liquidity: float
    active: bool
    closed: bool
    yes_price: Optional[float] = None
    no_price: Optional[float] = None
    market_slug: Optional[str] = None
    event_slug: Optional[str] = None
    tokens: List[TokenData] = []


class AnalyzeRequest(BaseModel):
    condition_id: str
    question: str
    yes_price: Optional[float] = None
    volume: Optional[float] = None
    bankroll_usd: float = Field(default=1000.0, description="Total bankroll for Kelly sizing")
    trading_symbols: list[str] = Field(
        default_factory=lambda: ["BTC", "ETH"],
        description="Symbols in the user's portfolio for relevance scoring",
    )


# Legacy schema — kept only for backward compatibility
class RecommendationResponse(BaseModel):
    recommendation: str
    outcome_recommended: str
    suggested_amount: int
    analysis: str


def _to_market_data(market: PolymarketMarket) -> MarketData:
    return MarketData(
        condition_id=market.condition_id,
        question=market.question,
        description=market.description,
        category=market.category,
        end_date_iso=market.end_date_iso,
        volume=market.volume,
        liquidity=market.liquidity,
        active=market.active,
        closed=market.closed,
        yes_price=market.yes_price,
        no_price=market.no_price,
        market_slug=market.market_slug,
        event_slug=market.event_slug,
        tokens=[
            TokenData(token_id=t.token_id, outcome=t.outcome, price=t.price)
            for t in market.tokens
        ],
    )


# ---------------------------------------------------------------------------
# Router Factory
# ---------------------------------------------------------------------------


def create_polymarket_router() -> APIRouter:
    """Create Polymarket prediction market routes."""
    router = APIRouter(prefix="/polymarket", tags=["Polymarket"])

    @router.get(
        "/markets",
        response_model=SuccessResponse[List[MarketData]],
        summary="Get prediction markets",
        description="Fetch active prediction markets from Polymarket",
    )
    async def list_markets(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
        keyword: Optional[str] = Query(None, description="Filter by keyword"),
    ):
        """Get active Polymarket prediction markets."""
        try:
            markets = await get_markets(limit=limit, offset=offset, keyword=keyword)
            data = [_to_market_data(m) for m in markets]
            return SuccessResponse.create(
                data=data,
                msg=f"Retrieved {len(data)} prediction markets",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch markets: {str(e)}")

    @router.get(
        "/markets/crypto",
        response_model=SuccessResponse[List[MarketData]],
        summary="Get crypto-relevant markets",
        description="Fetch Polymarket markets relevant to crypto & finance trading decisions",
    )
    async def list_crypto_markets(
        limit: int = Query(10, ge=1, le=50),
    ):
        """Get crypto and finance relevant prediction markets."""
        try:
            markets = await get_crypto_relevant_markets(limit=limit)
            data = [_to_market_data(m) for m in markets]
            return SuccessResponse.create(
                data=data,
                msg=f"Retrieved {len(data)} crypto-relevant markets",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post(
        "/markets/analyze",
        response_model=SuccessResponse[MarketAnalysis],
        summary="Multi-signal market analysis",
        description=(
            "Run comprehensive multi-signal analysis on a Polymarket market. "
            "Combines market quality, momentum, news impact, edge detection, "
            "orderbook health, and relevance scoring with Kelly criterion sizing."
        ),
    )
    async def analyze_market_endpoint(req: AnalyzeRequest):
        """Run multi-signal scoring pipeline on a market."""
        try:
            # 1. Fetch full market data from Gamma API
            market = await get_market_by_id(req.condition_id)
            if market is None:
                raise HTTPException(status_code=404, detail=f"Market {req.condition_id} not found")

            # 2. Gather news context (with caching)
            news_cache = get_news_cache()
            cached_news = news_cache.get(req.question)

            if cached_news is not None:
                news_text, news_impact = cached_news
                logger.info("Using cached news for: {q}", q=req.question[:60])
            else:
                news_text, news_impact = await _gather_news_context(req.question)
                news_cache.put(req.question, (news_text, news_impact))

            # 3. Run the full analysis pipeline
            analysis = await analyze_market(
                market=market,
                news_text=news_text,
                news_impact=news_impact,
                trading_symbols=req.trading_symbols,
                bankroll_usd=req.bankroll_usd,
            )

            # 4. Generate AI narrative to explain the scores
            analysis.ai_narrative = await _generate_narrative(analysis)

            return SuccessResponse.create(data=analysis, msg="Analysis completed")

        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Market analysis failed for {cid}", cid=req.condition_id)
            raise HTTPException(status_code=500, detail=str(e))

    return router


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _gather_news_context(
    question: str,
) -> tuple[str, NewsImpactResult | None]:
    """Ask NewsAgent for context, then attempt to structure the result.

    Returns ``(raw_news_text, structured_impact_or_None)``.
    """
    try:
        news_agent = NewsAgent()
        query = (
            f"Find the latest news and facts that could influence "
            f"the outcome of this prediction market: '{question}'. "
            f"Summarize only the facts. Include source names and dates."
        )
        news_text = await news_agent.run(query)

        # Try to get structured analysis from LLM
        news_impact = await _structure_news(question, news_text)

        return (news_text, news_impact)
    except Exception as exc:
        logger.warning("News gathering failed: {err}", err=str(exc))
        return ("", None)


async def _structure_news(
    question: str,
    news_text: str,
) -> NewsImpactResult | None:
    """Use an LLM to convert raw news text into a structured NewsImpactResult."""
    try:
        model = model_utils.get_model("AGENT_MODEL_ID")
        agent = AgnoAgent(
            model=model,
            output_schema=NewsImpactResult,
            markdown=False,
            use_json_mode=model_utils.model_should_use_json_mode(model),
        )

        prompt = f"""Analyze this news research for the prediction market question: "{question}"

NEWS CONTEXT:
{news_text[:3000]}

Classify the impact:
- impact_direction: "supports_yes", "supports_no", "neutral", or "mixed"
- confidence: 0.0 to 1.0 (how confident the news supports the direction)
- recency_hours: approximate age of the most recent news in hours
- source_quality: "tier1" (Reuters, Bloomberg, AP, official govt), "tier2" (major news outlets), or "unverified"
- key_facts: top 3 key facts (short bullet points)
- contradictions: any contradictory information found"""

        response = await agent.arun(prompt)
        data = getattr(response, "content", None) or response

        if isinstance(data, NewsImpactResult):
            return data

        logger.warning("LLM did not produce valid NewsImpactResult, falling back to neutral")
        return None

    except Exception as exc:
        logger.warning("News structuring failed: {err}", err=str(exc))
        return None


async def _generate_narrative(analysis: MarketAnalysis) -> str:
    """Generate a human-readable explanation of the analysis scores."""
    try:
        model = model_utils.get_model("AGENT_MODEL_ID")
        agent = AgnoAgent(model=model, markdown=False)

        prompt = f"""You are a prediction market analyst. Write a concise 3-4 sentence analysis
explaining this recommendation to a trader. Be direct and data-driven.

Market: {analysis.question}
YES Price: {analysis.yes_price:.1%} | Volume: ${analysis.volume:,.0f} | Liquidity: ${analysis.liquidity:,.0f}

Scores:
- Market Quality: {analysis.market_quality_score:.2f}/1.0
- Momentum: {analysis.momentum_score:.2f}/1.0 ({analysis.momentum_context.get('direction', 'FLAT')})
- News Impact: {analysis.news_impact_score:.2f}/1.0
- Edge Detection: {analysis.edge_score:.2f}/1.0
- Orderbook Health: {analysis.orderbook_health_score:.2f}/1.0
- Relevance: {analysis.relevance_score:.2f}/1.0

Composite: {analysis.composite_score:.2f} → {analysis.recommendation}
Recommended: {analysis.recommended_side} | Kelly: {analysis.suggested_allocation_pct:.1f}% of bankroll
Risk factors: {', '.join(analysis.risk_factors) if analysis.risk_factors else 'None identified'}

Explain why {analysis.recommendation} is the right call based on these scores. Be specific about which signals drive the decision."""

        response = await agent.arun(prompt)
        return str(getattr(response, "content", response))[:1000]

    except Exception as exc:
        logger.warning("Narrative generation failed: {err}", err=str(exc))
        return f"Composite score: {analysis.composite_score:.2f} → {analysis.recommendation}"
