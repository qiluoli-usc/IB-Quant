from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys

from ib_quant.broker.ib_client import IBBroker
from ib_quant.config import AppConfig
from ib_quant.marketdata.line_budget import estimate_market_data_lines
from ib_quant.runtime import ensure_storage_dirs, validate_symbols


REQUIRED_IMPORTS = ["ib_async", "yfinance", "pandas", "yaml", "pyarrow"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local IB quant setup.")
    parser.add_argument("--config", default="configs/local.yaml")
    parser.add_argument("--connect", action="store_true", help="Also connect to IB and qualify configured stocks.")
    args = parser.parse_args()

    ok = True
    print(f"Python: {sys.executable}")
    for module in REQUIRED_IMPORTS:
        found = importlib.util.find_spec(module) is not None
        print(f"import {module}: {'OK' if found else 'MISSING'}")
        ok = ok and found

    try:
        config = AppConfig.load(args.config)
        config = AppConfig(
            ib=config.ib,
            symbols=validate_symbols(config.symbols),
            strategy=config.strategy,
            risk=config.risk,
            storage=config.storage,
            marketdata=config.marketdata,
        )
        ensure_storage_dirs(config)
        print(f"Config: OK ({len(config.symbols)} symbols)")
        print(f"Trade enabled: {config.risk.trade_enabled}; readonly: {config.risk.readonly}")
        estimated_lines = estimate_market_data_lines(len(config.symbols), config.marketdata.feed_mode)
        print(
            f"Market data feed: {config.marketdata.feed_mode}; "
            f"estimated lines: {estimated_lines}/{config.marketdata.max_market_data_lines}"
        )
        if estimated_lines >= config.marketdata.max_market_data_lines:
            print("Market data warning: estimated usage is at or above configured line budget.")
    except Exception as exc:
        print(f"Config: FAILED ({exc})")
        return 2

    if args.connect:
        try:
            asyncio.run(_check_ib(config))
        except Exception as exc:
            print(f"IB connection: FAILED ({exc})")
            return 3

    if not ok:
        print("Install missing packages with: conda run -n ib-env python -m pip install -r requirements.txt")
        return 1
    return 0


async def _check_ib(config: AppConfig) -> None:
    broker = IBBroker(config.ib)
    status = await broker.connect()
    broker.set_market_data_type(config.marketdata.market_data_type)
    print(f"IB connection: OK account={status.account}")
    if config.risk.expected_account and status.account != config.risk.expected_account:
        raise RuntimeError(
            f"connected account {status.account!r} does not match expected_account {config.risk.expected_account!r}"
        )
    contracts = await broker.qualify_stocks(config.symbols)
    print(f"Contract qualification: OK ({len(contracts)} contracts)")
    broker.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
