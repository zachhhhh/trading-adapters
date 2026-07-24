from __future__ import annotations

import argparse
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("framework", choices=["qlib", "finrl"])
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()

    client = NoryntaClient(
        base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
        api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
    )
    adapter = NoryntaFrameworkAdapter(client)
    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    if args.framework == "qlib":
        frame = adapter.qlib_frame(instrument, timeframe=args.timeframe)
    else:
        frame = adapter.finrl_frame(instrument, timeframe=args.timeframe)

    if frame.empty:
        raise SystemExit("No historical trades were returned for this instrument.")
    print(frame.head().to_string())
    print(f"rows={len(frame)} framework={args.framework}")


if __name__ == "__main__":
    main()
