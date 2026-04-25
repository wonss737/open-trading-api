"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  Bell,
  RefreshCw,
  Plus,
  X,
  TrendingUp,
  TrendingDown,
  AlertCircle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Globe,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getSignals, getMarketLeaders } from "@/lib/api";
import type { SignalItem, SignalStatus, SignalStrategyOption } from "@/types/signals";
import { SIGNAL_STRATEGIES } from "@/types/signals";
import type { MarketLeaderItem } from "@/types/market_leaders";

const LOCALSTORAGE_KEY = "signal_watchlist_v2";
const MAX_LEADERS = 15;

function loadWatchlist(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(LOCALSTORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

function saveWatchlist(list: string[]) {
  if (typeof window === "undefined") return;
  localStorage.setItem(LOCALSTORAGE_KEY, JSON.stringify(list));
}

function formatPrice(price: number | null, symbol: string): string {
  if (price == null) return "-";
  const isUs = /^[A-Za-z]/.test(symbol);
  if (isUs) return `$${price.toFixed(2)}`;
  return `₩${Math.round(price).toLocaleString()}`;
}

// ── Signal Badge ──────────────────────────────────────────
function SignalBadge({
  signal,
  label,
}: {
  signal?: SignalStatus;
  label: "매수" | "매도";
}) {
  if (!signal) {
    return (
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">{label}</span>
        <span className="text-xs text-slate-400">-</span>
      </div>
    );
  }

  const pct = signal.proximity_pct;

  if (signal.active) {
    const isBuy = label === "매수";
    return (
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">{label}</span>
        <span
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold",
            isBuy
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
              : "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
          )}
        >
          {isBuy ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
          ON
        </span>
      </div>
    );
  }

  const abs = Math.abs(pct);
  const color =
    abs < 1.5
      ? "text-amber-500 dark:text-amber-400"
      : abs < 5
      ? "text-yellow-500 dark:text-yellow-400"
      : "text-slate-400";
  const sign = pct >= 0 ? "+" : "";

  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-slate-500">{label}</span>
      <span className={cn("text-xs font-mono tabular-nums", color)}>
        {sign}
        {pct.toFixed(2)}%
      </span>
    </div>
  );
}

// ── Signal Card ───────────────────────────────────────────
function SignalCard({
  item,
  loading,
}: {
  item: SignalItem | { symbol: string; name: string };
  loading?: boolean;
}) {
  const signalItem = "buy_signal" in item || "error" in item ? (item as SignalItem) : null;
  const hasBuyOn = signalItem?.buy_signal?.active;
  const hasSellOn = signalItem?.sell_signal?.active;

  return (
    <div
      className={cn(
        "card transition-all",
        hasBuyOn && "border-emerald-300 dark:border-emerald-700",
        hasSellOn && !hasBuyOn && "border-amber-300 dark:border-amber-700",
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-slate-900 dark:text-white text-sm leading-tight truncate">
            {item.name !== item.symbol ? item.name : item.symbol}
          </p>
          {item.name !== item.symbol && (
            <p className="text-xs text-slate-400 font-mono mt-0.5">{item.symbol}</p>
          )}
        </div>
        {signalItem?.current_price != null && (
          <p className="text-sm font-mono font-bold text-slate-700 dark:text-slate-300 ml-2 shrink-0">
            {formatPrice(signalItem.current_price, item.symbol)}
          </p>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          계산 중...
        </div>
      ) : signalItem?.error ? (
        <div className="flex items-center gap-1.5 text-xs text-red-400">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          {signalItem.error}
        </div>
      ) : signalItem ? (
        <div className="space-y-1.5">
          <SignalBadge signal={signalItem.buy_signal} label="매수" />
          <SignalBadge signal={signalItem.sell_signal} label="매도" />
          {signalItem.updated_at && (
            <p className="mt-1.5 text-[10px] text-slate-400 text-right">
              {new Date(signalItem.updated_at).toLocaleDateString("ko-KR")}
            </p>
          )}
        </div>
      ) : (
        <div className="text-xs text-slate-400">데이터 대기 중</div>
      )}
    </div>
  );
}

// ── Param Input ───────────────────────────────────────────
function ParamInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <label className="text-xs text-slate-500 mb-1 block">{label}</label>
      <input
        type="number"
        min={1}
        max={200}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full px-2 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg text-sm bg-white dark:bg-slate-800"
      />
    </div>
  );
}

// ── Leaders Section ───────────────────────────────────────
function LeadersSection({
  title,
  leaders,
  signals,
  loading,
  flagEmoji,
}: {
  title: string;
  leaders: MarketLeaderItem[];
  signals: Map<string, SignalItem>;
  loading: boolean;
  flagEmoji: string;
}) {
  if (leaders.length === 0) return null;

  return (
    <div>
      <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2 text-sm">
        <span>{flagEmoji}</span>
        {title}
        <span className="text-slate-400 font-normal">({leaders.length}종목)</span>
      </h3>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {leaders.map((leader) => {
          const s = signals.get(leader.code);
          return (
            <SignalCard
              key={leader.code}
              item={s ?? { symbol: leader.code, name: leader.name }}
              loading={loading && !s}
            />
          );
        })}
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────
export default function SignalPage() {
  // 관심 종목 (localStorage)
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [inputValue, setInputValue] = useState("");

  // 시장 선도주 (API)
  const [krLeaders, setKrLeaders] = useState<MarketLeaderItem[]>([]);
  const [usLeaders, setUsLeaders] = useState<MarketLeaderItem[]>([]);
  const [leadersLoading, setLeadersLoading] = useState(false);

  // 전략 설정
  const [strategyId, setStrategyId] = useState("macd_signal");
  const [selectedStrategy, setSelectedStrategy] = useState<SignalStrategyOption>(SIGNAL_STRATEGIES[0]);
  const [fastPeriod, setFastPeriod] = useState(12);
  const [slowPeriod, setSlowPeriod] = useState(26);
  const [signalPeriod, setSignalPeriod] = useState(9);
  const [paramsOpen, setParamsOpen] = useState(false);

  // 신호 데이터
  const [leaderSignals, setLeaderSignals] = useState<Map<string, SignalItem>>(new Map());
  const [watchlistSignals, setWatchlistSignals] = useState<Map<string, SignalItem>>(new Map());
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  // 초기 watchlist 로드
  useEffect(() => {
    setWatchlist(loadWatchlist());
  }, []);

  // 전략 변경 시 기본 파라미터 동기화
  useEffect(() => {
    const s = SIGNAL_STRATEGIES.find((s) => s.id === strategyId) ?? SIGNAL_STRATEGIES[0];
    setSelectedStrategy(s);
    if (s.fast_default) setFastPeriod(s.fast_default);
    if (s.slow_default) setSlowPeriod(s.slow_default);
    if (s.signal_default) setSignalPeriod(s.signal_default);
  }, [strategyId]);

  // 시장 선도주 로드
  const loadLeaders = useCallback(async () => {
    setLeadersLoading(true);
    try {
      const [kr, us] = await Promise.allSettled([
        getMarketLeaders("kr"),
        getMarketLeaders("us"),
      ]);
      if (kr.status === "fulfilled") {
        setKrLeaders(kr.value.by_market_cap.slice(0, MAX_LEADERS));
      }
      if (us.status === "fulfilled") {
        setUsLeaders(us.value.by_market_cap.slice(0, MAX_LEADERS));
      }
    } catch (e) {
      console.error("선도주 로드 실패:", e);
    } finally {
      setLeadersLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLeaders();
  }, [loadLeaders]);

  // 신호 계산 공통 함수
  const calcSignals = useCallback(
    async (symbols: string[]): Promise<SignalItem[]> => {
      if (symbols.length === 0) return [];
      const res = await getSignals({
        symbols,
        strategy_id: strategyId,
        fast_period: fastPeriod,
        slow_period: selectedStrategy.slow_default != null ? slowPeriod : undefined,
        signal_period: selectedStrategy.signal_default != null ? signalPeriod : undefined,
      });
      return res.signals;
    },
    [strategyId, fastPeriod, slowPeriod, signalPeriod, selectedStrategy],
  );

  // 전체 신호 새로고침
  const refresh = useCallback(async () => {
    const leaderCodes = [
      ...krLeaders.map((l) => l.code),
      ...usLeaders.map((l) => l.code),
    ];
    const allSymbols = [...new Set([...leaderCodes, ...watchlist])];

    if (allSymbols.length === 0) return;
    setSignalsLoading(true);
    setError(null);

    try {
      const items = await calcSignals(allSymbols);
      const newLeaderMap = new Map<string, SignalItem>();
      const newWatchMap = new Map<string, SignalItem>();
      const leaderSet = new Set(leaderCodes);

      for (const item of items) {
        if (leaderSet.has(item.symbol)) newLeaderMap.set(item.symbol, item);
        if (watchlist.includes(item.symbol)) newWatchMap.set(item.symbol, item);
      }
      setLeaderSignals(newLeaderMap);
      setWatchlistSignals(newWatchMap);
      setLastRefreshed(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "신호 조회 실패");
    } finally {
      setSignalsLoading(false);
    }
  }, [krLeaders, usLeaders, watchlist, calcSignals]);

  // 선도주 로드 완료 또는 전략 변경 시 자동 계산
  useEffect(() => {
    if (krLeaders.length > 0 || usLeaders.length > 0) {
      refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [krLeaders, usLeaders, strategyId]);

  // 관심 종목 추가
  const addSymbol = useCallback(() => {
    const sym = inputValue.trim().toUpperCase();
    if (!sym || watchlist.includes(sym)) {
      setInputValue("");
      return;
    }
    const next = [...watchlist, sym];
    setWatchlist(next);
    saveWatchlist(next);
    setInputValue("");
  }, [inputValue, watchlist]);

  const removeSymbol = useCallback(
    (sym: string) => {
      const next = watchlist.filter((s) => s !== sym);
      setWatchlist(next);
      saveWatchlist(next);
      setWatchlistSignals((prev) => {
        const m = new Map(prev);
        m.delete(sym);
        return m;
      });
    },
    [watchlist],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") addSymbol();
  };

  // 신호 발동 카운트
  const onCountLeaders = useMemo(
    () =>
      [...leaderSignals.values()].filter(
        (s) => s.buy_signal?.active || s.sell_signal?.active,
      ).length,
    [leaderSignals],
  );

  return (
    <div className="max-w-screen-2xl mx-auto px-4 py-8">
      {/* 페이지 헤더 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Bell className="w-6 h-6 text-kis-blue" />
          신호 알림
        </h1>
        <p className="text-slate-600 dark:text-slate-400 mt-1">
          한국·미국 시장 선도주의 매수/매도 신호 발동 현황과 임박도를 한눈에 확인하세요
        </p>
      </div>

      <div className="grid xl:grid-cols-[280px_1fr] gap-6">
        {/* 왼쪽: 설정 */}
        <div className="space-y-4">
          {/* 전략 선택 */}
          <div className="card">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3 text-sm">전략 선택</h3>
            <select
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-sm"
            >
              {SIGNAL_STRATEGIES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>

            <button
              onClick={() => setParamsOpen((o) => !o)}
              className="mt-3 w-full flex items-center justify-between text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
            >
              <span>파라미터</span>
              {paramsOpen ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
            {paramsOpen && (
              <div className="mt-3 space-y-2">
                {selectedStrategy.fast_label && (
                  <ParamInput label={selectedStrategy.fast_label} value={fastPeriod} onChange={setFastPeriod} />
                )}
                {selectedStrategy.slow_label && (
                  <ParamInput label={selectedStrategy.slow_label} value={slowPeriod} onChange={setSlowPeriod} />
                )}
                {selectedStrategy.signal_label && (
                  <ParamInput label={selectedStrategy.signal_label} value={signalPeriod} onChange={setSignalPeriod} />
                )}
              </div>
            )}
          </div>

          {/* 관심 종목 */}
          <div className="card">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3 text-sm">관심 종목 추가</h3>
            <div className="flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="005930 또는 AAPL"
                className="flex-1 px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-sm"
              />
              <button
                onClick={addSymbol}
                disabled={!inputValue.trim()}
                className="p-2 rounded-lg bg-kis-blue text-white disabled:opacity-40 disabled:cursor-not-allowed hover:bg-kis-blue-dark transition-colors"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {watchlist.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {watchlist.map((sym) => (
                  <span
                    key={sym}
                    className="inline-flex items-center gap-1 px-2 py-1 bg-slate-100 dark:bg-slate-700 rounded-lg text-xs font-mono"
                  >
                    {sym}
                    <button
                      onClick={() => removeSymbol(sym)}
                      className="text-slate-400 hover:text-red-500 transition-colors"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* 새로고침 */}
          <button
            onClick={refresh}
            disabled={signalsLoading || (krLeaders.length === 0 && usLeaders.length === 0)}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 rounded-xl font-medium text-sm transition-all",
              !signalsLoading
                ? "bg-kis-blue hover:bg-kis-blue-dark text-white"
                : "bg-slate-200 text-slate-400 cursor-not-allowed",
            )}
          >
            {signalsLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            {signalsLoading ? "계산 중..." : "신호 새로고침"}
          </button>

          {lastRefreshed && (
            <p className="text-xs text-slate-400 text-center">
              마지막: {lastRefreshed.toLocaleTimeString("ko-KR")}
            </p>
          )}

          {/* 범례 */}
          <div className="card text-xs text-slate-500 space-y-1.5">
            <p className="font-semibold text-slate-700 dark:text-slate-300 mb-2">읽는 법</p>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 font-bold text-[10px]">
                <TrendingUp className="w-2.5 h-2.5" /> ON
              </span>
              <span>매수 신호 발동</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-700 font-bold text-[10px]">
                <TrendingDown className="w-2.5 h-2.5" /> ON
              </span>
              <span>매도 신호 발동</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-amber-500">-1.5%</span>
              <span>발동까지 1.5% 남음</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-slate-400">-5.0%</span>
              <span>발동까지 5.0% 남음</span>
            </div>
          </div>
        </div>

        {/* 오른쪽: 신호 결과 */}
        <div className="space-y-8 min-w-0">
          {error && (
            <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* 상태 요약 */}
          {!leadersLoading && (krLeaders.length > 0 || usLeaders.length > 0) && (
            <div className="flex items-center gap-4 text-sm text-slate-500">
              <Globe className="w-4 h-4 text-slate-400" />
              <span>
                시장 선도주{" "}
                <span className="font-semibold text-slate-700 dark:text-slate-300">
                  {krLeaders.length + usLeaders.length}종목
                </span>{" "}
                중{" "}
                <span className="font-semibold text-emerald-600">{onCountLeaders}개</span> 신호 발동
              </span>
              {signalsLoading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
            </div>
          )}

          {/* 한국 선도주 */}
          {leadersLoading ? (
            <div className="card flex items-center justify-center py-12 text-slate-400">
              <Loader2 className="w-6 h-6 animate-spin mr-2" />
              선도주 로딩 중...
            </div>
          ) : (
            <>
              <LeadersSection
                title="한국 시장 선도주"
                leaders={krLeaders}
                signals={leaderSignals}
                loading={signalsLoading}
                flagEmoji="🇰🇷"
              />
              <LeadersSection
                title="미국 시장 선도주"
                leaders={usLeaders}
                signals={leaderSignals}
                loading={signalsLoading}
                flagEmoji="🇺🇸"
              />
            </>
          )}

          {/* 관심 종목 (커스텀) */}
          {watchlist.length > 0 && (
            <div>
              <h3 className="font-semibold text-slate-800 dark:text-slate-200 mb-3 flex items-center gap-2 text-sm">
                <Bell className="w-4 h-4 text-kis-blue" />
                관심 종목
                <span className="text-slate-400 font-normal">({watchlist.length}종목)</span>
              </h3>
              <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
                {watchlist.map((sym) => {
                  const s = watchlistSignals.get(sym);
                  return (
                    <SignalCard
                      key={sym}
                      item={s ?? { symbol: sym, name: sym }}
                      loading={signalsLoading && !s}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* 비어있는 상태 */}
          {!leadersLoading && krLeaders.length === 0 && usLeaders.length === 0 && (
            <div className="card flex flex-col items-center justify-center py-20 text-slate-400">
              <Bell className="w-16 h-16 mb-4 opacity-20" />
              <p className="text-lg font-medium">시장 선도주 없음</p>
              <p className="text-sm mt-1">
                백엔드 서버를 시작하거나 먼저{" "}
                <span className="text-kis-blue">시장 선도주를 업데이트</span>
                해 주세요
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
