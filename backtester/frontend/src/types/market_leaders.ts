export type MarketType = "kr" | "us";

export interface MarketLeaderItem {
  code: string;
  name: string;
  reason: string[];
}

export interface MarketLeadersStatus {
  is_updating: boolean;
  last_updated: string | null;
  needs_update: boolean;
  counts: {
    by_market_cap?: number;
    by_trading_amount?: number;
    by_revenue?: number;
    all_leaders?: number;
  };
}

export interface MarketLeadersResponse {
  status: string;
  market: MarketType;
  updated_at: string | null;
  total: number;
  by_market_cap: MarketLeaderItem[];
  by_trading_amount: MarketLeaderItem[];
  by_revenue: MarketLeaderItem[];
  all_leaders: MarketLeaderItem[];
}
