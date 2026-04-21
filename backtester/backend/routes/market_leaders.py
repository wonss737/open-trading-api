"""시장 선도주 API 라우터

시가총액 상위 150, 매출 상위 150, 거래대금 상위 300 기준으로 시장 선도주를 선정합니다.
한국 (KOSPI) / 미국 (NASDAQ·NYSE·AMEX) 시장을 별도 지원합니다.
결과는 .master/market_leaders_{kr|us}.json 에 캐시되며 매일 갱신이 필요합니다.
"""
import asyncio
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
    cache = _get_cache(market)
    if cache is None:
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


def _fetch_kr_market_cap(limit: int = 300) -> list[dict]:
    """한국 KOSPI 시가총액 상위 종목 (FHPST01740000)
    fid_div_cls_code=1 (보통주) → ETF/펀드/우선주 자동 제외
    fid_input_iscd=0001 → 거래소(KOSPI)만
    """
    stocks: list[dict] = []
    tr_cont = ""
    while len(stocks) < limit:
        params = {
            "fid_input_price_2": "",
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20174",
            "fid_div_cls_code": "1",       # 보통주
            "fid_input_iscd": "0001",      # 거래소 (KOSPI)
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_input_price_1": "",
            "fid_vol_cnt": "",
        }
        res = ka._url_fetch(
            "/uapi/domestic-stock/v1/ranking/market-cap",
            "FHPST01740000", tr_cont, params,
        )
        if not res.isOK():
            logger.warning(f"KR 시가총액 API 오류: {res.getErrorMessage()}")
            break
        output = res.getBody().output or []
        for row in (output if isinstance(output, list) else []):
            code = str(row.get("mksc_shrn_iscd", "") if isinstance(row, dict) else "").strip()
            name = str(row.get("hts_kor_isnm", "") if isinstance(row, dict) else "").strip()
            if code and name and len(code) == 6 and code.isdigit():
                stocks.append({"code": code, "name": name})
            if len(stocks) >= limit:
                break
        tr_cont = res.getHeader().tr_cont
        if tr_cont != "M" or len(stocks) >= limit:
            break
        time.sleep(0.2)
    logger.info(f"KR 시가총액 조회: {len(stocks)}개")
    return stocks[:limit]


def _fetch_kr_trading_amount(limit: int = 300) -> list[dict]:
    """한국 KOSPI 거래대금 상위 종목 (FHPST01710000, 거래금액순)"""
    stocks: list[dict] = []
    tr_cont = ""
    while len(stocks) < limit:
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": "0001",      # 거래소 (KOSPI)
            "FID_DIV_CLS_CODE": "1",       # 보통주
            "FID_BLNG_CLS_CODE": "3",      # 거래금액순
            "FID_TRGT_CLS_CODE": "111111111",
            "FID_TRGT_EXLS_CLS_CODE": "0000000000",
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": "",
        }
        res = ka._url_fetch(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000", tr_cont, params,
        )
        if not res.isOK():
            logger.warning(f"KR 거래대금 API 오류: {res.getErrorMessage()}")
            break
        output = res.getBody().output or []
        for row in (output if isinstance(output, list) else []):
            code = str(row.get("mksc_shrn_iscd", "") if isinstance(row, dict) else "").strip()
            name = str(row.get("hts_kor_isnm", "") if isinstance(row, dict) else "").strip()
            if code and name and len(code) == 6 and code.isdigit():
                stocks.append({"code": code, "name": name})
            if len(stocks) >= limit:
                break
        tr_cont = res.getHeader().tr_cont
        if tr_cont != "M" or len(stocks) >= limit:
            break
        time.sleep(0.2)
    logger.info(f"KR 거래대금 조회: {len(stocks)}개")
    return stocks[:limit]


def _fetch_kr_revenue_for_stock(code: str) -> Optional[int]:
    """단일 KOSPI 종목의 최근 연간 매출액 조회 (FHKST66430200)"""
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
        if not res.isOK():
            return None
        output = res.getBody().output
        if not output:
            return None
        # output이 list면 첫 번째(가장 최근 연도), 아니면 그대로
        first = output[0] if isinstance(output, list) else output
        sale = (first.get("sale_account", "") if isinstance(first, dict)
                else getattr(first, "sale_account", "") or "")
        return _parse_revenue(sale)
    except Exception as e:
        logger.debug(f"KR 매출 조회 오류 ({code}): {e}")
        return None


def _fetch_kr_revenue_leaders(universe: list[dict], limit: int = 150) -> list[dict]:
    """KOSPI universe 기반 매출 상위 종목 배치 조회"""
    revenues: list[tuple[dict, int]] = []
    for i, stock in enumerate(universe):
        rev = _fetch_kr_revenue_for_stock(stock["code"])
        if rev is not None and rev > 0:
            revenues.append((stock, rev))
        if (i + 1) % 50 == 0:
            logger.info(f"KR 매출 조회 진행: {i + 1}/{len(universe)}")
        time.sleep(0.1)
    revenues.sort(key=lambda x: x[1], reverse=True)
    result = [s for s, _ in revenues[:limit]]
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
    """해외주식 시가총액순위 (HHDFS76350100) - 단일 거래소"""
    stocks: list[dict] = []
    tr_cont = ""
    keyb = ""
    depth = 0
    while len(stocks) < limit and depth < 10:
        params = {
            "EXCD": excd,
            "VOL_RANG": "0",   # 전체
            "KEYB": keyb,
            "AUTH": "",
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
                stocks.append({"code": symb, "name": name, "exchange": excd})
            if len(stocks) >= limit:
                break
        tr_cont = res.getHeader().tr_cont
        # output1에서 KEYB 추출
        output1 = res.getBody().output1
        if isinstance(output1, dict):
            keyb = output1.get("keyb", "") or ""
        elif hasattr(output1, "keyb"):
            keyb = getattr(output1, "keyb", "") or ""
        if tr_cont not in ("M", "F") or len(stocks) >= limit:
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


def _rank_us_by_trading_amount(stocks: list[dict], limit: int = 300) -> list[dict]:
    """US market cap API에서 가져온 종목을 거래대금(tamt) 기준 재정렬"""
    # 거래대금은 별도 API 호출 없이 market_cap API의 tamt 필드를 활용
    # 현재 _fetch_us_market_cap_for_excd가 tamt를 반환하지 않으므로
    # tamt 포함 버전을 사용한다
    ranked: list[dict] = []
    tr_cont = ""
    for excd, _ in _US_EXCHANGES:
        keyb = ""
        depth = 0
        while depth < 10:
            params = {
                "EXCD": excd,
                "VOL_RANG": "0",
                "KEYB": keyb,
                "AUTH": "",
            }
            res = ka._url_fetch(
                "/uapi/overseas-stock/v1/ranking/market-cap",
                "HHDFS76350100", tr_cont, params,
            )
            if not res.isOK():
                break
            output2 = res.getBody().output2 or []
            for row in (output2 if isinstance(output2, list) else []):
                symb = str(row.get("symb", "") if isinstance(row, dict) else "").strip()
                name = str(row.get("name", "") if isinstance(row, dict) else "").strip()
                tamt_raw = row.get("tamt", "0") if isinstance(row, dict) else "0"
                try:
                    tamt = float(str(tamt_raw).replace(",", "") or "0")
                except ValueError:
                    tamt = 0.0
                if symb and name and not _is_us_etf(name):
                    ranked.append({"code": symb, "name": name, "exchange": excd, "tamt": tamt})
            output1 = res.getBody().output1
            if isinstance(output1, dict):
                keyb = output1.get("keyb", "") or ""
            elif hasattr(output1, "keyb"):
                keyb = getattr(output1, "keyb", "") or ""
            tr_cont = res.getHeader().tr_cont
            if tr_cont not in ("M", "F"):
                break
            depth += 1
            time.sleep(0.2)
        time.sleep(0.3)

    ranked.sort(key=lambda x: x.get("tamt", 0), reverse=True)
    result = [{"code": s["code"], "name": s["name"]} for s in ranked[:limit]]
    logger.info(f"US 거래대금 조회: {len(result)}개")
    return result


# ============================================
# 백그라운드 업데이트 작업
# ============================================


def _build_leaders_data(
    cap: list[dict],
    amount: list[dict],
    revenue: list[dict],
) -> dict:
    """3개 리스트를 합산하여 all_leaders 구성"""
    all_leaders: dict[str, dict] = {}

    def _add(stocks: list[dict], reason: str):
        for s in stocks:
            code = s["code"]
            if code not in all_leaders:
                all_leaders[code] = {"code": code, "name": s["name"], "reasons": []}
            if reason not in all_leaders[code]["reasons"]:
                all_leaders[code]["reasons"].append(reason)

    _add(cap, "시가총액")
    _add(amount, "거래대금")
    _add(revenue, "매출")

    return {
        "updated_at": datetime.now().isoformat(),
        "by_market_cap": [{"code": s["code"], "name": s["name"]} for s in cap],
        "by_trading_amount": [{"code": s["code"], "name": s["name"]} for s in amount],
        "by_revenue": [{"code": s["code"], "name": s["name"]} for s in revenue],
        "all_leaders": [
            {"code": v["code"], "name": v["name"], "reasons": v["reasons"]}
            for v in all_leaders.values()
        ],
    }


async def _do_update_kr():
    global _is_updating, _cache, _cache_date
    _is_updating["kr"] = True
    try:
        loop = asyncio.get_event_loop()
        logger.info("KR 시장 선도주 업데이트 시작...")

        cap_raw = await loop.run_in_executor(None, lambda: _fetch_kr_market_cap(300))
        amount_raw = await loop.run_in_executor(None, lambda: _fetch_kr_trading_amount(300))
        revenue = await loop.run_in_executor(None, lambda: _fetch_kr_revenue_leaders(cap_raw, 150))

        data = _build_leaders_data(cap_raw[:150], amount_raw[:300], revenue)
        _save_cache("kr", data)
        _cache["kr"] = data
        _cache_date["kr"] = date.today()
        logger.info(f"KR 시장 선도주 업데이트 완료: 총 {len(data['all_leaders'])}개")
    except Exception as e:
        logger.error(f"KR 시장 선도주 업데이트 오류: {e}", exc_info=True)
    finally:
        _is_updating["kr"] = False


async def _do_update_us():
    global _is_updating, _cache, _cache_date
    _is_updating["us"] = True
    try:
        loop = asyncio.get_event_loop()
        logger.info("US 시장 선도주 업데이트 시작 (NYS·NAS·AMS)...")

        # 시가총액 + 거래대금은 같은 API 사용
        cap_raw = await loop.run_in_executor(None, lambda: _fetch_us_market_cap(200))
        amount_raw = await loop.run_in_executor(None, lambda: _rank_us_by_trading_amount(cap_raw, 300))

        # 중복 제거 후 시가총액 상위 150
        seen: set[str] = set()
        cap_dedup: list[dict] = []
        for s in cap_raw:
            if s["code"] not in seen:
                seen.add(s["code"])
                cap_dedup.append({"code": s["code"], "name": s["name"]})
        cap_top150 = cap_dedup[:150]

        # US 매출 데이터는 KIS API에서 제공하지 않으므로 빈 리스트
        data = _build_leaders_data(cap_top150, amount_raw, [])
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
):
    """시장 선도주 업데이트 실행 (백그라운드)

    KIS API 인증이 필요합니다. 완료까지 수 분 소요됩니다.
    - kr: KOSPI 보통주 기준, 매출 조회 포함
    - us: NYS·NAS·AMS 합산, ETF 제외 (매출 데이터 미제공)
    """
    if _is_updating[market]:
        raise HTTPException(status_code=409, detail=f"업데이트가 이미 진행 중입니다 ({market})")
    if not trading_state.is_authenticated:
        raise HTTPException(
            status_code=401,
            detail="KIS API 인증이 필요합니다. 설정에서 로그인하세요.",
        )
    task = _do_update_kr if market == "kr" else _do_update_us
    background_tasks.add_task(task)
    return {
        "status": "started",
        "market": market,
        "message": f"{'한국(KOSPI)' if market == 'kr' else '미국(NYS·NAS·AMS)'} 시장 선도주 업데이트가 시작되었습니다.",
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
