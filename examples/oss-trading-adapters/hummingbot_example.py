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

    client = NoryntaClient(
        base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
        api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
    )
    adapter = NoryntaFrameworkAdapter(client)
    snapshot = adapter.hummingbot_snapshot(
        adapter.instrument(args.event_pubkey, args.outcome_index)
    )
    result: dict[str, object] = {"content": snapshot, "nativeMessage": False}
    try:
        from hummingbot.core.data_type.order_book_message import (
            OrderBookMessage,
            OrderBookMessageType,
        )
    except ImportError:
        result["hint"] = (
            "Install Hummingbot to construct its native OrderBookMessage; "
            "the emitted content is already compatible."
        )
    else:
        message = OrderBookMessage(
            OrderBookMessageType.SNAPSHOT,
            snapshot,
            float(snapshot["timestamp"]),
        )
        result["nativeMessage"] = True
        result["updateId"] = str(message.update_id)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
