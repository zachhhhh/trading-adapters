# Norynta OSS Trading Adapter Starters

Clone this repository and use this directory as a ready-to-run starting point
for CCXT-style clients, Hummingbot, Freqtrade, NautilusTrader, LEAN,
Backtrader, Backtesting.py, vectorbt, vn.py, Qlib, FinRL/FinRL-X, Jesse,
OpenBB, Lumibot, QuantStats, TensorTrade, Zipline Reloaded, or OctoBot.

The examples are read-only unless a command explicitly includes `--paper`.
There is no live-order flag in this starter. Live execution remains available
through the Python SDK only when the caller supplies a wallet-signed Norynta
payload and deterministic idempotency key.

## Setup

```bash
cd examples/oss-trading-adapters
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Export the variables from `.env`, or set them in your shell:

```bash
export NORYNTA_BASE_URL=http://localhost:3000
export NORYNTA_AGENT_API_KEY=pmak_your_scoped_key
```

Verify the server and adapter contract:

```bash
norynta-adapters list
norynta-adapters doctor
python ccxt_example.py EVENT_PUBKEY
python hummingbot_example.py EVENT_PUBKEY
python nautilustrader_example.py EVENT_PUBKEY
python lumibot_example.py EVENT_PUBKEY --timeframe 1m
```

Historical examples require an API key with `exports:read`:

```bash
python research_export.py freqtrade EVENT_PUBKEY --timeframe 5m
python research_export.py nautilustrader EVENT_PUBKEY
python research_export.py lean EVENT_PUBKEY
python research_export.py backtrader EVENT_PUBKEY --timeframe 1h
python research_export.py backtesting EVENT_PUBKEY --timeframe 1h
python research_export.py vectorbt EVENT_PUBKEY --timeframe 1h
python research_export.py vnpy EVENT_PUBKEY --timeframe 1m
python research_export.py qlib EVENT_PUBKEY --timeframe 1h
python research_export.py finrl EVENT_PUBKEY --timeframe 1h
python research_export.py jesse EVENT_PUBKEY --timeframe 5m
python research_export.py openbb EVENT_PUBKEY --timeframe 1h
python research_export.py lumibot EVENT_PUBKEY --timeframe 1h
python research_export.py quantstats EVENT_PUBKEY --timeframe 1h
python research_export.py tensortrade EVENT_PUBKEY --timeframe 1h
python research_export.py zipline EVENT_PUBKEY --timeframe 1h
python research_export.py octobot EVENT_PUBKEY --timeframe 5m
```

Generated data is written atomically under `output/`.

## Optional native research tools

```bash
python -m pip install -r requirements-research.txt
python backtrader_vectorbt.py backtrader EVENT_PUBKEY
python backtesting_example.py EVENT_PUBKEY
python backtrader_vectorbt.py vectorbt EVENT_PUBKEY
```

The native framework samples only prove data wiring. They are not recommended
strategies.

The second research-toolkit wave has a shared executable sample:

```bash
python research_toolkit_example.py openbb EVENT_PUBKEY
python research_toolkit_example.py lumibot EVENT_PUBKEY
python research_toolkit_example.py quantstats EVENT_PUBKEY
python research_toolkit_example.py tensortrade EVENT_PUBKEY
python research_toolkit_example.py zipline EVENT_PUBKEY
python research_toolkit_example.py octobot EVENT_PUBKEY
```

OpenBB receives historical-price model records, Lumibot a UTC-indexed OHLCV
frame, QuantStats decimal returns, TensorTrade deterministic feed features,
Zipline Reloaded bundle-ingest rows, and OctoBot historical candles. These are
data/backtest adapters and never load exchange or wallet credentials.

The installable OpenBB provider extension is under `openbb_provider/`; after
installation, run `openbb-build` as required by OpenBB's extension registry.

## Resilient order-book streaming

```bash
python streaming_orderbook.py EVENT_SLUG EVENT_PUBKEY --outcome-index 0
```

The stream starts from a full snapshot, accepts gaps in Norynta's global
exchange sequence, applies price-level deltas, and automatically fetches a
read-only REST snapshot when a delta is ambiguous or regresses. It reports
staleness and reconciliation counts in each emitted book.

## vn.py

```bash
python vnpy_example.py EVENT_PUBKEY --timeframe 1m
```

Without vn.py installed, the example emits `BarData`-compatible records. When
vn.py is available, it constructs native `BarData` objects with
`Exchange.LOCAL`; this is a historical-data bridge, not a live gateway.

## Qlib and FinRL/FinRL-X

Install the lightweight research dependencies and inspect the native frames:

```bash
python -m pip install -r requirements-research.txt
python ai_research_example.py qlib EVENT_PUBKEY --timeframe 1h
python ai_research_example.py finrl EVENT_PUBKEY --timeframe 1h
```

Qlib receives a `(datetime, instrument)` feature index. FinRL and FinRL-X
receive `date`, `tic`, OHLCV, and weekday columns. Install those frameworks in
their own pinned environments when training models; Norynta does not force
their large dependency trees into the SDK.

## Jesse

```bash
python jesse_example.py EVENT_PUBKEY --timeframe 5m
```

The emitted candle order is `timestamp, open, close, high, low, volume`. Copy
`jesse/NoryntaResearch` into a Jesse project's `strategies` directory for a
minimal wiring check. Norynta does not advertise this bridge as a native Jesse
live exchange.

## Freqtrade

Generate candles:

```bash
python research_export.py freqtrade EVENT_PUBKEY --timeframe 5m
```

Copy `freqtrade/NoryntaResearchStrategy.py` into the Freqtrade user-data
strategy directory. Norynta's bridge is for research/backtesting; it is not
advertised as a native Freqtrade live exchange.

## Hummingbot

`hummingbot_example.py` emits Hummingbot `OrderBookMessage`-compatible snapshot
content. If Hummingbot is installed, it also constructs the native snapshot
message class. This bridge intentionally does not take custody of wallet keys
or claim native live-connector lifecycle support.

## NautilusTrader

The quote-tick export contains:

```text
instrument_id,timestamp,sequence,bid_price,bid_size,ask_price,ask_size
```

Use it as custom data or map it into NautilusTrader `QuoteTick` objects in the
engine version you pin. Sequence regressions fail closed by default.

## LEAN

Generate the custom-data CSV and copy `lean/NoryntaQuote.py` into a LEAN Python
project. Set the custom data path in the algorithm configuration before adding
the data subscription.

## Docker

From the repository root:

```bash
docker build -f examples/oss-trading-adapters/Dockerfile -t norynta-adapters .
docker run --rm norynta-adapters list
docker run --rm \
  -e NORYNTA_BASE_URL=http://host.docker.internal:3000 \
  -e NORYNTA_AGENT_API_KEY \
  -v "$PWD/examples/oss-trading-adapters/output:/output" \
  norynta-adapters export freqtrade EVENT_PUBKEY --output /output/freqtrade.csv
```

Or:

```bash
cd examples/oss-trading-adapters
docker compose run --rm adapters list
```

## Validation

From the repository root:

```bash
PYTHONPATH=packages/python-sdk/src python3 -m unittest discover -s packages/python-sdk/tests -p 'test_*.py'
PYTHONPATH=packages/python-sdk/src python3 scripts/check_python_adapter_compatibility.py
PYTHONPATH=packages/python-sdk/src python3 scripts/benchmark_python_adapters.py
python3 -m compileall -q examples/oss-trading-adapters
```
