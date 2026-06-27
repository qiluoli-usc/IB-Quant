from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ib_quant.risk.safety import MarketSnapshot, RuntimeState, SafetyGate
from ib_quant.storage.audit import AuditStore
from ib_quant.strategy.base import TradeIntent


class Broker(Protocol):
    def place_limit_order(self, intent: TradeIntent) -> int | None:
        ...


@dataclass(frozen=True)
class ExecutionResult:
    allowed: bool
    reason: str
    signal_id: int
    ib_order_id: int | None = None


class TradeExecutor:
    def __init__(self, broker: Broker, audit: AuditStore, safety_gate: SafetyGate):
        self.broker = broker
        self.audit = audit
        self.safety_gate = safety_gate

    def process_intent(
        self,
        intent: TradeIntent,
        snapshot: MarketSnapshot,
        state: RuntimeState,
    ) -> ExecutionResult:
        signal_id = self.audit.record_signal(
            intent.strategy_tag,
            intent.symbol,
            intent.side,
            intent.quantity,
            intent.limit_price,
            intent.reason,
        )
        decision = self.safety_gate.evaluate(intent, snapshot, state)
        if not decision.allowed:
            self.audit.record_rejection(signal_id, decision.reason)
            return ExecutionResult(False, decision.reason, signal_id)

        try:
            ib_order_id = self.broker.place_limit_order(intent)
        except Exception as exc:
            reason = f"broker_error:{type(exc).__name__}"
            self.audit.record_rejection(signal_id, reason, {"message": str(exc)})
            return ExecutionResult(False, reason, signal_id)

        self.safety_gate.record_accepted(intent, state)
        self.audit.record_order(signal_id, intent.side, intent.quantity, intent.limit_price, ib_order_id)
        return ExecutionResult(True, "submitted", signal_id, ib_order_id)
