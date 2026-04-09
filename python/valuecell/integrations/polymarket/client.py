"""Polymarket Gamma API client (read-only, no auth require)."""

from typing import List, Optional
import httpx
from loguru import logger

from .models import PolymarketMarket, PolymarketToken

# Polymarket public Gamma API (no auth required)
GAMMA_API_BASE = "https://gamma-api.polymarket.com"

# Tag/category keywords yang relevan dengan crypto & finance
CRYPTO_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "crypto",
    "fed", "interest rate", "inflation", "recession",
    "nasdaq", "s&p", "stock market", "sec", "etf",
]

async def get_markets(
    limit: int = 20,
    offset: int = 0,
    active: bool = True,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
) -> List[PolymarketMarket]:
    """Fetch active prediction markets from Polymarket Gamma API."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if keyword:
                url = f"{GAMMA_API_BASE}/public-search"
                params = {
                    "limit": limit,
                    "offset": offset,
                    "q": keyword,
                }
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                raw_markets = []
                for event in data.get("events", []):
                    # Bubble down useful event fields to markets if missing
                    e_cat = event.get("category")
                    e_end = event.get("endDate")
                    e_slug = event.get("slug")
                    
                    for market in event.get("markets", []):
                        if "category" not in market and e_cat:
                            market["category"] = e_cat
                        if "endDateIso" not in market and e_end:
                            market["endDateIso"] = e_end
                        if e_slug:
                            market["event_slug"] = e_slug
                        # Sometimes active flag inside public-search markets is missing, we can assume True or parse from event
                        if "active" not in market:
                            market["active"] = event.get("active", True)
                        if "closed" not in market:
                            market["closed"] = event.get("closed", False)
                            
                        # Filter out inactive or closed markets to ensure valid, realtime data
                        if not market["active"] or market["closed"]:
                            continue
                            
                        raw_markets.append(market)
                
                # Only take up to the requested limit 
                raw_markets = raw_markets[:limit]
                
            else:
                url = f"{GAMMA_API_BASE}/markets"
                params = {
                    "limit": limit,
                    "offset": offset,
                    "active": str(active).lower(),
                    "closed": "false",
                    "order": "volume",
                    "ascending": "false",
                }
                if category:
                    params["category"] = category
                
                response = await client.get(url, params=params)
                response.raise_for_status()
                raw_markets = response.json()
                
        return _parse_markets(raw_markets)
    
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch Polymarket markets: {err}", err=str(exc))
        return []


async def get_crypto_relevant_markets(limit: int = 10) -> List[PolymarketMarket]:
    """Fetch Polymarket markets that are relevant to crypto/finance decisions."""
    results: List[PolymarketMarket] = []
    
    for keyword in ["crypto", "bitcoin", "fed rate", "inflation"]:
        markets = await get_markets(limit=5, keyword=keyword)
        results.extend(markets)
        if len(results) >= limit:
            break 
    
    # Deduplicate by condition_id
    seen: set = set()
    unique: List[PolymarketMarket] = []
    for m in results:
        if m.condition_id not in seen:
            seen.add(m.condition_id)
            unique.append(m)
            
    return unique[:limit]


async def get_market_by_id(condition_id: str) -> Optional[PolymarketMarket]:
    """Fetch a single market by its condition ID."""
    url = f"{GAMMA_API_BASE}/markets/{condition_id}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return _parse_single_market(response.json())
    except httpx.HTTPError as exc:
        logger.warning("Failed to fetch market {id}: {err}", id=condition_id, err=str(exc))
        return None 
    

def _parse_markets(raw: list) -> List[PolymarketMarket]:
    """Parse raw API response into PolymarketMarket models."""
    markets = []
    for item in raw:
        market = _parse_single_market(item)
        if market is not None:
            markets.append(market)
    return markets


def _parse_single_market(item: dict) -> Optional[PolymarketMarket]:
    """Parse a single raw market dict.

    Gamma API returns prices primarily in `outcomePrices` (a JSON-stringified
    list) alongside `outcomes` (also JSON-stringified). We prefer these fields
    over the `tokens` array because token prices are often 0 in the response.
    """
    import json as _json

    try:
        # --- Parse outcome prices (primary source) ---
        raw_outcomes = item.get("outcomes", "[]")
        raw_prices = item.get("outcomePrices", "[]")

        # outcomePrices and outcomes can be either a JSON string or already a list
        if isinstance(raw_outcomes, str):
            try:
                outcomes_list: list = _json.loads(raw_outcomes)
            except Exception:
                outcomes_list = []
        else:
            outcomes_list = raw_outcomes or []

        if isinstance(raw_prices, str):
            try:
                prices_list: list = _json.loads(raw_prices)
            except Exception:
                prices_list = []
        else:
            prices_list = raw_prices or []

        tokens = []
        if outcomes_list and prices_list and len(outcomes_list) == len(prices_list):
            # Build tokens from outcomePrices — the reliable source
            for outcome_label, price_val in zip(outcomes_list, prices_list):
                try:
                    price = float(price_val)
                except (TypeError, ValueError):
                    price = 0.0
                tokens.append(PolymarketToken(
                    token_id="",
                    outcome=str(outcome_label),
                    price=price,
                ))
        else:
            # Fallback: use tokens array directly
            for token_data in item.get("tokens", []):
                tokens.append(PolymarketToken(
                    token_id=token_data.get("token_id", ""),
                    outcome=token_data.get("outcome", ""),
                    price=float(token_data.get("price", 0.0)),
                ))

        return PolymarketMarket(
            condition_id=item.get("conditionId") or item.get("condition_id", ""),
            question=item.get("question", ""),
            description=item.get("description"),
            category=item.get("category"),
            end_date_iso=item.get("endDateIso") or item.get("end_date_iso"),
            volume=float(item.get("volumeNum") or item.get("volume") or 0.0),
            liquidity=float(item.get("liquidityNum") or item.get("liquidity") or 0.0),
            active=item.get("active", True),
            closed=item.get("closed", False),
            tokens=tokens,
            market_slug=item.get("slug") or item.get("market_slug"),
            event_slug=item.get("event_slug") or (item.get("events")[0].get("slug") if item.get("events") and len(item.get("events")) > 0 else None) or item.get("slug") or item.get("market_slug"),
        )
    except Exception as exc:
        logger.warning("Failed to parse market: {err}", err=str(exc))
        return None
