export interface PolymarketToken {
  token_id: string;
  outcome: string;
  price: number;
}

export interface PolymarketMarket {
  condition_id: string;
  question: string;
  description?: string;
  category?: string;
  end_date_iso?: string;
  volume: number;
  liquidity: number;
  active: boolean;
  closed: boolean;
  yes_price?: number;
  no_price?: number;
  market_slug?: string;
  tokens: PolymarketToken[];
}
