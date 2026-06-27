import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from ib_quant.risk.safety import (
    MarketSnapshot,
    RuntimeState,
    SafetyConfig,
    SafetyGate,
)
from ib_quant.strategy.base import TradeIntent


NY = ZoneInfo("America/New_York")


def intent(symbol="AAPL", side="BUY", quantity=10, price=100.0):
    return TradeIntent(
        symbol=symbol,
        side=side,
        quantity=quantity,
        limit_price=price,
        reason="unit test",
        strategy_tag="test",
    )


class SafetyGateTests(unittest.TestCase):
    def test_blocks_trades_during_midday_no_trade_window(self):
        gate = SafetyGate(SafetyConfig(midday_no_trade_start="11:30", midday_no_trade_end="13:30"))
        decision = gate.evaluate(
            intent(),
            MarketSnapshot(symbol="AAPL", bid=99.99, ask=100.01, last=100.0),
            RuntimeState(now=datetime(2026, 6, 1, 12, 0, tzinfo=NY), account="TEST_ACCOUNT"),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "midday_no_trade_window")

    def test_blocks_trades_when_spread_is_too_wide(self):
        gate = SafetyGate(SafetyConfig(max_spread_pct=0.001))
        decision = gate.evaluate(
            intent(),
            MarketSnapshot(symbol="AAPL", bid=99.0, ask=101.0, last=100.0),
            RuntimeState(now=datetime(2026, 6, 1, 10, 0, tzinfo=NY), account="TEST_ACCOUNT"),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "spread_too_wide")

    def test_blocks_duplicate_order_for_same_symbol_minute_side_and_strategy(self):
        gate = SafetyGate(SafetyConfig())
        state = RuntimeState(now=datetime(2026, 6, 1, 10, 0, 10, tzinfo=NY), account="TEST_ACCOUNT")
        snapshot = MarketSnapshot(symbol="AAPL", bid=99.99, ask=100.01, last=100.0)

        first = gate.evaluate(intent(), snapshot, state)
        self.assertTrue(first.allowed)
        gate.record_accepted(intent(), state)

        duplicate = gate.evaluate(intent(), snapshot, state)
        self.assertFalse(duplicate.allowed)
        self.assertEqual(duplicate.reason, "duplicate_order")

    def test_blocks_when_expected_account_does_not_match(self):
        gate = SafetyGate(SafetyConfig(expected_account="OTHER_ACCOUNT"))
        decision = gate.evaluate(
            intent(),
            MarketSnapshot(symbol="AAPL", bid=99.99, ask=100.01, last=100.0),
            RuntimeState(now=datetime(2026, 6, 1, 10, 0, tzinfo=NY), account="TEST_ACCOUNT"),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "account_mismatch")


if __name__ == "__main__":
    unittest.main()
