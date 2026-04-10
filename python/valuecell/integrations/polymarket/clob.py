"""CLOB (Central Limit Order Book) client for Polymarket orderbook data.

Read-only wrapper around ``py-clob-client`` that fetches live orderbook
depth.  No authentication is required for read operations.
"""

from __future__ import annotations

from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field


CLOB_BASE_URL = "https://clob.polymarket.com"


class OrderbookSummary(BaseModel):
    """Condensed orderbook snapshot for scoring."""

    token_id: str
    best_bid: float = 0.0
    best_ask: float = 1.0
    spread: float = 1.0
    bids: list[tuple[float, float]] = Field(default_factory=list)  # (price, size)
    asks: list[tuple[float, float]] = Field(default_factory=list)  # (price, size)
    bid_depth_usd: float = 0.0
    ask_depth_usd: float = 0.0


async def fetch_orderbook(token_id: str, *, depth: int = 10) -> OrderbookSummary:
    """Fetch orderbook for a single token from CLOB REST API.

    Falls back to an empty summary on any network error so callers can
    degrade gracefully.
    """
    url = f"{CLOB_BASE_URL}/book"
    params = {"token_id": token_id}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        bids = _parse_levels(data.get("bids", []))
        asks = _parse_levels(data.get("asks", []))

        # Sort: bids descending, asks ascending
        bids.sort(key=lambda x: x[0], reverse=True)
        asks.sort(key=lambda x: x[0])

        # Trim to requested depth
        bids = bids[:depth]
        asks = asks[:depth]

        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 1.0
        spread = best_ask - best_bid

        bid_depth = sum(p * s for p, s in bids)
        ask_depth = sum(p * s for p, s in asks)

        return OrderbookSummary(
            token_id=token_id,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            bids=bids,
            asks=asks,
            bid_depth_usd=round(bid_depth, 2),
            ask_depth_usd=round(ask_depth, 2),
        )

    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch CLOB orderbook for {tid}: {err}", tid=token_id, err=str(exc))
        return OrderbookSummary(token_id=token_id)
    except Exception as exc:
        logger.warning("Unexpected error fetching orderbook for {tid}: {err}", tid=token_id, err=str(exc))
        return OrderbookSummary(token_id=token_id)


async def fetch_market_orderbooks(
    yes_token_id: str,
    no_token_id: str | None = None,
) -> dict[str, OrderbookSummary]:
    """Fetch orderbooks for both YES and NO tokens of a market.

    Returns a dict with keys ``"yes"`` and (optionally) ``"no"``.
    """
    result: dict[str, OrderbookSummary] = {}
    result["yes"] = await fetch_orderbook(yes_token_id)
    if no_token_id:
        result["no"] = await fetch_orderbook(no_token_id)
    return result


def _parse_levels(raw: list[dict[str, Any]]) -> list[tuple[float, float]]:
    """Parse CLOB price levels from ``[{"price": "0.55", "size": "120"}, ...]``."""
    levels: list[tuple[float, float]] = []
    for entry in raw:
        try:
            price = float(entry.get("price", 0))
            size = float(entry.get("size", 0))
            if price > 0 and size > 0:
                levels.append((price, size))
        except (TypeError, ValueError):
            continue
    return levels
