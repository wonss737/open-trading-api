"""시장 선도주 API 라우터

시가총액 상위 DEFAULT_CAP_LIMIT, 매출 상위 DEFAULT_REVENUE_LIMIT,
거래대금 상위 DEFAULT_AMOUNT_LIMIT 기준으로 시장 선도주를 선정합니다.
한국 (KOSPI) / 미국 (NASDAQ·NYSE·AMEX) 시장을 별도 지원합니다.
결과는 .master/market_leaders_{kr|us}.json 에 캐시되며 매일 갱신이 필요합니다.
"""
import asyncio
import csv
import json
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional

import kis_auth as ka
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel

from backend.state import trading_state

logger = logging.getLogger(__name__)
router = APIRouter(tags=["market-leaders"])

CACHE_DIR = Path(".master")
Market = Literal["kr", "us"]

# 인메모리 캐시 (market별)
_cache: dict[str, Optional[dict]] = {"kr": None, "us": None}
_cache_date: dict[str, Optional[date]] = {"kr": None, "us": None}
_is_updating: dict[str, bool] = {"kr": False, "us": False}

# US ETF/펀드 제외 키워드
_US_ETF_KEYWORDS = {
    "ETF", "FUND", "TRUST", "INDEX", "BOND", "NOTE", "PORTFOLIO",
    "ISHARES", "SPDR", "VANGUARD", "INVESCO", "PROSHARES", "FIDELITY",
    "SCHWAB", "BLACKROCK", "WISDOMTREE",
}

# KOSPI 보통주 필터링 시 ETF/펀드 제외용 키워드 (대문자 비교)
_KR_ETF_NAME_KEYWORDS = frozenset({
    "ETF", "ETN", "KODEX", "TIGER", "KINDEX", "ARIRANG", "HANARO",
    "KOSEF", "KBSTAR", "TIMEFOLIO", "ACE", "SOL",
})

# 기본 순위 기준 (변경 시 이 값만 수정하면 됨)
DEFAULT_CAP_LIMIT: int = 100
DEFAULT_REVENUE_LIMIT: int = 100
DEFAULT_AMOUNT_LIMIT: int = 200


# ============================================
# 스키마
# ============================================


class MarketLeaderItem(BaseModel):
    code: str
    name: str
    reason: list[str]


class MarketLeadersStatus(BaseModel):
    is_updating: bool
    last_updated: Optional[str] = None
    needs_update: bool
    counts: dict


class MarketLeadersResponse(BaseModel):
    status: str = "success"
    market: str = "kr"
    updated_at: Optional[str] = None
    total: int
    by_market_cap: list[MarketLeaderItem]
    by_trading_amount: list[MarketLeaderItem]
    by_revenue: list[MarketLeaderItem]
    all_leaders: list[MarketLeaderItem]


# ============================================
# 캐시 유틸리티
# ============================================


def _cache_file(market: Market) -> Path:
    return CACHE_DIR / f"market_leaders_{market}.json"


def _load_cache(market: Market) -> Optional[dict]:
    path = _cache_file(market)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"시장 선도주 캐시 로드 오류 ({market}): {e}")
        return None


def _save_cache(market: Market, data: dict):
    CACHE_DIR.mkdir(exist_ok=True)
    with open(_cache_file(market), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _get_cache(market: Market) -> Optional[dict]:
    today = date.today()
    if _cache[market] and _cache_date[market] == today:
        return _cache[market]
    loaded = _load_cache(market)
    if loaded:
        try:
            cached_date = datetime.fromisoformat(loaded.get("updated_at", "")).date()
            if cached_date == today:
                _cache[market] = loaded
                _cache_date[market] = today
                return _cache[market]
        except Exception:
            pass
    return None


def _check_needs_update(market: Market) -> bool:
    cache = _get_cache(market) or _load_cache(market)
    if cache is None:
        return True
    # 캐시에 실제 데이터가 없으면 날짜 무관하게 업데이트 필요
    if not cache.get("by_market_cap"):
        return True
    try:
        cached_date = datetime.fromisoformat(cache.get("updated_at", "")).date()
        return cached_date < date.today()
    except Exception:
        return True


# ============================================
# 공통 헬퍼
# ============================================


def _parse_revenue(sale: object) -> Optional[int]:
    """매출액 문자열을 정수로 파싱 (콤마, 소수점 모두 허용)"""
    try:
        s = str(sale).replace(",", "").strip()
        if not s:
            return None
        val = float(s)
        return int(val) if val > 0 else None
    except (ValueError, TypeError):
        return None


def _is_us_etf(name: str) -> bool:
    """US ETF/펀드 여부 판별"""
    upper = name.upper()
    return any(kw in upper for kw in _US_ETF_KEYWORDS)


# ============================================
# 한국 (KOSPI) KIS API 호출
# ============================================


def _load_kospi_common_stocks() -> list[dict]:
    """kospi.csv에서 KOSPI 보통주 목록 로드 (ETF/펀드/우선주 제외)

    FHPST01740000 은 호출당 30건 고정이며 업종코드 필터도 지원하지 않아
    ranking API 만으로는 150/300개를 얻을 수 없다.
    대신 .master/kospi.csv 전체 종목 리스트를 로드하여 개별 현재가 조회의 universe로 사용한다.
    """
    csv_path = CACHE_DIR / "kospi.csv"
    if not csv_path.exists():
        logger.warning("kospi.csv가 없습니다. .master/ 에 파일을 먼저 배치하세요.")
        return []
    stocks: list[dict] = []
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                code = str(row.get("code", "")).strip().zfill(6)
                name = str(row.get("name", "")).strip()
                # 6자리 순수 숫자여야 함 (알파벳 포함 코드 제외)
                # 1XXXXX는 수익증권(펀드) 전용 코드 범위 → 제외
                # 2·4·5XXXXX는 알파벳 포함 코드가 많아 isdigit()에서 이미 걸러짐
                if not (len(code) == 6 and code.isdigit()):
                    continue
                if code.startswith("1"):
                    continue
                # 우선주 제외 (이름이 "우", "우B", "우C"로 끝나는 경우)
                if name.endswith("우") or name.endswith("우B") or name.endswith("우C"):
                    continue
                # ETF/펀드 제외 (이름에 ETF 제공사 키워드 포함)
                if any(kw in name.upper() for kw in _KR_ETF_NAME_KEYWORDS):
                    continue
                stocks.append({"code": code, "name": name})
    except Exception as e:
        logger.error(f"kospi.csv 로드 오류: {e}")
    logger.info(f"KOSPI 보통주 {len(stocks)}개 로드됨")
    return stocks


def _fetch_kr_inquire_price(code: str) -> Optional[dict]:
    """단일 KOSPI 종목 현재가 조회 (FHKST01010100)

    hts_avls(HTS 시가총액)와 acml_tr_pbmn(누적 거래대금)을 반환한다.
    두 지표를 1회 호출로 동시에 수집하여 이중 조회를 방지한다.
    """
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": code,
    }
    try:
        res = ka._url_fetch(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100", "", params,
        )
        if not res.isOK():
            return None
        output = res.getBody().output
        if not output:
            return None
        row = output if not isinstance(output, list) else (output[0] if output else None)
        if row is None:
            return None

        def _to_int(key: str) -> int:
            val = row.get(key, "0") if isinstance(row, dict) else getattr(row, key, "0")
            try:
                return int(str(val).replace(",", "") or "0")
            except (ValueError, TypeError):
                return 0

        return {"hts_avls": _to_int("hts_avls"), "acml_tr_pbmn": _to_int("acml_tr_pbmn")}
    except Exception as e:
        logger.debug(f"현재가 조회 오류 ({code}): {e}")
        return None


def _fetch_kr_stock_universe(universe: list[dict]) -> list[dict]:
    """KOSPI 보통주 전체 현재가 1회 조회 (시가총액 + 거래대금 동시 수집)

    시가총액과 거래대금을 1회 루프로 모두 수집하여 이중 API 호출을 방지한다.
    결과 리스트는 정렬되지 않은 상태로 반환되며 caller 에서 원하는 기준으로 정렬한다.
    """
    result: list[dict] = []
    total = len(universe)
    for i, stock in enumerate(universe):
        data = _fetch_kr_inquire_price(stock["code"])
        if data and (data["hts_avls"] > 0 or data["acml_tr_pbmn"] > 0):
            result.append({
                "code": stock["code"],
                "name": stock["name"],
                "hts_avls": data["hts_avls"],
                "acml_tr_pbmn": data["acml_tr_pbmn"],
            })
        if (i + 1) % 100 == 0:
            logger.info(f"KOSPI 현재가 조회 진행: {i + 1}/{total}")
        time.sleep(0.1)
    logger.info(f"KOSPI 현재가 조회 완료: 유효 {len(result)}/{total}개")
    return result


def _fetch_kr_revenue_for_stock(code: str) -> Optional[int]:
    """단일 KOSPI 종목의 최근 연간 매출액 조회 (FHKST66430200 → yfinance fallback)"""
    params = {
        "FID_DIV_CLS_CODE": "0",    # 연간
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": code,
    }
    try:
        res = ka._url_fetch(
            "/uapi/domestic-stock/v1/finance/income-statement",
            "FHKST66430200", "", params,
        )
        if res.isOK():
            output = res.getBody().output
            if output:
                first = output[0] if isinstance(output, list) else output
                sale = (first.get("sale_account", "") if isinstance(first, dict)
                        else getattr(first, "sale_account", "") or "")
                rev = _parse_revenue(sale)
                if rev is not None:
                    return rev
    except Exception as e:
        logger.debug(f"KR KIS 매출 조회 오류 ({code}): {e}")

    # KIS API 실패 → yfinance fallback
    return _fetch_kr_revenue_yfinance(code)


# KIS FHKST66430200 sale_account 단위: 억원 / yfinance totalRevenue 단위: 원(KRW)
# 1억원 = 100,000,000원 → yfinance 원 단위를 억원으로 변환
_YF_KR_REVENUE_SCALE = 100_000_000


def _fetch_kr_revenue_yfinance(code: str) -> Optional[int]:
    """yfinance로 KOSPI 종목 매출 조회 (KIS 실패 시 fallback, 단위: 백만원)

    연간 financials → 4분기 합산 TTM → info.totalRevenue 순으로 시도.
    """
    try:
        import yfinance as yf
        import pandas as pd
        ticker = yf.Ticker(f"{code}.KS")
        rev: Optional[float] = None

        # 1차: 연간 financials
        try:
            df = ticker.financials
            if df is not None and not df.empty:
                for row_name in ("Total Revenue", "Revenue"):
                    if row_name in df.index:
                        val = df.loc[row_name].iloc[0]
                        if pd.notna(val) and float(val) > 0:
                            rev = float(val)
                            break
        except Exception:
            pass

        # 2차: 4분기 합산 TTM
        if rev is None:
            try:
                qdf = ticker.quarterly_financials
                if qdf is not None and not qdf.empty:
                    for row_name in ("Total Revenue", "Revenue"):
                        if row_name in qdf.index:
                            quarters = qdf.loc[row_name].dropna().iloc[:4]
                            if len(quarters) == 4:
                                rev = float(quarters.sum())
                            break
            except Exception:
                pass

        # 3차: info.totalRevenue
        if rev is None:
            rev_raw = ticker.info.get("totalRevenue")
            if rev_raw and rev_raw > 0:
                rev = float(rev_raw)

        if rev and rev > 0:
            logger.debug(f"yfinance KR 매출 사용 ({code}): {rev:.0f} KRW")
            return int(rev / _YF_KR_REVENUE_SCALE)
    except Exception as e:
        logger.debug(f"yfinance KR 매출 조회 오류 ({code}): {e}")
    return None


def _fetch_kr_revenue_leaders(universe: list[dict], limit: int = 150) -> list[dict]:
    """KOSPI universe 기반 매출 상위 종목 배치 조회

    반환 dict에 revenue 필드를 포함하여 CSV 저장 및 정렬에 활용.
    """
    revenues: list[tuple[dict, int]] = []
    for i, stock in enumerate(universe):
        rev = _fetch_kr_revenue_for_stock(stock["code"])
        if rev is not None and rev > 0:
            revenues.append((stock, rev))
        if (i + 1) % 50 == 0:
            logger.info(f"KR 매출 조회 진행: {i + 1}/{len(universe)}")
        time.sleep(0.1)
    revenues.sort(key=lambda x: x[1], reverse=True)
    result = [
        {"code": s["code"], "name": s["name"], "revenue": rev}
        for s, rev in revenues[:limit]
    ]
    logger.info(f"KR 매출 조회 완료: {len(result)}개 (유효 데이터 {len(revenues)}개 / {len(universe)}개)")
    return result


# ============================================
# 미국 (NASDAQ·NYSE·AMEX) KIS API 호출
# ============================================

_US_EXCHANGES = [
    ("NAS", "나스닥"),
    ("NYS", "뉴욕"),
    ("AMS", "아멕스"),
]


def _fetch_us_market_cap_for_excd(excd: str, limit: int) -> list[dict]:
    """해외주식 시가총액순위 (HHDFS76350100) - 단일 거래소

    응답 1페이지 = 최대 100개. tr_cont='F'이면 더 이상 데이터 없음.
    tomv(시가총액 USD), tvol(거래량), last(현재가 USD) 포함하여 반환.
    거래대금(tamt)은 API 응답에 없으므로 tvol * last 로 계산.
    """
    stocks: list[dict] = []
    tr_cont = ""
    depth = 0
    while len(stocks) < limit and depth < 10:
        params = {
            "EXCD": excd,
            "VOL_RANG": "0",
            "KEYB": "",
            "AUTH": "",
            "CURR_GB": "0",
        }
        res = ka._url_fetch(
            "/uapi/overseas-stock/v1/ranking/market-cap",
            "HHDFS76350100", tr_cont, params,
        )
        if not res.isOK():
            logger.warning(f"US 시가총액 API 오류 ({excd}): {res.getErrorMessage()}")
            break
        output2 = res.getBody().output2 or []
        for row in (output2 if isinstance(output2, list) else []):
            symb = str(row.get("symb", "") if isinstance(row, dict) else "").strip()
            name = str(row.get("name", "") if isinstance(row, dict) else "").strip()
            if symb and name and not _is_us_etf(name):
                def _fval(key: str) -> float:
                    v = row.get(key, "0") if isinstance(row, dict) else getattr(row, key, "0")
                    try:
                        return float(str(v).replace(",", "") or "0")
                    except ValueError:
                        return 0.0
                tvol = _fval("tvol")
                last = _fval("last")
                stocks.append({
                    "code": symb,
                    "name": name,
                    "exchange": excd,
                    "tomv": _fval("tomv"),
                    "tamt": tvol * last,  # 거래대금 = 거래량 × 현재가
                })
            if len(stocks) >= limit:
                break
        tr_cont = res.getHeader().tr_cont
        if tr_cont != "M" or len(stocks) >= limit:
            break
        depth += 1
        time.sleep(0.2)
    return stocks


def _fetch_us_market_cap(limit_each: int = 200) -> list[dict]:
    """NYS + NAS + AMS 시가총액 합산, ETF 제외"""
    all_stocks: list[dict] = []
    for excd, _ in _US_EXCHANGES:
        stocks = _fetch_us_market_cap_for_excd(excd, limit_each)
        all_stocks.extend(stocks)
        time.sleep(0.3)
    logger.info(f"US 시가총액 조회: {len(all_stocks)}개 (3개 거래소 합산)")
    return all_stocks


def _rank_us_by_trading_amount(cap_raw: list[dict], limit: int = 300) -> list[dict]:
    """cap_raw에서 거래대금(tvol×last) 기준 상위 limit개 반환 (별도 API 호출 없음)"""
    seen: set[str] = set()
    deduped: list[dict] = []
    for s in cap_raw:
        if s["code"] not in seen:
            seen.add(s["code"])
            deduped.append(s)

    deduped.sort(key=lambda x: x.get("tamt", 0), reverse=True)
    result = [
        {"code": s["code"], "name": s["name"], "tamt": s.get("tamt", 0)}
        for s in deduped[:limit]
    ]
    logger.info(f"US 거래대금 정렬 완료: {len(result)}개")
    return result


# ============================================
# 미국 매출 조회 (yfinance) — USD 정규화
# ============================================

# 통화→USD 환율 캐시 (서버 재시작 전까지 유지)
_fx_rate_cache: dict[str, float] = {}


def _get_usd_rate(currency: str) -> float:
    """통화 → USD 환율 반환 (세션 캐시 포함). 조회 실패 시 1.0."""
    key = currency.upper()
    if key == "USD":
        return 1.0
    if key in _fx_rate_cache:
        return _fx_rate_cache[key]
    try:
        import yfinance as yf
        rate = yf.Ticker(f"{key}USD=X").info.get("regularMarketPrice", 0)
        if rate and float(rate) > 0:
            _fx_rate_cache[key] = float(rate)
            logger.debug(f"환율 캐시: 1 {key} = {rate} USD")
            return float(rate)
    except Exception:
        pass
    logger.warning(f"환율 조회 실패 ({key}/USD) — 변환 없이 원래 값 사용")
    _fx_rate_cache[key] = 1.0
    return 1.0


def _fetch_us_revenue_for_stock(symbol: str) -> Optional[int]:
    """yfinance로 US 종목 최근 연간 매출 조회, USD로 정규화하여 반환.

    info 호출로 financialCurrency를 먼저 확보한 뒤,
    financials / income_stmt → info.totalRevenue 순으로 값을 가져온다.
    USD 이외 통화(JPY, EUR, CNY 등)는 실시간 환율로 변환한다.
    """
    try:
        import yfinance as yf
        import pandas as pd
        ticker = yf.Ticker(symbol)

        # info 1회 호출: 보고 통화 + totalRevenue(fallback용) 동시 획득
        info = ticker.info
        financial_currency = (
            info.get("financialCurrency") or info.get("currency") or "USD"
        ).upper()

        rev: Optional[float] = None

        # 1차: annual financials (연간 결산, 가장 최근 회계연도)
        try:
            df = ticker.financials
            if df is not None and not df.empty:
                for row_name in ("Total Revenue", "Revenue"):
                    if row_name in df.index:
                        val = df.loc[row_name].iloc[0]
                        if pd.notna(val) and float(val) > 0:
                            rev = float(val)
                            break
        except Exception:
            pass

        # 2차: 최근 4분기 합산 → TTM (외국 ADR 등 연간 데이터 없는 경우)
        if rev is None:
            try:
                qdf = ticker.quarterly_financials
                if qdf is not None and not qdf.empty:
                    for row_name in ("Total Revenue", "Revenue"):
                        if row_name in qdf.index:
                            quarters = qdf.loc[row_name].dropna().iloc[:4]
                            if len(quarters) == 4:
                                rev = float(quarters.sum())
                                logger.debug(f"{symbol}: 4분기 합산 TTM 사용 ({financial_currency})")
                            break
            except Exception:
                pass

        # 3차: info.totalRevenue (TTM, 최후 수단)
        if rev is None:
            rev_raw = info.get("totalRevenue")
            if rev_raw and rev_raw > 0:
                rev = float(rev_raw)

        if not rev or rev <= 0:
            return None

        # USD 이외 통화 → USD 환율 변환
        if financial_currency != "USD":
            rate = _get_usd_rate(financial_currency)
            converted = rev * rate
            logger.debug(
                f"환율 변환 ({symbol}): {rev:,.0f} {financial_currency} "
                f"× {rate:.6f} = {converted:,.0f} USD"
            )
            rev = converted

        return int(rev)
    except Exception as e:
        logger.debug(f"yfinance US 매출 조회 오류 ({symbol}): {e}")
    return None


def _fetch_us_revenues_all(stocks: list[dict]) -> dict[str, int]:
    """yfinance로 US 종목 매출 전수 조회. {code: revenue_USD} 반환"""
    result: dict[str, int] = {}
    total = len(stocks)
    for i, stock in enumerate(stocks):
        rev = _fetch_us_revenue_for_stock(stock["code"])
        if rev is not None and rev > 0:
            result[stock["code"]] = rev
        if (i + 1) % 50 == 0:
            logger.info(f"US 매출 조회 진행 (yfinance): {i + 1}/{total}")
        time.sleep(0.2)
    logger.info(f"US 매출 조회 완료 (yfinance): {len(result)}/{total}개 성공")
    return result


# ============================================
# CSV 저장 유틸리티
# ============================================

_CSV_FIELDS = ["name", "code", "market_cap", "revenue", "trading_amount"]


def _save_kr_csv(all_data: list[dict], revenue_list: list[dict]) -> None:
    """KR 전체 데이터를 한 파일에 저장 (시가총액 내림차순)

    all_data  : _fetch_kr_stock_universe() 결과 (hts_avls, acml_tr_pbmn 포함)
    revenue_list : _fetch_kr_revenue_leaders() 결과 (revenue 필드 포함)
    """
    path = CACHE_DIR / "kr_market_data.csv"
    CACHE_DIR.mkdir(exist_ok=True)

    revenue_map: dict[str, int] = {s["code"]: s.get("revenue", 0) for s in revenue_list}
    sorted_data = sorted(all_data, key=lambda x: x["hts_avls"], reverse=True)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for s in sorted_data:
            writer.writerow({
                "name": s["name"],
                "code": s["code"],
                "market_cap": s["hts_avls"],
                "revenue": revenue_map.get(s["code"], ""),
                "trading_amount": s["acml_tr_pbmn"],
            })
    logger.info(f"KR 시장 데이터 CSV 저장: {path} ({len(sorted_data)}개)")


def _save_us_csv(
    cap_raw: list[dict],
    amount_raw: list[dict],
    revenue_list: Optional[list[dict]] = None,
) -> None:
    """US 전체 데이터를 한 파일에 저장 (시가총액 순위 순)

    cap_raw      : _fetch_us_market_cap() 결과 (API 반환 순서 = 시가총액 순)
    amount_raw   : _rank_us_by_trading_amount() 결과 (tamt 필드 포함)
    revenue_list : _fetch_us_revenue_leaders() 결과 (revenue 필드 포함, USD 단위)
    """
    path = CACHE_DIR / "us_market_data.csv"
    CACHE_DIR.mkdir(exist_ok=True)

    trading_map: dict[str, float] = {s["code"]: s.get("tamt", 0) for s in amount_raw}
    revenue_map: dict[str, int] = {s["code"]: s.get("revenue", 0) for s in (revenue_list or [])}

    seen: set[str] = set()
    rows: list[dict] = []
    for s in cap_raw:
        if s["code"] in seen:
            continue
        seen.add(s["code"])
        rows.append({
            "name": s["name"],
            "code": s["code"],
            "market_cap": s.get("tomv", ""),  # 시가총액 (USD), tomv = tvol×last 기반
            "revenue": revenue_map.get(s["code"], ""),
            "trading_amount": trading_map.get(s["code"], ""),
        })

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"US 시장 데이터 CSV 저장: {path} ({len(rows)}개)")


# ============================================
# 백그라운드 업데이트 작업
# ============================================


def _build_leaders_data(
    cap: list[dict],
    amount: list[dict],
    revenue: list[dict],
) -> dict:
    """3개 기준의 교집합으로 all_leaders 구성

    시가총액 상위 150 ∩ 거래대금 상위 300 ∩ 매출 상위 150 에 모두 속하는 종목만 선정.
    매출 데이터가 없는 경우(미국 시장)에는 시가총액 ∩ 거래대금 2개 기준 교집합을 사용한다.
    """
    cap_codes = {s["code"] for s in cap}
    amount_codes = {s["code"] for s in amount}
    revenue_codes = {s["code"] for s in revenue}

    if revenue_codes:
        intersection_codes = cap_codes & amount_codes & revenue_codes
    else:
        # 매출 데이터 미제공(US) → 시가총액 ∩ 거래대금
        intersection_codes = cap_codes & amount_codes

    name_map: dict[str, str] = {s["code"]: s["name"] for s in cap + amount + revenue}

    all_leaders = []
    for code in intersection_codes:
        reasons = []
        if code in cap_codes:
            reasons.append("시가총액")
        if code in amount_codes:
            reasons.append("거래대금")
        if code in revenue_codes:
            reasons.append("매출")
        all_leaders.append({"code": code, "name": name_map[code], "reasons": reasons})

    return {
        "updated_at": datetime.now().isoformat(),
        "by_market_cap": [{"code": s["code"], "name": s["name"]} for s in cap],
        "by_trading_amount": [{"code": s["code"], "name": s["name"]} for s in amount],
        "by_revenue": [{"code": s["code"], "name": s["name"]} for s in revenue],
        "all_leaders": all_leaders,
    }


async def _do_update_kr(
    cap_limit: int = DEFAULT_CAP_LIMIT,
    revenue_limit: int = DEFAULT_REVENUE_LIMIT,
    amount_limit: int = DEFAULT_AMOUNT_LIMIT,
    force: bool = False,
):
    """KR 시장 선도주 업데이트

    Args:
        cap_limit: 시가총액 상위 N개 (기본 150)
        revenue_limit: 매출 상위 N개 (기본 150)
        amount_limit: 거래대금 상위 N개 (기본 300)
        force: True이면 오늘 이미 업데이트된 경우에도 강제 재실행
    """
    global _is_updating, _cache, _cache_date

    # 오늘 이미 업데이트된 캐시가 있으면 스킵 (force=True이면 무시)
    if not force and not _check_needs_update("kr"):
        logger.info("KR 시장 선도주: 오늘 이미 업데이트됨 — 스킵 (강제 실행하려면 force=true)")
        return

    _is_updating["kr"] = True
    try:
        loop = asyncio.get_event_loop()
        logger.info(f"KR 시장 선도주 업데이트 시작 (시가총액 {cap_limit}, 매출 {revenue_limit}, 거래대금 {amount_limit})...")

        # 1. KOSPI 보통주 목록 로드 (kospi.csv)
        universe = _load_kospi_common_stocks()
        if not universe:
            logger.error("KOSPI 보통주 목록이 비어 있어 업데이트를 중단합니다.")
            return

        # 2. 전체 현재가 조회 (시가총액 + 거래대금) — 1회 루프로 동시 수집
        all_data = await loop.run_in_executor(None, lambda: _fetch_kr_stock_universe(universe))

        # 3. 시가총액 기준 정렬
        by_cap = sorted(all_data, key=lambda x: x["hts_avls"], reverse=True)
        cap_top = [{"code": s["code"], "name": s["name"]} for s in by_cap[:cap_limit]]
        # 매출 조회용 universe는 cap_limit * 2 또는 최소 300개로 확장
        rev_universe_size = max(cap_limit * 2, 300)
        cap_rev_universe = [{"code": s["code"], "name": s["name"]} for s in by_cap[:rev_universe_size]]

        # 4. 거래대금 기준 정렬
        by_amount = sorted(all_data, key=lambda x: x["acml_tr_pbmn"], reverse=True)
        amount_top = [{"code": s["code"], "name": s["name"]} for s in by_amount[:amount_limit]]

        # 5. 매출 조회 (시가총액 상위 universe 기반)
        revenue = await loop.run_in_executor(
            None, lambda: _fetch_kr_revenue_leaders(cap_rev_universe, revenue_limit)
        )

        # CSV 저장 (시가총액·매출·거래대금 통합 1개 파일)
        await loop.run_in_executor(None, lambda: _save_kr_csv(all_data, revenue))

        data = _build_leaders_data(cap_top, amount_top, revenue)
        _save_cache("kr", data)
        _cache["kr"] = data
        _cache_date["kr"] = date.today()
        logger.info(f"KR 시장 선도주 업데이트 완료: 총 {len(data['all_leaders'])}개")
    except Exception as e:
        logger.error(f"KR 시장 선도주 업데이트 오류: {e}", exc_info=True)
    finally:
        _is_updating["kr"] = False


async def _do_update_us(
    cap_limit: int = DEFAULT_CAP_LIMIT,
    revenue_limit: int = DEFAULT_REVENUE_LIMIT,
    amount_limit: int = DEFAULT_AMOUNT_LIMIT,
    force: bool = False,
):
    """US 시장 선도주 업데이트 (매출은 yfinance 사용)

    Args:
        cap_limit: 시가총액 상위 N개 (기본 150)
        revenue_limit: 매출 상위 N개 (기본 150)
        amount_limit: 거래대금 상위 N개 (기본 300)
        force: True이면 오늘 이미 업데이트된 경우에도 강제 재실행
    """
    global _is_updating, _cache, _cache_date

    # 오늘 이미 업데이트된 캐시가 있으면 스킵 (force=True이면 무시)
    if not force and not _check_needs_update("us"):
        logger.info("US 시장 선도주: 오늘 이미 업데이트됨 — 스킵 (강제 실행하려면 force=true)")
        return

    _is_updating["us"] = True
    try:
        loop = asyncio.get_event_loop()
        logger.info(
            f"US 시장 선도주 업데이트 시작 (NYS·NAS·AMS) "
            f"(시가총액 {cap_limit}, 매출 {revenue_limit}, 거래대금 {amount_limit})..."
        )

        # 시가총액 + 거래대금은 같은 KIS API 사용 (fetch 수는 cap_limit보다 넉넉히)
        fetch_size = max(cap_limit * 2, 200)
        cap_raw = await loop.run_in_executor(None, lambda: _fetch_us_market_cap(fetch_size))
        amount_raw = await loop.run_in_executor(None, lambda: _rank_us_by_trading_amount(cap_raw, amount_limit))

        # 중복 제거 후 tomv(시가총액) 기준 정렬 → 상위 cap_limit
        seen: set[str] = set()
        cap_dedup: list[dict] = []
        for s in sorted(cap_raw, key=lambda x: x.get("tomv", 0), reverse=True):
            if s["code"] not in seen:
                seen.add(s["code"])
                cap_dedup.append({"code": s["code"], "name": s["name"]})
        cap_top = cap_dedup[:cap_limit]

        # 매출 조회 (yfinance) — 시가총액 상위 universe 전수 조회
        rev_universe_size = max(cap_limit * 2, 300)
        rev_universe = cap_dedup[:rev_universe_size]
        name_map = {s["code"]: s["name"] for s in rev_universe}
        all_rev_map: dict[str, int] = await loop.run_in_executor(
            None, lambda: _fetch_us_revenues_all(rev_universe)
        )

        # 상위 revenue_limit개: market leaders 교집합 계산용
        revenue_sorted = sorted(all_rev_map.items(), key=lambda x: x[1], reverse=True)
        revenue_top = [
            {"code": c, "name": name_map.get(c, c), "revenue": v}
            for c, v in revenue_sorted[:revenue_limit]
        ]

        # 전체 revenue: CSV에 모든 조회 성공 종목 기록
        revenue_all = [
            {"code": c, "name": name_map.get(c, c), "revenue": v}
            for c, v in all_rev_map.items()
        ]

        # CSV 저장 (시가총액·거래대금·매출 통합 1개 파일)
        await loop.run_in_executor(None, lambda: _save_us_csv(cap_raw, amount_raw, revenue_all))

        data = _build_leaders_data(cap_top, amount_raw, revenue_top)
        _save_cache("us", data)
        _cache["us"] = data
        _cache_date["us"] = date.today()
        logger.info(f"US 시장 선도주 업데이트 완료: 총 {len(data['all_leaders'])}개")
    except Exception as e:
        logger.error(f"US 시장 선도주 업데이트 오류: {e}", exc_info=True)
    finally:
        _is_updating["us"] = False


# ============================================
# API 엔드포인트
# ============================================


@router.get("/defaults", summary="기본 순위 기준값 조회")
async def get_defaults() -> dict:
    """DEFAULT_CAP_LIMIT / DEFAULT_REVENUE_LIMIT / DEFAULT_AMOUNT_LIMIT 반환"""
    return {
        "cap_limit": DEFAULT_CAP_LIMIT,
        "revenue_limit": DEFAULT_REVENUE_LIMIT,
        "amount_limit": DEFAULT_AMOUNT_LIMIT,
    }


@router.get("/status", response_model=MarketLeadersStatus)
async def get_market_leaders_status(
    market: Market = Query(default="kr", description="시장 구분 (kr: 한국, us: 미국)"),
) -> MarketLeadersStatus:
    """시장 선도주 캐시 상태 조회"""
    cache = _get_cache(market) or _load_cache(market)
    counts: dict = {}
    last_updated = None
    if cache:
        last_updated = cache.get("updated_at")
        counts = {
            "by_market_cap": len(cache.get("by_market_cap", [])),
            "by_trading_amount": len(cache.get("by_trading_amount", [])),
            "by_revenue": len(cache.get("by_revenue", [])),
            "all_leaders": len(cache.get("all_leaders", [])),
        }
    return MarketLeadersStatus(
        is_updating=_is_updating[market],
        last_updated=last_updated,
        needs_update=_check_needs_update(market),
        counts=counts,
    )


@router.post("/update")
async def trigger_update(
    background_tasks: BackgroundTasks,
    market: Market = Query(default="kr", description="시장 구분 (kr: 한국, us: 미국)"),
    cap_limit: int = Query(default=DEFAULT_CAP_LIMIT, ge=1, le=500, description=f"시가총액 상위 N개 (기본 {DEFAULT_CAP_LIMIT})"),
    revenue_limit: int = Query(default=DEFAULT_REVENUE_LIMIT, ge=1, le=500, description=f"매출 상위 N개 — KR 전용 (기본 {DEFAULT_REVENUE_LIMIT})"),
    amount_limit: int = Query(default=DEFAULT_AMOUNT_LIMIT, ge=1, le=1000, description=f"거래대금 상위 N개 (기본 {DEFAULT_AMOUNT_LIMIT})"),
    force: bool = Query(default=False, description="오늘 이미 업데이트된 경우에도 강제 재실행"),
):
    """시장 선도주 업데이트 실행 (백그라운드)

    KIS API 인증이 필요합니다. 완료까지 수 분 소요됩니다.
    - kr: KOSPI 보통주 기준, KIS API 매출 조회 (실패 시 yfinance fallback)
    - us: NYS·NAS·AMS 합산, ETF 제외, 매출은 yfinance 조회
    - force=true: 오늘 이미 업데이트된 경우에도 강제 재실행
    """
    if _is_updating[market]:
        raise HTTPException(status_code=409, detail=f"업데이트가 이미 진행 중입니다 ({market})")
    if not trading_state.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail="KIS API 인증이 필요합니다. 설정에서 로그인하세요.",
        )

    # 오늘 이미 업데이트됐고 force가 아니면 즉시 반환
    if not force and not _check_needs_update(market):
        cache = _get_cache(market) or _load_cache(market)
        return {
            "status": "skipped",
            "market": market,
            "message": f"오늘 이미 업데이트된 데이터가 있습니다 (갱신 시각: {cache.get('updated_at') if cache else '알 수 없음'}). 강제 실행하려면 force=true를 사용하세요.",
        }

    if market == "kr":
        background_tasks.add_task(_do_update_kr, cap_limit, revenue_limit, amount_limit, force)
    else:
        background_tasks.add_task(_do_update_us, cap_limit, revenue_limit, amount_limit, force)
    return {
        "status": "started",
        "market": market,
        "cap_limit": cap_limit,
        "revenue_limit": revenue_limit,
        "amount_limit": amount_limit,
        "message": (
            f"{'한국(KOSPI)' if market == 'kr' else '미국(NYS·NAS·AMS)'} 시장 선도주 업데이트가 시작되었습니다. "
            f"(시가총액 {cap_limit}, 매출 {revenue_limit}, 거래대금 {amount_limit})"
        ),
    }


@router.get("", response_model=MarketLeadersResponse)
async def get_market_leaders(
    market: Market = Query(default="kr", description="시장 구분 (kr: 한국, us: 미국)"),
) -> MarketLeadersResponse:
    """시장 선도주 목록 조회

    데이터가 없으면 /update 엔드포인트로 업데이트를 먼저 실행하세요.
    """
    cache = _get_cache(market) or _load_cache(market)
    if not cache:
        raise HTTPException(
            status_code=404,
            detail=f"{'한국' if market == 'kr' else '미국'} 시장 선도주 데이터가 없습니다. ⚙ 설정에서 업데이트를 실행하세요.",
        )

    def _to_items(items: list[dict], default_reason: Optional[str] = None) -> list[MarketLeaderItem]:
        result = []
        for s in items:
            reasons = s.get("reasons") or ([default_reason] if default_reason else [])
            result.append(MarketLeaderItem(code=s["code"], name=s["name"], reason=reasons))
        return result

    return MarketLeadersResponse(
        market=market,
        updated_at=cache.get("updated_at"),
        total=len(cache.get("all_leaders", [])),
        by_market_cap=_to_items(cache.get("by_market_cap", []), "시가총액"),
        by_trading_amount=_to_items(cache.get("by_trading_amount", []), "거래대금"),
        by_revenue=_to_items(cache.get("by_revenue", []), "매출"),
        all_leaders=_to_items(cache.get("all_leaders", [])),
    )
