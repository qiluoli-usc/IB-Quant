from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ib_quant.config import MarketDataConfig
from ib_quant.marketdata.bars import L1Tick, L1TickMinuteAggregator, MinuteBar, RollingBarWindow
from ib_quant.risk.safety import MarketSnapshot
from ib_quant.storage.parquet_store import ParquetMinuteBarStore


MinuteCallback = Callable[[MinuteBar, dict[str, list[MinuteBar]], dict[str, MarketSnapshot]], Awaitable[None] | None]


@dataclass(frozen=True)
class TickSubscriptionHandles:
    tickers: dict[str, Any]


class IBL1TickFeed:
    """Build local minute bars from IB L1 market-data updates.

    This uses reqMktData, not reqTickByTickData. It is lower-latency and uses
    one top-of-book line per symbol, but it should be validated against broker
    bars before treating it as an official consolidated OHLC feed.
    """

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
        self.aggregators = {symbol: L1TickMinuteAggregator(symbol) for symbol in contracts}
        self.tickers: dict[str, Any] = {}
        self._ticker_symbols: dict[int, str] = {}
        self._last_tick_keys: set[tuple[str, datetime | None, float | None, float | None]] = set()
        self._handler = None
        self._clock_task: asyncio.Task | None = None
        self._on_minute: MinuteCallback | None = None

    def start(self, on_minute: MinuteCallback) -> TickSubscriptionHandles:
        self._on_minute = on_minute
        for symbol, contract in self.contracts.items():
            ticker = self.ib.reqMktData(contract, "", False, False)
            self.tickers[symbol] = ticker
            self._ticker_symbols[id(ticker)] = symbol

        self._handler = self._make_ticker_handler()
        self.ib.pendingTickersEvent += self._handler
        self._clock_task = asyncio.get_running_loop().create_task(self._clock_flush_loop())
        return TickSubscriptionHandles(dict(self.tickers))

    def stop(self) -> None:
        if self._handler is not None:
            try:
                self.ib.pendingTickersEvent -= self._handler
            except Exception:
                pass
            self._handler = None
        if self._clock_task is not None:
            self._clock_task.cancel()
            self._clock_task = None
        for ticker in self.tickers.values():
            try:
                self.ib.cancelMktData(ticker.contract)
            except Exception:
                pass

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

    def _make_ticker_handler(self):
        def handler(tickers) -> None:
            for ticker in tickers:
                symbol = self._ticker_symbols.get(id(ticker))
                if symbol is None:
                    continue
                tick = self._ticker_to_l1_tick(symbol, ticker)
                if tick is None:
                    continue
                completed = self.aggregators[symbol].add(tick)
                if completed is not None:
                    asyncio.get_running_loop().create_task(self._emit(completed))

        return handler

    async def _clock_flush_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.config.clock_flush_interval_seconds)
                now = datetime.now(timezone.utc)
                for aggregator in self.aggregators.values():
                    completed = aggregator.flush_completed(now)
                    if completed is not None:
                        await self._emit(completed)
        except asyncio.CancelledError:
            return

    async def _emit(self, completed: MinuteBar) -> None:
        self.store.append(completed)
        self.window.append(completed)
        if self._on_minute is None:
            return
        result = self._on_minute(completed, self.window.snapshot(), self.snapshots())
        if inspect.isawaitable(result):
            await result

    def _ticker_to_l1_tick(self, symbol: str, ticker: Any) -> L1Tick | None:
        price = _finite_or_none(getattr(ticker, "last", None))
        if price is None or price <= 0:
            return None
        raw_time = getattr(ticker, "time", None)
        if isinstance(raw_time, datetime):
            timestamp = raw_time if raw_time.tzinfo else raw_time.replace(tzinfo=timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)
        size = _finite_or_none(getattr(ticker, "lastSize", None)) or 0.0
        key = (symbol, timestamp, price, size)
        if key in self._last_tick_keys:
            return None
        self._last_tick_keys.add(key)
        if len(self._last_tick_keys) > 10_000:
            self._last_tick_keys.clear()
            self._last_tick_keys.add(key)
        return L1Tick(symbol=symbol, time=timestamp, price=price, size=size)


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number
