import tempfile
import textwrap
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from ib_quant.marketdata.bars import MinuteBar
from ib_quant.storage.audit import AuditStore
from ib_quant.storage.parquet_store import ParquetMinuteBarStore
from ib_quant.strategy.loader import StrategyLoader


class StrategyAndStorageTests(unittest.TestCase):
    def test_strategy_loader_loads_create_strategy_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            strategy_path = Path(tmp) / "my_strategy.py"
            strategy_path.write_text(
                textwrap.dedent(
                    """
                    from ib_quant.strategy.base import Strategy, TradeIntent

                    class MyStrategy(Strategy):
                        def on_minute(self, context, bars):
                            return [TradeIntent("AAPL", "BUY", 1, 100.0, "demo", "my_strategy")]

                    def create_strategy(settings):
                        return MyStrategy(settings)
                    """
                ),
                encoding="utf-8",
            )

            strategy = StrategyLoader().load_from_path(strategy_path, settings={"x": 1})
            intents = strategy.on_minute(context={}, bars={})

        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0].symbol, "AAPL")

    def test_audit_store_records_signal_rejection_and_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = AuditStore(Path(tmp) / "audit.sqlite3")
            signal_id = store.record_signal("test", "AAPL", "BUY", 10, 100.0, "breakout")
            store.record_rejection(signal_id, "spread_too_wide")
            order_id = store.record_order(signal_id, "BUY", 10, 100.0, ib_order_id=123)

            rows = store.fetch_all("trade_events")

        self.assertEqual(signal_id, 1)
        self.assertEqual(order_id, 3)
        self.assertEqual([row["event_type"] for row in rows], ["signal", "rejection", "order"])

    def test_parquet_store_uses_symbol_and_date_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ParquetMinuteBarStore(Path(tmp))
            bar = MinuteBar(
                symbol="AAPL",
                time=datetime(2026, 6, 1, 13, 30, tzinfo=timezone.utc),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000,
            )

            with patch.object(pd.DataFrame, "to_parquet") as to_parquet:
                path = store.append(bar)

        self.assertEqual(path.name, "bars.parquet")
        self.assertIn("symbol=AAPL", path.parts)
        self.assertIn("date=2026-06-01", path.parts)
        to_parquet.assert_called_once()


if __name__ == "__main__":
    unittest.main()
