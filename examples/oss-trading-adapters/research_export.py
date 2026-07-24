from __future__ import annotations

import argparse
import os
from pathlib import Path

from norynta.frameworks import main as adapters_main


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "framework",
        choices=[
            "freqtrade",
            "nautilustrader",
            "lean",
            "backtrader",
            "backtesting",
            "vectorbt",
            "vnpy",
            "qlib",
            "finrl",
            "jesse",
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
    parser.add_argument("--timeframe", default="1m")
    parser.add_argument("--from-time")
    parser.add_argument("--to-time")
    args = parser.parse_args()

    suffix = "csv"
    output = Path("output") / (
        f"{args.framework}-{args.event_pubkey}-{args.outcome_index}.{suffix}"
    )
    argv = [
        "--base-url",
        os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
    ]
    api_key = os.getenv("NORYNTA_AGENT_API_KEY")
    if api_key:
        argv.extend(["--api-key", api_key])
    argv.extend([
        "export",
        args.framework,
        args.event_pubkey,
        "--outcome-index",
        str(args.outcome_index),
        "--timeframe",
        args.timeframe,
        "--output",
        str(output),
    ])
    if args.from_time:
        argv.extend(["--from-time", args.from_time])
    if args.to_time:
        argv.extend(["--to-time", args.to_time])
    raise SystemExit(adapters_main(argv))


if __name__ == "__main__":
    main()
