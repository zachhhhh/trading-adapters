from __future__ import annotations

import argparse
import json
import os

from norynta import NoryntaCcxtAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    parser.add_argument("--paper", action="store_true")
    parser.add_argument("--contracts", type=int, default=1)
    parser.add_argument("--price", type=float, default=0.49)
    parser.add_argument("--idempotency-key")
    args = parser.parse_args()

    exchange = NoryntaCcxtAdapter(
        base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
        api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
    )
    symbol = f"{args.event_pubkey}:{args.outcome_index}/USDC"
    payload: dict[str, object] = {
        "symbol": symbol,
        "orderbook": exchange.fetch_order_book(symbol),
    }
    if args.paper:
        if not args.idempotency_key:
            parser.error("--idempotency-key is required with --paper")
        payload["paperOrder"] = exchange.create_order(
            symbol,
            "limit",
            "buy",
            args.contracts,
            args.price,
            {"idempotencyKey": args.idempotency_key},
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
