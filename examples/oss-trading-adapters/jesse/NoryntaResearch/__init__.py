from __future__ import annotations

import jesse.indicators as ta
from jesse.strategies import Strategy


class NoryntaResearch(Strategy):
    """Minimal research strategy for Norynta-exported Jesse candles."""

    def should_long(self) -> bool:
        return bool(ta.sma(self.candles, period=3) > ta.sma(self.candles, period=8))

    def go_long(self) -> None:
        quantity = max(1, int(self.balance * 0.05 / self.price))
        self.buy = quantity, self.price

    def should_short(self) -> bool:
        return False

    def go_short(self) -> None:
        return None

    def should_cancel_entry(self) -> bool:
        return False

    def update_position(self) -> None:
        if ta.sma(self.candles, period=3) < ta.sma(self.candles, period=8):
            self.liquidate()
