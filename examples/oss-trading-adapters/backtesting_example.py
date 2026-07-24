from __future__ import annotations

import argparse
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
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
    frame = adapter.backtesting_frame(instrument, timeframe=args.timeframe)

    try:
        from backtesting import Backtest, Strategy
    except ImportError:
        print(frame)
        print("Install backtesting to run the native engine smoke.")
        return

    class Hold(Strategy):
        def init(self) -> None:
            pass

        def next(self) -> None:
            pass

    stats = Backtest(frame, Hold, cash=10_000, finalize_trades=True).run()
    print(stats)


if __name__ == "__main__":
    main()
