from __future__ import annotations

import argparse
import json
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("slug")
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    parser.add_argument("--updates", type=int, default=10)
    args = parser.parse_args()

    client = NoryntaClient(
        base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
        api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
    )
    adapter = NoryntaFrameworkAdapter(client)
    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    for index, book in enumerate(
        adapter.reconciled_orderbook_stream(args.slug, instrument),
        start=1,
    ):
        print(json.dumps(book, separators=(",", ":")))
        if index >= args.updates:
            break


if __name__ == "__main__":
    main()
