from __future__ import annotations

from statistics import fmean

from ib_quant.strategy.base import Strategy, TradeIntent


class ExampleMomentumStrategy(Strategy):
    """Safe example strategy. It does nothing unless settings.enabled is true."""

    def on_minute(self, context, bars):
        if not self.settings.get("enabled", False):
            return []

        symbol = self.settings.get("symbol", "AAPL").upper()
        quantity = int(self.settings.get("quantity", 1))
        lookback = int(self.settings.get("lookback", 20))
        symbol_bars = bars.get(symbol, [])
        if len(symbol_bars) < lookback:
            return []

        recent = symbol_bars[-lookback:]
        average_close = fmean(bar.close for bar in recent)
        latest = recent[-1]
        snapshot = context["snapshots"].get(symbol)
        if snapshot is None or snapshot.ask is None or snapshot.bid is None:
            return []

        if latest.close > average_close:
            return [
                TradeIntent(
                    symbol=symbol,
                    side="BUY",
                    quantity=quantity,
                    limit_price=round(snapshot.ask, 2),
                    reason=f"close_above_{lookback}_bar_average",
                    strategy_tag="example_momentum",
                )
            ]
        return []


def create_strategy(settings):
    return ExampleMomentumStrategy(settings)
