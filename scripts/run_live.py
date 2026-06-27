from __future__ import annotations

import argparse
import asyncio

from ib_quant.config import AppConfig
from ib_quant.runtime import LiveRuntime, ensure_storage_dirs, validate_symbols


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the live IB minute strategy loop.")
    parser.add_argument("--config", default="configs/local.yaml")
    args = parser.parse_args()

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
    asyncio.run(LiveRuntime(config).run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
