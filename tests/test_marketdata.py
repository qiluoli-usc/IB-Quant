import unittest
from datetime import datetime, timezone

from ib_quant.config import MarketDataConfig
from ib_quant.marketdata.bars import (
    L1Tick,
    L1TickMinuteAggregator,
    MinuteBarAggregator,
    RealTimeBar,
    RollingBarWindow,
)
from ib_quant.marketdata.ib_realtime import convert_ib_realtime_bar


class MarketDataTests(unittest.TestCase):
    def test_aggregates_five_second_bars_into_minute_bar(self):
        aggregator = MinuteBarAggregator("AAPL")

        first = aggregator.add(
            RealTimeBar(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 30, 5, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.5,
                close=100.5,
                volume=10,
            )
        )
        self.assertIsNone(first)

        second = aggregator.add(
            RealTimeBar(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 30, 55, tzinfo=timezone.utc),
                open=100.6,
                high=102.0,
                low=100.2,
                close=101.5,
                volume=15,
            )
        )
        self.assertIsNone(second)

        completed = aggregator.add(
            RealTimeBar(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 31, 0, tzinfo=timezone.utc),
                open=101.6,
                high=102.5,
                low=101.0,
                close=102.0,
                volume=20,
            )
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed.symbol, "AAPL")
        self.assertEqual(completed.time, datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc))
        self.assertEqual(completed.open, 100.0)
        self.assertEqual(completed.high, 102.0)
        self.assertEqual(completed.low, 99.5)
        self.assertEqual(completed.close, 101.5)
        self.assertEqual(completed.volume, 25)

    def test_ib_realtime_bar_volume_uses_configured_multiplier(self):
        class RawBar:
            time = datetime(2026, 6, 1, 13, 30, 5, tzinfo=timezone.utc)
            open_ = 100.0
            high = 101.0
            low = 99.5
            close = 100.5
            volume = 7

        bar = convert_ib_realtime_bar("AAPL", RawBar(), MarketDataConfig(realtime_bar_volume_multiplier=100.0))

        self.assertEqual(bar.volume, 700.0)

    def test_rolling_window_discards_oldest_bars(self):
        window = RollingBarWindow(maxlen=3)

        for minute in range(5):
            window.append(
                RealTimeBar(
                    symbol="MSFT",
                    time=datetime(2026, 6, 1, 13, minute, tzinfo=timezone.utc),
                    open=float(minute),
                    high=float(minute),
                    low=float(minute),
                    close=float(minute),
                    volume=minute,
                ).to_minute_bar()
            )

        bars = window.get("MSFT")
        self.assertEqual(len(bars), 3)
        self.assertEqual([bar.close for bar in bars], [2.0, 3.0, 4.0])

    def test_tick_aggregator_closes_bar_at_clock_boundary(self):
        aggregator = L1TickMinuteAggregator("AAPL")
        aggregator.add(
            L1Tick(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 30, 5, tzinfo=timezone.utc),
                price=100.0,
                size=10,
            )
        )
        aggregator.add(
            L1Tick(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 30, 45, tzinfo=timezone.utc),
                price=101.5,
                size=5,
            )
        )

        completed = aggregator.flush_completed(
            datetime(2026, 6, 1, 13, 31, 0, tzinfo=timezone.utc)
        )

        self.assertIsNotNone(completed)
        self.assertEqual(completed.time, datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc))
        self.assertEqual(completed.open, 100.0)
        self.assertEqual(completed.high, 101.5)
        self.assertEqual(completed.low, 100.0)
        self.assertEqual(completed.close, 101.5)
        self.assertEqual(completed.volume, 15)

    def test_tick_aggregator_completes_previous_minute_when_new_tick_arrives(self):
        aggregator = L1TickMinuteAggregator("AAPL")
        first = aggregator.add(
            L1Tick(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 30, 59, tzinfo=timezone.utc),
                price=100.0,
                size=10,
            )
        )
        second = aggregator.add(
            L1Tick(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 31, 1, tzinfo=timezone.utc),
                price=101.0,
                size=4,
            )
        )

        self.assertIsNone(first)
        self.assertIsNotNone(second)
        self.assertEqual(second.time, datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc))
        current = aggregator.flush()
        self.assertIsNotNone(current)
        self.assertEqual(current.time, datetime(2026, 6, 1, 13, 31, tzinfo=timezone.utc))
        self.assertEqual(current.close, 101.0)


if __name__ == "__main__":
    unittest.main()
