export interface SignalStatus {
  active: boolean;
  proximity_pct: number;
}

export interface SignalItem {
  symbol: string;
  name: string;
  current_price: number | null;
  strategy_id: string;
  buy_signal?: SignalStatus;
  sell_signal?: SignalStatus;
  updated_at?: string;
  error?: string;
}

export interface SignalsResponse {
  signals: SignalItem[];
  strategy_id: string;
  computed_at: string;
}

export interface SignalStrategyOption {
  id: string;
  name: string;
  fast_label?: string;
  slow_label?: string;
  signal_label?: string;
  fast_default?: number;
  slow_default?: number;
  signal_default?: number;
}

export const SIGNAL_STRATEGIES: SignalStrategyOption[] = [
  {
    id: "macd_signal",
    name: "MACD 골든/데드 크로스",
    fast_label: "단기 EMA",
    slow_label: "장기 EMA",
    signal_label: "시그널",
    fast_default: 12,
    slow_default: 26,
    signal_default: 9,
  },
  {
    id: "sma_crossover",
    name: "SMA 골든/데드 크로스",
    fast_label: "단기 SMA",
    slow_label: "장기 SMA",
    fast_default: 5,
    slow_default: 20,
  },
  {
    id: "momentum",
    name: "모멘텀 (ROC)",
    fast_label: "기간",
    fast_default: 20,
  },
  {
    id: "rsi",
    name: "RSI 과매도/과매수",
    fast_label: "RSI 기간",
    fast_default: 14,
  },
];
