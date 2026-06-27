import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ib_quant.config import AppConfig
from ib_quant.config import ConfigError
from ib_quant.execution.executor import TradeExecutor
from ib_quant.risk.safety import MarketSnapshot, RuntimeState, SafetyConfig, SafetyGate
from ib_quant.storage.audit import AuditStore
from ib_quant.strategy.base import TradeIntent


NY = ZoneInfo("America/New_York")


class FakeBroker:
    def __init__(self):
        self.orders = []

    def place_limit_order(self, intent):
        self.orders.append(intent)
        return 456


class ConfigAndExecutionTests(unittest.TestCase):
    def test_app_config_builds_from_mapping(self):
        config = AppConfig.from_mapping(
            {
                "ib": {"host": "127.0.0.1", "port": 4002, "client_id": 17},
                "symbols": ["aapl", "MSFT"],
                "strategy": {"path": "strategies/example_strategy.py", "settings": {"quantity": 3}},
                "risk": {"expected_account": "TEST_ACCOUNT", "max_spread_pct": 0.002, "midday_no_trade_start": "11:15"},
                "storage": {"root": "data"},
            }
        )

        self.assertEqual(config.ib.port, 4002)
        self.assertFalse(hasattr(config.ib, "expected_account"))
        self.assertEqual(config.risk.expected_account, "TEST_ACCOUNT")
        self.assertEqual(config.symbols, ["AAPL", "MSFT"])
        self.assertEqual(config.risk.max_spread_pct, 0.002)
        self.assertEqual(config.risk.midday_no_trade_start, "11:15")
        self.assertEqual(config.strategy.settings["quantity"], 3)

    def test_legacy_ib_expected_account_is_mapped_to_risk_only(self):
        config = AppConfig.from_mapping(
            {
                "ib": {"host": "127.0.0.1", "port": 4002, "client_id": 17, "expected_account": "TEST_ACCOUNT"},
                "risk": {},
            }
        )

        self.assertFalse(hasattr(config.ib, "expected_account"))
        self.assertEqual(config.risk.expected_account, "TEST_ACCOUNT")

    def test_rejects_trade_enabled_when_ib_connection_is_readonly(self):
        with self.assertRaisesRegex(ConfigError, "ib.readonly=false"):
            AppConfig.from_mapping(
                {
                    "ib": {"readonly": True},
                    "risk": {"trade_enabled": True, "readonly": False},
                }
            )

    def test_executor_places_order_when_safety_allows(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditStore(Path(tmp) / "audit.sqlite3")
            broker = FakeBroker()
            executor = TradeExecutor(broker, audit, SafetyGate(SafetyConfig()))
            intent = TradeIntent("AAPL", "BUY", 2, 100.0, "breakout", "test")

            result = executor.process_intent(
                intent,
                MarketSnapshot("AAPL", bid=99.99, ask=100.01, last=100.0),
                RuntimeState(now=datetime(2026, 6, 1, 10, 0, tzinfo=NY), account="TEST_ACCOUNT"),
            )
            rows = audit.fetch_all("trade_events")

        self.assertTrue(result.allowed)
        self.assertEqual(result.ib_order_id, 456)
        self.assertEqual(len(broker.orders), 1)
        self.assertEqual([row["event_type"] for row in rows], ["signal", "order"])

    def test_executor_records_rejection_without_calling_broker(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit = AuditStore(Path(tmp) / "audit.sqlite3")
            broker = FakeBroker()
            executor = TradeExecutor(
                broker,
                audit,
                SafetyGate(SafetyConfig(midday_no_trade_start="11:30", midday_no_trade_end="13:30")),
            )
            intent = TradeIntent("AAPL", "BUY", 2, 100.0, "breakout", "test")

            result = executor.process_intent(
                intent,
                MarketSnapshot("AAPL", bid=99.99, ask=100.01, last=100.0),
                RuntimeState(now=datetime(2026, 6, 1, 12, 0, tzinfo=NY), account="TEST_ACCOUNT"),
            )
            rows = audit.fetch_all("trade_events")

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "midday_no_trade_window")
        self.assertEqual(len(broker.orders), 0)
        self.assertEqual([row["event_type"] for row in rows], ["signal", "rejection"])


if __name__ == "__main__":
    unittest.main()
