from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Iterable, Mapping, Sequence

from .client import NoryntaClient
from .streaming import NoryntaOrderBookReconciler, NoryntaStreamSequenceError


FRAMEWORK_ADAPTERS_VERSION = "2026-07-24.4"

FRAMEWORK_ADAPTERS: dict[str, dict[str, Any]] = {
    "ccxt": {
        "kind": "exchange_facade",
        "modes": ["market_data", "paper", "caller_signed_live"],
        "entrypoint": "norynta.NoryntaCcxtAdapter",
        "output": "CCXT-style markets, order books, trades, and OHLCV",
    },
    "hummingbot": {
        "kind": "clob_data_bridge",
        "modes": ["market_data", "paper"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.hummingbot_snapshot",
        "output": "Hummingbot OrderBookMessage-compatible content",
    },
    "freqtrade": {
        "kind": "ohlcv_bridge",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.ohlcv",
        "output": "Freqtrade-compatible OHLCV rows",
    },
    "nautilustrader": {
        "kind": "quote_tick_bridge",
        "modes": ["research", "replay"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.quote_ticks",
        "output": "Quote-tick records for a NautilusTrader custom data adapter",
    },
    "lean": {
        "kind": "custom_data_bridge",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.lean_rows",
        "output": "LEAN BaseData-compatible CSV rows",
    },
    "backtrader": {
        "kind": "pandas_feed",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.backtrader_frame",
        "output": "Backtrader PandasData-compatible frame",
    },
    "backtesting": {
        "kind": "pandas_feed",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.backtesting_frame",
        "output": "Backtesting.py OHLCV frame",
    },
    "vectorbt": {
        "kind": "pandas_bridge",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.vectorbt_frame",
        "output": "vectorbt-ready price and volume frame",
    },
    "vnpy": {
        "kind": "bar_data_bridge",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.vnpy_rows",
        "output": "vn.py BarData-compatible records",
    },
    "qlib": {
        "kind": "ai_dataset_bridge",
        "modes": ["research", "machine_learning", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.qlib_frame",
        "output": "Qlib instrument/datetime feature frame",
    },
    "finrl": {
        "kind": "reinforcement_learning_dataset_bridge",
        "modes": ["research", "machine_learning", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.finrl_frame",
        "output": "FinRL and FinRL-X date/ticker OHLCV frame",
    },
    "jesse": {
        "kind": "candle_bridge",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.jesse_candles",
        "output": "Jesse-compatible candle arrays",
    },
    "openbb": {
        "kind": "equity_price_model_bridge",
        "modes": ["research", "analysis"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.openbb_rows",
        "output": "OpenBB EquityHistoricalData-compatible records",
    },
    "lumibot": {
        "kind": "historical_data_bridge",
        "modes": ["research", "backtest", "paper"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.lumibot_frame",
        "output": "Lumibot PandasData-compatible OHLCV frame",
    },
    "quantstats": {
        "kind": "returns_series_bridge",
        "modes": ["research", "analytics"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.quantstats_returns",
        "output": "QuantStats-ready UTC return series",
    },
    "tensortrade": {
        "kind": "data_feed_bridge",
        "modes": ["research", "machine_learning", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.tensortrade_rows",
        "output": "TensorTrade DataFeed-compatible feature records",
    },
    "zipline": {
        "kind": "bundle_ingest_bridge",
        "modes": ["research", "backtest"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.zipline_rows",
        "output": "Zipline Reloaded bundle-ingest OHLCV records",
    },
    "octobot": {
        "kind": "historical_candle_bridge",
        "modes": ["research", "backtest", "paper"],
        "entrypoint": "norynta.NoryntaFrameworkAdapter.octobot_candles",
        "output": "OctoBot historical candle arrays",
    },
}


@dataclass(frozen=True, slots=True)
class NoryntaInstrument:
    event_pubkey: str
    outcome_index: int
    title: str = ""
    outcome: str = ""
    slug: str = ""

    @property
    def symbol(self) -> str:
        return f"{self.event_pubkey}:{self.outcome_index}/USDC"


class NoryntaSequenceError(ValueError):
    """Raised when historical market data regresses its exchange sequence."""


def _records(value: Any, *keys: str) -> list[dict[str, Any]]:
    current = value
    if isinstance(current, Mapping):
        for key in keys:
            candidate = current.get(key)
            if isinstance(candidate, list):
                current = candidate
                break
    if not isinstance(current, list):
        return []
    return [dict(row) for row in current if isinstance(row, Mapping)]


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _timestamp_ms(value: Any) -> int:
    if isinstance(value, (int, float)):
        numeric = float(value)
        if not math.isfinite(numeric):
            return 0
        return int(numeric if numeric >= 10_000_000_000 else numeric * 1000)
    raw = str(value or "").strip()
    if not raw:
        return 0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def _level(level: Any) -> list[float] | None:
    if isinstance(level, Sequence) and not isinstance(level, (str, bytes)) and len(level) >= 2:
        price_cents = _float(level[0], -1)
        size = _float(level[1], -1)
        if (
            math.isfinite(price_cents)
            and 0 <= price_cents <= 100
            and math.isfinite(size)
            and size >= 0
        ):
            return [price_cents / 100, size]
        return None
    if isinstance(level, Mapping):
        price = level.get("priceCents", level.get("price_cents", level.get("price")))
        size = level.get(
            "sizeShares",
            level.get("size_shares", level.get("size", level.get("amount"))),
        )
        if price is not None and size is not None:
            price_cents = _float(price, -1)
            normalized_size = _float(size, -1)
            if (
                math.isfinite(price_cents)
                and 0 <= price_cents <= 100
                and math.isfinite(normalized_size)
                and normalized_size >= 0
            ):
                return [price_cents / 100, normalized_size]
    return None


def _levels(value: Any, *, bids: bool) -> list[list[float]]:
    if not isinstance(value, list):
        return []
    levels = [normalized for row in value if (normalized := _level(row)) is not None]
    levels.sort(key=lambda row: row[0], reverse=bids)
    return levels


def _book_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    for key in ("orderbook", "book", "data"):
        nested = payload.get(key)
        if isinstance(nested, Mapping) and ("bids" in nested or "asks" in nested):
            return nested
    return payload


def _timeframe_ms(timeframe: str) -> int:
    units = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}
    raw = timeframe.strip().lower()
    if len(raw) < 2 or raw[-1] not in units:
        raise ValueError("timeframe must use m, h, or d, for example 1m or 1h")
    size = _int(raw[:-1])
    if size <= 0:
        raise ValueError("timeframe size must be positive")
    return size * units[raw[-1]]


class NoryntaFrameworkAdapter:
    """Normalize Norynta prediction-market data for popular OSS trading tools."""

    def __init__(self, client: NoryntaClient) -> None:
        self.client = client

    @staticmethod
    def instrument(event_pubkey: str, outcome_index: int = 0) -> NoryntaInstrument:
        event = event_pubkey.strip()
        if not event:
            raise ValueError("event_pubkey is required")
        if outcome_index < 0:
            raise ValueError("outcome_index must be non-negative")
        return NoryntaInstrument(event_pubkey=event, outcome_index=outcome_index)

    @staticmethod
    def parse_symbol(symbol: str) -> NoryntaInstrument:
        market, separator, quote = symbol.strip().partition("/")
        if separator != "/" or quote.upper() != "USDC":
            raise ValueError("symbol must be <eventPubkey>:<outcomeIndex>/USDC")
        event_pubkey, separator, outcome = market.rpartition(":")
        if separator != ":" or not event_pubkey or not outcome.isdigit():
            raise ValueError("symbol must be <eventPubkey>:<outcomeIndex>/USDC")
        return NoryntaFrameworkAdapter.instrument(event_pubkey, int(outcome))

    def markets(self, limit: int = 100) -> list[NoryntaInstrument]:
        payload = self.client.request("GET", "/api/v1/markets", query={"limit": limit})
        events = _records(payload, "events", "markets")
        instruments: list[NoryntaInstrument] = []
        for event in events:
            event_pubkey = str(
                event.get("eventPubkey")
                or event.get("event_pubkey")
                or event.get("event_v2_pubkey")
                or event.get("id")
                or ""
            ).strip()
            if not event_pubkey:
                continue
            outcomes = event.get("outcomes")
            outcome_rows = outcomes if isinstance(outcomes, list) and outcomes else ["Yes", "No"]
            for index, outcome in enumerate(outcome_rows):
                if isinstance(outcome, Mapping):
                    outcome_index = _int(outcome.get("index", outcome.get("outcomeIndex", index)), index)
                    label = str(outcome.get("label") or outcome.get("name") or outcome.get("title") or "")
                else:
                    outcome_index = index
                    label = str(outcome)
                instruments.append(
                    NoryntaInstrument(
                        event_pubkey=event_pubkey,
                        outcome_index=outcome_index,
                        title=str(event.get("title") or event.get("question") or ""),
                        outcome=label,
                        slug=str(event.get("slug") or ""),
                    )
                )
        return instruments

    def orderbook(self, instrument: NoryntaInstrument, depth: int | None = None) -> dict[str, Any]:
        payload = self.client.orderbook(instrument.event_pubkey, instrument.outcome_index, depth)
        book = _book_payload(payload)
        bids = _levels(book.get("bids"), bids=True)
        asks = _levels(book.get("asks"), bids=False)
        timestamp = _timestamp_ms(
            book.get("stateTime")
            or book.get("serverTime")
            or book.get("observedAt")
            or payload.get("serverTime")
        )
        return {
            "symbol": instrument.symbol,
            "bids": bids,
            "asks": asks,
            "timestamp": timestamp or None,
            "datetime": (
                datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()
                if timestamp
                else None
            ),
            "nonce": str(book.get("sequence") or payload.get("sequence") or "") or None,
            "info": dict(payload),
        }

    def reconciled_orderbook_stream(
        self,
        slug: str,
        instrument: NoryntaInstrument,
        *,
        interval_ms: int = 750,
        snapshot_every: int = 20,
        max_duration_ms: int = 55_000,
        reconnect: bool = True,
        stale_after_seconds: float = 30.0,
    ) -> Generator[dict[str, Any], None, None]:
        """Yield sequence-checked books and repair ambiguous deltas via REST."""
        reconciler = NoryntaOrderBookReconciler(instrument.symbol)
        for message in self.client.orderbook_stream(
            slug,
            outcome_index=instrument.outcome_index,
            interval_ms=interval_ms,
            snapshot_every=snapshot_every,
            max_duration_ms=max_duration_ms,
            reconnect=reconnect,
        ):
            event = str(message.get("event") or "")
            payload = message.get("data")
            if not isinstance(payload, Mapping):
                continue
            action = reconciler.apply(event, payload)
            output_action = str(action)
            source = "stream"
            if action == "resync_required":
                snapshot = self.orderbook(instrument)
                snapshot_info = snapshot.get("info")
                raw_info = snapshot_info if isinstance(snapshot_info, Mapping) else {}
                repair = reconciler.apply("snapshot", {
                    "sequence": snapshot.get("nonce"),
                    "bookRevision": raw_info.get("bookRevision"),
                    "sequenceConsistency": raw_info.get("sequenceConsistency"),
                    "stateTime": raw_info.get("stateTime"),
                    "serverTime": raw_info.get("serverTime"),
                    "truncated": raw_info.get("truncated"),
                    "bids": [
                        [level[0] * 100, level[1]]
                        for level in snapshot["bids"]
                    ],
                    "asks": [
                        [level[0] * 100, level[1]]
                        for level in snapshot["asks"]
                    ],
                })
                if repair != "applied":
                    raise NoryntaStreamSequenceError(
                        reconciler.resync_reason or "order-book resynchronization failed"
                    )
                output_action = "resynced"
                source = "rest_snapshot"
            if output_action not in {"applied", "resynced"} or event == "heartbeat":
                continue
            yield {
                **reconciler.state(max_age_seconds=stale_after_seconds),
                "action": output_action,
                "source": source,
            }

    def trades(
        self,
        instrument: NoryntaInstrument,
        *,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        rows = self.client.research_export(
            "trades",
            event_pubkey=instrument.event_pubkey,
            outcome_index=instrument.outcome_index,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
        )
        trades: list[dict[str, Any]] = []
        for row in rows:
            timestamp = _timestamp_ms(row.get("inserted_at") or row.get("block_time"))
            price_cents = _float(
                row.get("trade_price_cents", row.get("priceCents")),
                -1,
            )
            amount = _float(row.get("fill_shares", row.get("sizeShares")))
            if (
                timestamp <= 0
                or not math.isfinite(price_cents)
                or not 0 <= price_cents <= 100
                or not math.isfinite(amount)
                or amount < 0
            ):
                continue
            price = price_cents / 100
            trades.append(
                {
                    "id": str(row.get("id") or row.get("signature") or ""),
                    "symbol": instrument.symbol,
                    "timestamp": timestamp or None,
                    "datetime": (
                        datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).isoformat()
                        if timestamp
                        else None
                    ),
                    "price": price,
                    "amount": amount,
                    "cost": price * amount,
                    "side": None,
                    "info": row,
                }
            )
        return trades

    def ohlcv(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 10_000,
    ) -> list[list[float | int]]:
        bucket_ms = _timeframe_ms(timeframe)
        buckets: dict[int, list[float]] = {}
        trades = self.trades(
            instrument,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
        )
        trades.sort(
            key=lambda trade: (
                _int(trade.get("timestamp")),
                str(trade.get("id") or ""),
            )
        )
        seen_trade_ids: set[str] = set()
        for trade in trades:
            trade_id = str(trade.get("id") or "").strip()
            if trade_id:
                if trade_id in seen_trade_ids:
                    continue
                seen_trade_ids.add(trade_id)
            timestamp = _int(trade.get("timestamp"))
            bucket = timestamp - (timestamp % bucket_ms)
            price = _float(trade.get("price"))
            amount = _float(trade.get("amount"))
            if bucket not in buckets:
                buckets[bucket] = [price, price, price, price, amount]
            else:
                candle = buckets[bucket]
                candle[1] = max(candle[1], price)
                candle[2] = min(candle[2], price)
                candle[3] = price
                candle[4] += amount
        return [[timestamp, *buckets[timestamp]] for timestamp in sorted(buckets)]

    def orderbook_history(
        self,
        instrument: NoryntaInstrument,
        *,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        return self.client.research_export(
            "orderbooks",
            event_pubkey=instrument.event_pubkey,
            outcome_index=instrument.outcome_index,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
        )

    def quote_ticks(
        self,
        instrument: NoryntaInstrument,
        *,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 10_000,
        strict_sequences: bool = True,
    ) -> list[dict[str, Any]]:
        ticks: list[dict[str, Any]] = []
        prior_sequence: int | None = None
        for row in self.orderbook_history(
            instrument,
            from_time=from_time,
            to_time=to_time,
            limit=limit,
        ):
            sequence = str(row.get("sequence") or "")
            numeric_sequence = int(sequence) if sequence.isdigit() else None
            if numeric_sequence is not None and prior_sequence is not None:
                if numeric_sequence < prior_sequence and strict_sequences:
                    raise NoryntaSequenceError(
                        f"order-book sequence regressed from {prior_sequence} to {numeric_sequence}"
                    )
                if numeric_sequence == prior_sequence:
                    continue
            if numeric_sequence is not None:
                prior_sequence = numeric_sequence
            bids = _levels(row.get("bids"), bids=True)
            asks = _levels(row.get("asks"), bids=False)
            bid = bids[0] if bids else None
            ask = asks[0] if asks else None
            ticks.append(
                {
                    "instrument_id": instrument.symbol,
                    "timestamp": _timestamp_ms(row.get("captured_at")),
                    "sequence": sequence,
                    "bid_price": bid[0] if bid else None,
                    "bid_size": bid[1] if bid else None,
                    "ask_price": ask[0] if ask else None,
                    "ask_size": ask[1] if ask else None,
                }
            )
        return ticks

    def hummingbot_snapshot(self, instrument: NoryntaInstrument) -> dict[str, Any]:
        book = self.orderbook(instrument)
        sequence = str(book["nonce"] or "")
        return {
            "trading_pair": instrument.symbol,
            "update_id": int(sequence) if sequence.isdigit() else 0,
            "sequence": sequence,
            "timestamp": (book["timestamp"] or 0) / 1000,
            "bids": book["bids"],
            "asks": book["asks"],
        }

    def lean_rows(self, instrument: NoryntaInstrument, **filters: Any) -> list[dict[str, Any]]:
        return [
            {
                "time": datetime.fromtimestamp(tick["timestamp"] / 1000, tz=timezone.utc).isoformat(),
                "symbol": instrument.symbol,
                "bid": tick["bid_price"],
                "ask": tick["ask_price"],
                "bid_size": tick["bid_size"],
                "ask_size": tick["ask_size"],
                "sequence": tick["sequence"],
            }
            for tick in self.quote_ticks(instrument, **filters)
            if tick["timestamp"]
        ]

    def pandas_frame(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> Any:
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as error:
            raise RuntimeError("Install the research extra: pip install 'norynta[research]'") from error
        rows = self.ohlcv(instrument, timeframe=timeframe, **filters)
        frame = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if not frame.empty:
            frame["datetime"] = pd.to_datetime(frame.pop("timestamp"), unit="ms", utc=True)
            frame.set_index("datetime", inplace=True)
        return frame

    def backtrader_frame(self, instrument: NoryntaInstrument, **filters: Any) -> Any:
        return self.pandas_frame(instrument, **filters)

    def backtesting_frame(self, instrument: NoryntaInstrument, **filters: Any) -> Any:
        frame = self.pandas_frame(instrument, **filters)
        return frame.rename(columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

    def vectorbt_frame(self, instrument: NoryntaInstrument, **filters: Any) -> Any:
        return self.pandas_frame(instrument, **filters)

    def vnpy_rows(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        return [
            {
                "gateway_name": "NORYNTA",
                "symbol": f"{instrument.event_pubkey}:{instrument.outcome_index}",
                "exchange": "LOCAL",
                "datetime": datetime.fromtimestamp(
                    row[0] / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                "interval": timeframe,
                "volume": row[5],
                "turnover": row[4] * row[5],
                "open_interest": 0.0,
                "open_price": row[1],
                "high_price": row[2],
                "low_price": row[3],
                "close_price": row[4],
            }
            for row in self.ohlcv(instrument, timeframe=timeframe, **filters)
        ]

    def qlib_rows(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        return [
            {
                "instrument": f"{instrument.event_pubkey}:{instrument.outcome_index}",
                "datetime": datetime.fromtimestamp(
                    row[0] / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "factor": 1.0,
            }
            for row in self.ohlcv(instrument, timeframe=timeframe, **filters)
        ]

    def finrl_rows(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self.ohlcv(instrument, timeframe=timeframe, **filters):
            observed_at = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc)
            rows.append(
                {
                    "date": observed_at.isoformat(),
                    "tic": f"{instrument.event_pubkey}:{instrument.outcome_index}",
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5],
                    "day": observed_at.weekday(),
                }
            )
        return rows

    def jesse_candles(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[list[float | int]]:
        return [
            [row[0], row[1], row[4], row[2], row[3], row[5]]
            for row in self.ohlcv(instrument, timeframe=timeframe, **filters)
        ]

    def qlib_frame(self, instrument: NoryntaInstrument, **filters: Any) -> Any:
        try:
            import pandas as pd
        except ImportError as error:
            raise RuntimeError("Install the research extra: pip install 'norynta[research]'") from error
        frame = pd.DataFrame(self.qlib_rows(instrument, **filters))
        if not frame.empty:
            frame["datetime"] = pd.to_datetime(frame["datetime"], utc=True)
            frame.set_index(["datetime", "instrument"], inplace=True)
        return frame

    def finrl_frame(self, instrument: NoryntaInstrument, **filters: Any) -> Any:
        try:
            import pandas as pd
        except ImportError as error:
            raise RuntimeError("Install the research extra: pip install 'norynta[research]'") from error
        return pd.DataFrame(self.finrl_rows(instrument, **filters))

    def openbb_rows(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Return OpenBB EquityHistoricalData-compatible records."""
        return [
            {
                "date": datetime.fromtimestamp(
                    row[0] / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "vwap": row[4],
                "symbol": instrument.symbol,
            }
            for row in self.ohlcv(instrument, timeframe=timeframe, **filters)
        ]

    def lumibot_frame(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> Any:
        """Return a UTC-indexed frame accepted by Lumibot's pandas data source."""
        frame = self.pandas_frame(
            instrument,
            timeframe=timeframe,
            **filters,
        )
        return frame.rename(columns={"volume": "volume"})

    def quantstats_returns(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> Any:
        """Return a UTC-indexed decimal return series for QuantStats."""
        frame = self.pandas_frame(
            instrument,
            timeframe=timeframe,
            **filters,
        )
        returns = frame["close"].pct_change().dropna()
        returns.name = instrument.symbol
        return returns

    def tensortrade_rows(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Return deterministic features suitable for TensorTrade Stream sources."""
        rows = self.ohlcv(instrument, timeframe=timeframe, **filters)
        output: list[dict[str, Any]] = []
        prior_close: float | None = None
        for row in rows:
            close = float(row[4])
            output.append(
                {
                    "timestamp": int(row[0]),
                    "symbol": instrument.symbol,
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": close,
                    "volume": row[5],
                    "return": (
                        (close / prior_close) - 1
                        if prior_close not in {None, 0.0}
                        else 0.0
                    ),
                }
            )
            prior_close = close
        return output

    def zipline_rows(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Return rows for a Zipline Reloaded custom bundle ingest function."""
        return [
            {
                "date": datetime.fromtimestamp(
                    row[0] / 1000,
                    tz=timezone.utc,
                ).isoformat(),
                "symbol": instrument.symbol,
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "dividend": 0.0,
                "split": 1.0,
            }
            for row in self.ohlcv(instrument, timeframe=timeframe, **filters)
        ]

    def octobot_candles(
        self,
        instrument: NoryntaInstrument,
        *,
        timeframe: str = "1m",
        **filters: Any,
    ) -> list[list[float | int]]:
        """Return OctoBot historical candles as time/open/high/low/close/volume."""
        return [
            [row[0] // 1000, row[1], row[2], row[3], row[4], row[5]]
            for row in self.ohlcv(instrument, timeframe=timeframe, **filters)
        ]


class NoryntaCcxtAdapter:
    """Small CCXT-style façade without making CCXT a runtime dependency.

    The façade intentionally does not load wallet keys. Live writes require a
    caller-signed Norynta body and deterministic idempotency key in ``params``.
    """

    id = "norynta"
    name = "Norynta"
    countries: list[str] = []
    rateLimit = 250
    has = {
        "fetchMarkets": True,
        "fetchOrderBook": True,
        "fetchTrades": True,
        "fetchOHLCV": True,
        "createOrder": True,
        "cancelOrder": True,
    }
    timeframes = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "1h", "1d": "1d"}

    def __init__(
        self,
        client: NoryntaClient | None = None,
        *,
        base_url: str = "https://norynta.com",
        api_key: str | None = None,
    ) -> None:
        self.client = client or NoryntaClient(base_url=base_url, api_key=api_key)
        self.adapter = NoryntaFrameworkAdapter(self.client)
        self.markets: dict[str, dict[str, Any]] = {}

    def fetch_markets(self, limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{instrument.event_pubkey}:{instrument.outcome_index}",
                "symbol": instrument.symbol,
                "base": f"{instrument.event_pubkey}:{instrument.outcome_index}",
                "quote": "USDC",
                "settle": "USDC",
                "active": True,
                "spot": False,
                "contract": True,
                "prediction": True,
                "precision": {"price": 0.01, "amount": 1},
                "limits": {"price": {"min": 0.01, "max": 0.99}, "amount": {"min": 1}},
                "info": {
                    "eventPubkey": instrument.event_pubkey,
                    "outcomeIndex": instrument.outcome_index,
                    "title": instrument.title,
                    "outcome": instrument.outcome,
                    "slug": instrument.slug,
                },
            }
            for instrument in self.adapter.markets(limit=limit)
        ]

    def load_markets(self, reload: bool = False, params: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
        if reload or not self.markets:
            limit = _int((params or {}).get("limit"), 100)
            self.markets = {market["symbol"]: market for market in self.fetch_markets(limit)}
        return self.markets

    def fetch_order_book(self, symbol: str, limit: int | None = None, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        del params
        return self.adapter.orderbook(self.adapter.parse_symbol(symbol), limit)

    def fetch_trades(
        self,
        symbol: str,
        since: int | None = None,
        limit: int = 1000,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        filters = dict(params or {})
        from_time = filters.get("from")
        if since is not None:
            from_time = datetime.fromtimestamp(since / 1000, tz=timezone.utc).isoformat()
        return self.adapter.trades(
            self.adapter.parse_symbol(symbol),
            from_time=str(from_time) if from_time else None,
            to_time=str(filters["to"]) if filters.get("to") else None,
            limit=limit,
        )

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1m",
        since: int | None = None,
        limit: int = 1000,
        params: Mapping[str, Any] | None = None,
    ) -> list[list[float | int]]:
        filters = dict(params or {})
        from_time = filters.get("from")
        if since is not None:
            from_time = datetime.fromtimestamp(since / 1000, tz=timezone.utc).isoformat()
        return self.adapter.ohlcv(
            self.adapter.parse_symbol(symbol),
            timeframe=timeframe,
            from_time=str(from_time) if from_time else None,
            to_time=str(filters["to"]) if filters.get("to") else None,
            limit=limit,
        )

    def create_order(
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        price: float | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        options = dict(params or {})
        instrument = self.adapter.parse_symbol(symbol)
        if type.lower() != "limit" or price is None:
            raise ValueError("Norynta adapter currently accepts priced limit orders only")
        normalized_side = side.strip().lower()
        if normalized_side not in {"buy", "sell"}:
            raise ValueError("side must be buy or sell")
        if not float(amount).is_integer() or amount <= 0:
            raise ValueError("amount must be a positive whole number of contracts")
        if price < 0.01 or price > 0.99:
            raise ValueError("price must be from 0.01 to 0.99 USDC")
        if options.get("paper", True):
            if normalized_side != "buy":
                raise ValueError(
                    "paper create_order opens buy positions only; close an existing "
                    "paper position with NoryntaClient.close_paper_position"
                )
            key = str(options.get("idempotencyKey") or "").strip()
            if not key:
                raise ValueError("params.idempotencyKey is required for paper orders")
            response = self.client.open_paper_position(
                {
                    "eventPubkey": instrument.event_pubkey,
                    "outcomeIndex": instrument.outcome_index,
                    "contracts": int(amount),
                    "limitPriceCents": round(price * 100),
                },
                idempotency_key=key,
            )
            position = response.get("position")
            position_id = position.get("id") if isinstance(position, Mapping) else None
            return {
                "id": str(position_id or response.get("positionId") or response.get("id") or ""),
                "info": response,
            }
        signed_order = options.get("signedOrder")
        key = str(options.get("idempotencyKey") or "").strip()
        if not isinstance(signed_order, Mapping) or not key:
            raise ValueError(
                "live orders require params.signedOrder and params.idempotencyKey; "
                "the adapter never loads wallet keys"
            )
        signed_intent = signed_order.get("order")
        if not isinstance(signed_intent, Mapping):
            signed_intent = signed_order
        expected = {
            "eventPubkey": instrument.event_pubkey,
            "outcomeIndex": instrument.outcome_index,
            "side": normalized_side,
            "priceCents": round(price * 100),
            "sizeShares": int(amount),
        }
        aliases = {
            "eventPubkey": ("eventPubkey", "event_pubkey", "market"),
            "outcomeIndex": ("outcomeIndex", "outcome_index"),
            "side": ("side",),
            "priceCents": ("priceCents", "price_cents"),
            "sizeShares": ("sizeShares", "size_shares", "contracts"),
        }
        for field, names in aliases.items():
            actual = next((signed_intent[name] for name in names if name in signed_intent), None)
            if actual is None:
                continue
            if field in {"outcomeIndex", "priceCents", "sizeShares"}:
                matches = _int(actual, -1) == expected[field]
            else:
                matches = str(actual).strip().lower() == str(expected[field]).lower()
            if not matches:
                raise ValueError(
                    f"params.signedOrder {field} does not match the CCXT-style order arguments"
                )
        response = self.client.place_order(signed_order, key)
        return {"id": str(response.get("orderId") or response.get("id") or ""), "info": response}

    def cancel_order(
        self,
        id: str,
        symbol: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        del id, symbol
        options = dict(params or {})
        signed_cancel = options.get("signedCancel")
        key = str(options.get("idempotencyKey") or "").strip()
        if not isinstance(signed_cancel, Mapping) or not key:
            raise ValueError(
                "cancel_order requires params.signedCancel and params.idempotencyKey; "
                "the adapter never loads wallet keys"
            )
        response = self.client.cancel_orders(signed_cancel, key)
        return {"info": response}


def _write_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = [dict(row) for row in rows]
    fields = list(dict.fromkeys(key for row in materialized for key in row))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(materialized)
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        os.replace(temporary, path)
    except BaseException:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="norynta-adapters")
    parser.add_argument("--base-url", default=os.getenv("NORYNTA_BASE_URL", "https://norynta.com"))
    parser.add_argument("--api-key", default=os.getenv("NORYNTA_AGENT_API_KEY"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="List supported OSS framework bridges")
    subparsers.add_parser("doctor", help="Check Norynta discovery and adapter metadata")
    export = subparsers.add_parser("export", help="Export framework-ready market data")
    export.add_argument("framework", choices=sorted(FRAMEWORK_ADAPTERS))
    export.add_argument("event_pubkey")
    export.add_argument("--outcome-index", type=int, default=0)
    export.add_argument("--timeframe", default="1m")
    export.add_argument("--from-time")
    export.add_argument("--to-time")
    export.add_argument("--output", required=True)
    export.add_argument("--limit", type=int, default=10_000)
    args = parser.parse_args(argv)

    if args.command == "list":
        print(json.dumps(FRAMEWORK_ADAPTERS, indent=2, sort_keys=True))
        return 0

    client = NoryntaClient(base_url=args.base_url, api_key=args.api_key)
    adapter = NoryntaFrameworkAdapter(client)
    if args.command == "doctor":
        discovery = client.discover()
        compatibility = discovery.get("compatibility", {})
        server_adapters = (
            compatibility.get("ossAdapters", {})
            if isinstance(compatibility, Mapping)
            else {}
        )
        normalized_server_adapters = (
            {
                str(name).lower()
                for name in server_adapters
                if str(name) not in {"policy", "openClaw"}
            }
            if isinstance(server_adapters, Mapping)
            else set()
        )
        missing_server_adapters = sorted(
            set(FRAMEWORK_ADAPTERS) - normalized_server_adapters
        )
        contract_aligned = not missing_server_adapters
        print(json.dumps({
            "ok": contract_aligned,
            "baseUrl": client.base_url,
            "adapterSchemaVersion": FRAMEWORK_ADAPTERS_VERSION,
            "contractAligned": contract_aligned,
            "adapterCount": len(FRAMEWORK_ADAPTERS),
            "frameworks": sorted(FRAMEWORK_ADAPTERS),
            "serverAdvertisedAdapters": sorted(normalized_server_adapters),
            "missingServerAdapters": missing_server_adapters,
            "compatibilityPosture": (
                compatibility.get("posture") if isinstance(compatibility, Mapping) else None
            ),
        }, indent=2))
        return 0 if contract_aligned else 1

    instrument = adapter.instrument(args.event_pubkey, args.outcome_index)
    destination = Path(args.output)
    if args.framework == "ccxt":
        payload = {
            "orderbook": adapter.orderbook(instrument),
            "trades": adapter.trades(
                instrument,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        }
        _write_text(destination, json.dumps(payload, indent=2))
    elif args.framework == "hummingbot":
        _write_text(
            destination,
            json.dumps(adapter.hummingbot_snapshot(instrument), indent=2),
        )
    elif args.framework in {
        "freqtrade",
        "backtrader",
        "backtesting",
        "vectorbt",
        "lumibot",
    }:
        rows = adapter.ohlcv(
            instrument,
            timeframe=args.timeframe,
            from_time=args.from_time,
            to_time=args.to_time,
            limit=args.limit,
        )
        if args.framework == "backtesting":
            _write_rows(
                destination,
                (
                    {
                        "Date": datetime.fromtimestamp(
                            row[0] / 1000,
                            tz=timezone.utc,
                        ).isoformat(),
                        "Open": row[1],
                        "High": row[2],
                        "Low": row[3],
                        "Close": row[4],
                        "Volume": row[5],
                    }
                    for row in rows
                ),
            )
        else:
            _write_rows(
                destination,
                (
                    {
                        "date": datetime.fromtimestamp(
                            row[0] / 1000,
                            tz=timezone.utc,
                        ).isoformat(),
                        "open": row[1],
                        "high": row[2],
                        "low": row[3],
                        "close": row[4],
                        "volume": row[5],
                    }
                    for row in rows
                ),
            )
    elif args.framework == "openbb":
        _write_rows(
            destination,
            adapter.openbb_rows(
                instrument,
                timeframe=args.timeframe,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    elif args.framework == "tensortrade":
        _write_rows(
            destination,
            adapter.tensortrade_rows(
                instrument,
                timeframe=args.timeframe,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    elif args.framework == "zipline":
        _write_rows(
            destination,
            adapter.zipline_rows(
                instrument,
                timeframe=args.timeframe,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    elif args.framework == "octobot":
        _write_rows(
            destination,
            (
                {
                    "timestamp": row[0],
                    "open": row[1],
                    "high": row[2],
                    "low": row[3],
                    "close": row[4],
                    "volume": row[5],
                }
                for row in adapter.octobot_candles(
                    instrument,
                    timeframe=args.timeframe,
                    from_time=args.from_time,
                    to_time=args.to_time,
                    limit=args.limit,
                )
            ),
        )
    elif args.framework == "quantstats":
        candles = adapter.ohlcv(
            instrument,
            timeframe=args.timeframe,
            from_time=args.from_time,
            to_time=args.to_time,
            limit=args.limit,
        )
        previous_close: float | None = None
        returns: list[dict[str, Any]] = []
        for row in candles:
            close = float(row[4])
            if previous_close not in {None, 0.0}:
                returns.append({
                    "date": datetime.fromtimestamp(
                        row[0] / 1000,
                        tz=timezone.utc,
                    ).isoformat(),
                    "return": close / previous_close - 1,
                })
            previous_close = close
        _write_rows(destination, returns)
    elif args.framework == "vnpy":
        _write_rows(
            destination,
            adapter.vnpy_rows(
                instrument,
                timeframe=args.timeframe,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    elif args.framework == "qlib":
        _write_rows(
            destination,
            adapter.qlib_rows(
                instrument,
                timeframe=args.timeframe,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    elif args.framework == "finrl":
        _write_rows(
            destination,
            adapter.finrl_rows(
                instrument,
                timeframe=args.timeframe,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    elif args.framework == "jesse":
        _write_rows(
            destination,
            (
                {
                    "timestamp": row[0],
                    "open": row[1],
                    "close": row[2],
                    "high": row[3],
                    "low": row[4],
                    "volume": row[5],
                }
                for row in adapter.jesse_candles(
                    instrument,
                    timeframe=args.timeframe,
                    from_time=args.from_time,
                    to_time=args.to_time,
                    limit=args.limit,
                )
            ),
        )
    elif args.framework == "lean":
        _write_rows(
            destination,
            adapter.lean_rows(
                instrument,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    else:
        _write_rows(
            destination,
            adapter.quote_ticks(
                instrument,
                from_time=args.from_time,
                to_time=args.to_time,
                limit=args.limit,
            ),
        )
    print(json.dumps({"ok": True, "framework": args.framework, "output": str(destination)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
