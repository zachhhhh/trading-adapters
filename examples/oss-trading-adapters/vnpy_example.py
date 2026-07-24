from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    parser.add_argument("--timeframe", default="1m")
    args = parser.parse_args()

    client = NoryntaClient(
        base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
        api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
    )
    adapter = NoryntaFrameworkAdapter(client)
    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    rows = adapter.vnpy_rows(instrument, timeframe=args.timeframe)

    try:
        from vnpy.trader.constant import Exchange, Interval
        from vnpy.trader.object import BarData
    except ImportError:
        print(
            json.dumps(
                {
                    "nativeBars": False,
                    "rows": rows,
                    "hint": "Install vn.py to construct native BarData objects.",
                },
                indent=2,
            )
        )
        return

    interval = {
        "d": Interval.DAILY,
        "h": Interval.HOUR,
        "m": Interval.MINUTE,
    }.get(args.timeframe[-1:].lower(), Interval.MINUTE)
    bars = [
        BarData(
            gateway_name=row["gateway_name"],
            symbol=row["symbol"],
            exchange=Exchange.LOCAL,
            datetime=datetime.fromisoformat(row["datetime"]),
            interval=interval,
            volume=row["volume"],
            turnover=row["turnover"],
            open_interest=row["open_interest"],
            open_price=row["open_price"],
            high_price=row["high_price"],
            low_price=row["low_price"],
            close_price=row["close_price"],
        )
        for row in rows
    ]
    print(
        json.dumps(
            {
                "nativeBars": True,
                "count": len(bars),
                "first": repr(bars[0]) if bars else None,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
