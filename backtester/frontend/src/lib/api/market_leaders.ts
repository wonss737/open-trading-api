import { apiGet, apiPost } from "./client";
import type { MarketLeadersResponse, MarketLeadersStatus } from "@/types/market_leaders";

export type MarketType = "kr" | "us";

export interface MarketLeadersDefaults {
  cap_limit: number;
  revenue_limit: number;
  amount_limit: number;
}

export async function getMarketLeadersDefaults(): Promise<MarketLeadersDefaults> {
  return apiGet<MarketLeadersDefaults>("/api/market-leaders/defaults");
}

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
  const { market = "kr", cap_limit, revenue_limit, amount_limit, force = false } = params;
  const qs = new URLSearchParams({ market, force: String(force) });
  if (cap_limit != null) qs.set("cap_limit", String(cap_limit));
  if (revenue_limit != null) qs.set("revenue_limit", String(revenue_limit));
  if (amount_limit != null) qs.set("amount_limit", String(amount_limit));
  return apiPost<{ status: string; message: string }>(`/api/market-leaders/update?${qs}`);
}
