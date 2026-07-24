# Norynta Python SDK

Typed, zero-dependency Python access to Norynta prediction-market discovery,
market data, order books, and caller-signed execution workflows.

```bash
pip install --index-url https://code.norynta.com/python/simple norynta
```

The same wheel, source archive, SHA-256 manifest, and CycloneDX SBOM are
available at `https://code.norynta.com/python/packages/`. PyPI publication uses
the protected `pypi` GitHub environment and Trusted Publishing; no long-lived
PyPI token belongs in repository secrets.

```python
from norynta import NoryntaClient

client = NoryntaClient()
markets = client.search_markets("interest rates", limit=10)
print(markets)
```

For protected methods, pass a scoped token through your secret manager:

```python
import os
from norynta import NoryntaClient

client = NoryntaClient(api_key=os.environ["NORYNTA_AGENT_API_KEY"])
prepared = client.prepare_order(order, idempotency_key="unique-order-id")
```

The SDK never signs orders and never accepts seed phrases or private keys.
`place_signed_order` only forwards a signature created by the caller-controlled
wallet, and Norynta still enforces authentication, eligibility, balances, risk
limits, price guards, rate limits, and circuit breakers.

## OSS trading framework adapters

The package includes adapters and export bridges for CCXT, Hummingbot,
Freqtrade, NautilusTrader, LEAN, Backtrader, Backtesting.py, vectorbt, vn.py,
Qlib, FinRL/FinRL-X, Jesse, OpenBB, Lumibot, QuantStats, TensorTrade, Zipline
Reloaded, and OctoBot.

```bash
norynta-adapters list
norynta-adapters doctor
norynta-adapters export freqtrade EVENT_PUBKEY \
  --outcome-index 0 --timeframe 5m --output candles.csv
```

Cloneable examples, native starter files, and Docker setup live in
[`examples/oss-trading-adapters`](../../examples/oss-trading-adapters).
Research and paper modes are the default. Live submission is available only
through caller-signed request bodies with explicit idempotency keys.

```python
from norynta import NoryntaClient, NoryntaFrameworkAdapter

adapter = NoryntaFrameworkAdapter(NoryntaClient(base_url="http://localhost:3000"))
instrument = adapter.instrument("EVENT_PUBKEY", 0)
for book in adapter.reconciled_orderbook_stream("EVENT_SLUG", instrument):
    print(book["sequence"], book["stale"], book["resyncCount"])
```

The client retries safe reads and writes carrying an idempotency key with
capped exponential backoff. Order-book reconnects send `Last-Event-ID`, and
the reconciler repairs ambiguous or regressing deltas from a read-only
snapshot.

## Package verification

```bash
python3 -m pip install -e 'packages/python-sdk[dev]'
PYTHONPATH=packages/python-sdk/src python3 -m unittest discover -s packages/python-sdk/tests -p 'test_*.py'
PYTHONPATH=packages/python-sdk/src python3 scripts/check_python_adapter_compatibility.py
PYTHONPATH=packages/python-sdk/src python3 scripts/benchmark_python_adapters.py
python3 -m twine check packages/python-sdk/dist/*
```

`.github/workflows/python-sdk.yml` runs tests and strict type checking on
Python 3.11–3.13, compiles the starter examples, and verifies both the wheel
and its installed `norynta-adapters` entrypoint. An upstream matrix runs the
minimum-supported and latest Backtrader, Backtesting.py, and vectorbt releases,
enforces adapter performance budgets, and uploads a CycloneDX SBOM for every
compatibility lane. The verification depth for every heavier bridge is
recorded in `compatibility/upstream.json`.

- Developer docs: https://norynta.com/developers
- OpenAPI: https://norynta.com/openapi.json
- Read-only MCP: https://mcp.norynta.com/mcp
- Public source: https://github.com/norynta/trading-adapters
- Adapter support matrix: ../../docs/public/OSS_TRADING_FRAMEWORKS.md
