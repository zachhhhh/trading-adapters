from __future__ import annotations

import argparse
import json
import os

from norynta import NoryntaClient, NoryntaFrameworkAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("event_pubkey")
    parser.add_argument("--outcome-index", type=int, default=0)
    parser.add_argument("--timeframe", choices=["1m", "1d"], default="1m")
    args = parser.parse_args()

    adapter = NoryntaFrameworkAdapter(
        NoryntaClient(
            base_url=os.getenv("NORYNTA_BASE_URL", "http://localhost:3000"),
            api_key=os.getenv("NORYNTA_AGENT_API_KEY"),
        )
    )
    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    frame = adapter.lumibot_frame(instrument, timeframe=args.timeframe)
    try:
        from lumibot.entities import Asset, Data
    except ImportError:
        print(json.dumps({
            "nativeData": False,
            "rows": frame.reset_index().head().to_dict(orient="records"),
            "hint": "Install Lumibot to construct native Asset and Data objects.",
        }, indent=2, default=str))
        return

    asset = Asset(
        symbol=f"{instrument.event_pubkey}:{instrument.outcome_index}",
        asset_type=Asset.AssetType.CRYPTO,
    )
    quote = Asset(symbol="USDC", asset_type=Asset.AssetType.CRYPTO)
    data = Data(
        asset,
        frame,
        timestep="day" if args.timeframe == "1d" else "minute",
        quote=quote,
        timezone="UTC",
    )
    print(json.dumps({
        "nativeData": True,
        "asset": repr(asset),
        "data": repr(data),
        "rows": len(frame),
    }, indent=2))


if __name__ == "__main__":
    main()
