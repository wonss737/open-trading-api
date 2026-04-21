"use client";

import { useState, useEffect, useCallback } from "react";
import { TrendingUp, RefreshCw, Loader2, AlertTriangle, CheckSquare, Plus } from "lucide-react";
import { getMarketLeaders, getMarketLeadersStatus, triggerMarketLeadersUpdate } from "@/lib/api/market_leaders";
import type { MarketLeaderItem, MarketLeadersStatus, MarketType } from "@/types/market_leaders";
import { cn } from "@/lib/utils";

type RankTab = "all" | "market_cap" | "trading_amount" | "revenue";

interface TabConfig {
  id: RankTab;
  label: string;
}

const KR_TABS: TabConfig[] = [
  { id: "all", label: "전체" },
  { id: "market_cap", label: "시가총액 150" },
  { id: "trading_amount", label: "거래대금 300" },
  { id: "revenue", label: "매출 150" },
];

const US_TABS: TabConfig[] = [
  { id: "all", label: "전체" },
  { id: "market_cap", label: "시가총액 150" },
  { id: "trading_amount", label: "거래대금 300" },
];

const REASON_COLORS: Record<string, string> = {
  시가총액: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  거래대금: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  매출: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
};

interface ListData {
  all: MarketLeaderItem[];
  market_cap: MarketLeaderItem[];
  trading_amount: MarketLeaderItem[];
  revenue: MarketLeaderItem[];
}

const EMPTY_LIST: ListData = { all: [], market_cap: [], trading_amount: [], revenue: [] };

interface MarketLeadersPanelProps {
  selectedStocks: string[];
  onAddStocks: (codes: string[], names: Record<string, string>) => void;
}

export function MarketLeadersPanel({ selectedStocks, onAddStocks }: MarketLeadersPanelProps) {
  const [market, setMarket] = useState<MarketType>("kr");
  const [activeTab, setActiveTab] = useState<RankTab>("all");
  const [items, setItems] = useState<Record<MarketType, ListData>>({ kr: EMPTY_LIST, us: EMPTY_LIST });
  const [status, setStatus] = useState<Record<MarketType, MarketLeadersStatus | null>>({ kr: null, us: null });
  const [isLoading, setIsLoading] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);

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
            all: data.all_leaders,
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

  // 시장 변경 시 데이터 로드
  useEffect(() => {
    loadData(market);
  }, [market, loadData]);

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
          await loadData(market);
        }
      } catch {
        clearInterval(interval);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [status, market, loadData]);

  const handleMarketChange = (m: MarketType) => {
    setMarket(m);
    setActiveTab("all");
    setError(null);
    setUpdateMessage(null);
  };

  const handleUpdate = useCallback(async () => {
    setIsUpdating(true);
    setUpdateMessage(null);
    setError(null);
    try {
      const res = await triggerMarketLeadersUpdate(market);
      setUpdateMessage(res.message);
      setStatus((prev) => ({ ...prev, [market]: prev[market] ? { ...prev[market]!, is_updating: true } : null }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "업데이트 실패";
      setError(msg.includes("401") ? "KIS API 인증 후 업데이트를 실행하세요." : msg);
    } finally {
      setIsUpdating(false);
    }
  }, [market]);

  const currentStatus = status[market];
  const currentItems = items[market][activeTab];
  const tabs = market === "kr" ? KR_TABS : US_TABS;

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

  const notAddedCount = currentItems.filter((s) => !selectedStocks.includes(s.code)).length;
  const hasData = items[market].all.length > 0;

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

      {/* 한국 / 미국 마켓 선택 */}
      <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg">
        <button
          onClick={() => handleMarketChange("kr")}
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
      {(updateMessage || currentStatus?.is_updating) && (
        <div className="flex items-center gap-2 px-3 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
          <Loader2 className="w-3 h-3 animate-spin flex-shrink-0" />
          {currentStatus?.is_updating
            ? market === "kr"
              ? "업데이트 중... (매출 조회 포함 시 수 분 소요)"
              : "업데이트 중... (NYS·NAS·AMS 합산 조회)"
            : updateMessage}
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

      {/* US 매출 미지원 안내 */}
      {market === "us" && hasData && activeTab === "revenue" && items.us.revenue.length === 0 && (
        <div className="px-3 py-2 text-xs text-slate-500 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg">
          미국 주식 매출 데이터는 KIS API에서 제공하지 않습니다.
        </div>
      )}

      {/* 탭 + 목록 */}
      {hasData && (
        <>
          {/* 탭 */}
          <div className="flex gap-1 flex-wrap">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={cn(
                  "px-2.5 py-1 text-xs rounded-md transition-colors",
                  activeTab === tab.id
                    ? "bg-amber-500 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700"
                )}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 전체 추가 버튼 */}
          {notAddedCount > 0 && currentItems.length > 0 && (
            <button
              onClick={handleAddAll}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 border border-amber-200 dark:border-amber-800 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/30 transition-colors"
            >
              <CheckSquare className="w-3.5 h-3.5" />
              전체 추가 ({notAddedCount}개)
            </button>
          )}

          {/* 종목 목록 */}
          {isLoading ? (
            <div className="flex justify-center py-4">
              <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
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
