from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "python-sdk" / "src"))

from norynta import NoryntaFrameworkAdapter, NoryntaInstrument  # noqa: E402


ROW_BUDGET = 20_000
TIME_BUDGET_SECONDS = 3.0
MEMORY_BUDGET_BYTES = 64 * 1024 * 1024


class FixtureClient:
    def research_export(self, dataset: str, **_: Any) -> list[dict[str, Any]]:
        if dataset != "trades":
            return []
        start = 1_788_000_000
        return [
            {
                "id": str(index),
                "block_time": start + index,
                "trade_price_cents": 40 + index % 21,
                "fill_shares": 1 + index % 5,
            }
            for index in range(ROW_BUDGET)
        ]


def main() -> int:
    adapter = NoryntaFrameworkAdapter(FixtureClient())  # type: ignore[arg-type]
    instrument = NoryntaInstrument("PERF_EVENT", 0)
    tracemalloc.start()
    started = time.perf_counter()
    candles = adapter.ohlcv(instrument, timeframe="1m", limit=ROW_BUDGET)
    features = adapter.tensortrade_rows(
        instrument,
        timeframe="1m",
        limit=ROW_BUDGET,
    )
    elapsed = time.perf_counter() - started
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    ok = (
        bool(candles)
        and len(features) == len(candles)
        and elapsed <= TIME_BUDGET_SECONDS
        and peak_bytes <= MEMORY_BUDGET_BYTES
    )
    print(json.dumps({
        "ok": ok,
        "inputRows": ROW_BUDGET,
        "candleRows": len(candles),
        "elapsedSeconds": round(elapsed, 4),
        "timeBudgetSeconds": TIME_BUDGET_SECONDS,
        "peakBytes": peak_bytes,
        "memoryBudgetBytes": MEMORY_BUDGET_BYTES,
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
