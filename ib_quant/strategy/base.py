from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    side: str
    quantity: int
    limit_price: float
    reason: str
    strategy_tag: str

    def __post_init__(self) -> None:
        side = self.side.upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.limit_price <= 0:
            raise ValueError("limit_price must be positive")
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "symbol", self.symbol.upper())


class Strategy:
    """Base class for user strategies."""

    def __init__(self, settings: Mapping[str, Any] | None = None):
        self.settings = dict(settings or {})

    def on_minute(self, context: Mapping[str, Any], bars: Mapping[str, Any]) -> list[TradeIntent]:
        raise NotImplementedError
