from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ib_quant.risk.safety import SafetyConfig


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class IBConfig:
    host: str = "127.0.0.1"
    port: int = 4002
    client_id: int = 11
    readonly: bool = True
    connect_timeout_seconds: float = 10.0
    reconnect_initial_seconds: float = 2.0
    reconnect_max_seconds: float = 60.0
    auto_restart_start: str = "02:00"
    auto_restart_end: str = "02:15"


@dataclass(frozen=True)
class StrategyConfig:
    path: str = "strategies/example_strategy.py"
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StorageConfig:
    root: str = "data"
    audit_db: str = "data/audit.sqlite3"
    parquet_root: str = "data/bars"


@dataclass(frozen=True)
class MarketDataConfig:
    feed_mode: str = "realtime_bar"
    market_data_type: int = 1
    rolling_window_bars: int = 120
    stale_after_seconds: int = 90
    realtime_bar_size_seconds: int = 5
    realtime_bar_volume_multiplier: float = 100.0
    what_to_show: str = "TRADES"
    use_rth: bool = True
    max_market_data_lines: int = 100
    clock_flush_interval_seconds: float = 1.0


@dataclass(frozen=True)
class AppConfig:
    ib: IBConfig = field(default_factory=IBConfig)
    symbols: list[str] = field(default_factory=list)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: SafetyConfig = field(default_factory=SafetyConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    marketdata: MarketDataConfig = field(default_factory=MarketDataConfig)

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "AppConfig":
        ib_data = dict(mapping.get("ib", {}))
        risk_data = dict(mapping.get("risk", {}))
        legacy_expected_account = ib_data.pop("expected_account", None)
        if "expected_account" not in risk_data and legacy_expected_account:
            risk_data["expected_account"] = legacy_expected_account
        risk_data.setdefault("trade_enabled", False)
        if "readonly" not in risk_data and "readonly" in ib_data:
            risk_data["readonly"] = bool(ib_data["readonly"])

        return cls(
            ib=IBConfig(**ib_data),
            symbols=[str(symbol).upper() for symbol in mapping.get("symbols", [])],
            strategy=StrategyConfig(**dict(mapping.get("strategy", {}))),
            risk=SafetyConfig(**risk_data),
            storage=StorageConfig(**dict(mapping.get("storage", {}))),
            marketdata=MarketDataConfig(**dict(mapping.get("marketdata", {}))),
        ).validated()

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path)
        try:
            import yaml
        except ImportError as exc:
            raise RuntimeError(
                "YAML config loading requires PyYAML. Install dependencies with: "
                "conda run -n ib-env python -m pip install -r requirements.txt"
            ) from exc

        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, Mapping):
            raise ValueError(f"{config_path} must contain a mapping at the top level")
        return cls.from_mapping(data)

    def validated(self) -> "AppConfig":
        if self.marketdata.feed_mode not in {"realtime_bar", "tick_l1"}:
            raise ConfigError("marketdata.feed_mode must be realtime_bar or tick_l1")
        if self.marketdata.realtime_bar_size_seconds != 5:
            raise ConfigError("marketdata.realtime_bar_size_seconds must be 5 for IB reqRealTimeBars")
        if self.marketdata.market_data_type not in {1, 2, 3, 4}:
            raise ConfigError("marketdata.market_data_type must be one of 1, 2, 3, 4")
        if self.marketdata.feed_mode == "realtime_bar" and self.marketdata.market_data_type in {3, 4}:
            raise ConfigError("Delayed market data requires marketdata.feed_mode=tick_l1")
        if self.marketdata.clock_flush_interval_seconds <= 0:
            raise ConfigError("marketdata.clock_flush_interval_seconds must be positive")
        if self.marketdata.rolling_window_bars <= 0:
            raise ConfigError("marketdata.rolling_window_bars must be positive")
        if self.marketdata.realtime_bar_volume_multiplier <= 0:
            raise ConfigError("marketdata.realtime_bar_volume_multiplier must be positive")
        if self.ib.readonly and self.risk.trade_enabled and not self.risk.readonly:
            raise ConfigError("Live trading requires ib.readonly=false and risk.readonly=false")
        return self
