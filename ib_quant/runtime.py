from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from ib_quant.broker.ib_client import IBBroker
from ib_quant.config import AppConfig
from ib_quant.execution.executor import TradeExecutor
from ib_quant.marketdata.ib_tick import IBL1TickFeed
from ib_quant.marketdata.ib_realtime import IBRealtimeBarFeed
from ib_quant.marketdata.line_budget import estimate_market_data_lines
from ib_quant.risk.safety import MarketSnapshot, RuntimeState, SafetyGate, NY_TZ
from ib_quant.storage.audit import AuditStore
from ib_quant.storage.parquet_store import ParquetMinuteBarStore
from ib_quant.strategy.loader import StrategyLoader


@dataclass(frozen=True)
class LiveRuntime:
    config: AppConfig

    async def run_forever(self) -> None:
        broker = IBBroker(self.config.ib)
        audit = AuditStore(self.config.storage.audit_db)
        bar_store = ParquetMinuteBarStore(self.config.storage.parquet_root)
        strategy = StrategyLoader().load_from_path(self.config.strategy.path, self.config.strategy.settings)
        safety_gate = SafetyGate(self.config.risk)
        executor = TradeExecutor(broker, audit, safety_gate)

        while True:
            status = await broker.connect_forever()
            broker.set_market_data_type(self.config.marketdata.market_data_type)
            print(f"Connected to IB: account={status.account} clientId={self.config.ib.client_id}")
            if self.config.risk.expected_account and status.account != self.config.risk.expected_account:
                raise RuntimeError(
                    f"Connected account {status.account!r} does not match "
                    f"expected_account {self.config.risk.expected_account!r}"
                )

            contracts = await broker.qualify_stocks(self.config.symbols)
            line_estimate = estimate_market_data_lines(len(contracts), self.config.marketdata.feed_mode)
            print(
                f"Qualified {len(contracts)} contracts. "
                f"feed_mode={self.config.marketdata.feed_mode} estimated_lines={line_estimate}"
            )
            if self.config.marketdata.feed_mode == "tick_l1":
                feed = IBL1TickFeed(broker.ib, contracts, self.config.marketdata, bar_store)
            elif self.config.marketdata.feed_mode == "realtime_bar":
                feed = IBRealtimeBarFeed(broker.ib, contracts, self.config.marketdata, bar_store)
            else:
                raise ValueError(f"Unsupported marketdata.feed_mode: {self.config.marketdata.feed_mode}")

            async def on_minute(completed_bar, bars_by_symbol, snapshots) -> None:
                state = RuntimeState(
                    now=datetime.now(NY_TZ),
                    account=broker.primary_account(),
                    connected=broker.is_connected(),
                    market_data_stale=False,
                    positions=broker.positions(),
                    open_order_symbols=broker.open_order_symbols(),
                )
                context = {
                    "now": state.now,
                    "completed_bar": completed_bar,
                    "snapshots": snapshots,
                    "account": state.account,
                    "positions": state.positions,
                }
                intents = strategy.on_minute(context, bars_by_symbol)
                for intent in intents:
                    snapshot = snapshots.get(intent.symbol) or MarketSnapshot(intent.symbol, None, None, None)
                    result = executor.process_intent(intent, snapshot, state)
                    print(
                        f"{state.now.isoformat()} {intent.strategy_tag} {intent.symbol} "
                        f"{intent.side} {intent.quantity} allowed={result.allowed} "
                        f"reason={result.reason} ib_order_id={result.ib_order_id}"
                    )

            feed.start(on_minute)
            try:
                while broker.is_connected():
                    await asyncio.sleep(1)
            finally:
                feed.stop()
                broker.disconnect()

            print("IB disconnected. Waiting before auto-reconnect...")
            await asyncio.sleep(self.config.ib.reconnect_initial_seconds)


def validate_symbols(symbols: Iterable[str]) -> list[str]:
    normalized = [symbol.upper().strip() for symbol in symbols if symbol and symbol.strip()]
    if not normalized:
        raise ValueError("At least one symbol is required")
    duplicates = sorted({symbol for symbol in normalized if normalized.count(symbol) > 1})
    if duplicates:
        raise ValueError(f"Duplicate symbols in config: {', '.join(duplicates)}")
    return normalized


def ensure_storage_dirs(config: AppConfig) -> None:
    Path(config.storage.root).mkdir(parents=True, exist_ok=True)
    Path(config.storage.audit_db).parent.mkdir(parents=True, exist_ok=True)
    Path(config.storage.parquet_root).mkdir(parents=True, exist_ok=True)
