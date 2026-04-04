import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { useGetPolymarkets } from "@/api/polymarket";
import type { PolymarketMarket } from "@/types/polymarket";

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmt(value: number): string {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toFixed(0)}`;
}

function ProbabilityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  // > 60% → bullish → green | < 40% → bearish → red | else → neutral → yellow
  const color =
    pct > 60 ? "#22c55e" : pct < 40 ? "#ef4444" : "#f59e0b";

  return (
    <div className="w-full">
      <div className="flex justify-between text-xs mb-1">
        <span style={{ color }} className="font-medium">
          Yes {pct}%
        </span>
        <span className="text-muted-foreground">No {100 - pct}%</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}

function SentimentBadge({ yesPct }: { yesPct: number | null }) {
  if (yesPct === null) return null;
  const sentiment =
    yesPct > 60 ? "bullish" : yesPct < 40 ? "bearish" : "neutral";
  const cls =
    sentiment === "bullish"
      ? "text-green-500"
      : sentiment === "bearish"
        ? "text-red-500"
        : "text-yellow-500";
  return (
    <span className={`text-xs font-semibold uppercase tracking-wide ${cls}`}>
      {sentiment} signal
    </span>
  );
}

function MarketCard({ market }: { market: PolymarketMarket }) {
  const yesPct =
    market.yes_price != null ? Math.round(market.yes_price * 100) : null;

  const polymarketUrl = market.market_slug
    ? `https://polymarket.com/event/${market.market_slug}`
    : `https://polymarket.com`;

  return (
    <div className="flex flex-col justify-between rounded-xl border bg-card p-4 hover:shadow-md transition-shadow gap-3">
      {/* Top row: category + external link */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          {market.category && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary mb-2 inline-block">
              {market.category}
            </span>
          )}
          <p className="text-sm font-medium leading-snug line-clamp-3">
            {market.question}
          </p>
        </div>

        <a
          href={polymarketUrl}
          target="_blank"
          rel="noopener noreferrer"
          title="View on Polymarket"
          className="shrink-0 mt-1 text-muted-foreground hover:text-primary transition-colors"
        >
          <ExternalLink size={14} />
        </a>
      </div>

      {/* Probability bar */}
      {market.yes_price != null && (
        <ProbabilityBar value={market.yes_price} />
      )}

      {/* Stats row */}
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>Vol: {fmt(market.volume)}</span>
        <span>Liq: {fmt(market.liquidity)}</span>
        {market.end_date_iso && (
          <span>
            Ends: {new Date(market.end_date_iso).toLocaleDateString()}
          </span>
        )}
      </div>

      {/* Sentiment */}
      <SentimentBadge yesPct={yesPct} />
    </div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function PolymarketPage() {
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");

  const {
    data: markets,
    isLoading,
    error,
  } = useGetPolymarkets({ limit: 30, keyword: search || undefined });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(keyword);
  };

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-hidden bg-muted py-4 pr-4 pl-2 w-full h-full">
      <div className="flex-1 rounded-lg bg-card overflow-y-auto scroll-smooth">
        <div className="mx-auto py-8 px-6 xl:px-12 max-w-[1600px]">
          {/* Header */}
          <div className="mb-6">
            <h1 className="text-3xl font-medium">Polymarket Prediction Markets</h1>
            <p className="text-muted-foreground text-sm mt-2">
              Crowd wisdom from prediction markets — additional signals for your
              trading strategy
            </p>
          </div>

          {/* Search */}
          <form onSubmit={handleSearch} className="flex gap-2 mb-8 max-w-2xl">
            <input
              id="polymarket-search-input"
              type="text"
              className="flex-1 px-4 py-2.5 rounded-lg border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/50 shadow-sm"
              placeholder="Search markets… (e.g. bitcoin, fed, inflation)"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <button
              id="polymarket-search-btn"
              type="submit"
              className="px-6 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity shadow-sm"
            >
              Search
            </button>
          </form>

          {/* Loading */}
          {isLoading && (
            <div className="flex items-center justify-center py-24 text-muted-foreground text-sm">
              Loading prediction markets…
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="flex items-center justify-center py-24 text-red-500 text-sm">
              Failed to load markets. Make sure the backend is running.
            </div>
          )}

          {/* Markets grid */}
          {markets && markets.length > 0 && (
            <>
              <p className="text-xs text-muted-foreground mb-4">
                Showing {markets.length} relevant markets
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-5">
                {markets.map((market) => (
                  <MarketCard key={market.condition_id} market={market} />
                ))}
              </div>
            </>
          )}

          {markets && markets.length === 0 && (
            <div className="flex flex-col items-center justify-center py-24 text-muted-foreground text-sm">
              <p>No markets found matching your search.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
