"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { TrendingUp, RefreshCw, Loader2, AlertTriangle, CheckSquare, Plus, Trash2 } from "lucide-react";
import { getMarketLeaders, getMarketLeadersStatus, triggerMarketLeadersUpdate, getMarketLeadersDefaults } from "@/lib/api/market_leaders";
import type { MarketLeaderItem, MarketLeadersStatus, MarketType } from "@/types/market_leaders";
import { cn } from "@/lib/utils";

type FilterKey = "market_cap" | "trading_amount" | "revenue";

interface FilterConfig {
  id: FilterKey;
  label: string;
  color: string;
  activeClass: string;
}

const makeKrFilters = (capLimit: number, revenueLimit: number, amountLimit: number): FilterConfig[] => [
  { id: "market_cap",     label: "시가총액",   color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",     activeClass: "bg-blue-500 text-white" },
  { id: "revenue",        label: "매출",       color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400", activeClass: "bg-purple-500 text-white" },
  { id: "trading_amount", label: "거래대금",   color: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",  activeClass: "bg-green-500 text-white" },
];

const makeUsFilters = (capLimit: number, revenueLimit: number, amountLimit: number): FilterConfig[] => [
  { id: "market_cap",     label: "시가총액",   color: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",     activeClass: "bg-blue-500 text-white" },
  { id: "revenue",        label: "매출",       color: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400", activeClass: "bg-purple-500 text-white" },
  { id: "trading_amount", label: "거래대금",   color: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",  activeClass: "bg-green-500 text-white" },
];

const REASON_COLORS: Record<string, string> = {
  시가총액: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  거래대금: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  매출: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

interface ListData {
  market_cap: MarketLeaderItem[];
  trading_amount: MarketLeaderItem[];
  revenue: MarketLeaderItem[];
}

const EMPTY_LIST: ListData = { market_cap: [], trading_amount: [], revenue: [] };

interface MarketLeadersPanelProps {
  selectedStocks: string[];
  onAddStocks: (codes: string[], names: Record<string, string>) => void;
  onRemoveStocks: (codes: string[]) => void;
}

export function MarketLeadersPanel({ selectedStocks, onAddStocks, onRemoveStocks }: MarketLeadersPanelProps) {
  const [market, setMarket] = useState<MarketType>("kr");
  // 토글된 필터 집합 — 비어 있으면 전체 합집합
  const [activeFilters, setActiveFilters] = useState<Set<FilterKey>>(new Set());
  const [items, setItems] = useState<Record<MarketType, ListData>>({ kr: EMPTY_LIST, us: EMPTY_LIST });
  const [status, setStatus] = useState<Record<MarketType, MarketLeadersStatus | null>>({ kr: null, us: null });
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);
  const [showLimitSettings, setShowLimitSettings] = useState(false);
  const [capLimit, setCapLimit] = useState(100);
  const [revenueLimit, setRevenueLimit] = useState(100);
  const [amountLimit, setAmountLimit] = useState(200);

  // 백엔드 DEFAULT 값으로 초기화
  useEffect(() => {
    getMarketLeadersDefaults()
      .then((d) => {
        setCapLimit(d.cap_limit);
        setRevenueLimit(d.revenue_limit);
        setAmountLimit(d.amount_limit);
      })
      .catch(() => {/* 실패 시 하드코딩 기본값 유지 */});
  }, []);  const [forceUpdate, setForceUpdate] = useState(false);
  const loadData = useCallback(async (m: MarketType) => {
    setIsLoading(true);
    setError(null);
    try {
      const [data, statusData] = await Promise.all([
        getMarketLeaders(m).catch(() => null),
        getMarketLeadersStatus(m),
      ]);
      setStatus((prev) => ({ ...prev, [m]: statusData }));
      if (data) {
        setItems((prev) => ({
          ...prev,
          [m]: {
            market_cap: data.by_market_cap,
            trading_amount: data.by_trading_amount,
            revenue: data.by_revenue,
          },
        }));
      }
    } catch {
      try {
        const statusData = await getMarketLeadersStatus(m);
        setStatus((prev) => ({ ...prev, [m]: statusData }));
      } catch {
        setError("서버 연결 오류");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => { loadData(market); }, [market, loadData]);

  // 업데이트 진행 중 폴링
  useEffect(() => {
    const cur = status[market];
    if (!cur?.is_updating) return;
    const interval = setInterval(async () => {
      try {
        const s = await getMarketLeadersStatus(market);
        setStatus((prev) => ({ ...prev, [market]: s }));
        if (!s.is_updating) {
          clearInterval(interval);
          setUpdateMessage(null);
          await loadData(market);
        }
      } catch {
        clearInterval(interval);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [status, market, loadData]);

  const handleMarketChange = (m: MarketType) => {
    // 반대 마켓에서 추가된 종목 제거
    const prevMarket = market;
    if (prevMarket !== m) {
      const prevItems = items[prevMarket];
      const prevAllCodes = new Set<string>([
        ...prevItems.market_cap.map((i) => i.code),
        ...prevItems.trading_amount.map((i) => i.code),
        ...prevItems.revenue.map((i) => i.code),
      ]);
      const toRemove = selectedStocks.filter((c) => prevAllCodes.has(c));
      if (toRemove.length > 0) {
        onRemoveStocks(toRemove);
      }
    }
    setMarket(m);
    setActiveFilters(new Set());
    setError(null);
    setUpdateMessage(null);
  };

  const toggleFilter = (key: FilterKey) => {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const handleUpdate = useCallback(async () => {
    setIsUpdating(true);
    setUpdateMessage(null);
    setError(null);
    try {
      const res = await triggerMarketLeadersUpdate({
        market,
        cap_limit: capLimit,
        revenue_limit: revenueLimit,
        amount_limit: amountLimit,
        force: forceUpdate,
      });
      if (res.status === "skipped") {
        setUpdateMessage(res.message);
        setTimeout(() => setUpdateMessage(null), 5000);
      } else {
        setUpdateMessage(null);
        setStatus((prev) => ({ ...prev, [market]: prev[market] ? { ...prev[market]!, is_updating: true } : null }));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "업데이트 실패";
      setError(msg.includes("401") ? "KIS API 인증 후 업데이트를 실행하세요." : msg);
    } finally {
      setIsUpdating(false);
    }
  }, [market, capLimit, revenueLimit, amountLimit, forceUpdate]);

  const filters = market === "kr"
    ? makeKrFilters(capLimit, revenueLimit, amountLimit)
    : makeUsFilters(capLimit, revenueLimit, amountLimit);

  // 교집합 계산: 필터 없으면 전체 합집합, 있으면 교집합
  const currentItems = useMemo<MarketLeaderItem[]>(() => {
    const cur = items[market];
    // limit에 따라 각 리스트를 먼저 슬라이싱
    const sliced: Record<FilterKey, MarketLeaderItem[]> = {
      market_cap:     cur.market_cap.slice(0, capLimit),
      trading_amount: cur.trading_amount.slice(0, amountLimit),
      revenue:        cur.revenue.slice(0, revenueLimit),
    };
    const allLists: MarketLeaderItem[][] = [];
    if (activeFilters.size === 0) {
      // 아무것도 선택 안 했을 때는 전체 합집합
      const seen = new Set<string>();
      const merged: MarketLeaderItem[] = [];
      for (const list of [sliced.market_cap, sliced.trading_amount, sliced.revenue]) {
        for (const item of list) {
          if (!seen.has(item.code)) { seen.add(item.code); merged.push(item); }
        }
      }
      return merged;
    }
    // 선택된 필터의 리스트 수집
    for (const key of activeFilters) {
      allLists.push(sliced[key]);
    }
    if (allLists.length === 0) return [];
    // 교집합: 첫 번째 리스트 기준, 나머지 모두에 code가 있는 항목만
    const [first, ...rest] = allLists;
    const restSets = rest.map((l) => new Set(l.map((i) => i.code)));
    return first.filter((item) => restSets.every((s) => s.has(item.code)));
  }, [items, market, activeFilters, capLimit, revenueLimit, amountLimit]);

  const currentStatus = status[market];
  const hasData = items[market].market_cap.length > 0 || items[market].trading_amount.length > 0;

  const handleAddAll = useCallback(() => {
    const newCodes = currentItems.map((s) => s.code).filter((c) => !selectedStocks.includes(c));
    if (newCodes.length === 0) return;
    const names: Record<string, string> = {};
    currentItems.forEach((s) => { names[s.code] = s.name; });
    onAddStocks(newCodes, names);
  }, [currentItems, selectedStocks, onAddStocks]);

  const handleAddOne = useCallback((item: MarketLeaderItem) => {
    if (selectedStocks.includes(item.code)) return;
    onAddStocks([item.code], { [item.code]: item.name });
  }, [selectedStocks, onAddStocks]);

  const handleRemoveAll = useCallback(() => {
    const codesToRemove = currentItems.map((s) => s.code).filter((c) => selectedStocks.includes(c));
    if (codesToRemove.length === 0) return;
    onRemoveStocks(codesToRemove);
  }, [currentItems, selectedStocks, onRemoveStocks]);

  const notAddedCount = currentItems.filter((s) => !selectedStocks.includes(s.code)).length;

  return (
    <div className="space-y-3">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-amber-500" />
          <span className="text-sm font-medium text-slate-700 dark:text-slate-300">시장 선도주</span>
          {currentStatus && !currentStatus.is_updating && (currentStatus.counts.all_leaders ?? 0) > 0 && (
            <span className="text-xs text-slate-400">({currentStatus.counts.all_leaders}개)</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {currentStatus?.last_updated && (
            <span className="text-xs text-slate-400">
              {new Date(currentStatus.last_updated).toLocaleDateString("ko-KR")}
            </span>
          )}
          <button
            onClick={() => setShowLimitSettings((v) => !v)}
            className={cn(
              "px-2 py-1 text-xs rounded-md transition-colors",
              showLimitSettings
                ? "bg-slate-200 text-slate-700 dark:bg-slate-600 dark:text-slate-200"
                : "bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-400 dark:hover:bg-slate-600"
            )}
            title="순위 기준 설정"
          >
            ⚙
          </button>
          <button
            onClick={handleUpdate}
            disabled={isUpdating || currentStatus?.is_updating}
            className={cn(
              "flex items-center gap-1 px-2 py-1 text-xs rounded-md transition-colors",
              isUpdating || currentStatus?.is_updating
                ? "bg-slate-100 text-slate-400 cursor-not-allowed"
                : "bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-900/20 dark:text-amber-400"
            )}
          >
            {isUpdating || currentStatus?.is_updating
              ? <Loader2 className="w-3 h-3 animate-spin" />
              : <RefreshCw className="w-3 h-3" />}
            업데이트
          </button>
        </div>
      </div>

      {/* 순위 기준 설정 패널 */}
      {showLimitSettings && (
        <div className="p-3 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-lg space-y-2">
          <p className="text-xs font-medium text-slate-600 dark:text-slate-400">순위 기준 (다음 업데이트 시 적용)</p>
          <div className="grid grid-cols-3 gap-2">
            <div className="space-y-1">
              <label className="text-xs text-slate-500 dark:text-slate-400">시가총액</label>
              <input
                type="number"
                min={1}
                max={500}
                value={capLimit}
                onChange={(e) => setCapLimit(Math.max(1, Math.min(500, Number(e.target.value))))}
                className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-slate-500 dark:text-slate-400">
                매출{market === "us" ? " (yfinance)" : ""}
              </label>
              <input
                type="number"
                min={1}
                max={500}
                value={revenueLimit}
                onChange={(e) => setRevenueLimit(Math.max(1, Math.min(500, Number(e.target.value))))}
                className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-slate-500 dark:text-slate-400">거래대금</label>
              <input
                type="number"
                min={1}
                max={1000}
                value={amountLimit}
                onChange={(e) => setAmountLimit(Math.max(1, Math.min(1000, Number(e.target.value))))}
                className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
            </div>
          </div>
          <label className="flex items-center gap-2 pt-1 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={forceUpdate}
              onChange={(e) => setForceUpdate(e.target.checked)}
              className="w-3.5 h-3.5 accent-amber-500"
            />
            <span className="text-xs text-slate-600 dark:text-slate-400">
              강제 업데이트 (오늘 이미 업데이트된 경우에도 재실행)
            </span>
          </label>
        </div>
      )}

      {/* 한국 / 미국 마켓 선택 */}
      <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg">
        <button
          onClick={() => handleMarketChange("kr")}
          title={market === "us" ? "미국 탭에서 추가된 종목이 삭제됩니다" : undefined}
          className={cn(
            "flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors",
            market === "kr"
              ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
              : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          )}
        >
          🇰🇷 한국 (KOSPI)
        </button>
        <button
          onClick={() => handleMarketChange("us")}
          title={market === "kr" ? "한국 탭에서 추가된 종목이 삭제됩니다" : undefined}
          className={cn(
            "flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors",
            market === "us"
              ? "bg-white dark:bg-slate-700 text-slate-900 dark:text-white shadow-sm"
              : "text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
          )}
        >
          🇺🇸 미국 (NAS·NYSE·AMEX)
        </button>
      </div>

      {/* 업데이트 진행 메시지 */}
      {currentStatus?.is_updating && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
          <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
          {market === "kr"
            ? "업데이트 중... (KIS API 매출 조회 포함, 수 분 소요)"
            : "업데이트 중... (NYS·NAS·AMS 시세 + yfinance 매출 조회, 수 분 소요)"}
        </div>
      )}
      {updateMessage && !currentStatus?.is_updating && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg">
          {updateMessage}
        </div>
      )}

      {/* 에러 */}
      {error && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
          <AlertTriangle className="w-3 h-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* 데이터 없음 안내 */}
      {!isLoading && !hasData && !currentStatus?.is_updating && !error && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg">
          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0 text-amber-500" />
          데이터가 없습니다. KIS API 인증 후 업데이트를 실행하세요.
        </div>
      )}

      {/* 필터 토글 + 목록 */}
      {hasData && (
        <>
          {/* 필터 토글 버튼 — 다중 선택, 교집합 */}
          <div className="space-y-1.5">
            <div className="flex gap-1.5 flex-wrap">
              {filters.map((f) => {
                const active = activeFilters.has(f.id);
                return (
                  <button
                    key={f.id}
                    onClick={() => toggleFilter(f.id)}
                    className={cn(
                      "px-2.5 py-1 text-xs rounded-md font-medium transition-colors border",
                      active
                        ? `${f.activeClass} border-transparent`
                        : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border-slate-200 dark:border-slate-700 hover:bg-slate-200 dark:hover:bg-slate-700"
                    )}
                  >
                    {f.label}
                  </button>
                );
              })}
            </div>
            {/* 교집합 설명 */}
            <p className="text-xs text-slate-400 dark:text-slate-500">
              {activeFilters.size === 0
                ? `전체 합산 ${currentItems.length}개`
                : activeFilters.size === 1
                ? `${currentItems.length}개`
                : `교집합 ${currentItems.length}개 (선택된 조건 모두 해당)`}
            </p>
          </div>

          {/* 전체 추가 / 전체 삭제 버튼 */}
          {currentItems.length > 0 && (
            <div className="flex gap-2">
              {notAddedCount > 0 && (
                <button
                  onClick={handleAddAll}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
                >
                  <CheckSquare className="w-3.5 h-3.5" />
                  전체 추가 ({notAddedCount}개)
                </button>
              )}
              {currentItems.some((s) => selectedStocks.includes(s.code)) && (
                <button
                  onClick={handleRemoveAll}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  전체 삭제 ({currentItems.filter((s) => selectedStocks.includes(s.code)).length}개)
                </button>
              )}
            </div>
          )}

          {/* 종목 목록 */}
          {isLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
            </div>
          ) : currentItems.length === 0 ? (
            <div className="px-3 py-4 text-xs text-center text-slate-400 dark:text-slate-500">
              선택된 조건의 교집합이 없습니다.
            </div>
          ) : (
            <div className="max-h-48 overflow-y-auto space-y-1 pr-1">
              {currentItems.map((item) => {
                const isSelected = selectedStocks.includes(item.code);
                return (
                  <div
                    key={item.code}
                    className={cn(
                      "flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors",
                      isSelected
                        ? "bg-primary/10 opacity-60"
                        : "bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700"
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono text-xs text-slate-500 w-16 flex-shrink-0 truncate">
                        {item.code}
                      </span>
                      <span className="text-slate-800 dark:text-slate-200 truncate text-xs">
                        {item.name}
                      </span>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0 ml-2">
                      {item.reason.map((r) => (
                        <span
                          key={r}
                          className={cn(
                            "text-xs px-1 py-0.5 rounded",
                            REASON_COLORS[r] || "bg-slate-100 text-slate-600"
                          )}
                        >
                          {r}
                        </span>
                      ))}
                      <button
                        onClick={() => handleAddOne(item)}
                        disabled={isSelected}
                        className={cn(
                          "p-1 rounded transition-colors",
                          isSelected
                            ? "text-slate-300 cursor-default"
                            : "text-slate-400 hover:text-primary hover:bg-primary/10"
                        )}
                      >
                        <Plus className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default MarketLeadersPanel;
