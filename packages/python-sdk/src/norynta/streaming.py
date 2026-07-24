from __future__ import annotations

import math
import re
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal


ReconcileAction = Literal["applied", "ignored", "resync_required"]


class NoryntaStreamSequenceError(ValueError):
    """Raised when a stream cannot be repaired with an authoritative snapshot."""


def _sequence(value: Any) -> int | None:
    raw = str(value or "").strip()
    return int(raw) if raw.isdecimal() else None


def _level(value: Any) -> tuple[float, float] | None:
    if isinstance(value, Mapping):
        price = value.get("priceCents", value.get("price_cents"))
        size = value.get(
            "sizeShares",
            value.get("size_shares", value.get("size", value.get("amount"))),
        )
    elif (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) >= 2
    ):
        price, size = value[0], value[1]
    else:
        return None
    try:
        normalized_price = float(price)
        normalized_size = float(size)
    except (TypeError, ValueError):
        return None
    if (
        not math.isfinite(normalized_price)
        or not 0 <= normalized_price <= 100
        or not math.isfinite(normalized_size)
        or normalized_size < 0
    ):
        return None
    return normalized_price, normalized_size


class NoryntaOrderBookReconciler:
    """Apply Norynta SSE snapshots and deltas without assuming contiguous sequences.

    Norynta exchange sequences are global, so another market can create a gap.
    A gap is therefore valid. Reconciliation is required only when stream state
    is ambiguous: a delta arrives before a snapshot, a sequence regresses, a
    same-sequence delta would change state, or a level is malformed.
    """

    def __init__(
        self,
        symbol: str,
        *,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not symbol.strip():
            raise ValueError("symbol is required")
        self.symbol = symbol
        self._clock = monotonic_clock
        self._bids: dict[float, float] = {}
        self._asks: dict[float, float] = {}
        self._sequence: int | None = None
        self._sequence_text: str | None = None
        self._sequence_consistency: str | None = None
        self._book_revision: str | None = None
        self._state_time: str | None = None
        self._server_time: str | None = None
        self._truncated: bool | None = None
        self._last_event_at: float | None = None
        self._resync_count = 0
        self._resync_reason: str | None = None
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def needs_resync(self) -> bool:
        return self._resync_reason is not None

    @property
    def resync_reason(self) -> str | None:
        return self._resync_reason

    def _require_resync(self, reason: str) -> ReconcileAction:
        self._resync_count += 1
        self._resync_reason = reason
        return "resync_required"

    def _metadata(self, payload: Mapping[str, Any]) -> None:
        consistency = str(payload.get("sequenceConsistency") or "").strip()
        if consistency:
            self._sequence_consistency = consistency
        state_time = str(payload.get("stateTime") or "").strip()
        if state_time:
            self._state_time = state_time
        server_time = str(payload.get("serverTime") or "").strip()
        if server_time:
            self._server_time = server_time
        self._last_event_at = self._clock()

    @staticmethod
    def _parse_side(value: Any) -> dict[float, float] | None:
        if not isinstance(value, list):
            return None
        parsed: dict[float, float] = {}
        for raw_level in value:
            level = _level(raw_level)
            if level is None:
                return None
            price, size = level
            if size > 0:
                parsed[price] = size
        return parsed

    def apply(self, event: str, payload: Mapping[str, Any]) -> ReconcileAction:
        event_name = event.strip().lower()
        if event_name not in {"snapshot", "delta", "heartbeat"}:
            return "ignored"
        sequence = _sequence(payload.get("sequence"))
        if sequence is None:
            return self._require_resync(f"{event_name} has an invalid sequence")
        if self._sequence is not None and sequence < self._sequence:
            return self._require_resync(
                f"{event_name} sequence regressed from {self._sequence} to {sequence}"
            )

        payload_revision = str(payload.get("bookRevision") or "").strip() or None
        if payload_revision is not None and not re.fullmatch(r"[a-f0-9]{64}", payload_revision):
            return self._require_resync(f"{event_name} has an invalid book revision")

        if event_name == "heartbeat":
            if (
                self._book_revision is not None
                and payload_revision is not None
                and payload_revision != self._book_revision
            ):
                return self._require_resync(
                    "heartbeat revision does not match the current book"
                )
            self._metadata(payload)
            return "applied"

        bids = self._parse_side(payload.get("bids"))
        asks = self._parse_side(payload.get("asks"))
        if bids is None or asks is None:
            return self._require_resync(f"{event_name} contains an invalid price level")

        if event_name == "snapshot":
            self._bids = bids
            self._asks = asks
            self._sequence = sequence
            self._sequence_text = str(payload.get("sequence"))
            self._book_revision = payload_revision
            truncated = payload.get("truncated")
            self._truncated = truncated if isinstance(truncated, bool) else None
            self._initialized = True
            self._resync_reason = None
            self._metadata(payload)
            return "applied"

        if not self._initialized:
            return self._require_resync("delta arrived before an authoritative snapshot")

        previous_revision = (
            str(payload.get("previousBookRevision") or "").strip() or None
        )
        if previous_revision is not None and not re.fullmatch(
            r"[a-f0-9]{64}",
            previous_revision,
        ):
            return self._require_resync("delta has an invalid previous book revision")
        if previous_revision is not None and previous_revision != self._book_revision:
            return self._require_resync(
                "delta previous revision does not match the current book"
            )

        changes_state = any(
            (size == 0 and price in current) or (size > 0 and current.get(price) != size)
            for updates, current in ((bids, self._bids), (asks, self._asks))
            for price, size in updates.items()
        )
        raw_changes_include_deletes = any(
            (level := _level(raw_level)) is not None
            and level[1] == 0
            and level[0] in current
            for raw_side, current in (
                (payload.get("bids"), self._bids),
                (payload.get("asks"), self._asks),
            )
            if isinstance(raw_side, list)
            for raw_level in raw_side
        )
        changes_state = changes_state or raw_changes_include_deletes
        if self._sequence == sequence:
            if (
                changes_state
                or (
                    payload_revision is not None
                    and payload_revision != self._book_revision
                )
            ):
                return self._require_resync(
                    f"delta sequence {sequence} conflicts with the current book"
                )
            self._metadata(payload)
            return "ignored"

        for raw_side, current in (
            (payload.get("bids"), self._bids),
            (payload.get("asks"), self._asks),
        ):
            assert isinstance(raw_side, list)
            for raw_level in raw_side:
                level = _level(raw_level)
                assert level is not None
                price, size = level
                if size == 0:
                    current.pop(price, None)
                else:
                    current[price] = size
        self._sequence = sequence
        self._sequence_text = str(payload.get("sequence"))
        self._book_revision = payload_revision
        self._resync_reason = None
        self._metadata(payload)
        return "applied"

    def is_stale(self, max_age_seconds: float = 30.0) -> bool:
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, (int, float))
            or not math.isfinite(max_age_seconds)
            or max_age_seconds < 0
        ):
            raise ValueError("max_age_seconds must be a finite non-negative number")
        return (
            self._last_event_at is None
            or self._clock() - self._last_event_at > max_age_seconds
        )

    def state(self, *, max_age_seconds: float = 30.0) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bids": [
                [price / 100, self._bids[price]]
                for price in sorted(self._bids, reverse=True)
            ],
            "asks": [
                [price / 100, self._asks[price]]
                for price in sorted(self._asks)
            ],
            "sequence": self._sequence_text,
            "bookRevision": self._book_revision,
            "sequenceConsistency": self._sequence_consistency,
            "stateTime": self._state_time,
            "serverTime": self._server_time,
            "truncated": self._truncated,
            "initialized": self._initialized,
            "stale": self.is_stale(max_age_seconds),
            "needsResync": self.needs_resync,
            "resyncReason": self._resync_reason,
            "resyncCount": self._resync_count,
        }
