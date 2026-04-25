"""MACD-시그널 골든/데드 크로스 전략.

지표 spec: indicators/MACDSignalGoldencross.md, MACDSignalDeadcross.md

진입: MACD가 시그널선을 상향 돌파 (골든크로스)
청산: MACD가 시그널선을 하향 돌파 (데드크로스)
"""

from __future__ import annotations

from typing import Any, Dict

from kis_backtest.strategies.base import BaseStrategy
from kis_backtest.strategies.registry import register
from kis_backtest.core.strategy import StrategyDefinition
from kis_backtest.core.condition import Condition
from kis_backtest.core.risk import RiskManagement
from kis_backtest.dsl.helpers import MACD


@register(
    "macd_signal",
    name="MACD-시그널 골든/데드 크로스",
    category="trend",
    description="MACD가 시그널선을 상향 돌파하면 매수 (골든크로스), 하향 돌파하면 매도 (데드크로스)",
    tags=["macd", "trend", "crossover", "golden_cross", "death_cross"],
)
class MACDSignalStrategy(BaseStrategy):
    """MACD-시그널 골든/데드 크로스 전략

    Parameters:
        fast_period: MACD 단기 기간 (default: 12)
        slow_period: MACD 장기 기간 (default: 26)
        signal_period: 시그널 기간 (default: 9)
        stop_loss_pct: 손절 비율 % (default: 5.0)
        take_profit_pct: 익절 비율 % (default: 15.0)

    Entry Condition (매수):
        MACD.crosses_above(MACD.signal)
        → MACD가 시그널선 아래에서 위로 돌파 (골든크로스)

    Exit Condition (매도):
        MACD.crosses_below(MACD.signal)
        → MACD가 시그널선 위에서 아래로 돌파 (데드크로스)
    """

    PARAM_DEFINITIONS = {
        "fast_period": {"default": 12, "min": 2, "max": 50, "type": "int", "description": "MACD 단기 기간"},
        "slow_period": {"default": 26, "min": 5, "max": 100, "type": "int", "description": "MACD 장기 기간"},
        "signal_period": {"default": 9, "min": 2, "max": 30, "type": "int", "description": "시그널 기간"},
        "stop_loss_pct": {"default": 5.0, "min": 1, "max": 20, "type": "float", "description": "손절 %"},
        "take_profit_pct": {"default": 15.0, "min": 2, "max": 50, "type": "float", "description": "익절 %"},
    }

    buy_signal_name: str = "macd_golden_cross"
    sell_signal_name: str = "macd_dead_cross"

    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 15.0

    def __init__(
        self,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 15.0,
    ):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    @property
    def id(self) -> str:
        return "macd_signal"

    @property
    def name(self) -> str:
        return "MACD-시그널 골든/데드 크로스"

    @property
    def category(self) -> str:
        return "trend"

    @property
    def description(self) -> str:
        return (
            f"MACD({self.fast_period},{self.slow_period},{self.signal_period})"
            "가 시그널 상향돌파 시 매수, 하향돌파 시 매도"
        )

    def indicators(self) -> list:
        alias = "macd_main"
        return [
            MACD(self.fast_period, self.slow_period, self.signal_period, output="value", alias=alias),
            MACD(self.fast_period, self.slow_period, self.signal_period, output="signal", alias=alias),
        ]

    def entry_condition(self) -> Condition:
        """진입: MACD 골든크로스 (MACD가 시그널선 상향 돌파)"""
        alias = "macd_main"
        macd_val = MACD(self.fast_period, self.slow_period, self.signal_period, output="value", alias=alias)
        macd_sig = MACD(self.fast_period, self.slow_period, self.signal_period, output="signal", alias=alias)
        return macd_val.crosses_above(macd_sig)

    def exit_condition(self) -> Condition:
        """청산: MACD 데드크로스 (MACD가 시그널선 하향 돌파)"""
        alias = "macd_main"
        macd_val = MACD(self.fast_period, self.slow_period, self.signal_period, output="value", alias=alias)
        macd_sig = MACD(self.fast_period, self.slow_period, self.signal_period, output="signal", alias=alias)
        return macd_val.crosses_below(macd_sig)

    def risk_management(self) -> RiskManagement:
        return RiskManagement(
            stop_loss_pct=self.stop_loss_pct if self.stop_loss_pct > 0 else None,
            take_profit_pct=self.take_profit_pct if self.take_profit_pct > 0 else None,
        )

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
        )

    def to_lean_params(self) -> Dict[str, Any]:
        alias = "macd_main"
        return {
            alias: {
                "lean_class": "MovingAverageConvergenceDivergence",
                "init": (
                    f"MovingAverageConvergenceDivergence("
                    f"{self.fast_period}, {self.slow_period}, {self.signal_period}, "
                    f"MovingAverageType.Exponential)"
                ),
                "value": f"{alias}.Current.Value",
                "signal": f"{alias}.Signal.Current.Value",
                "warmup": self.slow_period + self.signal_period,
            },
            "entry": {
                "type": "cross_above",
                "indicator1": f"{alias}.value",
                "indicator2": f"{alias}.signal",
                "lean_condition": (
                    f"self.prev_{alias} <= self.prev_{alias}_signal "
                    f"and {alias} > {alias}_signal"
                ),
            },
            "exit": {
                "type": "cross_below",
                "indicator1": f"{alias}.value",
                "indicator2": f"{alias}.signal",
                "lean_condition": (
                    f"self.prev_{alias} >= self.prev_{alias}_signal "
                    f"and {alias} < {alias}_signal"
                ),
            },
        }
