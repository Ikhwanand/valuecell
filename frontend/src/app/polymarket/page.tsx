import { useState } from "react";
import { ExternalLink, X, Sparkles } from "lucide-react";
import { useGetPolymarkets, analyzeMarket } from "@/api/polymarket";
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
  const color = pct > 60 ? "#22c55e" : pct < 40 ? "#ef4444" : "#f59e0b";

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

function MarketCard({
  market,
  onClick,
}: {
  market: PolymarketMarket;
  onClick: () => void;
}) {
  const yesPct =
    market.yes_price != null ? Math.round(market.yes_price * 100) : null;

  const slug = market.event_slug || market.market_slug;
  const polymarketUrl = slug
    ? `https://polymarket.com/event/${slug}`
    : `https://polymarket.com`;

  return (
    <div
      onClick={onClick}
      className="flex flex-col justify-between rounded-xl border bg-card p-4 hover:shadow-[0_0_15px_rgba(255,255,255,0.05)] hover:border-primary/40 transition-all cursor-pointer gap-3 group"
    >
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
      {market.yes_price != null && <ProbabilityBar value={market.yes_price} />}

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

// Trade Drawer Component

// ─── Trade Drawer Component (UI Taruhan & AI) ────────────────────────────────

interface TradeDrawerProps {
  market: PolymarketMarket | null;
  onClose: () => void;
}

function TradeDrawer({ market, onClose }: TradeDrawerProps) {
  const [tradeType, setTradeType] = useState<"buy" | "sell">("buy");
  const [outcome, setOutcome] = useState<"yes" | "no" | null>(null);
  const [amount, setAmount] = useState<string>("");
  const [isAskingAi, setIsAskingAi] = useState(false);
  const [aiAnalysis, setAiAnalysis] = useState<string | null>(null);

  if (!market) return null;

  // Simulasi kerja Agen AI (Nantinya akan diganti dengan pemanggilan API ke Backend)
  const handleAskAi = async () => {
    if (!market) return;

    try {
      setIsAskingAi(true);

      const result = await analyzeMarket({
        condition_id: market.condition_id,
        question: market.question,
        yes_price: market.yes_price,
        volume: market.volume,
      });

      const {
        recommendation,
        outcome_recommended,
        suggested_amount,
        analysis,
      } = result.data;

      setAiAnalysis(analysis);
      setOutcome(outcome_recommended);
      setTradeType(recommendation);
      setAmount(suggested_amount.toString());
    } catch (e) {
      console.error(e);
      setAiAnalysis(
        "Sorry, our AI is too busy processing data, please try again later.",
      );
    } finally {
      setIsAskingAi(false);
    }
  };

  const yesPrice = market.yes_price ?? 0.5;
  const noPrice = 1 - yesPrice;

  // Kalkulasi Ringkasan Order
  const price = outcome === "yes" ? yesPrice : outcome === "no" ? noPrice : 0;
  const estimatedShares =
    price > 0 && amount ? (parseFloat(amount) / price).toFixed(2) : "0.00";
  const potentialReturn =
    price > 0 && amount ? (parseFloat(estimatedShares) * 1).toFixed(2) : "0.00";
  const roi =
    amount && parseFloat(amount) > 0
      ? (
          ((parseFloat(potentialReturn) - parseFloat(amount)) /
            parseFloat(amount)) *
          100
        ).toFixed(2)
      : "0.00";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Background Gelap Transparan */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Panel Laci Geser */}
      <div className="relative w-full max-w-md bg-card/95 backdrop-blur-xl border-l border-white/10 shadow-2xl h-full flex flex-col animate-in slide-in-from-right duration-300">
        {/* Header Drawer */}
        <div className="p-5 border-b border-border/50 flex justify-between items-start gap-4">
          <div>
            <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 text-primary mb-2 inline-block">
              {market.category || "General"}
            </span>
            <h2 className="font-semibold text-lg leading-tight">
              {market.question}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-muted rounded-full text-muted-foreground hover:text-foreground transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Area Konten Trading */}
        <div className="flex-1 overflow-y-auto p-5 space-y-6">
          {/* Toggle Beli / Jual */}
          <div className="flex bg-muted/50 p-1 rounded-lg">
            <button
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${tradeType === "buy" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setTradeType("buy")}
            >
              Buy
            </button>
            <button
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-all ${tradeType === "sell" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground"}`}
              onClick={() => setTradeType("sell")}
            >
              Sell
            </button>
          </div>

          {/* Tombol YES & NO */}
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => setOutcome("yes")}
              className={`flex flex-col items-center justify-center p-4 rounded-xl border-2 transition-all ${
                outcome === "yes"
                  ? "border-green-500/50 bg-green-500/10 text-green-500 shadow-[0_0_15px_rgba(34,197,94,0.15)]"
                  : "border-border/50 hover:border-green-500/30 bg-muted/20"
              }`}
            >
              <span className="text-xl font-bold">YES</span>
              <span className="text-sm opacity-80">
                {(yesPrice * 100).toFixed(1)}¢
              </span>
            </button>

            <button
              onClick={() => setOutcome("no")}
              className={`flex flex-col items-center justify-center p-4 rounded-xl border-2 transition-all ${
                outcome === "no"
                  ? "border-red-500/50 bg-red-500/10 text-red-500 shadow-[0_0_15px_rgba(239,68,68,0.15)]"
                  : "border-border/50 hover:border-red-500/30 bg-muted/20"
              }`}
            >
              <span className="text-xl font-bold">NO</span>
              <span className="text-sm opacity-80">
                {(noPrice * 100).toFixed(1)}¢
              </span>
            </button>
          </div>

          {/* AI Advisor Button (Fitur Auto-fill Agent) */}
          <div className="rounded-xl border border-blue-500/30 bg-blue-500/5 overflow-hidden">
            {!aiAnalysis ? (
              <button
                onClick={handleAskAi}
                disabled={isAskingAi}
                className="w-full p-4 flex items-center justify-center gap-2 text-blue-500 font-medium hover:bg-blue-500/10 transition-colors"
              >
                {isAskingAi ? (
                  <span className="animate-pulse flex items-center gap-2">
                    <Sparkles size={18} className="animate-spin" /> Agent is
                    analyzing...
                  </span>
                ) : (
                  <>
                    <Sparkles size={18} />
                    Ask Agent for Recommendation
                  </>
                )}
              </button>
            ) : (
              <div className="p-4 relative">
                <button
                  onClick={() => setAiAnalysis(null)}
                  className="absolute top-2 right-2 text-muted-foreground hover:text-foreground"
                >
                  <X size={14} />
                </button>
                <div className="flex items-center gap-2 text-blue-500 mb-2">
                  <Sparkles size={16} />
                  <span className="text-sm font-semibold">Agent Analysis</span>
                </div>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  {aiAnalysis}
                </p>
              </div>
            )}
          </div>

          {/* Input Dana (Amount USDC) */}
          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">
              Amount (USDC)
            </label>
            <div className="relative">
              <span className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground">
                $
              </span>
              <input
                type="number"
                placeholder="0.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                className="w-full bg-background border border-border/50 px-8 py-3 rounded-xl text-lg font-medium focus:ring-2 focus:ring-primary/50 focus:outline-none placeholder:text-muted-foreground/40"
              />
            </div>
          </div>

          {/* Ringkasan Taruhan (Order Summary) */}
          <div className="bg-muted/30 rounded-xl p-4 space-y-3">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Est. Shares</span>
              <span className="font-medium text-foreground">
                {estimatedShares}
              </span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Potential Return</span>
              <span className="font-medium text-green-500">
                ${potentialReturn}
              </span>
            </div>
            <div className="flex justify-between text-sm border-t border-border/50 pt-3 mt-1">
              <span className="text-muted-foreground">
                Return on Investment (ROI)
              </span>
              <span className="font-medium text-foreground">{roi}%</span>
            </div>
          </div>
        </div>

        {/* Footer actions (Trade Externally) */}
        <div className="p-5 border-t border-border/50 bg-card/60 backdrop-blur-md flex flex-col gap-2">
          <p className="text-xs text-center text-muted-foreground mb-1">
            Use the calculator above to simulate your strategy.
          </p>
          <a
            href={
              market.event_slug || market.market_slug
                ? `https://polymarket.com/event/${market.event_slug || market.market_slug}`
                : `https://polymarket.com`
            }
            target="_blank"
            rel="noopener noreferrer"
            className="w-full py-4 rounded-xl bg-primary text-primary-foreground font-semibold hover:opacity-90 transition-opacity flex justify-center items-center gap-2 shadow-[0_0_20px_rgba(var(--primary),0.3)]"
          >
            <ExternalLink size={18} />
            Bet directly on Polymarket
          </a>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────

// ─── Page ────────────────────────────────────────────────────────────────────

export default function PolymarketPage() {
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [selectedMarket, setSelectedMarket] = useState<PolymarketMarket | null>(
    null,
  );

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
            <h1 className="text-3xl font-medium">
              Polymarket Prediction Markets
            </h1>
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
                  <MarketCard
                    key={market.condition_id}
                    market={market}
                    onClick={() => setSelectedMarket(market)}
                  />
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

      <TradeDrawer
        market={selectedMarket}
        onClose={() => setSelectedMarket(null)}
      />
    </div>
  );
}
