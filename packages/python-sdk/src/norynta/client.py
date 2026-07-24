"""Norynta HTTP and streaming clients using only the Python standard library."""

from __future__ import annotations

import asyncio
import csv
import json
import math
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Generator, Iterable, Mapping, Sequence
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


class NoryntaApiError(RuntimeError):
    """An HTTP, protocol, or timeout failure returned by Norynta."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str = "HTTP_ERROR",
        request_id: str | None = None,
        retryable: bool | None = None,
        hint: str | None = None,
        retry_after: float | None = None,
    ) -> None:
        rendered = f"{status} {code}: {message}" if status is not None else message
        super().__init__(rendered)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.retryable = (
            status in {408, 409, 425, 429, 500, 502, 503, 504}
            if retryable is None
            else retryable
        )
        self.hint = hint
        self.retry_after = retry_after


class NoryntaClient:
    """Synchronous client for discovery, research, streams, and signed orders.

    The client never loads or stores wallet private keys. Trading methods accept
    caller-built, wallet-signed request bodies and require deterministic
    idempotency keys at the client boundary.
    """

    def __init__(
        self,
        base_url: str = "https://norynta.com",
        api_key: str | None = None,
        timeout: float = 15.0,
        user_agent: str = "norynta-python/0.1.0",
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
        retry_max_delay_seconds: float = 5.0,
        retry_jitter: float = 0.25,
    ) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("base_url must be an absolute HTTP(S) URL")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer")
        for name, value in {
            "retry_backoff_seconds": retry_backoff_seconds,
            "retry_max_delay_seconds": retry_max_delay_seconds,
            "retry_jitter": retry_jitter,
        }.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")
        self.base_url = base_url.rstrip("/")
        self.api_key = (api_key or "").strip() or None
        self.timeout = timeout
        self.user_agent = user_agent
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds
        self.retry_jitter = retry_jitter

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": self.user_agent}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if extra:
            headers.update({str(key): str(value) for key, value in extra.items()})
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | list[Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonObject:
        url = urllib.parse.urljoin(f"{self.base_url}/", path.lstrip("/"))
        if query:
            encoded = urllib.parse.urlencode(
                {key: value for key, value in query.items() if value is not None},
                doseq=True,
            )
            if encoded:
                url = f"{url}?{encoded}"
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        request_headers = self._headers(headers)
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        request_method = method.upper()
        retry_safe = request_method in {"GET", "HEAD", "OPTIONS"} or any(
            str(key).lower() == "idempotency-key" and str(value).strip()
            for key, value in request_headers.items()
        )
        for attempt in range(self.max_retries + 1):
            request = urllib.request.Request(
                url,
                data=payload,
                headers=request_headers,
                method=request_method,
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                    request_id = response.headers.get("x-request-id")
            except urllib.error.HTTPError as error:
                api_error = self._api_error(error)
                if not retry_safe or not api_error.retryable or attempt >= self.max_retries:
                    raise api_error from error
                time.sleep(self._retry_delay(attempt, api_error.retry_after))
                continue
            except (urllib.error.URLError, TimeoutError, socket.timeout) as error:
                if retry_safe and attempt < self.max_retries:
                    time.sleep(self._retry_delay(attempt))
                    continue
                raise NoryntaApiError(f"Norynta request failed: {error}") from error
            try:
                value = json.loads(raw) if raw else {}
            except json.JSONDecodeError as error:
                raise NoryntaApiError(
                    "Norynta returned a non-JSON response",
                    request_id=request_id,
                ) from error
            if not isinstance(value, dict):
                raise NoryntaApiError(
                    "Norynta returned an unexpected JSON value",
                    request_id=request_id,
                )
            return value
        raise RuntimeError("request retry loop exited unexpectedly")

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonObject:
        """Backward-compatible request hook used by the original SDK methods."""
        return self.request(method, path, body=body, headers=headers)

    @staticmethod
    def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
        raw = str(error.headers.get("retry-after") or "").strip()
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(raw)
                return max(0.0, retry_at.timestamp() - time.time())
            except (TypeError, ValueError, OverflowError):
                return None

    def _retry_delay(self, attempt: int, retry_after: float | None = None) -> float:
        base = retry_after if retry_after is not None else self.retry_backoff_seconds * (2**attempt)
        jitter = base * self.retry_jitter * random.random()
        return min(self.retry_max_delay_seconds, base + jitter)

    def _api_error(self, error: urllib.error.HTTPError) -> NoryntaApiError:
        raw = error.read()
        try:
            decoded = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            decoded = raw.decode(errors="replace")
        parsed = decoded if isinstance(decoded, Mapping) else {"message": str(decoded)}
        return NoryntaApiError(
            str(parsed.get("message") or parsed.get("error") or error.reason),
            status=error.code,
            code=str(parsed.get("code") or "HTTP_ERROR"),
            retryable=bool(parsed.get("retryable", error.code == 429 or error.code >= 500)),
            request_id=parsed.get("requestId") or error.headers.get("x-request-id"),
            hint=parsed.get("hint") or parsed.get("remediation"),
            retry_after=self._retry_after_seconds(error),
        )

    def search_markets(self, query: str, *, limit: int = 10) -> JsonObject:
        if not query.strip():
            raise ValueError("query must not be empty")
        return self.request("GET", "/api/search", query={"q": query, "limit": limit})

    def top_events(self, *, limit: int = 10) -> JsonObject:
        return self.request("GET", "/api/events/top", query={"limit": limit})

    def event_snapshots(self, slugs: Sequence[str]) -> JsonObject:
        values = [slug.strip() for slug in slugs if slug.strip()]
        if not values:
            raise ValueError("slugs must contain at least one event slug")
        if len(values) > 200:
            raise ValueError("slugs must contain at most 200 event slugs")
        return self.request("POST", "/api/events/snapshots", body={"slugs": values})

    def snapshots(
        self,
        *,
        slugs: Iterable[str] = (),
        event_pubkeys: Iterable[str] = (),
        lookback_hours: int = 72,
        outcome_limit: int = 16,
        include_resolved: bool = False,
    ) -> JsonObject:
        return self.request(
            "POST",
            "/api/events/snapshots",
            body={
                "slugs": list(slugs),
                "eventPubkeys": list(event_pubkeys),
                "lookbackHours": lookback_hours,
                "outcomeLimit": outcome_limit,
                "includeResolved": include_resolved,
            },
        )

    def event(self, slug: str) -> JsonObject:
        return self.request("GET", f"/api/events/{urllib.parse.quote(slug, safe='')}")

    def orderbook(
        self,
        event_pubkey: str,
        outcome_index: int = 0,
        depth: int | None = None,
    ) -> JsonObject:
        return self.request(
            "GET",
            f"/api/v1/markets/{urllib.parse.quote(event_pubkey, safe='')}/orderbook",
            query={"outcomeIndex": outcome_index, "depth": depth},
        )

    def discover(self) -> JsonObject:
        return self.request("GET", "/api/agent/access")

    def agent_bootstrap(self) -> JsonObject:
        return {
            "wellKnown": self.request("GET", "/.well-known/agent.json"),
            "card": self.request("GET", "/api/agent/card"),
            "access": self.discover(),
            "config": self.request("GET", "/api/bot/config"),
        }

    def service_levels(self) -> JsonObject:
        return self.request("GET", "/api/v1/developer/service-levels")

    def latency(self) -> JsonObject:
        return self.request("GET", "/api/v1/developer/latency")

    def quant(
        self,
        *,
        slugs: Iterable[str] = (),
        event_pubkeys: Iterable[str] = (),
    ) -> JsonObject:
        return self.request(
            "POST",
            "/api/bot/quant",
            body={"slugs": list(slugs), "eventPubkeys": list(event_pubkeys)},
        )

    def backtest(self, simulation: Mapping[str, Any]) -> JsonObject:
        return self.request("POST", "/api/v1/simulations/backtest", body=dict(simulation))

    def paper_positions(self, status: str = "open") -> JsonObject:
        return self.request("GET", "/api/v1/paper/orders", query={"status": status})

    def open_paper_position(
        self,
        order: Mapping[str, Any],
        idempotency_key: str,
    ) -> JsonObject:
        return self._idempotent_write(
            "POST",
            "/api/v1/paper/orders",
            {**dict(order), "action": "open"},
            idempotency_key,
        )

    def close_paper_position(
        self,
        position_id: str,
        idempotency_key: str,
        limit_price_cents: float | None = None,
    ) -> JsonObject:
        body: dict[str, Any] = {"action": "close", "positionId": position_id}
        if limit_price_cents is not None:
            body["limitPriceCents"] = limit_price_cents
        return self._idempotent_write("POST", "/api/v1/paper/orders", body, idempotency_key)

    def research_export(
        self,
        dataset: str,
        *,
        event_pubkey: str | None = None,
        outcome_index: int | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        response = self.request(
            "GET",
            "/api/v1/research/export",
            query={
                "dataset": dataset,
                "format": "json",
                "eventPubkey": event_pubkey,
                "outcomeIndex": outcome_index,
                "from": from_time,
                "to": to_time,
                "limit": limit,
            },
        )
        rows = response.get("rows", [])
        return [dict(row) for row in rows] if isinstance(rows, list) else []

    def validate_trade(
        self,
        payload: Mapping[str, Any],
        idempotency_key: str | None = None,
        *,
        signed_intent: Mapping[str, Any] | None = None,
    ) -> JsonObject:
        body = signed_intent if signed_intent is not None else payload
        return self._idempotent_write(
            "POST",
            "/api/v1/orders/validate",
            body,
            idempotency_key or "",
        )

    def estimate_impact(
        self,
        payload: Mapping[str, Any],
        idempotency_key: str | None = None,
    ) -> JsonObject:
        return self._idempotent_write(
            "POST",
            "/api/v1/orders/estimate-impact",
            payload,
            idempotency_key or "",
        )

    def prepare_order(self, payload: Mapping[str, Any], *, idempotency_key: str) -> JsonObject:
        return self._idempotent_write("POST", "/api/v1/orders/prepare", payload, idempotency_key)

    def place_order(self, signed_order: Mapping[str, Any], idempotency_key: str) -> JsonObject:
        return self._idempotent_write("POST", "/api/v1/orders", signed_order, idempotency_key)

    def cancel_orders(self, signed_cancel: Mapping[str, Any], idempotency_key: str) -> JsonObject:
        return self._idempotent_write("DELETE", "/api/v1/orders", signed_cancel, idempotency_key)

    def place_signed_order(
        self,
        payload: Mapping[str, Any],
        *,
        idempotency_key: str,
        signature: str,
        timestamp: str,
    ) -> JsonObject:
        """Submit caller-signed bytes; this method never creates or stores wallet keys."""
        if not self.api_key:
            raise ValueError("api_key is required for protected trading")
        return self.request(
            "POST",
            "/api/clob/v2/orders",
            body={**payload, "signature": signature},
            headers={
                "Idempotency-Key": idempotency_key,
                "X-Signature": signature,
                "X-Timestamp": timestamp,
            },
        )

    def _idempotent_write(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any],
        idempotency_key: str,
    ) -> JsonObject:
        key = idempotency_key.strip()
        if not key:
            raise ValueError("idempotency_key is required")
        return self.request(
            method,
            path,
            body=dict(body),
            headers={"Idempotency-Key": key},
        )

    def stream(
        self,
        slug: str,
        *,
        include_orderbook: bool = True,
        outcome_index: int = 0,
        reconnect: bool = True,
        retry_seconds: float = 1.0,
    ) -> Generator[dict[str, Any], None, None]:
        query = urllib.parse.urlencode(
            {
                "includeOrderbook": "1" if include_orderbook else "0",
                "outcomeIndex": outcome_index,
            }
        )
        url = f"{self.base_url}/api/events/{urllib.parse.quote(slug, safe='')}/stream?{query}"
        yield from self._sse_events(
            url,
            reconnect=reconnect,
            retry_seconds=retry_seconds,
            retry_max_seconds=retry_seconds,
        )

    def orderbook_stream(
        self,
        slug: str,
        *,
        outcome_index: int = 0,
        interval_ms: int = 750,
        snapshot_every: int = 20,
        max_duration_ms: int = 55_000,
        reconnect: bool = True,
        retry_seconds: float = 0.5,
        retry_max_seconds: float = 10.0,
    ) -> Generator[dict[str, Any], None, None]:
        query = urllib.parse.urlencode(
            {
                "outcomeIndex": outcome_index,
                "intervalMs": interval_ms,
                "snapshotEvery": snapshot_every,
                "maxDurationMs": max_duration_ms,
            }
        )
        url = (
            f"{self.base_url}/api/events/{urllib.parse.quote(slug, safe='')}"
            f"/orderbook/stream?{query}"
        )
        yield from self._sse_events(
            url,
            reconnect=reconnect,
            retry_seconds=retry_seconds,
            retry_max_seconds=retry_max_seconds,
        )

    @staticmethod
    def _decode_sse(response: Any) -> Generator[dict[str, Any], None, None]:
        event = "message"
        event_id: str | None = None
        data_lines: list[str] = []
        for raw in response:
            line = raw.decode("utf-8").rstrip("\r\n")
            if not line:
                if data_lines:
                    payload = "\n".join(data_lines)
                    try:
                        data: Any = json.loads(payload)
                    except json.JSONDecodeError:
                        data = payload
                    decoded: dict[str, Any] = {"event": event, "data": data}
                    if event_id is not None:
                        decoded["id"] = event_id
                    yield decoded
                event, event_id, data_lines = "message", None, []
            elif line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("id:"):
                event_id = line[3:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].strip())
        if data_lines:
            payload = "\n".join(data_lines)
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                data = payload
            decoded = {"event": event, "data": data}
            if event_id is not None:
                decoded["id"] = event_id
            yield decoded

    def _sse_events(
        self,
        url: str,
        *,
        reconnect: bool,
        retry_seconds: float,
        retry_max_seconds: float,
    ) -> Generator[dict[str, Any], None, None]:
        for name, value in {
            "retry_seconds": retry_seconds,
            "retry_max_seconds": retry_max_seconds,
        }.items():
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError(f"{name} must be a finite non-negative number")
        if retry_max_seconds < retry_seconds:
            raise ValueError("retry_max_seconds must be at least retry_seconds")
        reconnect_attempt = 0
        last_event_id: str | None = None
        while True:
            stream_headers = {**self._headers(), "Accept": "text/event-stream"}
            if last_event_id:
                stream_headers["Last-Event-ID"] = last_event_id
            request = urllib.request.Request(url, headers=stream_headers)
            received_event = False
            try:
                with urllib.request.urlopen(request, timeout=max(self.timeout, 60.0)) as response:
                    for decoded in self._decode_sse(response):
                        received_event = True
                        reconnect_attempt = 0
                        decoded_id = str(decoded.get("id") or "").strip()
                        if decoded_id:
                            last_event_id = decoded_id
                        yield decoded
            except (urllib.error.URLError, TimeoutError, socket.timeout):
                if not reconnect:
                    raise
            if not reconnect:
                return
            if not received_event:
                reconnect_attempt += 1
            delay = min(
                retry_max_seconds,
                retry_seconds * (2 ** max(0, reconnect_attempt - 1)),
            )
            time.sleep(delay)

    @staticmethod
    def write_parquet(rows: Iterable[Mapping[str, Any]], destination: str | Path) -> Path:
        try:
            import pyarrow as pa  # type: ignore[import-not-found]
            import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as error:
            raise RuntimeError("Install the parquet extra: pip install 'norynta[parquet]'") from error
        path = Path(destination)
        table = pa.Table.from_pylist([dict(row) for row in rows])
        pq.write_table(table, path, compression="zstd")
        return path

    @staticmethod
    def write_csv(rows: Iterable[Mapping[str, Any]], destination: str | Path) -> Path:
        path = Path(destination)
        materialized = [dict(row) for row in rows]
        fields = sorted({key for row in materialized for key in row})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(materialized)
        return path


class AsyncNoryntaClient:
    """Async facade that runs the zero-dependency client in worker threads."""

    def __init__(self, **kwargs: Any) -> None:
        self._sync = NoryntaClient(**kwargs)

    async def search_markets(self, query: str, *, limit: int = 10) -> JsonObject:
        return await asyncio.to_thread(self._sync.search_markets, query, limit=limit)

    async def top_events(self, *, limit: int = 10) -> JsonObject:
        return await asyncio.to_thread(self._sync.top_events, limit=limit)

    async def event_snapshots(self, slugs: Sequence[str]) -> JsonObject:
        return await asyncio.to_thread(self._sync.event_snapshots, slugs)

    async def event(self, slug: str) -> JsonObject:
        return await asyncio.to_thread(self._sync.event, slug)

    async def orderbook(
        self,
        event_pubkey: str,
        *,
        outcome_index: int | None = None,
        depth: int | None = None,
    ) -> JsonObject:
        return await asyncio.to_thread(
            self._sync.orderbook,
            event_pubkey,
            outcome_index or 0,
            depth,
        )

    async def agent_bootstrap(self) -> JsonObject:
        return await asyncio.to_thread(self._sync.agent_bootstrap)
