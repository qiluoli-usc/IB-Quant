import unittest

from ib_quant.config import AppConfig, ConfigError
from ib_quant.marketdata.line_budget import estimate_market_data_lines


class MarketDataConfigTests(unittest.TestCase):
    def test_tick_l1_feed_mode_uses_one_line_per_symbol(self):
        self.assertEqual(estimate_market_data_lines(50, "tick_l1"), 50)

    def test_realtime_bar_feed_mode_estimates_bars_plus_quotes(self):
        self.assertEqual(estimate_market_data_lines(50, "realtime_bar"), 100)

    def test_config_loads_feed_mode_and_line_budget(self):
        config = AppConfig.from_mapping(
            {
                "symbols": ["AAPL"],
                "marketdata": {
                    "feed_mode": "tick_l1",
                    "max_market_data_lines": 100,
                    "clock_flush_interval_seconds": 0.5,
                },
            }
        )

        self.assertEqual(config.marketdata.feed_mode, "tick_l1")
        self.assertEqual(config.marketdata.market_data_type, 1)
        self.assertEqual(config.marketdata.max_market_data_lines, 100)
        self.assertEqual(config.marketdata.clock_flush_interval_seconds, 0.5)

    def test_realtime_bar_size_must_be_five_seconds(self):
        with self.assertRaisesRegex(ConfigError, "realtime_bar_size_seconds must be 5"):
            AppConfig.from_mapping({"marketdata": {"realtime_bar_size_seconds": 1}})

    def test_market_data_type_must_be_supported_ib_value(self):
        with self.assertRaisesRegex(ConfigError, "market_data_type must be one of"):
            AppConfig.from_mapping({"marketdata": {"market_data_type": 9}})

    def test_delayed_market_data_requires_tick_l1_feed_mode(self):
        with self.assertRaisesRegex(ConfigError, "Delayed market data requires marketdata.feed_mode=tick_l1"):
            AppConfig.from_mapping({"marketdata": {"feed_mode": "realtime_bar", "market_data_type": 3}})


if __name__ == "__main__":
    unittest.main()
