"""Polymarket data models."""

from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class PolymarketToken(BaseModel):
    token_id: str
    outcome: str  # "Yes" or "No"
    price: float  # 0.0 - 1.0 (probability)


class PolymarketMarket(BaseModel):
    condition_id: str
    question: str
    description: Optional[str] = None
    category: Optional[str] = None
    end_date_iso: Optional[str] = None
    volume: float = 0.0
    liquidity: float = 0.0
    active: bool = True
    closed: bool = False
    tokens: List[PolymarketToken] = Field(default_factory=list)
    market_slug: Optional[str] = None

    # Derived fields — populated automatically after tokens are set
    yes_price: Optional[float] = None
    no_price: Optional[float] = None

    @model_validator(mode="after")
    def _compute_prices(self) -> "PolymarketMarket":
        """Derive yes/no prices from the tokens list so they serialize in API output."""
        for token in self.tokens:
            label = token.outcome.lower()
            if label == "yes" and self.yes_price is None:
                self.yes_price = token.price
            elif label == "no" and self.no_price is None:
                self.no_price = token.price
        return self


class PolymarketSignal(BaseModel):
    """Distilled signal from polymarket for use in StrategyAgent features."""
    question: str
    yes_probability: float  # 0.0 - 1.0
    volume: float
    relevance_score: float = 1.0  # Higher = more relevant to the asset
    category: Optional[str] = None
    
