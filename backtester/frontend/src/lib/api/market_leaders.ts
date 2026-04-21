import { apiGet, apiPost } from "./client";
import type { MarketLeadersResponse, MarketLeadersStatus } from "@/types/market_leaders";

export type MarketType = "kr" | "us";

export async function getMarketLeaders(market: MarketType = "kr"): Promise<MarketLeadersResponse> {
  return apiGet<MarketLeadersResponse>(`/api/market-leaders?market=${market}`);
}

export async function getMarketLeadersStatus(market: MarketType = "kr"): Promise<MarketLeadersStatus> {
  return apiGet<MarketLeadersStatus>(`/api/market-leaders/status?market=${market}`);
}

export async function triggerMarketLeadersUpdate(
  market: MarketType = "kr",
): Promise<{ status: string; message: string }> {
  return apiPost<{ status: string; message: string }>(
    `/api/market-leaders/update?market=${market}`,
  );
}
