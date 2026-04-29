"""Signal 알림 API Routes.

각 종목에 대해 매수/매도 신호의 발동 여부 및 임박도(%)를 계산합니다.
"""

import json
import logging
import numpy as np
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Query

from kis_backtest.lean.project_manager import LeanProjectManager

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================
# 지표 계산 (pandas)
# ============================================================

def _compute_macd(close: pd.Series, fast: int, slow: int, signal: int):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line


def _compute_sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def _compute_atr(df: pd.DataFrame, period: int) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
    """Wilder's RSI — SMA-seeded first window, correct NaN/zero-loss handling."""
    delta = close.diff()
    gain_arr = delta.clip(lower=0).to_numpy(dtype=float)
    loss_arr = (-delta.clip(upper=0)).to_numpy(dtype=float)
    n = len(close)

    avg_g = np.full(n, float("nan"))
    avg_l = np.full(n, float("nan"))

    if n > period:
        # Seed with simple average of first window
        avg_g[period] = gain_arr[1: period + 1].mean()
        avg_l[period] = loss_arr[1: period + 1].mean()
        # Wilder's smoothing: equivalent to EWM(alpha=1/period) but SMA-seeded
        f = (period - 1) / period
        a = 1.0 / period
        for i in range(period + 1, n):
            avg_g[i] = avg_g[i - 1] * f + gain_arr[i] * a
            avg_l[i] = avg_l[i - 1] * f + loss_arr[i] * a

    rsi = np.full(n, float("nan"))
    for i in range(period, n):
        if np.isnan(avg_g[i]):
            continue
        if avg_l[i] == 0:
            rsi[i] = 100.0  # pure bull streak
        else:
            rsi[i] = 100.0 - 100.0 / (1.0 + avg_g[i] / avg_l[i])

    return pd.Series(rsi, index=close.index)


# ============================================================
# 신호 결과 — numpy 타입을 Python 기본형으로 변환
# ============================================================

def _signal_result(buy_pct: float, sell_pct: float) -> dict:
    """numpy scalar를 Python 기본형으로 변환하여 반환."""
    return {
        "buy": {
            "active": bool(buy_pct > 0),
            "proximity_pct": round(float(buy_pct), 3),
        },
        "sell": {
            "active": bool(sell_pct > 0),
            "proximity_pct": round(float(sell_pct), 3),
        },
    }


# ============================================================
# 전략별 신호 계산 (12종)
# ============================================================

def calc_macd_signal(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD 골든/데드 크로스.
    buy +  = MACD > Signal (골든크로스 상태)
    sell + = MACD < Signal (데드크로스 상태)
    """
    if len(df) < slow + signal + 5:
        raise ValueError("데이터 부족 (MACD)")
    close = df["close"]
    macd, sig_line = _compute_macd(close, fast, slow, signal)
    price = float(close.iloc[-1])
    gap = float(macd.iloc[-1] - sig_line.iloc[-1])
    buy_pct = gap / price * 100
    return _signal_result(buy_pct, -buy_pct)


def calc_sma_crossover(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> dict:
    """SMA 골든/데드 크로스.
    buy +  = fast SMA > slow SMA
    sell + = fast SMA < slow SMA
    """
    if len(df) < slow + 5:
        raise ValueError("데이터 부족 (SMA)")
    close = df["close"]
    fast_sma = float(_compute_sma(close, fast).iloc[-1])
    slow_sma = float(_compute_sma(close, slow).iloc[-1])
    if not slow_sma:
        raise ValueError("SMA 계산 실패")
    gap_pct = (fast_sma - slow_sma) / slow_sma * 100
    return _signal_result(gap_pct, -gap_pct)


def calc_momentum(df: pd.DataFrame, period: int = 20, threshold_pct: float = 5.0) -> dict:
    """모멘텀 (ROC).
    buy +  = ROC > threshold (상승 모멘텀 발동)
    sell + = ROC < -threshold (하락 모멘텀 발동)
    """
    if len(df) < period + 5:
        raise ValueError("데이터 부족 (Momentum)")
    close = df["close"]
    roc = float((close.iloc[-1] - close.iloc[-period]) / close.iloc[-period] * 100)
    buy_pct = roc - threshold_pct
    sell_pct = -threshold_pct - roc
    return _signal_result(buy_pct, sell_pct)


def calc_week52_high(df: pd.DataFrame, lookback: int = 252) -> dict:
    """52주 신고가 돌파.
    buy +  = 현재가 > N일 최고가 (돌파 상태)
    sell + = 현재가 < N일 최저가
    """
    n = min(lookback, len(df))
    if n < 10:
        raise ValueError("데이터 부족 (52주)")
    close = df["close"]
    price = float(close.iloc[-1])
    high52 = float(close.iloc[-n:-1].max())
    low52  = float(close.iloc[-n:-1].min())
    buy_pct  = (price - high52) / high52 * 100   # + when above peak
    sell_pct = (low52 - price) / price * 100      # + when below trough
    return _signal_result(buy_pct, sell_pct)


def calc_consecutive_moves(df: pd.DataFrame, up_days: int = 5, down_days: int = 5) -> dict:
    """N일 연속 상승/하락.
    buy +  = 연속 상승일 >= up_days
    sell + = 연속 하락일 >= down_days
    proximity = (count / required - 1) * 100
    """
    if len(df) < max(up_days, down_days) + 5:
        raise ValueError("데이터 부족 (연속)")
    close = df["close"]
    diff = close.diff()
    count_up = 0
    count_down = 0
    for d in reversed(diff.iloc[-max(up_days, down_days) - 1:].tolist()):
        if d > 0:
            count_up += 1
            count_down = 0
        elif d < 0:
            count_down += 1
            count_up = 0
        else:
            break
    buy_pct  = (count_up  / up_days   - 1) * 100
    sell_pct = (count_down / down_days - 1) * 100
    return _signal_result(buy_pct, sell_pct)


def calc_ma_divergence(df: pd.DataFrame, period: int = 20, buy_ratio: float = 0.9, sell_ratio: float = 1.1) -> dict:
    """이동평균 이격도.
    buy +  = price < MA * buy_ratio (이격도 매수 조건 충족)
    sell + = price > MA * sell_ratio
    proximity_buy  = (buy_ratio  - price/MA) * 100  [+ = condition met]
    proximity_sell = (price/MA   - sell_ratio) * 100 [+ = condition met]
    """
    if len(df) < period + 5:
        raise ValueError("데이터 부족 (MA Divergence)")
    close = df["close"]
    ma = float(_compute_sma(close, period).iloc[-1])
    price = float(close.iloc[-1])
    if not ma:
        raise ValueError("MA 계산 실패")
    ratio = price / ma
    buy_pct  = (buy_ratio  - ratio) * 100
    sell_pct = (ratio - sell_ratio) * 100
    return _signal_result(buy_pct, sell_pct)


def calc_false_breakout(df: pd.DataFrame, lookback: int = 20) -> dict:
    """추세 돌파 후 이탈 (가짜 돌파 매수).
    buy +  = 현재가 > N일 전고점 (돌파 상태)
    sell + = 현재가 < N일 전저점
    """
    n = min(lookback, len(df))
    if n < 5:
        raise ValueError("데이터 부족 (FalseBreakout)")
    close = df["close"]
    price = float(close.iloc[-1])
    prev_high = float(close.iloc[-n:-1].max())
    prev_low  = float(close.iloc[-n:-1].min())
    buy_pct  = (price - prev_high) / prev_high * 100
    sell_pct = (prev_low - price) / price * 100
    return _signal_result(buy_pct, sell_pct)


def calc_strong_close(df: pd.DataFrame, min_close_ratio: float = 0.8) -> dict:
    """강한 종가 상승.
    IBS = (close - low) / (high - low)
    buy +  = IBS >= min_close_ratio
    sell + = IBS <= (1 - min_close_ratio)
    proximity = (IBS - min_close_ratio) * 100
    """
    if len(df) < 5:
        raise ValueError("데이터 부족 (StrongClose)")
    row = df.iloc[-1]
    high, low, close = float(row["high"]), float(row["low"]), float(row["close"])
    rng = high - low
    ibs = (close - low) / rng if rng > 0 else 0.5
    buy_pct  = (ibs - min_close_ratio) * 100
    sell_pct = ((1 - min_close_ratio) - ibs) * 100
    return _signal_result(buy_pct, sell_pct)


def calc_volatility_breakout(df: pd.DataFrame, atr_period: int = 10, lookback: int = 20, breakout_pct: float = 3.0) -> dict:
    """변동성 축소 후 확장 돌파.
    buy +  = 오늘 수익률 > breakout_pct%  AND  ATR 확장 중
    proximity_buy = today_roc - breakout_pct
    """
    if len(df) < max(atr_period, lookback) + 5:
        raise ValueError("데이터 부족 (VolatilityBreakout)")
    close = df["close"]
    today_roc = float((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100) if close.iloc[-2] else 0.0
    atr = _compute_atr(df, atr_period)
    atr_now  = float(atr.iloc[-1])
    atr_prev = float(atr.iloc[-lookback:-1].mean())
    atr_expanding = atr_now > atr_prev
    buy_raw  =  today_roc - breakout_pct
    sell_raw = -breakout_pct - today_roc
    # ATR 미확장 시 proximity를 더 부정적으로 조정
    if not atr_expanding:
        buy_raw -= 1.0
    return _signal_result(buy_raw, sell_raw)


def calc_short_term_reversal(df: pd.DataFrame, period: int = 5, threshold_pct: float = 3.0) -> dict:
    """단기 반전.
    buy +  = price < MA * (1 - threshold/100)  (과하락 반전 매수)
    sell + = price > MA * (1 + threshold/100)
    proximity_buy = (MA*(1-th/100) - price) / price * 100
    """
    if len(df) < period + 5:
        raise ValueError("데이터 부족 (ShortTermReversal)")
    close = df["close"]
    ma = float(_compute_sma(close, period).iloc[-1])
    price = float(close.iloc[-1])
    if not ma:
        raise ValueError("MA 계산 실패")
    buy_threshold  = ma * (1 - threshold_pct / 100)
    sell_threshold = ma * (1 + threshold_pct / 100)
    buy_pct  = (buy_threshold  - price) / price * 100
    sell_pct = (price - sell_threshold) / price * 100
    return _signal_result(buy_pct, sell_pct)


def calc_trend_filter_signal(df: pd.DataFrame, trend_period: int = 60) -> dict:
    """추세 필터 + 시그널.
    buy +  = price > trend MA  AND  당일 수익률 > 0
    proximity = (price/trend_MA - 1) * 100
    """
    if len(df) < trend_period + 5:
        raise ValueError("데이터 부족 (TrendFilter)")
    close = df["close"]
    trend_ma = float(_compute_sma(close, trend_period).iloc[-1])
    price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    if not trend_ma:
        raise ValueError("Trend MA 계산 실패")
    trend_pct = (price / trend_ma - 1) * 100
    daily_roc  = (price - prev_price) / prev_price * 100 if prev_price else 0.0
    # 두 조건 모두 충족해야 buy: trend_pct > 0 AND daily_roc > 0
    buy_pct  = min(trend_pct, daily_roc)
    sell_pct = max(-trend_pct, -daily_roc)
    return _signal_result(buy_pct, sell_pct)


def calc_three_band(df: pd.DataFrame, bb_period: int = 20, bb_std: float = 2.0,
                    env_period: int = 20, env_pct: float = 6.0) -> dict:
    """삼중밴드.
    buy +  = BB_upper > Env_upper  AND  price > Env_upper
    proximity = min(bb_upper - env_upper, price - env_upper) / price * 100
    """
    n = max(bb_period, env_period)
    if len(df) < n + 5:
        raise ValueError("데이터 부족 (ThreeBand)")
    close = df["close"]
    sma = _compute_sma(close, bb_period)
    std = close.rolling(bb_period).std(ddof=0)
    bb_upper  = float((sma + bb_std * std).iloc[-1])
    env_upper = float((sma * (1 + env_pct / 100)).iloc[-1])
    price = float(close.iloc[-1])
    bb_gap    = (bb_upper  - env_upper) / price * 100   # + when BB above Env
    price_gap = (price     - env_upper) / price * 100   # + when price above Env
    # buy requires both positive; use the minimum as the binding constraint
    buy_pct  = min(bb_gap, price_gap)
    sell_pct = -buy_pct
    return _signal_result(buy_pct, sell_pct)


def calc_rsi(df: pd.DataFrame, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> dict:
    """RSI 과매도/과매수.
    buy +  = RSI < oversold
    sell + = RSI > overbought
    """
    if len(df) < period + 10:
        raise ValueError("데이터 부족 (RSI)")
    rsi = float(_compute_rsi(df["close"], period).iloc[-1])
    buy_pct  = oversold   - rsi   # + when oversold (rsi < 30)
    sell_pct = rsi - overbought   # + when overbought (rsi > 70)
    return _signal_result(buy_pct, sell_pct)


# ============================================================
# 다중 지표 한번에 계산 (MACD, MA20/60, RSI, 밴드 거리)
# ============================================================

def calc_multi_signal(df: pd.DataFrame) -> dict:
    """MACD, MA20/60 크로스, RSI(14), Envelope/BB/STARC 상단 거리."""
    if len(df) < 65:
        raise ValueError("데이터 부족")
    close = df["close"]
    price = float(close.iloc[-1])

    # MACD (12, 26, 9)
    macd, sig_line = _compute_macd(close, 12, 26, 9)
    macd_gap_pct = float((macd.iloc[-1] - sig_line.iloc[-1]) / price * 100)

    # MA20 vs MA60
    sma20 = float(_compute_sma(close, 20).iloc[-1])
    sma60 = float(_compute_sma(close, 60).iloc[-1])
    ma_gap_pct = float((sma20 - sma60) / sma60 * 100) if sma60 else 0.0

    # RSI(14)
    rsi_val = float(_compute_rsi(close, 14).iloc[-1])

    # Envelope upper (SMA20 × 1.06)
    env_upper = sma20 * 1.06
    env_gap_price = float(price - env_upper)
    env_gap_pct   = float(env_gap_price / price * 100)

    # Bollinger Band upper (SMA20 + 2σ)
    std20 = float(close.rolling(20).std(ddof=0).iloc[-1])
    bb_upper = sma20 + 2.0 * std20
    bb_gap_price = float(price - bb_upper)
    bb_gap_pct   = float(bb_gap_price / price * 100)

    # STARC upper (SMA6 + 2 × ATR15)
    sma6 = float(_compute_sma(close, 6).iloc[-1])
    atr15 = float(_compute_atr(df, 15).iloc[-1])
    starc_upper   = sma6 + 2.0 * atr15
    starc_gap_price = float(price - starc_upper)
    starc_gap_pct   = float(starc_gap_price / price * 100)

    return {
        "macd":     {"gap_pct": round(macd_gap_pct, 3), "is_golden": bool(macd_gap_pct > 0)},
        "ma_cross": {"gap_pct": round(ma_gap_pct, 3)},
        "rsi":      {"value": round(rsi_val, 1)},
        "envelope": {"gap_pct": round(env_gap_pct, 3), "gap_price": round(env_gap_price, 2)},
        "bollinger":{"gap_pct": round(bb_gap_pct, 3),  "gap_price": round(bb_gap_price, 2)},
        "starc":    {"gap_pct": round(starc_gap_pct, 3),"gap_price": round(starc_gap_price, 2)},
    }


# ============================================================
# 전략 ID → 계산 함수 라우팅
# ============================================================

def _dispatch(strategy_id: str, df: pd.DataFrame, **kw) -> dict:
    if strategy_id == "macd_signal":
        return calc_macd_signal(df,
            fast=kw.get("fast_period", 12),
            slow=kw.get("slow_period", 26),
            signal=kw.get("signal_period", 9))
    if strategy_id == "sma_crossover":
        return calc_sma_crossover(df,
            fast=kw.get("fast_period", 5),
            slow=kw.get("slow_period", 20))
    if strategy_id == "momentum":
        return calc_momentum(df, period=kw.get("fast_period", 20))
    if strategy_id == "week52_high":
        return calc_week52_high(df, lookback=kw.get("fast_period", 252))
    if strategy_id == "consecutive_moves":
        return calc_consecutive_moves(df,
            up_days=kw.get("fast_period", 5),
            down_days=kw.get("slow_period", 5))
    if strategy_id == "ma_divergence":
        return calc_ma_divergence(df, period=kw.get("fast_period", 20))
    if strategy_id == "false_breakout":
        return calc_false_breakout(df, lookback=kw.get("fast_period", 20))
    if strategy_id == "strong_close":
        return calc_strong_close(df)
    if strategy_id == "volatility_breakout":
        return calc_volatility_breakout(df,
            atr_period=kw.get("fast_period", 10),
            lookback=kw.get("slow_period", 20))
    if strategy_id == "short_term_reversal":
        return calc_short_term_reversal(df, period=kw.get("fast_period", 5))
    if strategy_id == "trend_filter_signal":
        return calc_trend_filter_signal(df, trend_period=kw.get("fast_period", 60))
    if strategy_id == "three_band":
        return calc_three_band(df,
            bb_period=kw.get("fast_period", 20),
            env_pct=kw.get("slow_period", 6.0))
    if strategy_id == "rsi":
        return calc_rsi(df, period=kw.get("fast_period", 14))
    # 알 수 없는 전략 → MACD 기본값
    return calc_macd_signal(df)


# ============================================================
# 데이터 로드
# ============================================================

def _is_us_symbol(symbol: str) -> bool:
    import re
    if re.match(r'^\d{6}$', symbol):
        return False
    if re.match(r'^[A-Za-z][A-Za-z0-9.]{0,4}$', symbol):
        return True
    return False


def _load_from_csv(csv_path: Path, min_bars: int = 60) -> Optional[pd.DataFrame]:
    if not csv_path.exists() or csv_path.stat().st_size < 100:
        return None
    try:
        df = pd.read_csv(csv_path, header=None,
                         names=["date", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df = df.sort_values("date").reset_index(drop=True)
        if len(df) < min_bars:
            return None
        if (date.today() - df["date"].iloc[-1].date()).days > 7:
            return None
        return df[["date", "open", "high", "low", "close", "volume"]].copy()
    except Exception as e:
        logger.warning(f"CSV 로드 실패 ({csv_path}): {e}")
        return None


def _make_provider():
    """KIS 인증 및 Provider 생성. 실패 시 None 반환."""
    try:
        from kis_backtest.providers.kis.auth import KISAuth
        from kis_backtest.providers.kis.data import KISDataProvider
        auth = KISAuth.from_env()
        return KISDataProvider(auth)
    except Exception as e:
        logger.warning(f"KIS 인증 실패 — 캐시 데이터만 사용: {e}")
        return None


def _fetch_from_provider(provider, symbol: str, is_us: bool, bars: int = 260) -> Optional[pd.DataFrame]:
    """이미 생성된 provider로 데이터 요청."""
    try:
        end = date.today()
        start = end - timedelta(days=int(bars * 1.8))
        if is_us:
            raw_bars = []
            for exch in ["nasdaq", "nyse", "amex"]:
                try:
                    raw_bars = provider.get_overseas_daily(symbol, exchange=exch, start_date=start, end_date=end)
                    if raw_bars:
                        break
                except Exception:
                    continue
        else:
            raw_bars = provider.get_history(symbol, start, end)
        if not raw_bars:
            return None
        rows = [{
            "date": b.time if isinstance(b.time, datetime) else datetime.combine(b.time, datetime.min.time()),
            "open": b.open, "high": b.high, "low": b.low,
            "close": b.close, "volume": b.volume,
        } for b in raw_bars]
        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        return df if len(df) >= 30 else None
    except Exception as e:
        logger.warning(f"KIS 데이터 로드 실패 ({symbol}): {e}")
        return None


def _save_to_csv(df: pd.DataFrame, csv_path: Path) -> None:
    """KIS API로 받은 데이터를 CSV에 저장 (다음 요청 시 캐시로 사용)."""
    try:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df_out = df.copy()
        df_out["date_str"] = pd.to_datetime(df_out["date"]).dt.strftime("%Y%m%d")
        df_out[["date_str", "open", "high", "low", "close", "volume"]].to_csv(
            csv_path, header=False, index=False
        )
        logger.info(f"[Signal] {csv_path.name} 캐시 저장 ({len(df_out)}행)")
    except Exception as e:
        logger.warning(f"CSV 저장 실패 ({csv_path}): {e}")


def _get_ohlcv(symbol: str, workspace: Path, provider=None, force_refresh: bool = False) -> Optional[pd.DataFrame]:
    is_us = _is_us_symbol(symbol)
    market_dir = "usa" if is_us else "krx"
    csv_path = workspace / "data" / "equity" / market_dir / "daily" / f"{symbol.lower()}.csv"
    if not force_refresh:
        df = _load_from_csv(csv_path)
        if df is not None:
            return df
    if provider is None:
        return None
    logger.info(f"[Signal] {symbol} KIS API 요청 (force_refresh={force_refresh})")
    df = _fetch_from_provider(provider, symbol, is_us)
    if df is not None:
        _save_to_csv(df, csv_path)
    return df


_us_name_cache: dict[str, str] = {}


def _load_us_name_map() -> dict[str, str]:
    """market_leaders_us.json에서 US 종목 코드 → 이름 맵 로드 (1회 캐시)."""
    global _us_name_cache
    if _us_name_cache:
        return _us_name_cache
    try:
        master_dir = LeanProjectManager().workspace.parent / ".master"
        us_json = master_dir / "market_leaders_us.json"
        if us_json.exists():
            with open(us_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key in ("all_leaders", "by_market_cap", "by_trading_amount", "by_revenue"):
                for item in data.get(key, []):
                    code = item.get("code", "")
                    name = item.get("name", "")
                    if code and name and name != code:
                        _us_name_cache[code] = name
    except Exception as e:
        logger.debug(f"US 이름 맵 로드 실패: {e}")
    return _us_name_cache


def _get_stock_name(symbol: str) -> str:
    if _is_us_symbol(symbol):
        return _load_us_name_map().get(symbol, symbol)
    try:
        workspace = LeanProjectManager().workspace
        master_dir = workspace.parent / ".master"
        for fname in ["kospi.csv", "kosdaq.csv"]:
            fpath = master_dir / fname
            if not fpath.exists():
                continue
            df = pd.read_csv(fpath, dtype=str, encoding="utf-8", low_memory=False)
            code_col = next((c for c in df.columns if "code" in c.lower() or "종목" in c), None)
            name_col = next((c for c in df.columns if "name" in c.lower() or "명" in c), None)
            if code_col and name_col:
                row = df[df[code_col].str.strip() == symbol]
                if not row.empty:
                    return str(row.iloc[0][name_col])
    except Exception:
        pass
    return symbol


# ============================================================
# API
# ============================================================

@router.get("", summary="종목별 매수/매도 신호 조회")
async def get_signals(
    symbols: str = Query(..., description="콤마 구분 종목코드"),
    strategy_id: str = Query("three_band"),
    fast_period: Optional[int] = Query(None),
    slow_period: Optional[int] = Query(None),
    signal_period: Optional[int] = Query(None),
    force_refresh: bool = Query(False, description="True이면 CSV 캐시를 건너뛰고 KIS API에서 최신 데이터를 가져옴"),
):
    """종목별 매수/매도 신호 상태 및 임박도(%) 반환.

    - active=true → 신호 발동 상태 (ON)
    - proximity_pct > 0 → 발동 상태 (+X%)
    - proximity_pct < 0 → 발동까지 X% 남음 (-X%)
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    workspace = LeanProjectManager().workspace
    kw = {}
    if fast_period is not None:
        kw["fast_period"] = fast_period
    if slow_period is not None:
        kw["slow_period"] = slow_period
    if signal_period is not None:
        kw["signal_period"] = signal_period

    # KIS 인증은 한 번만 시도 — 실패해도 캐시 데이터로 진행
    provider = _make_provider()

    results = []
    for symbol in symbol_list:
        try:
            df = _get_ohlcv(symbol, workspace, provider=provider, force_refresh=force_refresh)
            if df is None or df.empty:
                results.append({
                    "symbol": symbol,
                    "name": _get_stock_name(symbol),
                    "current_price": None,
                    "strategy_id": strategy_id,
                    "error": "데이터 없음",
                })
                continue

            current_price = float(df["close"].iloc[-1])
            updated_at = df["date"].iloc[-1].isoformat()
            signal_data = _dispatch(strategy_id, df, **kw)

            results.append({
                "symbol": symbol,
                "name": _get_stock_name(symbol),
                "current_price": current_price,
                "strategy_id": strategy_id,
                "buy_signal": signal_data["buy"],
                "sell_signal": signal_data["sell"],
                "updated_at": updated_at,
            })
        except Exception as e:
            logger.warning(f"[Signal] {symbol} 계산 실패: {e}")
            results.append({
                "symbol": symbol,
                "name": _get_stock_name(symbol),
                "current_price": None,
                "strategy_id": strategy_id,
                "error": str(e),
            })

    return {
        "signals": results,
        "strategy_id": strategy_id,
        "computed_at": datetime.now().isoformat(),
    }


@router.get("/multi", summary="종목별 다중 지표 일괄 조회")
async def get_multi_signals(
    symbols: str = Query(..., description="콤마 구분 종목코드"),
    force_refresh: bool = Query(False, description="True이면 CSV 캐시를 건너뛰고 KIS API에서 최신 데이터를 가져옴"),
):
    """MACD 크로스, MA20/60 차이, RSI, Envelope/BB/STARC 상단 거리 반환."""
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    workspace = LeanProjectManager().workspace
    provider = _make_provider()

    results = []
    for symbol in symbol_list:
        try:
            df = _get_ohlcv(symbol, workspace, provider=provider, force_refresh=force_refresh)
            if df is None or df.empty:
                results.append({
                    "symbol": symbol,
                    "name": _get_stock_name(symbol),
                    "current_price": None,
                    "error": "데이터 없음",
                })
                continue

            current_price = float(df["close"].iloc[-1])
            updated_at = df["date"].iloc[-1].isoformat()
            signals = calc_multi_signal(df)

            results.append({
                "symbol": symbol,
                "name": _get_stock_name(symbol),
                "current_price": current_price,
                "signals": signals,
                "updated_at": updated_at,
            })
        except Exception as e:
            logger.warning(f"[MultiSignal] {symbol} 계산 실패: {e}")
            results.append({
                "symbol": symbol,
                "name": _get_stock_name(symbol),
                "current_price": None,
                "error": str(e),
            })

    return {
        "signals": results,
        "computed_at": datetime.now().isoformat(),
    }
