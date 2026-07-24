from __future__ import annotations

import argparse
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("framework", choices=["backtrader", "vectorbt"])
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
    frame = adapter.pandas_frame(instrument, timeframe=args.timeframe)
    if frame.empty:
        raise SystemExit("No historical trades were returned for this instrument.")

    fast = frame["close"].rolling(3).mean()
    slow = frame["close"].rolling(8).mean()
    entries = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    exits = (fast < slow) & (fast.shift(1) >= slow.shift(1))

    if args.framework == "vectorbt":
        import vectorbt as vbt

        portfolio = vbt.Portfolio.from_signals(
            frame["close"],
            entries,
            exits,
            fees=0.0025,
        )
        print(portfolio.stats().to_string())
        return

    import backtrader as bt

    class MovingAverageCross(bt.Strategy):
        params = (("fast", 3), ("slow", 8))

        def __init__(self) -> None:
            fast_average = bt.indicators.SimpleMovingAverage(
                self.data.close,
                period=self.params.fast,
            )
            slow_average = bt.indicators.SimpleMovingAverage(
                self.data.close,
                period=self.params.slow,
            )
            self.cross = bt.indicators.CrossOver(fast_average, slow_average)

        def next(self) -> None:
            if not self.position and self.cross > 0:
                self.buy(size=1)
            elif self.position and self.cross < 0:
                self.close()

    engine = bt.Cerebro()
    engine.adddata(bt.feeds.PandasData(dataname=frame))
    engine.addstrategy(MovingAverageCross)
    engine.broker.setcash(100)
    engine.run()
    print(f"final_value={engine.broker.getvalue():.4f}")


if __name__ == "__main__":
    main()
