from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Mapping
from zoneinfo import ZoneInfo

from ib_quant.strategy.base import TradeIntent


NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    bid: float | None
    ask: float | None
    last: float | None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RuntimeState:
    now: datetime
    account: str | None
    connected: bool = True
    market_data_stale: bool = False
    daily_order_count: int = 0
    positions: Mapping[str, int] = field(default_factory=dict)
    open_order_symbols: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SafetyConfig:
    expected_account: str | None = None
    trade_enabled: bool = True
    readonly: bool = False
    midday_no_trade_enabled: bool = True
    midday_no_trade_start: str = "11:30"
    midday_no_trade_end: str = "13:30"
    max_spread_pct: float = 0.003
    max_order_quantity: int = 1_000
    max_daily_orders: int = 100
    block_if_symbol_has_open_order: bool = True


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


class SafetyGate:
    def __init__(self, config: SafetyConfig):
        self.config = config
        self._accepted_keys: set[tuple[str, str, str, datetime]] = set()

    def evaluate(
        self,
        intent: TradeIntent,
        snapshot: MarketSnapshot,
        state: RuntimeState,
    ) -> SafetyDecision:
        if not self.config.trade_enabled or self.config.readonly:
            return SafetyDecision(False, "trading_disabled")
        if self.config.expected_account and state.account != self.config.expected_account:
            return SafetyDecision(False, "account_mismatch")
        if not state.connected:
            return SafetyDecision(False, "ib_disconnected")
        if state.market_data_stale:
            return SafetyDecision(False, "market_data_stale")
        if self._is_midday_no_trade(state.now):
            return SafetyDecision(False, "midday_no_trade_window")
        if intent.quantity > self.config.max_order_quantity:
            return SafetyDecision(False, "order_size_exceeds_limit")
        if state.daily_order_count >= self.config.max_daily_orders:
            return SafetyDecision(False, "daily_order_limit")
        if self.config.block_if_symbol_has_open_order and intent.symbol in state.open_order_symbols:
            return SafetyDecision(False, "open_order_exists")
        if self._spread_pct(snapshot) > self.config.max_spread_pct:
            return SafetyDecision(False, "spread_too_wide")
        if self._duplicate_key(intent, state.now) in self._accepted_keys:
            return SafetyDecision(False, "duplicate_order")
        return SafetyDecision(True, "allowed")

    def record_accepted(self, intent: TradeIntent, state: RuntimeState) -> None:
        self._accepted_keys.add(self._duplicate_key(intent, state.now))

    def _is_midday_no_trade(self, now: datetime) -> bool:
        if not self.config.midday_no_trade_enabled:
            return False
        local_now = now.astimezone(NY_TZ) if now.tzinfo else now.replace(tzinfo=NY_TZ)
        start = _parse_hhmm(self.config.midday_no_trade_start)
        end = _parse_hhmm(self.config.midday_no_trade_end)
        current = local_now.time().replace(second=0, microsecond=0)
        return start <= current < end

    def _duplicate_key(self, intent: TradeIntent, now: datetime) -> tuple[str, str, str, datetime]:
        local_now = now.astimezone(NY_TZ) if now.tzinfo else now.replace(tzinfo=NY_TZ)
        minute = local_now.replace(second=0, microsecond=0)
        return (intent.strategy_tag, intent.symbol, intent.side, minute)

    @staticmethod
    def _spread_pct(snapshot: MarketSnapshot) -> float:
        if snapshot.bid is None or snapshot.ask is None:
            return float("inf")
        if snapshot.bid <= 0 or snapshot.ask <= 0 or snapshot.ask < snapshot.bid:
            return float("inf")
        mid = (snapshot.bid + snapshot.ask) / 2
        if mid <= 0:
            return float("inf")
        return (snapshot.ask - snapshot.bid) / mid


def _parse_hhmm(value: str) -> time:
    hour_text, minute_text = value.split(":", maxsplit=1)
    return time(hour=int(hour_text), minute=int(minute_text))
