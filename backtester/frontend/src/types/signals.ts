export interface SignalStatus {
  active: boolean;
  proximity_pct: number;
}

export interface MultiSignalData {
  macd:     { gap_pct: number; is_golden: boolean };
  ma_cross: { gap_pct: number };
  rsi:      { value: number };
  envelope: { gap_pct: number; gap_price: number };
  bollinger:{ gap_pct: number; gap_price: number };
  starc:    { gap_pct: number; gap_price: number };
}

export interface MultiSignalItem {
  symbol: string;
  name: string;
  current_price: number | null;
  signals?: MultiSignalData;
  updated_at?: string;
  error?: string;
}

export interface MultiSignalsResponse {
  signals: MultiSignalItem[];
  computed_at: string;
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
    id: "week52_high",
    name: "52주 신고가 돌파",
    fast_label: "조회 기간 (일)",
    fast_default: 252,
  },
  {
    id: "consecutive_moves",
    name: "N일 연속 상승·하락",
    fast_label: "연속 상승일",
    slow_label: "연속 하락일",
    fast_default: 5,
    slow_default: 5,
  },
  {
    id: "ma_divergence",
    name: "이동평균 이격도",
    fast_label: "이평 기간",
    fast_default: 20,
  },
  {
    id: "false_breakout",
    name: "추세 돌파 후 이탈",
    fast_label: "전고점 기간",
    fast_default: 20,
  },
  {
    id: "strong_close",
    name: "전일 대비 강한 종가",
  },
  {
    id: "volatility_breakout",
    name: "변동성 축소 후 확장",
    fast_label: "ATR 기간",
    slow_label: "비교 기간",
    fast_default: 10,
    slow_default: 20,
  },
  {
    id: "short_term_reversal",
    name: "단기 반전",
    fast_label: "이평 기간",
    fast_default: 5,
  },
  {
    id: "trend_filter_signal",
    name: "추세 필터 + 시그널",
    fast_label: "추세 MA 기간",
    fast_default: 60,
  },
  {
    id: "three_band",
    name: "삼중밴드",
    fast_label: "BB 기간",
    slow_label: "Envelope %",
    fast_default: 20,
    slow_default: 6,
  },
];
