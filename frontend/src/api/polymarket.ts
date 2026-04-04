import { useQuery } from "@tanstack/react-query";
import { apiClient, type ApiResponse } from "@/lib/api-client";
import type { PolymarketMarket } from "@/types/polymarket";

// Query Keys
export const POLYMARKET_KEYS = {
  markets: ["polymarket", "markets"] as const,
  cryptoMarkets: ["polymarket", "crypto"] as const,
  filtered: (keyword: string) => ["polymarket", "markets", keyword] as const,
};

// Hooks

export const useGetPolymarkets = (params?: {
  limit?: number;
  keyword?: string;
}) =>
  useQuery({
    queryKey: params?.keyword
      ? POLYMARKET_KEYS.filtered(params.keyword)
      : POLYMARKET_KEYS.markets,
    queryFn: () => {
      const searchParams = new URLSearchParams();
      if (params?.limit) searchParams.set("limit", String(params.limit));
      if (params?.keyword) searchParams.set("keyword", params.keyword);
      const query = searchParams.toString();
      return apiClient.get<ApiResponse<PolymarketMarket[]>>(
        `polymarket/markets${query ? `?${query}` : ""}`,
      );
    },
    select: (data) => data.data,
    staleTime: 1000 * 60 * 2, // 2 minutes cache
  });

export const useGetCryptoPolymarkets = (limit = 10) =>
  useQuery({
    queryKey: [...POLYMARKET_KEYS.cryptoMarkets, limit],
    queryFn: () =>
      apiClient.get<ApiResponse<PolymarketMarket[]>>(
        `polymarket/markets/crypto?limit=${limit}`,
      ),
    select: (data) => data.data,
    staleTime: 1000 * 60 * 2,
  });
