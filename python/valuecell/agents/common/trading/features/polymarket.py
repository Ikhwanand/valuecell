"""Polymarket signal feature enricher for the strategy pipeline.

Fetches crypto-relevant prediction market data from Polymarket and converts
it into FeatureVector items so the LLM composer can consider crowd sentiment
alongside technical indicators. 
"""

from __future__ import annotations

from typing import List 
from loguru import logger

from valuecell.agents.common.trading.models import FeatureVector

# Lazy import to avoid hard dependency if Polymarket is unavailable
def _get_crypto_relevant_markets():
    from valuecell.integrations.polymarket.client import get_crypto_relevant_markets
    return get_crypto_relevant_markets

async def fetch_polymarket_features(limit: int = 5) -> List[FeatureVector]:
    """Fetch Polymarket prediction signals and return as FeatureVectors.

    Returns an empty list if the API is unreachable, so the strategy gracefully
    continues without Polymarket data rather than crashing.
    """
    try:
        get_markets = _get_crypto_relevant_markets()
        markets = await get_markets(limit=limit)
        
        if not markets:
            logger.info("No Polymarket signals retrieved, skipping enrichment.")
            return []

        features: List[FeatureVector] = []
        for market in markets:
            yes_prob = market.yes_price
            if yes_prob is None:
                continue 
            
            # Build a human-readable signal description for the LLM
            sentiment = "BULLISH" if yes_prob > 0.6 else ("BEARISH" if yes_prob < 0.4 else "NEUTRAL")
            description = (
                f"[Polymarket Signal] {market.question}\n"
                f" Yes Probability: {yes_prob:.1%}  |   "
                f"Volume: ${market.volume:,.0f}  |  "
                f"Sentiment: {sentiment}"
            )
            
            features.append(
                FeatureVector(
                    name=f"polymarket_{market.condition_id[:8]}",
                    description=description,
                    value=yes_prob,
                    meta={
                        "source": "polymarket",
                        "question": market.question,
                        "yes_probability": yes_prob,
                        "no_probability": market.no_price,
                        "volume": market.volume,
                        "liquidity": market.liquidity,
                        "category": market.category,
                        "sentiment": sentiment,
                    },
                )
            )
            
        logger.info("Fetched {n} Polymarket signals.", n=len(features))
        return features
    
    except Exception as e:
        # Non-critical: log warning but don't crash the strategy
        logger.warning("Polymarket enrichment failed, continuing without it: {err}", err=str(e))
        return []
    

