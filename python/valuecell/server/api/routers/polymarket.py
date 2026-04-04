"""Polymarket prediction market API routes."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ....integrations.polymarket.client import get_markets, get_crypto_relevant_markets
from ....integrations.polymarket.models import PolymarketMarket
from ..schemas import SuccessResponse

# Response Schemas

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
    tokens: List[TokenData] = []
    

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
        tokens=[
            TokenData(token_id=t.token_id, outcome=t.outcome, price=t.price)
            for t in market.tokens
        ],
    )
    

# Router Factory 

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
        
    return router

