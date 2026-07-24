"""Run Norynta data through OpenBB/Lumibot/QuantStats/TensorTrade/Zipline/OctoBot shapes.

The script is dependency-light by default. Install the corresponding framework
in its own pinned environment to pass the returned rows/frame into its native
provider, data source, feed, bundle, or backtest lifecycle.
"""

from __future__ import annotations

import argparse
import json
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "framework",
        choices=[
            "openbb",
            "lumibot",
            "quantstats",
            "tensortrade",
            "zipline",
            "octobot",
        ],
    )
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()

    client = NoryntaClient(
        base_url=os.getenv("NORYNTA_BASE_URL", "https://norynta.com"),
        api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
    )
    adapter = NoryntaFrameworkAdapter(client)
    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    filters = {"timeframe": args.timeframe}

    if args.framework == "openbb":
        value = adapter.openbb_rows(instrument, **filters)
    elif args.framework == "lumibot":
        value = adapter.lumibot_frame(instrument, **filters).reset_index().to_dict(
            orient="records"
        )
    elif args.framework == "quantstats":
        series = adapter.quantstats_returns(instrument, **filters)
        value = [
            {"date": timestamp.isoformat(), "return": float(result)}
            for timestamp, result in series.items()
        ]
    elif args.framework == "tensortrade":
        value = adapter.tensortrade_rows(instrument, **filters)
    elif args.framework == "zipline":
        value = adapter.zipline_rows(instrument, **filters)
    else:
        value = adapter.octobot_candles(instrument, **filters)

    print(json.dumps(value[:5], indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
