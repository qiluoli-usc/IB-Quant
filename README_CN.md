# IB Quant 自动盯盘交易脚本

[English README](README.md)

IB Quant 是一个本地优先、后续可迁移到 VPS 的 IBKR 分钟级量化脚本框架。它使用 [`ib_async`](https://github.com/ib-api-reloaded/ib_async) 连接 IB Gateway 或 Trader Workstation，订阅行情，构建 1 分钟 K 线，加载用户策略插件，执行硬保护风控，并把审计日志和行情数据落盘。

> 本项目用于个人研究和自动化，不构成投资建议，也不隶属于 Interactive Brokers。

## 功能

- 通过 `ib_async` 连接 IB Gateway/TWS。
- 默认本地 paper/只读优先，后续可迁移到 VPS。
- 从 `strategies/` 加载自定义策略文件。
- 支持用 IB 5 秒 realtime bars 或 L1 更新构建 1 分钟 K 线。
- 使用 rolling window，避免内存中的 DataFrame 无限增长。
- 用 SQLite 保存信号、拒单和订单审计。
- 用 Parquet 保存分钟 K 线。
- 内置硬保护：只读模式、账户校验、午间禁交易、spread 过滤、重复订单拦截、单笔数量上限、每日订单数上限。

## 项目结构

```text
configs/                 运行配置
ib_quant/                核心包
  broker/                IBKR 连接和订单适配
  execution/             TradeIntent 执行流程
  marketdata/            行情订阅和 K 线聚合
  risk/                  风控硬保护
  storage/               SQLite 和 Parquet 存储
  strategy/              策略插件接口
scripts/                 命令行入口
strategies/              用户策略插件
tests/                   单元测试
```

## 环境要求

- Windows、macOS 或 Linux
- Python 3.12+
- 已启用 Socket API 的 IB Gateway 或 Trader Workstation
- 名为 `ib-env` 的 conda 环境，或等价 Python 环境

安装依赖：

```powershell
cd IB-Quant
conda run -n ib-env python -m pip install -r requirements.txt
```

## IB Gateway/TWS 设置

推荐先使用 IB Gateway paper 环境：

- API 类型：`IB API`
- 交易模式：模拟交易 / paper trading
- Gateway paper 端口：`4002`
- Gateway live 端口：`4001`
- TWS paper 端口：`7497`
- TWS live 端口：`7496`

在 IB Gateway/TWS 中：

- 启用 Socket API。
- 允许本地 `127.0.0.1` 连接。
- API 端口只保留在本地，不要暴露到公网。
- 长时间自动化运行建议使用 IB Gateway。

## 快速开始

运行本地检查：

```powershell
cd IB-Quant
Copy-Item configs/local.example.yaml configs/local.yaml
conda run -n ib-env python -m scripts.doctor --config configs/local.yaml
```

检查 IB 连接和合约识别：

```powershell
conda run -n ib-env python -m scripts.doctor --config configs/local.yaml --connect
```

启动盯盘循环：

```powershell
conda run --no-capture-output -n ib-env python -m scripts.run_live --config configs/local.yaml
```

用 `Ctrl+C` 停止。

## 配置

先从已提交的示例配置创建你的本地配置：

```powershell
Copy-Item configs/local.example.yaml configs/local.yaml
```

运行时配置是 `configs/local.yaml`，它会被 git 忽略。仓库中提交的是 [configs/local.example.yaml](configs/local.example.yaml)。

`ib` 只负责 socket 连接：

```yaml
ib:
  host: "127.0.0.1"
  port: 4002
  client_id: 1
  readonly: true
```

账户号不是连接 IB API 的必要参数，只是可选风控校验：

```yaml
risk:
  expected_account: null
  trade_enabled: false
  readonly: true
```

默认配置是只读、不交易。

## 行情模式

当前默认适合没有实时行情订阅时测试：

```yaml
marketdata:
  feed_mode: "tick_l1"
  market_data_type: 3
```

模式说明：

- `tick_l1`：使用 `reqMktData` 的 L1 更新，本地构建 1 分钟 K 线。每只股票大约占 1 条行情线，可用于延迟行情测试。
- `realtime_bar`：使用 `reqRealTimeBars` 的 5 秒 IB bars，本地聚合为 1 分钟 K 线，同时额外订阅 L1 quote 做 spread 检查。需要实时行情权限，每只股票大约占 2 条行情线。

IB 行情类型：

- `1`：实时行情
- `2`：冻结行情
- `3`：延迟行情
- `4`：延迟冻结行情

当你订阅美股实时行情后，可以改回：

```yaml
marketdata:
  feed_mode: "realtime_bar"
  market_data_type: 1
```

## 策略插件

在配置中指定策略路径：

```yaml
strategy:
  path: "strategies/example_strategy.py"
```

每个策略文件必须暴露：

```python
def create_strategy(settings):
    return YourStrategy(settings)
```

策略对象必须实现：

```python
def on_minute(self, context, bars):
    return []
```

需要下单时返回 `TradeIntent`：

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

策略不要直接调用 `ib_async` 下单。框架会统一处理风控、审计和订单提交。

## 启用交易

测试阶段保持默认只读配置。

paper 测试稳定后，如需启用交易，必须显式修改：

```yaml
ib:
  readonly: false

risk:
  expected_account: "你的账户号"
  trade_enabled: true
  readonly: false
```

`expected_account` 可以保持 `null`，但实盘前强烈建议填写，用来防止连错账户。

## 数据存储

默认路径：

```yaml
storage:
  root: "data"
  audit_db: "data/audit.sqlite3"
  parquet_root: "data/bars"
```

- SQLite 保存信号、拒单和订单审计事件。
- Parquet 按 symbol/date 分区保存分钟 K 线。
- `data/` 已被 git 忽略。

## 测试

运行全部测试：

```powershell
cd IB-Quant
conda run -n ib-env python -m unittest discover -s tests -v
```

当前测试覆盖配置校验、行情聚合、rolling window、风控硬保护、策略加载、SQLite 审计和 Parquet 写入。

## 常见问题

### `No module named scripts.doctor`

请先进入项目根目录：

```powershell
cd IB-Quant
```

### Error 420: No market data permissions

这说明 IB 连接成功，但账户没有对应实时行情订阅。测试阶段可以使用 `tick_l1` + 延迟行情；要使用 `realtime_bar`，需要先订阅实时行情包。

### 启动后没有继续输出

非美股交易时段，尤其使用延迟行情时，长时间没有新行情推送是正常现象。程序仍在等待行情更新。

## 许可证

当前还没有选择许可证。如果要公开发布到 GitHub，请先添加许可证。
