from __future__ import annotations

import inspect
import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ib_quant.config import MarketDataConfig
from ib_quant.marketdata.bars import MinuteBar, MinuteBarAggregator, RealTimeBar, RollingBarWindow
from ib_quant.risk.safety import MarketSnapshot
from ib_quant.storage.parquet_store import ParquetMinuteBarStore


MinuteCallback = Callable[[MinuteBar, dict[str, list[MinuteBar]], dict[str, MarketSnapshot]], Awaitable[None] | None]


@dataclass(frozen=True)
class SubscriptionHandles:
    realtime_bars: list[Any]
    tickers: dict[str, Any]


class IBRealtimeBarFeed:
    def __init__(
        self,
        ib: Any,
        contracts: dict[str, Any],
        config: MarketDataConfig,
        store: ParquetMinuteBarStore,
    ):
        self.ib = ib
        self.contracts = contracts
        self.config = config
        self.store = store
        self.window = RollingBarWindow(config.rolling_window_bars)
        self.aggregators = {symbol: MinuteBarAggregator(symbol) for symbol in contracts}
        self.tickers: dict[str, Any] = {}
        self._handles: list[Any] = []

    def start(self, on_minute: MinuteCallback) -> SubscriptionHandles:
        for symbol, contract in self.contracts.items():
            self.tickers[symbol] = self.ib.reqMktData(contract, "", False, False)
            bars = self.ib.reqRealTimeBars(
                contract,
                self.config.realtime_bar_size_seconds,
                self.config.what_to_show,
                self.config.use_rth,
            )
            bars.updateEvent += self._make_realtime_handler(symbol, on_minute)
            self._handles.append(bars)
        return SubscriptionHandles(list(self._handles), dict(self.tickers))

    def stop(self) -> None:
        for bars in self._handles:
            try:
                self.ib.cancelRealTimeBars(bars)
            except Exception:
                pass
        for ticker in self.tickers.values():
            try:
                self.ib.cancelMktData(ticker.contract)
            except Exception:
                pass
        self._handles.clear()

    def snapshot(self, symbol: str) -> MarketSnapshot:
        ticker = self.tickers.get(symbol)
        if ticker is None:
            return MarketSnapshot(symbol=symbol, bid=None, ask=None, last=None)
        return MarketSnapshot(
            symbol=symbol,
            bid=_finite_or_none(getattr(ticker, "bid", None)),
            ask=_finite_or_none(getattr(ticker, "ask", None)),
            last=_finite_or_none(getattr(ticker, "last", None)),
            updated_at=getattr(ticker, "time", None),
        )

    def snapshots(self) -> dict[str, MarketSnapshot]:
        return {symbol: self.snapshot(symbol) for symbol in self.contracts}

    def _make_realtime_handler(self, symbol: str, on_minute: MinuteCallback):
        async def emit(completed: MinuteBar) -> None:
            self.store.append(completed)
            self.window.append(completed)
            result = on_minute(completed, self.window.snapshot(), self.snapshots())
            if inspect.isawaitable(result):
                await result

        def handler(bars, has_new_bar: bool) -> None:
            if not has_new_bar or not bars:
                return
            raw = bars[-1]
            completed = self.aggregators[symbol].add(convert_ib_realtime_bar(symbol, raw, self.config))
            if completed is not None:
                asyncio.get_running_loop().create_task(emit(completed))

        return handler


def convert_ib_realtime_bar(symbol: str, raw: Any, config: MarketDataConfig) -> RealTimeBar:
    raw_time = getattr(raw, "time")
    if isinstance(raw_time, datetime):
        timestamp = raw_time if raw_time.tzinfo else raw_time.replace(tzinfo=timezone.utc)
    else:
        timestamp = datetime.fromtimestamp(float(raw_time), tz=timezone.utc)
    return RealTimeBar(
        symbol=symbol,
        time=timestamp,
        open=float(getattr(raw, "open_", getattr(raw, "open", 0.0))),
        high=float(getattr(raw, "high")),
        low=float(getattr(raw, "low")),
        close=float(getattr(raw, "close")),
        volume=float(getattr(raw, "volume", 0.0)) * config.realtime_bar_volume_multiplier,
    )


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
