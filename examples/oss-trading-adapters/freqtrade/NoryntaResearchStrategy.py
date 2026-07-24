from __future__ import annotations

from pandas import DataFrame

from freqtrade.strategy import IStrategy


class NoryntaResearchStrategy(IStrategy):
    """Minimal research-only strategy for Norynta OHLCV exports."""

    timeframe = "5m"
    can_short = False
    minimal_roi = {"0": 100.0}
    stoploss = -0.99

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        del metadata
        dataframe["fast"] = dataframe["close"].rolling(3).mean()
        dataframe["slow"] = dataframe["close"].rolling(8).mean()
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        del metadata
        dataframe.loc[
            (dataframe["fast"] > dataframe["slow"])
            & (dataframe["fast"].shift(1) <= dataframe["slow"].shift(1)),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        del metadata
        dataframe.loc[
            (dataframe["fast"] < dataframe["slow"])
            & (dataframe["fast"].shift(1) >= dataframe["slow"].shift(1)),
            "exit_long",
        ] = 1
        return dataframe
