from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from ib_quant.strategy.base import Strategy


class StrategyLoader:
    def load_from_path(self, path: str | Path, settings: Mapping[str, Any] | None = None) -> Strategy:
        strategy_path = Path(path).resolve()
        if not strategy_path.exists():
            raise FileNotFoundError(strategy_path)

        module_name = f"user_strategy_{strategy_path.stem}_{abs(hash(strategy_path))}"
        module = self._load_module(module_name, strategy_path)
        factory = getattr(module, "create_strategy", None)
        if not callable(factory):
            raise AttributeError(f"{strategy_path} must define create_strategy(settings)")

        strategy = factory(dict(settings or {}))
        if not hasattr(strategy, "on_minute"):
            raise TypeError("create_strategy(settings) must return an object with on_minute(context, bars)")
        return strategy

    @staticmethod
    def _load_module(module_name: str, path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot import strategy from {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
