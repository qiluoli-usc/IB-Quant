from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def record_signal(
        self,
        strategy_tag: str,
        symbol: str,
        side: str,
        quantity: int,
        limit_price: float,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> int:
        return self._insert(
            event_type="signal",
            signal_id=None,
            strategy_tag=strategy_tag,
            symbol=symbol,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            reason=reason,
            ib_order_id=None,
            payload=payload,
        )

    def record_rejection(self, signal_id: int, reason: str, payload: dict[str, Any] | None = None) -> int:
        return self._insert(
            event_type="rejection",
            signal_id=signal_id,
            strategy_tag=None,
            symbol=None,
            side=None,
            quantity=None,
            limit_price=None,
            reason=reason,
            ib_order_id=None,
            payload=payload,
        )

    def record_order(
        self,
        signal_id: int,
        side: str,
        quantity: int,
        limit_price: float,
        ib_order_id: int | None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        return self._insert(
            event_type="order",
            signal_id=signal_id,
            strategy_tag=None,
            symbol=None,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
            reason=None,
            ib_order_id=ib_order_id,
            payload=payload,
        )

    def fetch_all(self, table: str) -> list[dict[str, Any]]:
        if table != "trade_events":
            raise ValueError("fetch_all only supports trade_events")
        with closing(sqlite3.connect(self.path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM trade_events ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def _initialize(self) -> None:
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_utc TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    signal_id INTEGER,
                    strategy_tag TEXT,
                    symbol TEXT,
                    side TEXT,
                    quantity INTEGER,
                    limit_price REAL,
                    reason TEXT,
                    ib_order_id INTEGER,
                    payload_json TEXT
                )
                """
            )
            conn.commit()

    def _insert(
        self,
        *,
        event_type: str,
        signal_id: int | None,
        strategy_tag: str | None,
        symbol: str | None,
        side: str | None,
        quantity: int | None,
        limit_price: float | None,
        reason: str | None,
        ib_order_id: int | None,
        payload: dict[str, Any] | None,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        payload_json = json.dumps(payload or {}, sort_keys=True)
        with closing(sqlite3.connect(self.path)) as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_events (
                    ts_utc, event_type, signal_id, strategy_tag, symbol, side,
                    quantity, limit_price, reason, ib_order_id, payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now,
                    event_type,
                    signal_id,
                    strategy_tag,
                    symbol,
                    side,
                    quantity,
                    limit_price,
                    reason,
                    ib_order_id,
                    payload_json,
                ),
            )
            row_id = int(cursor.lastrowid)
            conn.commit()
            return row_id
