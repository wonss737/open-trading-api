"""Signal 알림 API Routes.

각 종목에 대해 매수/매도 신호의 발동 여부 및 임박도(%)를 계산합니다.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

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


def _compute_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=period - 1, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


# ============================================================
# 전략별 신호 계산
# ============================================================

def _signal_result(buy_pct: float, sell_pct: float, current_price: float):
    """신호 결과 딕셔너리 생성."""
    return {
        "buy": {
            "active": buy_pct > 0,
            "proximity_pct": round(buy_pct, 3),
        },
        "sell": {
            "active": sell_pct > 0,
            "proximity_pct": round(sell_pct, 3),
        },
    }


def calc_macd_signal(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD 골든/데드 크로스 신호.

    buy proximity  = (macd - signal) / price * 100  [+ = 골든크로스 상태, - = 아직 미발동]
    sell proximity = (signal - macd) / price * 100  [+ = 데드크로스 상태, - = 아직 미발동]
    """
    if len(df) < slow + signal + 5:
        raise ValueError("데이터 부족 (MACD)")
    close = df["close"]
    macd, sig_line = _compute_macd(close, fast, slow, signal)
    price = close.iloc[-1]
    gap = macd.iloc[-1] - sig_line.iloc[-1]
    buy_pct = gap / price * 100
    sell_pct = -buy_pct
    return _signal_result(buy_pct, sell_pct, price)


def calc_sma_crossover(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> dict:
    """SMA 골든/데드 크로스 신호.

    buy proximity  = (fast_sma - slow_sma) / slow_sma * 100
    sell proximity = (slow_sma - fast_sma) / slow_sma * 100
    """
    if len(df) < slow + 5:
        raise ValueError("데이터 부족 (SMA)")
    close = df["close"]
    fast_sma = _compute_sma(close, fast).iloc[-1]
    slow_sma = _compute_sma(close, slow).iloc[-1]
    if not slow_sma or pd.isna(slow_sma):
        raise ValueError("SMA 계산 실패")
    gap_pct = (fast_sma - slow_sma) / slow_sma * 100
    return _signal_result(gap_pct, -gap_pct, close.iloc[-1])


def calc_momentum(df: pd.DataFrame, period: int = 20, threshold_pct: float = 5.0) -> dict:
    """모멘텀(ROC) 신호.

    buy proximity  = roc - threshold  [+ = 매수 신호 발동 상태]
    sell proximity = -threshold - roc [+ = 매도 신호 발동 상태 (roc < -threshold)]
    """
    if len(df) < period + 5:
        raise ValueError("데이터 부족 (Momentum)")
    close = df["close"]
    roc = (close.iloc[-1] - close.iloc[-period]) / close.iloc[-period] * 100
    buy_pct = roc - threshold_pct
    sell_pct = -threshold_pct - roc
    return _signal_result(buy_pct, sell_pct, close.iloc[-1])


def calc_rsi(df: pd.DataFrame, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> dict:
    """RSI 신호.

    buy proximity  = oversold - rsi      [+ = RSI 과매도 = 매수 신호]
    sell proximity = rsi - overbought    [+ = RSI 과매수 = 매도 신호]
    """
    if len(df) < period + 10:
        raise ValueError("데이터 부족 (RSI)")
    rsi = _compute_rsi(df["close"], period).iloc[-1]
    buy_pct = oversold - rsi
    sell_pct = rsi - overbought
    return _signal_result(buy_pct, sell_pct, df["close"].iloc[-1])


STRATEGY_CALC = {
    "macd_signal": calc_macd_signal,
    "sma_crossover": calc_sma_crossover,
    "momentum": calc_momentum,
}


# ============================================================
# 데이터 로드 (캐시 CSV → KIS API 순)
# ============================================================

def _is_us_symbol(symbol: str) -> bool:
    import re
    if re.match(r'^\d{6}$', symbol):
        return False
    if re.match(r'^[A-Za-z][A-Za-z0-9.]{0,4}$', symbol):
        return True
    return False


def _load_from_csv(csv_path: Path, min_bars: int = 60) -> Optional[pd.DataFrame]:
    """Lean CSV에서 OHLCV 데이터 로드."""
    if not csv_path.exists() or csv_path.stat().st_size < 100:
        return None
    try:
        df = pd.read_csv(
            csv_path, header=None,
            names=["date", "open", "high", "low", "close", "volume"],
        )
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d")
        df = df.sort_values("date").reset_index(drop=True)
        if len(df) < min_bars:
            return None
        # 최신 데이터가 5거래일(7일) 이내인지 확인
        last_date = df["date"].iloc[-1].date()
        if (date.today() - last_date).days > 7:
            return None
        return df[["date", "open", "high", "low", "close", "volume"]].copy()
    except Exception as e:
        logger.warning(f"CSV 로드 실패 ({csv_path}): {e}")
        return None


def _fetch_from_kis(symbol: str, is_us: bool, bars: int = 120) -> Optional[pd.DataFrame]:
    """KIS API에서 최근 N봉 로드."""
    try:
        from kis_backtest.providers.kis.auth import KISAuth
        from kis_backtest.providers.kis.data import KISDataProvider

        auth = KISAuth.from_env()
        provider = KISDataProvider(auth)

        end = date.today()
        start = end - timedelta(days=int(bars * 1.8))  # 주말·휴장 포함 여유

        if is_us:
            raw_bars = []
            for exch in ["nasdaq", "nyse", "amex"]:
                try:
                    raw_bars = provider.get_overseas_daily(
                        symbol, exchange=exch, start_date=start, end_date=end
                    )
                    if raw_bars:
                        break
                except Exception:
                    continue
        else:
            raw_bars = provider.get_history(symbol, start, end)

        if not raw_bars:
            return None

        rows = [
            {
                "date": b.time if isinstance(b.time, datetime) else datetime.combine(b.time, datetime.min.time()),
                "open": b.open, "high": b.high, "low": b.low,
                "close": b.close, "volume": b.volume,
            }
            for b in raw_bars
        ]
        df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        return df if len(df) >= 30 else None

    except Exception as e:
        logger.warning(f"KIS API 데이터 로드 실패 ({symbol}): {e}")
        return None


def _get_ohlcv(symbol: str, workspace: Path) -> Optional[pd.DataFrame]:
    """캐시 CSV → KIS API 순서로 OHLCV 조회."""
    is_us = _is_us_symbol(symbol)
    market_dir = "usa" if is_us else "krx"
    csv_path = workspace / "data" / "equity" / market_dir / "daily" / f"{symbol.lower()}.csv"

    df = _load_from_csv(csv_path)
    if df is not None:
        logger.debug(f"[Signal] {symbol} 캐시 사용 ({len(df)}봉)")
        return df

    logger.info(f"[Signal] {symbol} KIS API 요청")
    return _fetch_from_kis(symbol, is_us)


def _get_stock_name(symbol: str) -> str:
    """종목명 간단 조회 (마스터 파일)."""
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
                    return row.iloc[0][name_col]
    except Exception:
        pass
    return symbol


# ============================================================
# API 엔드포인트
# ============================================================

class SignalInfo:
    def __init__(self, active: bool, proximity_pct: float):
        self.active = active
        self.proximity_pct = proximity_pct


@router.get("", summary="종목별 매수/매도 신호 조회")
async def get_signals(
    symbols: str = Query(..., description="콤마 구분 종목코드 (예: 005930,AAPL)"),
    strategy_id: str = Query("macd_signal", description="전략 ID"),
    fast_period: Optional[int] = Query(None),
    slow_period: Optional[int] = Query(None),
    signal_period: Optional[int] = Query(None),
):
    """종목별 매수/매도 신호 상태 및 임박도(%) 반환.

    - active=true이면 신호 발동 상태 (ON)
    - proximity_pct > 0: 이미 발동 상태 (+X%)
    - proximity_pct < 0: 발동까지 X% 남음 (-X%)
    """
    symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    workspace = LeanProjectManager().workspace

    results = []
    for symbol in symbol_list:
        try:
            df = _get_ohlcv(symbol, workspace)
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

            # 전략별 파라미터 오버라이드
            if strategy_id == "macd_signal":
                kwargs = {}
                if fast_period:
                    kwargs["fast"] = fast_period
                if slow_period:
                    kwargs["slow"] = slow_period
                if signal_period:
                    kwargs["signal"] = signal_period
                signal_data = calc_macd_signal(df, **kwargs)

            elif strategy_id == "sma_crossover":
                kwargs = {}
                if fast_period:
                    kwargs["fast"] = fast_period
                if slow_period:
                    kwargs["slow"] = slow_period
                signal_data = calc_sma_crossover(df, **kwargs)

            elif strategy_id == "momentum":
                kwargs = {}
                if fast_period:
                    kwargs["period"] = fast_period
                signal_data = calc_momentum(df, **kwargs)

            elif strategy_id == "rsi":
                kwargs = {}
                if fast_period:
                    kwargs["period"] = fast_period
                signal_data = calc_rsi(df, **kwargs)

            else:
                # 알 수 없는 전략: MACD 기본값 사용
                signal_data = calc_macd_signal(df)

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
            logger.warning(f"[Signal] {symbol} 신호 계산 실패: {e}")
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
