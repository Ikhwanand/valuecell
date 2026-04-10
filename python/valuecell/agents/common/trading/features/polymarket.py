"""Polymarket multi-signal feature enricher for the strategy pipeline.

Fetches crypto-relevant prediction market data from Polymarket and converts
it into FeatureVector items with quantitative scoring — replacing the old
simple sentiment threshold approach.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, List

from loguru import logger

from valuecell.agents.common.trading.models import FeatureVector, InstrumentRef
from valuecell.integrations.polymarket.analyzer import analyze_market
from valuecell.integrations.polymarket.history import ProbabilitySnapshot, get_history_store

# Lazy import to avoid hard dependency if Polymarket is unavailable
def _get_crypto_relevant_markets():
    from valuecell.integrations.polymarket.client import get_crypto_relevant_markets
    return get_crypto_relevant_markets


async def fetch_polymarket_features(
    limit: int = 5,
    trading_symbols: list[str] | None = None,
) -> List[FeatureVector]:
    """Fetch Polymarket prediction signals and return as enriched FeatureVectors.

    Each market is run through the multi-signal scoring pipeline to produce
    quantitative scores rather than simple sentiment labels.  Returns an
    empty list if the API is unreachable, so the strategy gracefully
    continues without Polymarket data.
    """
    if trading_symbols is None:
        trading_symbols = ["BTC", "ETH"]

    try:
        get_markets = _get_crypto_relevant_markets()
        markets = await get_markets(limit=limit)

        if not markets:
            logger.info("No Polymarket signals retrieved, skipping enrichment.")
            return []

        features: List[FeatureVector] = []
        now_ms = int(time.time() * 1000)

        for market in markets:
            yes_prob = market.yes_price
            if yes_prob is None:
                continue

            # Record snapshot for future momentum computation
            history_store = get_history_store()
            history_store.record(
                ProbabilitySnapshot(
                    condition_id=market.condition_id,
                    timestamp_ms=now_ms,
                    yes_prob=yes_prob,
                    no_prob=market.no_price or (1.0 - yes_prob),
                    volume_24h=market.volume,
                    liquidity=market.liquidity,
                )
            )

            # Run lightweight analysis (no news — too slow for batch)
            try:
                analysis = await analyze_market(
                    market=market,
                    trading_symbols=trading_symbols,
                )
            except Exception as exc:
                logger.warning(
                    "Scoring failed for {q}, falling back to basic: {err}",
                    q=market.question[:50],
                    err=str(exc),
                )
                # Fallback: use basic data without scoring
                analysis = None

            if analysis is not None:
                # Rich multi-signal description
                rec = analysis.recommendation
                side = analysis.recommended_side
                composite = analysis.composite_score

                description = (
                    f"[Polymarket] {market.question}\n"
                    f"  YES: {yes_prob:.1%} | Vol: ${market.volume:,.0f} | "
                    f"Liq: ${market.liquidity:,.0f}\n"
                    f"  Composite: {composite:.2f} → {rec} ({side}) | "
                    f"Kelly: {analysis.suggested_allocation_pct:.1f}%\n"
                    f"  Quality: {analysis.market_quality_score:.2f} | "
                    f"Momentum: {analysis.momentum_score:.2f} "
                    f"({analysis.momentum_context.get('direction', 'FLAT')}) | "
                    f"Edge: {analysis.edge_score:.2f}"
                )
                if analysis.risk_factors:
                    description += f"\n  ⚠ {' | '.join(analysis.risk_factors[:2])}"

                meta_dict = {
                    "source": "polymarket",
                    "question": market.question,
                    "yes_probability": yes_prob,
                    "no_probability": market.no_price,
                    "volume": market.volume,
                    "liquidity": market.liquidity,
                    "category": market.category,
                    "composite_score": composite,
                    "recommendation": rec,
                    "recommended_side": side,
                    "kelly_fraction": analysis.kelly_fraction,
                    "market_quality": analysis.market_quality_score,
                    "momentum_score": analysis.momentum_score,
                    "momentum_direction": analysis.momentum_context.get("direction", "FLAT"),
                    "edge_score": analysis.edge_score,
                    "relevance": analysis.relevance_score,
                }
            else:
                # Fallback: minimal description
                description = (
                    f"[Polymarket] {market.question}\n"
                    f"  YES: {yes_prob:.1%} | Vol: ${market.volume:,.0f}"
                )
                meta_dict = {
                    "source": "polymarket",
                    "question": market.question,
                    "yes_probability": yes_prob,
                    "volume": market.volume,
                }

            features.append(
                FeatureVector(
                    ts=now_ms,
                    instrument=InstrumentRef(
                        symbol=f"POLY:{market.condition_id[:12]}",
                        exchange_id="polymarket",
                    ),
                    values={
                        "yes_prob": yes_prob,
                        "volume": market.volume,
                        "liquidity": market.liquidity,
                        "composite_score": analysis.composite_score if analysis else 0.0,
                        "kelly_fraction": analysis.kelly_fraction if analysis else 0.0,
                    },
                    meta=meta_dict,
                )
            )

        logger.info("Fetched {n} Polymarket signals with multi-signal scoring.", n=len(features))
        return features

    except Exception as e:
        # Non-critical: log warning but don't crash the strategy
        logger.warning("Polymarket enrichment failed, continuing without it: {err}", err=str(e))
        return []
