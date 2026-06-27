from __future__ import annotations


def estimate_market_data_lines(symbol_count: int, feed_mode: str) -> int:
    if symbol_count < 0:
        raise ValueError("symbol_count must be non-negative")
    if feed_mode == "tick_l1":
        return symbol_count
    if feed_mode == "realtime_bar":
        return symbol_count * 2
    raise ValueError(f"Unsupported marketdata.feed_mode: {feed_mode}")
