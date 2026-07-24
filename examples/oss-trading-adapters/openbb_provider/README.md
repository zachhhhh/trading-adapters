# OpenBB Norynta provider

Install this extension beside OpenBB 4.7 and rebuild its provider registry:

```bash
python -m pip install -e packages/python-sdk
python -m pip install -e examples/oss-trading-adapters/openbb_provider
openbb-build
```

Then query an event public key as the symbol:

```python
from openbb import obb

result = obb.equity.price.historical(
    symbol="EVENT_PUBKEY",
    provider="norynta",
    outcome_index=0,
    timeframe="1h",
)
```

Set `NORYNTA_BASE_URL` and, for protected historical exports,
`NORYNTA_AGENT_API_KEY`. The provider is read-only.
