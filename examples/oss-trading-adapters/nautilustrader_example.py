from __future__ import annotations

import argparse
import json
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    args = parser.parse_args()

    adapter = NoryntaFrameworkAdapter(
        NoryntaClient(
            base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
            api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
        )
    )
    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    rows = adapter.quote_ticks(instrument)
    try:
        from nautilus_trader.model.data import QuoteTick
        from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
        from nautilus_trader.model.objects import Price, Quantity
    except ImportError:
        print(json.dumps({
            "nativeTicks": False,
            "rows": rows[:5],
            "hint": "Install NautilusTrader to construct native QuoteTick objects.",
        }, indent=2))
        return

    instrument_id = InstrumentId(
        Symbol(f"{instrument.event_pubkey}:{instrument.outcome_index}"),
        Venue("NORYNTA"),
    )
    ticks = [
        QuoteTick(
            instrument_id=instrument_id,
            bid_price=Price.from_str(f"{row['bid_price']:.2f}"),
            ask_price=Price.from_str(f"{row['ask_price']:.2f}"),
            bid_size=Quantity.from_str(str(row["bid_size"])),
            ask_size=Quantity.from_str(str(row["ask_size"])),
            ts_event=int(row["timestamp"]) * 1_000_000,
            ts_init=int(row["timestamp"]) * 1_000_000,
        )
        for row in rows
        if all(
            row[field] is not None
            for field in ("bid_price", "ask_price", "bid_size", "ask_size")
        )
    ]
    print(json.dumps({
        "nativeTicks": True,
        "count": len(ticks),
        "first": repr(ticks[0]) if ticks else None,
    }, indent=2))


if __name__ == "__main__":
    main()
