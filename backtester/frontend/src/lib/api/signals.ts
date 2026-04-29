import { apiGet } from "./client";
import type { SignalsResponse, MultiSignalsResponse } from "@/types/signals";

export interface GetSignalsParams {
  symbols: string[];
  strategy_id?: string;
  fast_period?: number;
  slow_period?: number;
  signal_period?: number;
}

export async function getSignals(params: GetSignalsParams): Promise<SignalsResponse> {
  const { symbols, strategy_id = "macd_signal", fast_period, slow_period, signal_period } = params;
  const qs = new URLSearchParams({ symbols: symbols.join(","), strategy_id });
  if (fast_period != null) qs.set("fast_period", String(fast_period));
  if (slow_period != null) qs.set("slow_period", String(slow_period));
  if (signal_period != null) qs.set("signal_period", String(signal_period));
  return apiGet<SignalsResponse>(`/api/signals?${qs}`);
}

export async function getMultiSignals(symbols: string[], forceRefresh = false): Promise<MultiSignalsResponse> {
  const qs = new URLSearchParams({ symbols: symbols.join(",") });
  if (forceRefresh) qs.set("force_refresh", "true");
  return apiGet<MultiSignalsResponse>(`/api/signals/multi?${qs}`);
}
