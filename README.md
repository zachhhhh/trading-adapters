# Norynta Trading Adapters

Ready-to-run Python adapters and starter projects for using Norynta market
data with popular open-source trading and research frameworks.

Supported integrations:

- CCXT, Hummingbot, Freqtrade, NautilusTrader, and LEAN
- Backtrader, Backtesting.py, vectorbt, vn.py, Jesse, and OctoBot
- Qlib, FinRL/FinRL-X, OpenBB, Lumibot, QuantStats, TensorTrade, and
  Zipline Reloaded

The examples are read-only or paper-mode by default. The SDK never accepts
wallet private keys. Live order submission requires a caller-signed Norynta
request and a deterministic idempotency key.

## Quick start

```bash
git clone https://github.com/norynta/trading-adapters.git
cd trading-adapters
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e 'packages/python-sdk[research]'
cp examples/oss-trading-adapters/.env.example examples/oss-trading-adapters/.env
norynta-adapters list
```

Configure the Norynta API:

```bash
export NORYNTA_BASE_URL=https://norynta.com
export NORYNTA_AGENT_API_KEY=pmak_your_scoped_key
norynta-adapters doctor
```

Run an export:

```bash
norynta-adapters export freqtrade EVENT_PUBKEY \
  --outcome-index 0 \
  --timeframe 5m \
  --output freqtrade.csv
```

See [the starter guide](examples/oss-trading-adapters/README.md) for native
framework examples, streaming order books, Docker/Compose, and each
framework's exact support boundary. The complete
[support matrix](docs/public/OSS_TRADING_FRAMEWORKS.md) distinguishes native
integrations from research-data bridges.

## Docker

```bash
docker build -f examples/oss-trading-adapters/Dockerfile -t norynta-adapters .
docker run --rm norynta-adapters list
```

## Validation

```bash
PYTHONPATH=packages/python-sdk/src python -m unittest discover -s packages/python-sdk/tests -p 'test_*.py'
PYTHONPATH=packages/python-sdk/src python scripts/check_python_adapter_compatibility.py
PYTHONPATH=packages/python-sdk/src python scripts/benchmark_python_adapters.py
python -m compileall -q examples/oss-trading-adapters
```

CI runs the SDK on Python 3.11–3.13 and tests minimum/latest upstream versions
of Backtrader, Backtesting.py, and vectorbt. Compatibility metadata and a
CycloneDX SBOM are committed with each release.

## Security

Never put seed phrases, private keys, or signed payloads in this repository or
its environment files. Use narrowly scoped API keys and keep live signing in
caller-controlled wallet infrastructure.

Licensed under the MIT License.
