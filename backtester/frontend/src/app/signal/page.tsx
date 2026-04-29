"use client";

import { useState, useEffect, useCallback, useMemo, type ReactNode } from "react";
import {
  Bell,
  RefreshCw,
  Plus,
  X,
  AlertCircle,
  Loader2,
  Globe,
  Download,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getMultiSignals, getMarketLeaders } from "@/lib/api";
import type { MultiSignalItem } from "@/types/signals";
import type { MarketLeaderItem } from "@/types/market_leaders";

const LOCALSTORAGE_KEY = "signal_watchlist_v2";
const BATCH_SIZE = 10;

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

function formatPrice(price: number | null, symbol: string): ReactNode {
  if (price == null) return "-";
  const isUs = /^[A-Za-z]/.test(symbol);
  if (isUs) return `$${price.toFixed(2)}`;
  return <><span style={{ fontSize: "0.8em" }}>₩</span>{Math.round(price).toLocaleString()}</>;
}

function formatGapPrice(gap_price: number, symbol: string): ReactNode {
  const isUs = /^[A-Za-z]/.test(symbol);
  const abs = Math.abs(gap_price);
  if (isUs) return `$${abs.toFixed(2)}`;
  return <><span style={{ fontSize: "0.8em" }}>₩</span>{Math.round(abs).toLocaleString()}</>;
}

// ── Band Row ──────────────────────────────────────────────────
function BandRow({
  label,
  gap_pct,
  gap_price,
  symbol,
}: {
  label: string;
  gap_pct: number;
  gap_price: number;
  symbol: string;
}) {
  const isAbove = gap_pct > 0;
  const isClose = !isAbove && gap_pct > -2;
  const color = isAbove
    ? "text-emerald-500 dark:text-emerald-400"
    : isClose
    ? "text-amber-500 dark:text-amber-400"
    : "text-slate-400";
  const pctStr = `${gap_pct >= 0 ? "+" : ""}${gap_pct.toFixed(2)}%`;
  const priceStr = formatGapPrice(gap_price, symbol);

  return (
    <div className="flex items-center justify-between text-xs">
      <span className="text-slate-500 w-12 shrink-0">{label}</span>
      <span className={cn("font-mono tabular-nums", color)}>
        {pctStr}
        <span className="ml-1.5 text-slate-500 dark:text-slate-400">{priceStr}</span>
      </span>
    </div>
  );
}

// ── Multi Signal Card ─────────────────────────────────────────
function MultiSignalCard({
  item,
  loading,
}: {
  item: MultiSignalItem | { symbol: string; name: string };
  loading?: boolean;
}) {
  const multi =
    "signals" in item || "error" in item ? (item as MultiSignalItem) : null;
  const signals = multi?.signals;
  const isGolden = signals?.macd.is_golden;

  return (
    <div
      className={cn(
        "card transition-all",
        isGolden && "border-emerald-300 dark:border-emerald-700",
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-2">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-slate-900 dark:text-white text-sm leading-tight truncate">
            {item.name !== item.symbol ? item.name : item.symbol}
          </p>
          {item.name !== item.symbol && (
            <p className="text-xs text-slate-400 font-mono mt-0.5">{item.symbol}</p>
          )}
        </div>
        {multi?.current_price != null && (
          <p className="text-sm font-mono font-bold text-slate-700 dark:text-slate-300 ml-2 shrink-0">
            {formatPrice(multi.current_price, item.symbol)}
          </p>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          계산 중...
        </div>
      ) : multi?.error ? (
        <div className="flex items-center gap-1.5 text-xs text-red-400">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          {multi.error}
        </div>
      ) : signals ? (
        <div className="space-y-1">
          {/* MACD */}
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 w-14 shrink-0">MACD</span>
            <span
              className={cn(
                "font-mono tabular-nums font-medium",
                signals.macd.is_golden
                  ? "text-emerald-500 dark:text-emerald-400"
                  : "text-red-400",
              )}
            >
              {signals.macd.gap_pct >= 0 ? "+" : ""}
              {signals.macd.gap_pct.toFixed(2)}%
              <span className="ml-1 text-[12px]">
                {signals.macd.is_golden ? "Golden" : "Dead"}
              </span>
            </span>
          </div>

          {/* MA20/60 */}
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 w-14 shrink-0">MA20/60</span>
            <span
              className={cn(
                "font-mono tabular-nums",
                signals.ma_cross.gap_pct > 0
                  ? "text-emerald-500 dark:text-emerald-400"
                  : "text-slate-400",
              )}
            >
              {signals.ma_cross.gap_pct >= 0 ? "+" : ""}
              {signals.ma_cross.gap_pct.toFixed(2)}%
            </span>
          </div>

          {/* RSI */}
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-500 w-14 shrink-0">RSI</span>
            <span
              className={cn(
                "font-mono tabular-nums",
                signals.rsi.value < 30
                  ? "text-emerald-500 dark:text-emerald-400"
                  : signals.rsi.value > 70
                  ? "text-red-400"
                  : "text-slate-600 dark:text-slate-300",
              )}
            >
              {signals.rsi.value.toFixed(1)}
            </span>
          </div>

          {/* Band distances */}
          <div className="border-t border-slate-100 dark:border-slate-700 pt-1 space-y-1">
            <BandRow
              label="Env"
              gap_pct={signals.envelope.gap_pct}
              gap_price={signals.envelope.gap_price}
              symbol={item.symbol}
            />
            <BandRow
              label="BB"
              gap_pct={signals.bollinger.gap_pct}
              gap_price={signals.bollinger.gap_price}
              symbol={item.symbol}
            />
            <BandRow
              label="STARC"
              gap_pct={signals.starc.gap_pct}
              gap_price={signals.starc.gap_price}
              symbol={item.symbol}
            />
          </div>

          {multi?.updated_at && (
            <p className="text-[10px] text-slate-400 text-right pt-0.5">
              {new Date(multi.updated_at).toLocaleDateString("ko-KR")}
            </p>
          )}
        </div>
      ) : (
        <div className="text-xs text-slate-400">데이터 대기 중</div>
      )}
    </div>
  );
}

// ── Leaders Section ───────────────────────────────────────────
function LeadersSection({
  title,
  leaders,
  signals,
  loading,
  flagEmoji,
}: {
  title: string;
  leaders: MarketLeaderItem[];
  signals: Map<string, MultiSignalItem>;
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
            <MultiSignalCard
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

// ── Main Page ─────────────────────────────────────────────────
export default function SignalPage() {
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [inputValue, setInputValue] = useState("");

  const [krLeaders, setKrLeaders] = useState<MarketLeaderItem[]>([]);
  const [usLeaders, setUsLeaders] = useState<MarketLeaderItem[]>([]);
  const [leadersLoading, setLeadersLoading] = useState(false);

  const [leaderSignals, setLeaderSignals] = useState<Map<string, MultiSignalItem>>(new Map());
  const [watchlistSignals, setWatchlistSignals] = useState<Map<string, MultiSignalItem>>(new Map());
  const [signalsLoading, setSignalsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);

  useEffect(() => {
    setWatchlist(loadWatchlist());
  }, []);

  const loadLeaders = useCallback(async () => {
    setLeadersLoading(true);
    try {
      const [kr, us] = await Promise.allSettled([
        getMarketLeaders("kr"),
        getMarketLeaders("us"),
      ]);
      if (kr.status === "fulfilled") setKrLeaders(kr.value.all_leaders);
      if (us.status === "fulfilled") setUsLeaders(us.value.all_leaders);
    } catch (e) {
      console.error("선도주 로드 실패:", e);
    } finally {
      setLeadersLoading(false);
    }
  }, []);

  useEffect(() => {
    loadLeaders();
  }, [loadLeaders]);

  const refresh = useCallback(async (forceRefresh = false) => {
    const leaderCodes = [
      ...krLeaders.map((l) => l.code),
      ...usLeaders.map((l) => l.code),
    ];
    const allSymbols = [...new Set([...leaderCodes, ...watchlist])];
    const leaderSet = new Set(leaderCodes);

    if (allSymbols.length === 0) return;
    setSignalsLoading(true);
    setError(null);
    setLeaderSignals(new Map());
    setWatchlistSignals(new Map());

    try {
      for (let i = 0; i < allSymbols.length; i += BATCH_SIZE) {
        const batch = allSymbols.slice(i, i + BATCH_SIZE);
        const res = await getMultiSignals(batch, forceRefresh);

        setLeaderSignals((prev) => {
          const m = new Map(prev);
          for (const item of res.signals) {
            if (leaderSet.has(item.symbol)) m.set(item.symbol, item);
          }
          return m;
        });
        setWatchlistSignals((prev) => {
          const m = new Map(prev);
          for (const item of res.signals) {
            if (watchlist.includes(item.symbol)) m.set(item.symbol, item);
          }
          return m;
        });
      }
      setLastRefreshed(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "신호 조회 실패");
    } finally {
      setSignalsLoading(false);
    }
  }, [krLeaders, usLeaders, watchlist]);

  useEffect(() => {
    if (krLeaders.length > 0 || usLeaders.length > 0) {
      refresh(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [krLeaders, usLeaders]);

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

  const goldenCount = useMemo(
    () =>
      [...leaderSignals.values()].filter((s) => s.signals?.macd?.is_golden === true).length,
    [leaderSignals],
  );

  const hasData = leaderSignals.size > 0 || watchlistSignals.size > 0;

  const downloadCSV = useCallback(() => {
    const headers = [
      "Market", "Symbol", "Name", "Price",
      "MACD%", "MACD State", "MA20/60%", "RSI",
      "Env%", "Env Price", "BB%", "BB Price", "STARC%", "STARC Price",
      "Updated",
    ];

    const fmt = (v: number | undefined, d = 2) =>
      v == null || isNaN(v) ? "" : v.toFixed(d);

    const rows: string[][] = [];

    const addRow = (
      market: string,
      code: string,
      fallbackName: string,
      item: MultiSignalItem | undefined,
    ) => {
      const isUs = /^[A-Za-z]/.test(code);
      const price = item?.current_price;
      const priceStr =
        price == null ? "" :
        isUs ? `$${price.toFixed(2)}` : `₩${Math.round(price)}`;
      const s = item?.signals;
      rows.push([
        market, code, item?.name || fallbackName, priceStr,
        s ? fmt(s.macd.gap_pct, 3) : "",
        s ? (s.macd.is_golden ? "Golden" : "Dead") : "",
        s ? fmt(s.ma_cross.gap_pct, 3) : "",
        s ? fmt(s.rsi.value, 1) : "",
        s ? fmt(s.envelope.gap_pct, 3) : "",
        s ? fmt(s.envelope.gap_price, 2) : "",
        s ? fmt(s.bollinger.gap_pct, 3) : "",
        s ? fmt(s.bollinger.gap_price, 2) : "",
        s ? fmt(s.starc.gap_pct, 3) : "",
        s ? fmt(s.starc.gap_price, 2) : "",
        item?.updated_at
          ? new Date(item.updated_at).toLocaleDateString("ko-KR")
          : "",
      ]);
    };

    for (const l of krLeaders)
      addRow("KR", l.code, l.name, leaderSignals.get(l.code));
    for (const l of usLeaders)
      addRow("US", l.code, l.name, leaderSignals.get(l.code));
    for (const sym of watchlist)
      addRow("관심", sym, sym, watchlistSignals.get(sym));

    const csv = [
      headers.join(","),
      ...rows.map((r) =>
        r.map((c) => `"${c.replace(/"/g, '""')}"`).join(","),
      ),
    ].join("\n");

    const blob = new Blob(["﻿" + csv], {
      type: "text/csv;charset=utf-8;",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `신호알림_${new Date().toISOString().slice(0, 10)}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [krLeaders, usLeaders, watchlist, leaderSignals, watchlistSignals]);

  return (
    <div className="max-w-screen-2xl mx-auto px-4 py-8">
      {/* 페이지 헤더 */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
          <Bell className="w-6 h-6 text-kis-blue" />
          신호 알림
        </h1>
        <p className="text-slate-600 dark:text-slate-400 mt-1">
          MACD 크로스, MA20/60, RSI, Envelope / BB / STARC 밴드 거리를 한눈에 확인하세요
        </p>
      </div>

      <div className="grid xl:grid-cols-[280px_1fr] gap-6">
        {/* 왼쪽: 사이드바 */}
        <div className="space-y-4">
          {/* 관심 종목 */}
          <div className="card">
            <h3 className="font-semibold text-slate-900 dark:text-white mb-3 text-sm">
              관심 종목 추가
            </h3>
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
            onClick={() => refresh(true)}
            disabled={signalsLoading || (krLeaders.length === 0 && usLeaders.length === 0)}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 rounded-xl font-medium text-sm transition-all",
              !signalsLoading
                ? "bg-kis-blue hover:bg-kis-blue-dark text-white"
                : "bg-slate-200 text-slate-400 cursor-not-allowed",
            )}
          >
            {signalsLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            {signalsLoading ? "가져오는 중..." : "최신 데이터 가져오기"}
          </button>

          {lastRefreshed && (
            <p className="text-xs text-slate-400 text-center">
              마지막: {lastRefreshed.toLocaleTimeString("ko-KR")}
            </p>
          )}

          {/* CSV 내보내기 */}
          <button
            onClick={downloadCSV}
            disabled={!hasData}
            className={cn(
              "w-full flex items-center justify-center gap-2 py-2.5 rounded-xl font-medium text-sm transition-all border",
              hasData
                ? "border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-700"
                : "border-slate-100 dark:border-slate-800 text-slate-300 dark:text-slate-600 cursor-not-allowed",
            )}
          >
            <Download className="w-4 h-4" />
            CSV 내보내기
          </button>

          {/* 범례 */}
          <div className="card text-xs text-slate-500 space-y-3">
            <p className="font-semibold text-slate-700 dark:text-slate-300">읽는 법</p>

            <div className="space-y-1">
              <p className="font-medium text-slate-600 dark:text-slate-400">MACD</p>
              <div className="flex items-center gap-2">
                <span className="font-mono text-emerald-500">+0.3% Golden</span>
                <span>MACD &gt; 시그널 (상승)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-red-400">-0.5% Dead</span>
                <span>MACD &lt; 시그널 (하락)</span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="font-medium text-slate-600 dark:text-slate-400">MA20/60</p>
              <div className="flex items-center gap-2">
                <span className="font-mono text-emerald-500">+1.2%</span>
                <span>20일선 위 (상승 추세)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-slate-400">-0.8%</span>
                <span>20일선 아래 (하락 추세)</span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="font-medium text-slate-600 dark:text-slate-400">RSI</p>
              <div className="flex items-center gap-2">
                <span className="font-mono text-emerald-500">≤ 30</span>
                <span>과매도</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-red-400">≥ 70</span>
                <span>과매수</span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="font-medium text-slate-600 dark:text-slate-400">밴드 (Env / BB / STARC)</p>
              <div className="flex items-center gap-2">
                <span className="font-mono text-emerald-500">+0.8%</span>
                <span>상단 돌파 상태</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-amber-500">-1.5%</span>
                <span>상단까지 1.5% 남음</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-slate-400">-5.0%</span>
                <span>상단까지 5.0% 남음</span>
              </div>
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
                중 MACD Golden{" "}
                <span className="font-semibold text-emerald-600">{goldenCount}개</span>
              </span>
              {signalsLoading && <Loader2 className="w-4 h-4 animate-spin text-slate-400" />}
            </div>
          )}

          {/* 한국·미국 선도주 */}
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

          {/* 관심 종목 */}
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
                    <MultiSignalCard
                      key={sym}
                      item={s ?? { symbol: sym, name: sym }}
                      loading={signalsLoading && !s}
                    />
                  );
                })}
              </div>
            </div>
          )}

          {/* 빈 상태 */}
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
