import { apiGet, apiPost } from "./client";
import type { MarketLeadersResponse, MarketLeadersStatus } from "@/types/market_leaders";

export type MarketType = "kr" | "us";

export async function getMarketLeaders(market: MarketType = "kr"): Promise<MarketLeadersResponse> {
  return apiGet<MarketLeadersResponse>(`/api/market-leaders?market=${market}`);
}

export async function getMarketLeadersStatus(market: MarketType = "kr"): Promise<MarketLeadersStatus> {
  return apiGet<MarketLeadersStatus>(`/api/market-leaders/status?market=${market}`);
}

export interface MarketLeadersUpdateParams {
  market?: MarketType;
  cap_limit?: number;
  revenue_limit?: number;
  amount_limit?: number;
  force?: boolean;
}

export async function triggerMarketLeadersUpdate(
  params: MarketLeadersUpdateParams = {},
): Promise<{ status: string; message: string }> {
  const { market = "kr", cap_limit = 75, revenue_limit = 75, amount_limit = 150, force = false } = params;
  const qs = new URLSearchParams({
    market,
    cap_limit: String(cap_limit),
    revenue_limit: String(revenue_limit),
    amount_limit: String(amount_limit),
    force: String(force),
  });
  return apiPost<{ status: string; message: string }>(`/api/market-leaders/update?${qs}`);
}
