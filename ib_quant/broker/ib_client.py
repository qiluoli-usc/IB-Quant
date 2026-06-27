from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from ib_quant.config import IBConfig
from ib_quant.strategy.base import TradeIntent


@dataclass(frozen=True)
class ConnectionStatus:
    connected: bool
    account: str | None


class IBBroker:
    def __init__(self, config: IBConfig):
        try:
            from ib_async import IB
        except ImportError as exc:
            raise RuntimeError("ib_async is required. Activate ib-env before running live scripts.") from exc

        self.config = config
        self.ib = IB()
        self.contracts: dict[str, Any] = {}

    async def connect(self) -> ConnectionStatus:
        await self.ib.connectAsync(
            self.config.host,
            self.config.port,
            clientId=self.config.client_id,
            timeout=self.config.connect_timeout_seconds,
            readonly=self.config.readonly,
            raiseSyncErrors=True,
        )
        return ConnectionStatus(self.ib.isConnected(), self.primary_account())

    async def connect_forever(self) -> ConnectionStatus:
        delay = self.config.reconnect_initial_seconds
        while True:
            try:
                return await self.connect()
            except Exception:
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.config.reconnect_max_seconds)

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()

    def is_connected(self) -> bool:
        return bool(self.ib.isConnected())

    def primary_account(self) -> str | None:
        accounts = self.ib.managedAccounts()
        return accounts[0] if accounts else None

    def set_market_data_type(self, market_data_type: int) -> None:
        self.ib.reqMarketDataType(market_data_type)

    async def qualify_stocks(self, symbols: list[str]) -> dict[str, Any]:
        from ib_async import Stock

        contracts = [Stock(symbol, "SMART", "USD") for symbol in symbols]
        qualified = await self.ib.qualifyContractsAsync(*contracts)
        self.contracts = {contract.symbol.upper(): contract for contract in qualified}
        missing = sorted(set(symbols) - set(self.contracts))
        if missing:
            raise RuntimeError(f"Could not qualify contracts: {', '.join(missing)}")
        return self.contracts

    def open_order_symbols(self) -> frozenset[str]:
        symbols: set[str] = set()
        for trade in self.ib.openTrades():
            contract = getattr(trade, "contract", None)
            symbol = getattr(contract, "symbol", None)
            if symbol:
                symbols.add(symbol.upper())
        return frozenset(symbols)

    def positions(self) -> dict[str, int]:
        positions: dict[str, int] = {}
        for position in self.ib.positions():
            symbol = getattr(position.contract, "symbol", None)
            if symbol:
                positions[symbol.upper()] = int(position.position)
        return positions

    def place_limit_order(self, intent: TradeIntent) -> int | None:
        from ib_async import LimitOrder

        contract = self.contracts.get(intent.symbol)
        if contract is None:
            raise RuntimeError(f"{intent.symbol} is not qualified")

        order = LimitOrder(intent.side, intent.quantity, intent.limit_price)
        trade = self.ib.placeOrder(contract, order)
        order_obj = getattr(trade, "order", order)
        return getattr(order_obj, "orderId", None)
