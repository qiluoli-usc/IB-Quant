from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Deque


@dataclass(frozen=True)
class MinuteBar:
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["time"] = self.time.isoformat()
        return data


@dataclass(frozen=True)
class RealTimeBar:
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_minute_bar(self) -> MinuteBar:
        minute = self.time.replace(second=0, microsecond=0)
        return MinuteBar(
            symbol=self.symbol,
            time=minute,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


@dataclass(frozen=True)
class L1Tick:
    symbol: str
    time: datetime
    price: float
    size: float = 0.0


class MinuteBarAggregator:
    """Aggregate a stream of five-second bars into completed one-minute bars."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._current: MinuteBar | None = None

    def add(self, bar: RealTimeBar) -> MinuteBar | None:
        if bar.symbol != self.symbol:
            raise ValueError(f"Aggregator for {self.symbol} received {bar.symbol}")

        incoming = bar.to_minute_bar()
        if self._current is None:
            self._current = incoming
            return None

        if incoming.time < self._current.time:
            return None

        if incoming.time == self._current.time:
            self._current = MinuteBar(
                symbol=self.symbol,
                time=self._current.time,
                open=self._current.open,
                high=max(self._current.high, incoming.high),
                low=min(self._current.low, incoming.low),
                close=incoming.close,
                volume=self._current.volume + incoming.volume,
            )
            return None

        completed = self._current
        self._current = incoming
        return completed

    def flush(self) -> MinuteBar | None:
        completed = self._current
        self._current = None
        return completed


class L1TickMinuteAggregator:
    """Aggregate L1 last-price updates into local one-minute bars."""

    def __init__(self, symbol: str):
        self.symbol = symbol
        self._current: MinuteBar | None = None

    def add(self, tick: L1Tick) -> MinuteBar | None:
        if tick.symbol != self.symbol:
            raise ValueError(f"Aggregator for {self.symbol} received {tick.symbol}")
        if tick.price <= 0:
            return None

        incoming = MinuteBar(
            symbol=tick.symbol,
            time=tick.time.replace(second=0, microsecond=0),
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            volume=max(tick.size, 0.0),
        )
        if self._current is None:
            self._current = incoming
            return None

        if incoming.time < self._current.time:
            return None

        if incoming.time == self._current.time:
            self._current = MinuteBar(
                symbol=self.symbol,
                time=self._current.time,
                open=self._current.open,
                high=max(self._current.high, incoming.high),
                low=min(self._current.low, incoming.low),
                close=incoming.close,
                volume=self._current.volume + incoming.volume,
            )
            return None

        completed = self._current
        self._current = incoming
        return completed

    def flush_completed(self, now: datetime) -> MinuteBar | None:
        if self._current is None:
            return None
        current_minute = now.replace(second=0, microsecond=0)
        if self._current.time >= current_minute:
            return None
        return self.flush()

    def flush(self) -> MinuteBar | None:
        completed = self._current
        self._current = None
        return completed


class RollingBarWindow:
    """Per-symbol bounded in-memory minute-bar cache."""

    def __init__(self, maxlen: int = 120):
        if maxlen <= 0:
            raise ValueError("maxlen must be positive")
        self.maxlen = maxlen
        self._bars: dict[str, Deque[MinuteBar]] = defaultdict(lambda: deque(maxlen=maxlen))

    def append(self, bar: MinuteBar) -> None:
        self._bars[bar.symbol].append(bar)

    def get(self, symbol: str) -> list[MinuteBar]:
        return list(self._bars.get(symbol, ()))

    def latest(self, symbol: str) -> MinuteBar | None:
        bars = self._bars.get(symbol)
        if not bars:
            return None
        return bars[-1]

    def snapshot(self) -> dict[str, list[MinuteBar]]:
        return {symbol: list(bars) for symbol, bars in self._bars.items()}
