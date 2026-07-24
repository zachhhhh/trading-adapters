from __future__ import annotations

import argparse
from typing import Any

from norynta import NoryntaClient, NoryntaFrameworkAdapter, NoryntaInstrument


class StaticAdapter(NoryntaFrameworkAdapter):
    def __init__(self) -> None:
        super().__init__(NoryntaClient(base_url="http://invalid.local"))

    def ohlcv(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[list[float | int]]:
        del instrument, timeframe, filters
        return [
            [1_700_000_000_000, 0.45, 0.48, 0.44, 0.47, 100],
            [1_700_000_060_000, 0.47, 0.51, 0.46, 0.50, 120],
            [1_700_000_120_000, 0.50, 0.52, 0.48, 0.49, 90],
            [1_700_000_180_000, 0.49, 0.55, 0.49, 0.54, 130],
        ]


def smoke_backtrader(adapter: StaticAdapter, instrument: NoryntaInstrument) -> None:
    import backtrader as bt

    engine = bt.Cerebro(stdstats=False)
    engine.adddata(bt.feeds.PandasData(dataname=adapter.backtrader_frame(instrument)))
    engine.run()


def smoke_backtesting(adapter: StaticAdapter, instrument: NoryntaInstrument) -> None:
    from backtesting import Backtest, Strategy

    class Hold(Strategy):
        def init(self) -> None:
            pass

        def next(self) -> None:
            pass

    backtest = Backtest(
        adapter.backtesting_frame(instrument),
        Hold,
        cash=10_000,
        finalize_trades=True,
    )
    backtest.run()


def smoke_vectorbt(adapter: StaticAdapter, instrument: NoryntaInstrument) -> None:
    import vectorbt as vbt

    close = adapter.vectorbt_frame(instrument)["close"]
    entries = close > close.shift(1)
    exits = close < close.shift(1)
    vbt.Portfolio.from_signals(close, entries, exits, init_cash=10_000)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "framework",
        choices=["backtrader", "backtesting", "vectorbt"],
    )
    args = parser.parse_args()
    adapter = StaticAdapter()
    instrument = NoryntaInstrument("CompatibilityFixture", 0)
    smoke = {
        "backtrader": smoke_backtrader,
        "backtesting": smoke_backtesting,
        "vectorbt": smoke_vectorbt,
    }[args.framework]
    smoke(adapter, instrument)
    print(f"{args.framework}: upstream compatibility smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
