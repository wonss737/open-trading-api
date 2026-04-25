"""삼중밴드 전략.

지표 spec: indicators/BBandsUp.md, EnvelopeUp.md, StarcUpper.md

진입: 볼린저밴드 상단 > 엔벨로프 상단이고 가격이 엔벨로프 상단을 상향 돌파
청산: 가격이 STARC 밴드 상단을 하향 돌파
"""

from __future__ import annotations

from typing import Any, Dict

from kis_backtest.strategies.base import BaseStrategy
from kis_backtest.strategies.registry import register
from kis_backtest.core.strategy import StrategyDefinition
from kis_backtest.core.condition import Condition
from kis_backtest.core.risk import RiskManagement
from kis_backtest.core.indicator import Indicator
from kis_backtest.dsl.helpers import SMA, ATR, BB


@register(
    "three_band",
    name="삼중밴드 전략",
    category="volatility",
    description=(
        "볼린저밴드 상단이 엔벨로프 상단 위에 있고 가격이 엔벨로프 상단을 상향돌파 시 매수, "
        "Envelope 상단 또는 STARC 상단 하향돌파 시 매도"
    ),
    tags=["bollinger", "envelope", "starc", "band", "three_band"],
)
class ThreeBandStrategy(BaseStrategy):
    """삼중밴드 전략

    Parameters:
        bb_period: 볼린저밴드 이평 기간 (default: 20)
        bb_std: 볼린저밴드 표준편차 배수 (default: 2.0)
        env_period: 엔벨로프 이평 기간 (default: 20)
        env_pct: 엔벨로프 상단 비율 % (default: 6.0)
        starc_ma_period: STARC 이평 기간 (default: 6)
        starc_atr_period: STARC ATR 기간 (default: 15)
        starc_constant: STARC 상단 배수 (default: 2.0)
        stop_loss_pct: 손절 비율 % (default: 5.0)

    Entry Condition (매수):
        BBandsUp > EnvelopeUp AND price crosses above EnvelopeUp
        → 볼린저밴드 상단 > 엔벨로프 상단이고 가격이 엔벨로프 상단을 위로 돌파

    Exit Condition (매도):
        price crosses below EnvelopeUpper OR price crosses below StarcUpper
        → 가격이 Envelope 상단 또는 STARC 상단을 아래로 돌파
    """

    PARAM_DEFINITIONS = {
        "bb_period": {"default": 20, "min": 5, "max": 60, "type": "int", "description": "볼린저밴드 기간"},
        "bb_std": {"default": 2.0, "min": 0.5, "max": 4.0, "type": "float", "description": "볼린저밴드 표준편차 배수"},
        "env_period": {"default": 20, "min": 5, "max": 60, "type": "int", "description": "엔벨로프 이평 기간"},
        "env_pct": {"default": 6.0, "min": 0.5, "max": 20.0, "type": "float", "description": "엔벨로프 상단 비율 (%)"},
        "starc_ma_period": {"default": 6, "min": 2, "max": 30, "type": "int", "description": "STARC 이평 기간"},
        "starc_atr_period": {"default": 15, "min": 5, "max": 30, "type": "int", "description": "STARC ATR 기간"},
        "starc_constant": {"default": 2.0, "min": 0.5, "max": 4.0, "type": "float", "description": "STARC 상단 배수"},
        "stop_loss_pct": {"default": 5.0, "min": 1, "max": 20, "type": "float", "description": "손절 %"},
    }

    buy_signal_name: str = "envelope_upper_cross"
    sell_signal_name: str = "envelope_or_starc_upper_break"

    bb_period: int = 20
    bb_std: float = 2.0
    env_period: int = 20
    env_pct: float = 6.0
    starc_ma_period: int = 6
    starc_atr_period: int = 15
    starc_constant: float = 2.0
    stop_loss_pct: float = 5.0

    def __init__(
        self,
        bb_period: int = 20,
        bb_std: float = 2.0,
        env_period: int = 20,
        env_pct: float = 6.0,
        starc_ma_period: int = 6,
        starc_atr_period: int = 15,
        starc_constant: float = 2.0,
        stop_loss_pct: float = 5.0,
    ):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.env_period = env_period
        self.env_pct = env_pct
        self.starc_ma_period = starc_ma_period
        self.starc_atr_period = starc_atr_period
        self.starc_constant = starc_constant
        self.stop_loss_pct = stop_loss_pct

    @property
    def id(self) -> str:
        return "three_band"

    @property
    def name(self) -> str:
        return "삼중밴드 전략"

    @property
    def category(self) -> str:
        return "volatility"

    @property
    def description(self) -> str:
        return (
            f"BB({self.bb_period},{self.bb_std}) 상단 > Envelope({self.env_period},{self.env_pct}%) 상단이고 "
            f"엔벨로프 상단 상향돌파 시 매수, STARC({self.starc_ma_period},{self.starc_atr_period}) 상단 하향돌파 시 매도"
        )

    def indicators(self) -> list:
        """사용 지표: BB(upper), SMA(envelope), SMA(STARC), ATR(STARC), 플래그 2개"""
        bb = BB(self.bb_period, self.bb_std)
        return [
            bb.upper,
            SMA(self.env_period, alias="sma_env"),
            SMA(self.starc_ma_period, alias="sma_starc"),
            ATR(self.starc_atr_period, alias="atr_starc"),
            # 커스텀 로직이 이 플래그 값을 덮어씀
            Indicator("consecutive", {"direction": "up"}, alias="three_band_entry"),
            Indicator("consecutive", {"direction": "up"}, alias="three_band_exit"),
        ]

    def entry_condition(self) -> Condition:
        """진입: three_band_entry 플래그 > 0 (커스텀 로직에서 설정)"""
        return Indicator("consecutive", {"direction": "up"}, alias="three_band_entry") > 0

    def exit_condition(self) -> Condition:
        """청산: three_band_exit 플래그 > 0 (커스텀 로직에서 설정)"""
        return Indicator("consecutive", {"direction": "up"}, alias="three_band_exit") > 0

    def risk_management(self) -> RiskManagement:
        return RiskManagement(
            stop_loss_pct=self.stop_loss_pct if self.stop_loss_pct > 0 else None,
        )

    def get_custom_lean_code(self) -> str:
        """삼중밴드 조건 계산 및 플래그 설정

        indicator_values 이후, entry/exit 조건 평가 이전에 실행됩니다.
        three_band_entry / three_band_exit 로컬 변수를 직접 덮어씁니다.
        """
        bb_alias = f"bb_{self.bb_period}"
        return f'''
            # === 삼중밴드 조건 계산 ===
            bb_upper_val = self.indicators[symbol]['{bb_alias}'].UpperBand.Current.Value
            sma_env_val = self.indicators[symbol]['sma_env'].Current.Value
            sma_starc_val = self.indicators[symbol]['sma_starc'].Current.Value
            atr_val = self.indicators[symbol]['atr_starc'].Current.Value

            # EnvelopeUp = SMA * (1 + pct/100)
            env_upper = sma_env_val * (1.0 + {self.env_pct} / 100.0) if sma_env_val > 0 else 0.0

            # StarcUpper = SMA + ATR * constant
            starc_upper = sma_starc_val + atr_val * {self.starc_constant} if sma_starc_val > 0 else 0.0

            prev_price_tb = self.prev_values[symbol].get('price', price)
            prev_env_upper = self.prev_values[symbol].get('env_upper', env_upper)
            prev_starc_upper = self.prev_values[symbol].get('starc_upper', starc_upper)

            # 매수: BB상단 > Envelope상단  AND  가격이 Envelope상단을 상향 돌파
            three_band_entry = 1.0 if (
                env_upper > 0 and
                bb_upper_val > env_upper and
                prev_price_tb <= prev_env_upper and
                price > env_upper
            ) else 0.0

            # 매도: Envelope 상단 하향 돌파 OR STARC 상단 하향 돌파
            env_cross_below = (
                env_upper > 0 and
                prev_price_tb >= prev_env_upper and
                price < env_upper
            )
            starc_cross_below = (
                starc_upper > 0 and
                prev_price_tb >= prev_starc_upper and
                price < starc_upper
            )
            three_band_exit = 1.0 if (env_cross_below or starc_cross_below) else 0.0

            # 다음 봉 비교를 위해 저장
            self.prev_values[symbol]['env_upper'] = env_upper
            self.prev_values[symbol]['starc_upper'] = starc_upper'''

    def build(self) -> StrategyDefinition:
        return StrategyDefinition(
            id=self.id,
            name=self.name,
            category=self.category,
            description=self.description,
            indicators=[ind.to_dict() for ind in self.indicators()],
            entry=self.entry_condition().to_dict(),
            exit=self.exit_condition().to_dict(),
            risk_management=self.risk_management().to_dict(),
            params=self._build_params(),
            metadata={"custom_logic": True},
        )
