# IB Quant

[中文文档](README_CN.md)

IB Quant is a local-first Python framework for personal IBKR minute-level monitoring and trading. It uses [`ib_async`](https://github.com/ib-api-reloaded/ib_async) to connect to IB Gateway or Trader Workstation, streams market data, builds one-minute bars, loads user strategy plugins, applies hard safety checks, and persists audit/bar data locally.

> This project is for personal research and automation. It is not financial advice and is not affiliated with Interactive Brokers.

## Features

- Connects to IB Gateway/TWS through `ib_async`.
- Supports paper-first local operation and later VPS deployment.
- Loads custom strategy files from `strategies/`.
- Builds one-minute bars from either IB 5-second realtime bars or L1 quote updates.
- Uses bounded rolling windows to avoid unbounded in-memory DataFrame growth.
- Stores trade signals, rejections, and order submissions in SQLite.
- Stores minute bars as Parquet files.
- Adds hard safety gates: readonly mode, account check, midday no-trade window, spread filter, duplicate-order block, order-size cap, and daily-order cap.

## Project Layout

```text
configs/                 Runtime configuration
ib_quant/                Core package
  broker/                IBKR connection and order adapter
  execution/             TradeIntent execution pipeline
  marketdata/            L1/realtime-bar feeds and bar aggregation
  risk/                  Safety checks
  storage/               SQLite and Parquet storage
  strategy/              Strategy plugin interface
scripts/                 CLI entry points
strategies/              User strategy plugins
tests/                   Unit tests
```

## Requirements

- Windows, macOS, or Linux
- Python 3.12+
- IB Gateway or Trader Workstation with Socket API enabled
- A conda environment named `ib-env` or an equivalent Python environment

Install dependencies:

```powershell
cd IB-Quant
conda run -n ib-env python -m pip install -r requirements.txt
```

## IB Gateway/TWS Setup

Recommended starting point:

- API type: `IB API`
- Trading mode: `Simulated Trading` / paper trading
- Gateway paper port: `4002`
- Gateway live port: `4001`
- TWS paper port: `7497`
- TWS live port: `7496`

In IB Gateway/TWS:

- Enable Socket API.
- Allow local connections from `127.0.0.1`.
- Keep API ports local; do not expose them to the public internet.
- Prefer IB Gateway for long-running automation.

## Quick Start

Run local checks:

```powershell
cd IB-Quant
Copy-Item configs/local.example.yaml configs/local.yaml
conda run -n ib-env python -m scripts.doctor --config configs/local.yaml
```

Check the IB connection and contract qualification:

```powershell
conda run -n ib-env python -m scripts.doctor --config configs/local.yaml --connect
```

Start the monitoring loop:

```powershell
conda run --no-capture-output -n ib-env python -m scripts.run_live --config configs/local.yaml
```

Stop with `Ctrl+C`.

## Configuration

Create your local configuration from the committed example:

```powershell
Copy-Item configs/local.example.yaml configs/local.yaml
```

The runtime configuration is `configs/local.yaml`, which is ignored by git. The committed template is [configs/local.example.yaml](configs/local.example.yaml).

The `ib` section is only for socket connection settings:

```yaml
ib:
  host: "127.0.0.1"
  port: 4002
  client_id: 1
  readonly: true
```

The account number is not required to connect to the IB API. It is only an optional safety check:

```yaml
risk:
  expected_account: null
  trade_enabled: false
  readonly: true
```

The default config is readonly and non-trading.

## Market Data Modes

Current default for testing without paid realtime market-data subscriptions:

```yaml
marketdata:
  feed_mode: "tick_l1"
  market_data_type: 3
```

Modes:

- `tick_l1`: uses `reqMktData` L1 updates and locally builds one-minute bars. This uses about one market-data line per symbol. It can work with delayed market data.
- `realtime_bar`: uses `reqRealTimeBars` 5-second IB bars and locally aggregates them into one-minute bars. It also subscribes to L1 quotes for spread checks. It requires realtime market-data permission and uses about two lines per symbol.

IB market data type values:

- `1`: realtime
- `2`: frozen
- `3`: delayed
- `4`: delayed frozen

When you subscribe to realtime US stock data, switch back to:

```yaml
marketdata:
  feed_mode: "realtime_bar"
  market_data_type: 1
```

## Strategy Plugins

Set the strategy path in config:

```yaml
strategy:
  path: "strategies/example_strategy.py"
```

Each strategy file must expose:

```python
def create_strategy(settings):
    return YourStrategy(settings)
```

The strategy object must implement:

```python
def on_minute(self, context, bars):
    return []
```

To request an order, return `TradeIntent` objects:

```python
from ib_quant.strategy.base import TradeIntent

TradeIntent(
    symbol="AAPL",
    side="BUY",
    quantity=1,
    limit_price=100.25,
    reason="your_signal_reason",
    strategy_tag="your_strategy_name",
)
```

Strategies should not call `ib_async` directly. The framework handles safety checks, audit logging, and order submission.

## Enabling Trading

Keep the default readonly config while testing.

After paper testing is stable, trading requires explicit changes:

```yaml
ib:
  readonly: false

risk:
  expected_account: "YOUR_ACCOUNT_ID"
  trade_enabled: true
  readonly: false
```

You can leave `expected_account: null`, but setting it before live trading is strongly recommended.

## Data Storage

Default paths:

```yaml
storage:
  root: "data"
  audit_db: "data/audit.sqlite3"
  parquet_root: "data/bars"
```

- SQLite stores signal, rejection, and order audit events.
- Parquet stores minute bars partitioned by symbol/date.
- `data/` is ignored by git.

## Testing

Run all tests:

```powershell
cd IB-Quant
conda run -n ib-env python -m unittest discover -s tests -v
```

Current tests cover configuration validation, market-data aggregation, rolling windows, safety gates, strategy loading, SQLite audit storage, and Parquet writes.

## Common Issues

### `No module named scripts.doctor`

Run commands from the project root:

```powershell
cd IB-Quant
```

### Error 420: No market data permissions

This means the IB connection works, but the account lacks the requested realtime market-data subscription. Use `tick_l1` with delayed data for testing, or subscribe to the required realtime market-data package before using `realtime_bar`.

### No output after startup

This can be normal outside US market hours, especially with delayed data. The process is still waiting for market-data updates.

## License

No license has been selected yet. Add a license before publishing this repository publicly.
