# OSS Trading Framework Adapters

## What Norynta supports

Norynta ships a Python adapter kit for widely used open-source trading and
research frameworks. The kit lives in `packages/python-sdk`, has no mandatory
framework dependency, and keeps prediction-market identity explicit as:

```text
<eventPubkey>:<outcomeIndex>/USDC
```

Prices exposed to general trading frameworks use USDC units (`0.49`), while
Norynta API requests continue to use integer cents (`49`) where the API contract
requires them. Exchange sequences remain decimal strings and are never coerced
to JavaScript or floating-point numbers.

## Why these projects

The following projects are both widely used and relevant to Norynta's
market-data, research, market-making, or execution surface. Popularity figures
are a July 2026 snapshot from each official GitHub repository; stars are only a
rough adoption signal, not a quality ranking.

| Project | Approx. GitHub stars | Primary use | Norynta integration |
|---|---:|---|---|
| [Freqtrade](https://github.com/freqtrade/freqtrade) | 51.5k | crypto strategies, optimization, bot operations | OHLCV research/backtest bridge |
| [Qlib](https://github.com/microsoft/qlib) | 46.6k | AI-oriented quantitative research | instrument/datetime feature-frame bridge |
| [vn.py](https://github.com/vnpy/vnpy) | 43.8k | event-driven quantitative trading | `BarData`-compatible research/backtest bridge |
| [CCXT](https://github.com/ccxt/ccxt) | 43.4k | unified exchange API | exchange-style market data, paper orders, caller-signed live orders |
| [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) | 24.9k | event-driven research and execution | quote-tick research/replay bridge |
| [Backtrader](https://github.com/mementum/backtrader) | 22.5k | Python backtesting | PandasData-compatible feed |
| [LEAN](https://github.com/QuantConnect/Lean) | 20.7k | multi-asset algorithm engine | custom-data CSV bridge |
| [Hummingbot](https://github.com/hummingbot/hummingbot) | 19.2k | CLOB market making | order-book snapshot bridge |
| [FinRL / FinRL-X](https://github.com/AI4Finance-Foundation/FinRL) | 15.8k | reinforcement-learning research and production pipelines | date/ticker OHLCV frame bridge |
| [Backtesting.py](https://github.com/kernc/backtesting.py) | 8.7k | concise Python strategy backtests | native `Open`/`High`/`Low`/`Close`/`Volume` frame |
| [vectorbt](https://github.com/polakowo/vectorbt) | 8.4k | vectorized research and parameter sweeps | pandas price/volume bridge |
| [Jesse](https://github.com/jesse-ai/jesse) | 8.2k | crypto strategy research and bots | native candle-shape research/backtest bridge |
| [OpenBB](https://github.com/OpenBB-finance/OpenBB) | active | investment research platform | historical-price model bridge |
| [Lumibot](https://github.com/Lumiwealth/lumibot) | active | event-driven backtesting and bots | pandas historical-data bridge |
| [QuantStats](https://github.com/ranaroussi/quantstats) | active | portfolio analytics and reports | UTC decimal-return series |
| [TensorTrade](https://github.com/tensortrade-org/tensortrade) | active | reinforcement-learning trading environments | deterministic data-feed features |
| [Zipline Reloaded](https://github.com/stefan-jansen/zipline-reloaded) | active | event-driven backtesting | custom bundle-ingest rows |
| [OctoBot](https://github.com/Drakkar-Software/OctoBot) | active | crypto automation and backtesting | historical candle bridge |

These projects do not share one execution model. Hummingbot connectors,
Freqtrade exchanges, NautilusTrader adapters, and LEAN brokerages each have
substantial framework-owned lifecycle contracts. Norynta therefore advertises
the exact supported mode for every bridge instead of claiming that a data
export is a native live brokerage.

## Ready-to-run repository

The cloneable starter for all eighteen integrations is at
[`examples/oss-trading-adapters`](https://github.com/norynta/trading-adapters/tree/main/examples/oss-trading-adapters).
It includes executable CCXT-style and Hummingbot examples, historical export
commands for every research bridge, native Backtrader/Backtesting.py/vectorbt and vn.py
samples, Qlib/FinRL frame examples, Freqtrade, LEAN, and Jesse starter classes,
sequence-aware order-book streaming, and Docker/Compose setup.

The same starter URL and exact supported modes are machine-readable under
`compatibility.ossAdapters` on `/api/bot/config`, `/api/agent/access`, and
`/api/agent/card`. This lets an agent discover the integration without scraping
this page.

## Install from this repository

```bash
git clone https://github.com/norynta/trading-adapters.git
cd trading-adapters
python3 -m venv .venv-norynta
. .venv-norynta/bin/activate
python -m pip install -e packages/python-sdk
norynta-adapters list
```

Optional research integrations:

```bash
python -m pip install -e 'packages/python-sdk[research]'
python -m pip install -e 'packages/python-sdk[backtrader]'
python -m pip install -e 'packages/python-sdk[backtesting]'
python -m pip install -e 'packages/python-sdk[vectorbt]'
```

Configure a local or hosted Norynta API:

```bash
export NORYNTA_BASE_URL=http://localhost:3000
export NORYNTA_AGENT_API_KEY=pmak_your_scoped_key
norynta-adapters doctor
```

Do not put wallet private keys in these variables. The Python SDK and adapter
kit never load or store wallet keys.

`doctor` exits nonzero when the installed SDK advertises an adapter missing
from the server discovery contract. This catches partial upgrades in CI before
a bot starts.

## One-command exports

Use an event public key and outcome index:

```bash
norynta-adapters export ccxt EVENT_PUBKEY --outcome-index 0 --output norynta-ccxt.json
norynta-adapters export hummingbot EVENT_PUBKEY --outcome-index 0 --output hummingbot-book.json
norynta-adapters export freqtrade EVENT_PUBKEY --outcome-index 0 --timeframe 5m --output freqtrade.csv
norynta-adapters export nautilustrader EVENT_PUBKEY --outcome-index 0 --output nautilus-quotes.csv
norynta-adapters export lean EVENT_PUBKEY --outcome-index 0 --output lean-custom-data.csv
norynta-adapters export backtrader EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output backtrader.csv
norynta-adapters export backtesting EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output backtesting.csv
norynta-adapters export vectorbt EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output vectorbt.csv
norynta-adapters export vnpy EVENT_PUBKEY --outcome-index 0 --timeframe 1m --output vnpy-bars.csv
norynta-adapters export qlib EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output qlib-features.csv
norynta-adapters export finrl EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output finrl-market-data.csv
norynta-adapters export jesse EVENT_PUBKEY --outcome-index 0 --timeframe 5m --output jesse-candles.csv
norynta-adapters export openbb EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output openbb-prices.csv
norynta-adapters export lumibot EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output lumibot-bars.csv
norynta-adapters export quantstats EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output quantstats-returns.csv
norynta-adapters export tensortrade EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output tensortrade-feed.csv
norynta-adapters export zipline EVENT_PUBKEY --outcome-index 0 --timeframe 1h --output zipline-bundle.csv
norynta-adapters export octobot EVENT_PUBKEY --outcome-index 0 --timeframe 5m --output octobot-candles.csv
```

Every export accepts `--from-time` and `--to-time` ISO-8601 bounds. Files are
written atomically, price levels outside 0–100 cents and negative sizes are
rejected, order books are normalized best-price-first, duplicate sequences are
removed, and sequence regressions fail closed for replay data.

Historical trade and order-book exports require an API key with
`exports:read`. Current order-book reads use the normal market-data contract.

## CCXT-style usage

The facade follows familiar CCXT method names without monkey-patching or
vendoring CCXT:

```python
from norynta import NoryntaCcxtAdapter

exchange = NoryntaCcxtAdapter(
    base_url="http://localhost:3000",
    api_key="pmak_scoped_key",
)
markets = exchange.load_markets()
book = exchange.fetch_order_book("EVENT_PUBKEY:0/USDC")
candles = exchange.fetch_ohlcv("EVENT_PUBKEY:0/USDC", "5m")
```

Paper orders are the default:

```python
result = exchange.create_order(
    "EVENT_PUBKEY:0/USDC",
    "limit",
    "buy",
    10,
    0.49,
    {"idempotencyKey": "paper:strategy-a:001"},
)
```

Live submission fails closed unless the caller provides both a signed Norynta
body and a deterministic idempotency key:

```python
result = exchange.create_order(
    "EVENT_PUBKEY:0/USDC",
    "limit",
    "buy",
    10,
    0.49,
    {
        "paper": False,
        "signedOrder": caller_signed_norynta_body,
        "idempotencyKey": "live:strategy-a:001",
    },
)
```

The adapter does not generate signatures, timestamps, nonces, or wallet keys.
Transport retries must reuse the same signed body and idempotency key.

## Python framework usage

```python
from norynta import NoryntaClient, NoryntaFrameworkAdapter

client = NoryntaClient(
    base_url="http://localhost:3000",
    api_key="pmak_scoped_key",
)
adapter = NoryntaFrameworkAdapter(client)
instrument = adapter.instrument("EVENT_PUBKEY", 0)

hummingbot_content = adapter.hummingbot_snapshot(instrument)
freqtrade_ohlcv = adapter.ohlcv(instrument, timeframe="5m")
nautilus_ticks = adapter.quote_ticks(instrument)
lean_rows = adapter.lean_rows(instrument)
backtrader_frame = adapter.backtrader_frame(instrument, timeframe="1h")
backtesting_frame = adapter.backtesting_frame(instrument, timeframe="1h")
vectorbt_frame = adapter.vectorbt_frame(instrument, timeframe="1h")
vnpy_rows = adapter.vnpy_rows(instrument, timeframe="1m")
qlib_frame = adapter.qlib_frame(instrument, timeframe="1h")
finrl_frame = adapter.finrl_frame(instrument, timeframe="1h")
jesse_candles = adapter.jesse_candles(instrument, timeframe="5m")
openbb_rows = adapter.openbb_rows(instrument, timeframe="1h")
lumibot_frame = adapter.lumibot_frame(instrument, timeframe="1h")
quantstats_returns = adapter.quantstats_returns(instrument, timeframe="1h")
tensortrade_rows = adapter.tensortrade_rows(instrument, timeframe="1h")
zipline_rows = adapter.zipline_rows(instrument, timeframe="1h")
octobot_candles = adapter.octobot_candles(instrument, timeframe="5m")
```

For Backtrader, pass the returned frame to `backtrader.feeds.PandasData`. For
Backtesting.py, pass its native-capitalized frame directly to `Backtest`. For
vectorbt, use the frame's `close` column as the price series. For
NautilusTrader and LEAN, the normalized rows are intentionally custom-data
inputs; they are not advertised as native live execution clients.

For vn.py, the starter constructs native `BarData` objects when vn.py is
installed. Qlib uses a `(datetime, instrument)` feature index, FinRL/FinRL-X
receives `date`/`tic` OHLCV rows, and Jesse receives candles ordered as
`timestamp, open, close, high, low, volume`. These four bridges are likewise
research/backtest inputs, not native Norynta live gateways.

## Support and safety matrix

| Adapter | Market data | Historical/replay | Paper | Live |
|---|---:|---:|---:|---:|
| CCXT-style facade | Yes | Yes | Yes | Caller-signed Norynta request only |
| Hummingbot bridge | Yes | No | Via Norynta paper API | No native connector yet |
| Freqtrade bridge | OHLCV | Yes | Backtest/dry-run data | No |
| NautilusTrader bridge | Quote ticks | Yes | Engine-side simulation | No |
| LEAN bridge | Custom data | Yes | Engine-side simulation | No |
| Backtrader bridge | OHLCV frame | Yes | Backtest | No |
| Backtesting.py bridge | Native OHLCV frame | Yes | Backtest | No |
| vectorbt bridge | Price/volume frame | Yes | Backtest | No |
| vn.py bridge | `BarData`-compatible bars | Yes | Backtest | No native gateway |
| Qlib bridge | AI feature frame | Yes | Backtest/ML | No |
| FinRL/FinRL-X bridge | RL-ready OHLCV frame | Yes | Backtest/ML | No |
| Jesse bridge | Native candle shape | Yes | Backtest | No native exchange |
| OpenBB bridge | Historical price records | Yes | Analysis | No |
| Lumibot bridge | OHLCV frame | Yes | Backtest/paper data | No native broker |
| QuantStats bridge | Return series | Yes | Analytics | No |
| TensorTrade bridge | Feed features | Yes | Backtest/ML | No |
| Zipline Reloaded bridge | Bundle rows | Yes | Backtest | No |
| OctoBot bridge | Historical candles | Yes | Backtest/paper data | No native exchange |

The machine-readable version of this matrix is exposed at
`/api/bot/config`, `/api/agent/access`, and `/api/agent/card` under
`compatibility.ossAdapters`, including the GitHub starter URL for every
adapter.

## Sequence-aware order-book streaming

The SDK can maintain a normalized book from the dedicated SSE stream:

```python
for book in adapter.reconciled_orderbook_stream(
    "EVENT_SLUG",
    instrument,
    stale_after_seconds=30,
):
    print(book["sequence"], book["bids"][:1], book["asks"][:1])
```

Norynta sequences are global exchange sequences, so jumps are valid and do not
by themselves cause a resync. The reconciler repairs deltas that arrive before
a snapshot, regress, conflict at the same sequence, or contain invalid levels.
Each snapshot carries a deterministic SHA-256 `bookRevision`; deltas bind both
`previousBookRevision` and `bookRevision`, so a missed same-market update is
detectable even when unrelated markets legitimately advance the global
sequence. SSE event IDs use
`orderbook:<decimal-sequence>:<book-revision>`. Both Python and TypeScript
clients send the last ID on reconnect, the server replays up to 100 persisted
events, and a `resync` event directs the client to the following authoritative
snapshot when the bounded replay window is unavailable or exhausted.
Repair uses the read-only current-order-book endpoint and exposes `stale`,
`resyncCount`, `source`, and `action` in every yielded state. It does not submit
orders or load wallet keys.

## Upstream compatibility policy

`packages/python-sdk/compatibility/upstream.json` identifies the official
repository and actual verification depth for every adapter. Lightweight native
integrations—Backtrader, Backtesting.py, and vectorbt—install both their
minimum-supported and latest SDK-compatible releases and run a real engine
smoke. Heavy or
source-oriented frameworks use contract fixtures and compiled starters so the
repository does not pretend an export bridge is a fully installed live
connector.

## Validate the repository setup

```bash
npm run trading-adapters:check
npm run trading-adapters:upstream:check
npm run python-sdk:check
npm run openapi:check
npm run check:agent-docs
```

`python-sdk:check` requires the development extras, including `mypy`, `build`,
and `twine`.
