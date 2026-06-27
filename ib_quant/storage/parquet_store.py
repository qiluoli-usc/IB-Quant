from __future__ import annotations

from pathlib import Path

import pandas as pd

from ib_quant.marketdata.bars import MinuteBar


class ParquetMinuteBarStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def append(self, bar: MinuteBar) -> Path:
        partition_dir = self.root / f"symbol={bar.symbol}" / f"date={bar.time.date().isoformat()}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        path = partition_dir / "bars.parquet"
        row = pd.DataFrame([bar.to_dict()])

        if path.exists():
            existing = pd.read_parquet(path)
            row = pd.concat([existing, row], ignore_index=True)

        try:
            row.to_parquet(path, index=False)
        except ImportError as exc:
            raise RuntimeError(
                "Parquet support requires pyarrow. Install dependencies with: "
                "conda run -n ib-env python -m pip install -r requirements.txt"
            ) from exc
        return path
