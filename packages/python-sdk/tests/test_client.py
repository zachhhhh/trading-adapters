import io
import itertools
import json
import math
import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from norynta import NoryntaClient


class FakeResponse:
    def __init__(self, value):
        self.value = value
        self.headers = {"x-request-id": "req_test"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.value).encode()


class StreamResponse:
    def __init__(self, lines):
        self.lines = [line.encode() for line in lines]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def __iter__(self):
        return iter(self.lines)


class NoryntaClientTests(unittest.TestCase):
    @staticmethod
    def http_error(status, payload, headers=None):
        response_headers = Message()
        for name, value in (headers or {}).items():
            response_headers[name] = value
        return urllib.error.HTTPError(
            "https://example.test/api",
            status,
            "error",
            response_headers,
            io.BytesIO(json.dumps(payload).encode()),
        )

    def test_search_encodes_query_and_uses_public_api(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse({"results": []})) as opened:
            client = NoryntaClient()
            self.assertEqual(client.search_markets("Fed rates", limit=4), {"results": []})
            request = opened.call_args.args[0]
            self.assertEqual(request.full_url, "https://norynta.com/api/search?q=Fed+rates&limit=4")
            self.assertIsNone(request.get_header("Authorization"))

    def test_signed_order_requires_api_key(self):
        client = NoryntaClient()
        with self.assertRaisesRegex(ValueError, "api_key"):
            client.place_signed_order(
                {"side": "buy"},
                idempotency_key="order-1",
                signature="caller-signature",
                timestamp="2026-07-19T00:00:00Z",
            )

    def test_signed_order_forwards_caller_authorization(self):
        with patch("urllib.request.urlopen", return_value=FakeResponse({"ok": True})) as opened:
            client = NoryntaClient(api_key="scoped-token")
            result = client.place_signed_order(
                {"side": "buy"},
                idempotency_key="order-1",
                signature="caller-signature",
                timestamp="2026-07-19T00:00:00Z",
            )
            self.assertEqual(result, {"ok": True})
            request = opened.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer scoped-token")
            self.assertEqual(request.get_header("Idempotency-key"), "order-1")
            self.assertEqual(request.get_header("X-signature"), "caller-signature")

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_reads_retry_retryable_failures(self, opened, sleep):
        opened.side_effect = [
            self.http_error(
                429,
                {"code": "RATE_LIMITED", "retryable": True},
                {"retry-after": "1"},
            ),
            FakeResponse({"ok": True}),
        ]
        client = NoryntaClient("https://example.test", retry_jitter=0)

        self.assertTrue(client.service_levels()["ok"])
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(1.0)

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_only_idempotent_writes_retry(self, opened, sleep):
        opened.side_effect = [
            self.http_error(503, {"code": "UNAVAILABLE", "retryable": True}),
            FakeResponse({"ok": True}),
        ]
        client = NoryntaClient("https://example.test", retry_jitter=0)

        self.assertTrue(client.place_order({"signature": "signed"}, "strategy:retry:1")["ok"])
        self.assertEqual(opened.call_count, 2)
        sleep.assert_called_once_with(0.25)

        opened.reset_mock()
        sleep.reset_mock()
        opened.side_effect = self.http_error(
            503,
            {"code": "UNAVAILABLE", "retryable": True},
        )
        with self.assertRaisesRegex(Exception, "503 UNAVAILABLE"):
            client.backtest({"frames": [], "orders": []})
        self.assertEqual(opened.call_count, 1)
        sleep.assert_not_called()

    def test_retry_configuration_rejects_invalid_values_and_caps_retry_after(self):
        for invalid_retries in (-1, 1.5, True):
            with self.subTest(max_retries=invalid_retries):
                with self.assertRaises(ValueError):
                    NoryntaClient("https://example.test", max_retries=invalid_retries)

        for invalid_delay in (-1, math.nan, math.inf, True):
            with self.subTest(retry_backoff_seconds=invalid_delay):
                with self.assertRaises(ValueError):
                    NoryntaClient(
                        "https://example.test",
                        retry_backoff_seconds=invalid_delay,
                    )

        client = NoryntaClient(
            "https://example.test",
            retry_jitter=0,
            retry_max_delay_seconds=2,
        )
        self.assertEqual(client._retry_delay(0, retry_after=30), 2)

    @patch("urllib.request.urlopen")
    def test_orderbook_stream_decodes_ids_and_resumes(self, opened):
        opened.side_effect = [
            StreamResponse(
                [
                    "event: snapshot\n",
                    "id: orderbook:12:" + ("a" * 64) + "\n",
                    'data: {"sequence":"12","bids":[],"asks":[]}\n',
                    "\n",
                ]
            ),
            StreamResponse(
                [
                    "event: snapshot\n",
                    "id: orderbook:15:" + ("b" * 64) + "\n",
                    'data: {"sequence":"15","bids":[],"asks":[]}\n',
                    "\n",
                ]
            ),
        ]
        client = NoryntaClient("https://example.test")

        with patch("time.sleep"):
            messages = list(
                itertools.islice(
                    client.orderbook_stream("event", reconnect=True),
                    2,
                )
            )

        self.assertEqual(
            [message["data"]["sequence"] for message in messages],
            ["12", "15"],
        )
        second_request = opened.call_args_list[1].args[0]
        self.assertEqual(
            second_request.headers["Last-event-id"],
            "orderbook:12:" + ("a" * 64),
        )

    @patch("time.sleep")
    @patch("urllib.request.urlopen")
    def test_orderbook_stream_resumes_with_last_event_id(self, urlopen, _sleep):
        urlopen.side_effect = [
            StreamResponse([
                "event: snapshot\n",
                "id: orderbook:12:" + ("a" * 64) + "\n",
                'data: {"sequence":"12","bids":[],"asks":[]}\n',
                "\n",
            ]),
            StreamResponse([
                "event: snapshot\n",
                "id: orderbook:15:" + ("b" * 64) + "\n",
                'data: {"sequence":"15","bids":[],"asks":[]}\n',
                "\n",
            ]),
        ]
        client = NoryntaClient("https://example.test")

        messages = list(itertools.islice(
            client.orderbook_stream("event", reconnect=True),
            2,
        ))

        self.assertEqual([message["data"]["sequence"] for message in messages], ["12", "15"])
        second_request = urlopen.call_args_list[1].args[0]
        self.assertEqual(
            second_request.headers["Last-event-id"],
            "orderbook:12:" + ("a" * 64),
        )


if __name__ == "__main__":
    unittest.main()
