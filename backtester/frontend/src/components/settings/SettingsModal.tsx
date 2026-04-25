"use client";
import { useState, useEffect } from "react";
import { X, RefreshCw, Database, Shield, Clock, TrendingUp } from "lucide-react";
import { useAuth } from "@/hooks";
import { getMasterStatus, collectMasterFiles } from "@/lib/api/symbols";
import { getMarketLeadersStatus, triggerMarketLeadersUpdate } from "@/lib/api/market_leaders";
import type { MasterStatus } from "@/types/symbols";
import type { MarketLeadersStatus } from "@/types/market_leaders";
import type { AuthMode } from "@/types/auth";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function SettingsModal({ isOpen, onClose }: SettingsModalProps) {
  const { status, isLoading, error, login, switchMode } = useAuth();
  const [masterStatus, setMasterStatus] = useState<MasterStatus | null>(null);
  const [isCollecting, setIsCollecting] = useState(false);
  const [cooldownTimer, setCooldownTimer] = useState(0);
  const [mlStatus, setMlStatus] = useState<MarketLeadersStatus | null>(null);
  const [isUpdatingML, setIsUpdatingML] = useState(false);
  const [mlUpdateMsg, setMlUpdateMsg] = useState<string | null>(null);
  const [mlMarket, setMlMarket] = useState<"kr" | "us">("kr");
  const [mlCapLimit, setMlCapLimit] = useState(75);
  const [mlRevenueLimit, setMlRevenueLimit] = useState(75);
  const [mlAmountLimit, setMlAmountLimit] = useState(150);
  const [mlForceUpdate, setMlForceUpdate] = useState(false);

  useEffect(() => {
    if (isOpen) {
      fetchMasterStatus();
      fetchMLStatus();
    }
  }, [isOpen]);

  // 서버에서 받은 쿨다운 값으로 초기화
  useEffect(() => {
    if (status.cooldown_remaining && status.cooldown_remaining > 0) {
      setCooldownTimer(status.cooldown_remaining);
    }
  }, [status.cooldown_remaining]);

  // 1초마다 감소
  useEffect(() => {
    if (cooldownTimer > 0) {
      const interval = setInterval(() => {
        setCooldownTimer((prev) => Math.max(0, prev - 1));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [cooldownTimer]);

  const fetchMasterStatus = async () => {
    try {
      setMasterStatus(await getMasterStatus());
    } catch {
      // 상태 조회 실패 시 무시
    }
  };

  const fetchMLStatus = async () => {
    try {
      setMlStatus(await getMarketLeadersStatus());
    } catch {
      // 무시
    }
  };

  const handleMLUpdate = async () => {
    setIsUpdatingML(true);
    setMlUpdateMsg(null);
    try {
      const res = await triggerMarketLeadersUpdate({
        market: mlMarket,
        cap_limit: mlCapLimit,
        revenue_limit: mlRevenueLimit,
        amount_limit: mlAmountLimit,
        force: mlForceUpdate,
      });
      setMlUpdateMsg(res.message);
      if (res.status === "started") {
        setMlStatus((prev) => prev ? { ...prev, is_updating: true } : prev);
        // 완료될 때까지 폴링
        const interval = setInterval(async () => {
          try {
            const s = await getMarketLeadersStatus(mlMarket);
            setMlStatus(s);
            if (!s.is_updating) {
              clearInterval(interval);
              setMlUpdateMsg("업데이트가 완료되었습니다.");
            }
          } catch {
            clearInterval(interval);
          }
        }, 5000);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "업데이트 실패";
      setMlUpdateMsg(msg.includes("401") ? "KIS API 인증 후 업데이트를 실행하세요." : msg);
    } finally {
      setIsUpdatingML(false);
    }
  };

  const handleCollect = async () => {
    setIsCollecting(true);
    try {
      await collectMasterFiles();
      await fetchMasterStatus();
      window.dispatchEvent(new Event("symbols-collected"));
    } catch {
      // 수집 실패 시 무시
    } finally {
      setIsCollecting(false);
    }
  };

  const handleLogin = async (mode: AuthMode) => {
    await login(mode);
  };

  const handleSwitchMode = async () => {
    const newMode = status.mode === "vps" ? "prod" : "vps";
    const success = await switchMode(newMode);
    if (success) {
      setCooldownTimer(60);
    }
  };

  if (!isOpen) return null;

  const canSwitch = status.can_switch_mode !== false && cooldownTimer === 0;
  const isVps = status.mode === "vps";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="relative w-full max-w-md mx-4 bg-white dark:bg-slate-900 rounded-xl shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 dark:border-slate-700">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            설정
          </h2>
          <button
            onClick={onClose}
            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5 text-slate-600 dark:text-slate-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-6">
          {/* 인증 및 모드 섹션 */}
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
              <Shield className="w-4 h-4" />
              인증 및 모드
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg space-y-3">
              {/* 인증 상태 */}
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-600 dark:text-slate-400">
                  인증 상태
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-bold ${
                    status.authenticated
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                      : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                  }`}
                >
                  {status.authenticated ? "인증됨" : "미인증"}
                </span>
              </div>

              {/* 현재 모드 */}
              {status.authenticated && (
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600 dark:text-slate-400">
                    현재 모드
                  </span>
                  <span
                    className={`px-2 py-0.5 rounded text-xs font-bold ${
                      isVps
                        ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                        : "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                    }`}
                  >
                    {status.mode_display || (isVps ? "모의투자" : "실전투자")}
                  </span>
                </div>
              )}

              {/* 쿨다운 바 */}
              {cooldownTimer > 0 && (
                <div className="flex items-center gap-2 p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                  <Clock className="w-4 h-4 text-amber-600 dark:text-amber-400" />
                  <span className="text-sm text-amber-600 dark:text-amber-400 font-medium">
                    쿨다운: {cooldownTimer}초 남음
                  </span>
                  <div className="flex-1 h-1 bg-amber-200 dark:bg-amber-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-amber-500 transition-all duration-1000"
                      style={{ width: `${(cooldownTimer / 60) * 100}%` }}
                    />
                  </div>
                </div>
              )}

              {/* 모의/실전 버튼 */}
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={() => {
                    if (!status.authenticated) {
                      handleLogin("vps");
                    } else if (!isVps && canSwitch) {
                      handleSwitchMode();
                    }
                  }}
                  disabled={
                    isLoading ||
                    (status.authenticated && isVps) ||
                    (status.authenticated && !isVps && !canSwitch)
                  }
                  className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    isVps && status.authenticated
                      ? "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400 ring-2 ring-yellow-500 cursor-default"
                      : isLoading
                        ? "bg-slate-100 dark:bg-slate-700 opacity-50"
                        : "bg-slate-100 dark:bg-slate-700 hover:bg-yellow-50 dark:hover:bg-yellow-900/20"
                  }`}
                >
                  {isLoading ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <span className="w-2 h-2 rounded-full bg-yellow-500" />
                      모의투자
                    </>
                  )}
                </button>
                <button
                  onClick={() => {
                    if (!status.authenticated) {
                      handleLogin("prod");
                    } else if (isVps && canSwitch) {
                      handleSwitchMode();
                    }
                  }}
                  disabled={
                    isLoading ||
                    (status.authenticated && !isVps) ||
                    (status.authenticated && isVps && !canSwitch)
                  }
                  className={`py-2 px-3 rounded-lg text-sm font-medium transition-colors flex items-center justify-center gap-2 ${
                    !isVps && status.authenticated
                      ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 ring-2 ring-green-500 cursor-default"
                      : isLoading
                        ? "bg-slate-100 dark:bg-slate-700 opacity-50"
                        : "bg-slate-100 dark:bg-slate-700 hover:bg-green-50 dark:hover:bg-green-900/20"
                  }`}
                >
                  {isLoading ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <>
                      <span className="w-2 h-2 rounded-full bg-green-500" />
                      실전투자
                    </>
                  )}
                </button>
              </div>

              {error && (
                <div className="px-2 py-1.5 rounded bg-red-50 dark:bg-red-900/20 text-xs text-red-600 dark:text-red-400">
                  {error}
                </div>
              )}

              <p className="text-xs text-slate-500 dark:text-slate-400 text-center">
                모드 전환은 1분에 1회만 가능합니다
              </p>
            </div>
          </section>

          {/* 종목 마스터파일 섹션 */}
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
              <Database className="w-4 h-4" />
              종목 마스터파일
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg space-y-3">
              {masterStatus ? (
                <>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-600 dark:text-slate-400">
                        코스피
                      </span>
                      <span className="font-mono">
                        {masterStatus.kospi_count.toLocaleString()}개
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-600 dark:text-slate-400">
                        코스닥
                      </span>
                      <span className="font-mono">
                        {masterStatus.kosdaq_count.toLocaleString()}개
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-slate-600 dark:text-slate-400">
                      총 종목 수
                    </span>
                    <span className="font-mono font-bold">
                      {masterStatus.total_count.toLocaleString()}개
                    </span>
                  </div>
                  {masterStatus.kospi_updated && (
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      마지막 업데이트:{" "}
                      {new Date(masterStatus.kospi_updated).toLocaleString()}
                    </div>
                  )}
                  {masterStatus.needs_update && (
                    <div className="text-xs text-amber-600 dark:text-amber-400">
                      업데이트가 필요합니다
                    </div>
                  )}
                </>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">
                  로딩 중...
                </div>
              )}
              <button
                onClick={handleCollect}
                disabled={isCollecting}
                className="w-full py-2 px-4 rounded-lg text-sm font-medium bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors disabled:opacity-50"
              >
                {isCollecting ? (
                  <span className="flex items-center justify-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    수집 중...
                  </span>
                ) : (
                  "마스터파일 수집"
                )}
              </button>
            </div>
          </section>

          {/* 시장 선도주 섹션 */}
          <section className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-700 dark:text-slate-300">
              <TrendingUp className="w-4 h-4 text-amber-500" />
              시장 선도주
            </div>
            <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg space-y-3">
              <p className="text-xs text-slate-500 dark:text-slate-400">
                시가총액·매출·거래대금 기준으로 선도주를 선정합니다. 한국: KIS API, 미국: KIS+yfinance. 인증 후 사용 가능.
              </p>
              {/* 시장 + limit 설정 */}
              <div className="space-y-2">
                {/* 시장 선택 */}
                <div className="flex gap-1 p-0.5 bg-slate-200 dark:bg-slate-700 rounded-md">
                  {(["kr", "us"] as const).map((m) => (
                    <button
                      key={m}
                      onClick={() => setMlMarket(m)}
                      className={`flex-1 py-1 text-xs rounded transition-colors ${
                        mlMarket === m
                          ? "bg-white dark:bg-slate-600 text-slate-900 dark:text-slate-100 font-medium shadow-sm"
                          : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300"
                      }`}
                    >
                      {m === "kr" ? "한국 (KR)" : "미국 (US)"}
                    </button>
                  ))}
                </div>
                {/* 순위 입력 */}
                <div className="grid grid-cols-3 gap-2">
                  <div className="space-y-1">
                    <label className="text-xs text-slate-500 dark:text-slate-400">시가총액</label>
                    <input
                      type="number" min={1} max={500}
                      value={mlCapLimit}
                      onChange={(e) => setMlCapLimit(Math.max(1, Math.min(500, Number(e.target.value))))}
                      className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-slate-500 dark:text-slate-400">
                      매출{mlMarket === "us" ? " (yfinance)" : ""}
                    </label>
                    <input
                      type="number" min={1} max={500}
                      value={mlRevenueLimit}
                      onChange={(e) => setMlRevenueLimit(Math.max(1, Math.min(500, Number(e.target.value))))}
                      className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-slate-500 dark:text-slate-400">거래대금</label>
                    <input
                      type="number" min={1} max={1000}
                      value={mlAmountLimit}
                      onChange={(e) => setMlAmountLimit(Math.max(1, Math.min(1000, Number(e.target.value))))}
                      className="w-full px-2 py-1 text-xs border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-1 focus:ring-amber-400"
                    />
                  </div>
                </div>
                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={mlForceUpdate}
                    onChange={(e) => setMlForceUpdate(e.target.checked)}
                    className="w-3.5 h-3.5 accent-amber-500"
                  />
                  <span className="text-xs text-slate-600 dark:text-slate-400">
                    강제 업데이트 (오늘 이미 업데이트된 경우에도 재실행)
                  </span>
                </label>
              </div>
              {mlStatus && (
                <div className="space-y-1.5 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-600 dark:text-slate-400">전체 선도주</span>
                    <span className="font-mono">{mlStatus.counts.all_leaders ?? 0}개</span>
                  </div>
                  {mlStatus.last_updated && (
                    <div className="text-xs text-slate-500 dark:text-slate-400">
                      마지막 업데이트: {new Date(mlStatus.last_updated).toLocaleString()}
                    </div>
                  )}
                  {mlStatus.needs_update && !mlStatus.is_updating && (
                    <div className="text-xs text-amber-600 dark:text-amber-400">
                      업데이트가 필요합니다
                    </div>
                  )}
                  {mlStatus.is_updating && (
                    <div className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
                      <RefreshCw className="w-3 h-3 animate-spin" />
                      업데이트 진행 중...
                    </div>
                  )}
                </div>
              )}
              {mlUpdateMsg && (
                <div className="text-xs text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 px-2 py-1.5 rounded">
                  {mlUpdateMsg}
                </div>
              )}
              <button
                onClick={handleMLUpdate}
                disabled={isUpdatingML || mlStatus?.is_updating}
                className="w-full py-2 px-4 rounded-lg text-sm font-medium bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400 hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors disabled:opacity-50"
              >
                {isUpdatingML || mlStatus?.is_updating ? (
                  <span className="flex items-center justify-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    업데이트 중...
                  </span>
                ) : (
                  "시장 선도주 업데이트"
                )}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default SettingsModal;
