"""Polymarket integration module."""

from .client import get_markets, get_crypto_relevant_markets, get_market_by_id
from .models import PolymarketMarket, PolymarketSignal, PolymarketToken
from .analyzer import MarketAnalysis, analyze_market
from .scoring import (
    compute_composite,
    kelly_fraction,
    recommendation_from_composite,
    score_edge,
    score_market_quality,
    score_momentum,
    score_news_impact,
    score_orderbook_health,
    score_relevance,
    NewsImpactResult,
)
from .clob import fetch_orderbook, fetch_market_orderbooks, OrderbookSummary
from .history import ProbabilitySnapshot, ProbabilityHistoryStore, get_history_store
from .cache import TTLCache, get_news_cache

__all__ = [
    # Client
    "get_markets",
    "get_crypto_relevant_markets",
    "get_market_by_id",
    # Models
    "PolymarketMarket",
    "PolymarketSignal",
    "PolymarketToken",
    # Analyzer
    "MarketAnalysis",
    "analyze_market",
    # Scoring
    "compute_composite",
    "kelly_fraction",
    "recommendation_from_composite",
    "score_edge",
    "score_market_quality",
    "score_momentum",
    "score_news_impact",
    "score_orderbook_health",
    "score_relevance",
    "NewsImpactResult",
    # CLOB
    "fetch_orderbook",
    "fetch_market_orderbooks",
    "OrderbookSummary",
    # History
    "ProbabilitySnapshot",
    "ProbabilityHistoryStore",
    "get_history_store",
    # Cache
    "TTLCache",
    "get_news_cache",
]
