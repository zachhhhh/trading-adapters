import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from norynta import (
    FRAMEWORK_ADAPTERS,
    FRAMEWORK_ADAPTERS_VERSION,
    NoryntaCcxtAdapter,
    NoryntaFrameworkAdapter,
    NoryntaInstrument,
    NoryntaSequenceError,
)
from norynta.frameworks import main


class FakeClient:
    def __init__(self):
        self.paper_orders = []
        self.live_orders = []
        self.cancel_requests = []
        self.base_url = "https://example.test"
        self.stream_messages = []

    def request(self, method, path, query=None, body=None, headers=None):
        del method, body, headers
        if path == "/api/v1/markets":
            return {
                "events": [
                    {
                        "event_v2_pubkey": "Event111",
                        "slug": "event-one",
                        "title": "Will the event happen?",
                        "outcomes": ["Yes", "No"],
                    }
                ],
                "query": query,
            }
        if path == "/api/agent/access":
            return {"compatibility": {"posture": "standards_first"}}
        raise AssertionError(f"unexpected request: {path}")

    def orderbook(self, event_pubkey, outcome_index=0, depth=None):
        return {
            "eventPubkey": event_pubkey,
            "outcomeIndex": outcome_index,
            "depth": depth,
            "sequence": "9007199254740993",
            "serverTime": "2026-07-24T10:00:00.000Z",
            "bids": [
                {"priceCents": 48, "sizeShares": 5},
                [49, 12],
                [101, 100],
            ],
            "asks": [[52, 2], [51, 8], [-1, 10]],
        }

    def orderbook_stream(self, slug, **options):
        del slug, options
        yield from self.stream_messages

    def research_export(
        self,
        dataset,
        *,
        event_pubkey=None,
        outcome_index=None,
        from_time=None,
        to_time=None,
        limit=1000,
    ):
        del event_pubkey, outcome_index, from_time, to_time, limit
        if dataset == "trades":
            return [
                {
                    "id": 3,
                    "inserted_at": "2026-07-24T10:01:10.000Z",
                    "trade_price_cents": 50,
                    "fill_shares": 4,
                },
                {
                    "id": 1,
                    "inserted_at": "2026-07-24T10:00:05.000Z",
                    "trade_price_cents": 49,
                    "fill_shares": 2,
                },
                {
                    "id": 2,
                    "inserted_at": "2026-07-24T10:00:45.000Z",
                    "trade_price_cents": 51,
                    "fill_shares": 3,
                },
                {
                    "id": 1,
                    "inserted_at": "2026-07-24T10:00:05.000Z",
                    "trade_price_cents": 49,
                    "fill_shares": 2,
                },
                {
                    "id": 4,
                    "inserted_at": "2026-07-24T10:00:55.000Z",
                    "trade_price_cents": 150,
                    "fill_shares": 100,
                },
            ]
        if dataset == "orderbooks":
            return [
                {
                    "captured_at": "2026-07-24T10:00:00.000Z",
                    "sequence": "9007199254740993",
                    "bids": [[49, 12]],
                    "asks": [[51, 8]],
                }
            ]
        return []

    def open_paper_position(self, order, idempotency_key):
        self.paper_orders.append((order, idempotency_key))
        return {"position": {"id": "paper-1"}}

    def place_order(self, order, idempotency_key):
        self.live_orders.append((order, idempotency_key))
        return {"orderId": "live-1"}

    def cancel_orders(self, cancel, idempotency_key):
        self.cancel_requests.append((cancel, idempotency_key))
        return {"ok": True}

    def discover(self):
        adapters = {name: {} for name in FRAMEWORK_ADAPTERS}
        adapters["nautilusTrader"] = adapters.pop("nautilustrader")
        adapters["policy"] = "standards-first"
        adapters["openClaw"] = {"status": "standards_supported_no_bespoke_adapter"}
        return {
            "compatibility": {
                "posture": "standards_first",
                "ossAdapters": adapters,
            }
        }


class NoryntaFrameworkTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.adapter = NoryntaFrameworkAdapter(self.client)
        self.instrument = NoryntaInstrument("Event111", 0)

    def test_manifest_covers_popular_frameworks_with_honest_modes(self):
        self.assertEqual(
            set(FRAMEWORK_ADAPTERS),
            {
                "ccxt",
                "hummingbot",
                "freqtrade",
                "nautilustrader",
                "lean",
                "backtrader",
                "backtesting",
                "vectorbt",
                "vnpy",
                "qlib",
                "finrl",
                "jesse",
                "openbb",
                "lumibot",
                "quantstats",
                "tensortrade",
                "zipline",
                "octobot",
            },
        )
        self.assertIn("caller_signed_live", FRAMEWORK_ADAPTERS["ccxt"]["modes"])
        self.assertNotIn("caller_signed_live", FRAMEWORK_ADAPTERS["freqtrade"]["modes"])
        self.assertNotIn("caller_signed_live", FRAMEWORK_ADAPTERS["jesse"]["modes"])
        self.assertEqual(FRAMEWORK_ADAPTERS_VERSION, "2026-07-24.4")

    def test_market_and_symbol_normalization(self):
        markets = self.adapter.markets()

        self.assertEqual([market.symbol for market in markets], [
            "Event111:0/USDC",
            "Event111:1/USDC",
        ])
        self.assertEqual(
            self.adapter.parse_symbol("Event111:1/USDC"),
            NoryntaInstrument("Event111", 1),
        )
        with self.assertRaises(ValueError):
            self.adapter.parse_symbol("BTC/USDC")

    def test_orderbook_preserves_large_sequence_as_string(self):
        book = self.adapter.orderbook(self.instrument)

        self.assertEqual(book["nonce"], "9007199254740993")
        self.assertEqual(book["bids"], [[0.49, 12.0], [0.48, 5.0]])
        self.assertEqual(book["asks"], [[0.51, 8.0], [0.52, 2.0]])
        self.assertIsInstance(book["timestamp"], int)

    def test_ohlcv_and_framework_rows_are_deterministic(self):
        candles = self.adapter.ohlcv(self.instrument)
        quotes = self.adapter.quote_ticks(self.instrument)
        lean = self.adapter.lean_rows(self.instrument)
        hummingbot = self.adapter.hummingbot_snapshot(self.instrument)

        self.assertEqual(candles[0][1:], [0.49, 0.51, 0.49, 0.51, 5.0])
        self.assertEqual(candles[1][1:], [0.5, 0.5, 0.5, 0.5, 4.0])
        self.assertEqual(quotes[0]["sequence"], "9007199254740993")
        self.assertEqual(lean[0]["bid"], 0.49)
        self.assertEqual(hummingbot["update_id"], 9007199254740993)
        self.assertEqual(hummingbot["sequence"], "9007199254740993")

    def test_second_wave_framework_shapes(self):
        vnpy = self.adapter.vnpy_rows(self.instrument)
        qlib = self.adapter.qlib_rows(self.instrument)
        finrl = self.adapter.finrl_rows(self.instrument)
        jesse = self.adapter.jesse_candles(self.instrument)

        self.assertEqual(vnpy[0]["gateway_name"], "NORYNTA")
        self.assertEqual(vnpy[0]["exchange"], "LOCAL")
        self.assertEqual(vnpy[0]["turnover"], 2.55)
        self.assertEqual(qlib[0]["factor"], 1.0)
        self.assertEqual(qlib[0]["instrument"], "Event111:0")
        self.assertEqual(finrl[0]["tic"], "Event111:0")
        self.assertEqual(finrl[0]["day"], 4)
        self.assertEqual(jesse[0], [1784887200000, 0.49, 0.51, 0.51, 0.49, 5.0])

    def test_research_toolkit_shapes(self):
        openbb = self.adapter.openbb_rows(self.instrument)
        tensortrade = self.adapter.tensortrade_rows(self.instrument)
        zipline = self.adapter.zipline_rows(self.instrument)
        octobot = self.adapter.octobot_candles(self.instrument)

        self.assertEqual(openbb[0]["symbol"], "Event111:0/USDC")
        self.assertEqual(openbb[0]["vwap"], 0.51)
        self.assertEqual(tensortrade[0]["return"], 0.0)
        self.assertAlmostEqual(tensortrade[1]["return"], (0.5 / 0.51) - 1)
        self.assertEqual(zipline[0]["split"], 1.0)
        self.assertEqual(zipline[0]["dividend"], 0.0)
        self.assertEqual(octobot[0], [1784887200, 0.49, 0.51, 0.49, 0.51, 5.0])

    def test_backtesting_frame_uses_native_column_names(self):
        class FakeFrame:
            def __init__(self):
                self.renamed = {}

            def rename(self, *, columns):
                self.renamed = columns
                return self

        source = FakeFrame()
        with patch.object(self.adapter, "pandas_frame", return_value=source):
            frame = self.adapter.backtesting_frame(self.instrument)

        self.assertIs(frame, source)
        self.assertEqual(source.renamed, {
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        })

    def test_reconciled_stream_accepts_global_gaps_and_repairs_regressions(self):
        self.client.stream_messages = [
            {
                "event": "snapshot",
                "data": {
                    "sequence": "10",
                    "bids": [[49, 2]],
                    "asks": [[51, 3]],
                },
            },
            {
                "event": "delta",
                "data": {
                    "sequence": "20",
                    "bids": [{"priceCents": 50, "sizeShares": 4}],
                    "asks": [],
                },
            },
            {
                "event": "delta",
                "data": {
                    "sequence": "19",
                    "bids": [],
                    "asks": [],
                },
            },
        ]

        books = list(self.adapter.reconciled_orderbook_stream(
            "event-one",
            self.instrument,
            reconnect=False,
        ))

        self.assertEqual([book["action"] for book in books], [
            "applied",
            "applied",
            "resynced",
        ])
        self.assertEqual(books[1]["sequence"], "20")
        self.assertEqual(books[2]["sequence"], "9007199254740993")
        self.assertEqual(books[2]["source"], "rest_snapshot")
        self.assertEqual(books[2]["resyncCount"], 1)

    def test_quote_ticks_deduplicate_sequences_and_fail_on_regression(self):
        rows = [
            {
                "captured_at": "2026-07-24T10:00:00.000Z",
                "sequence": "11",
                "bids": [[48, 2], [49, 1]],
                "asks": [[52, 3], [51, 4]],
            },
            {
                "captured_at": "2026-07-24T10:00:01.000Z",
                "sequence": "11",
                "bids": [[49, 1]],
                "asks": [[51, 4]],
            },
            {
                "captured_at": "2026-07-24T10:00:02.000Z",
                "sequence": "10",
                "bids": [[49, 1]],
                "asks": [[51, 4]],
            },
        ]
        with patch.object(self.adapter, "orderbook_history", return_value=rows):
            with self.assertRaisesRegex(NoryntaSequenceError, "regressed"):
                self.adapter.quote_ticks(self.instrument)
            ticks = self.adapter.quote_ticks(self.instrument, strict_sequences=False)

        self.assertEqual(len(ticks), 2)
        self.assertEqual(ticks[0]["bid_price"], 0.49)
        self.assertEqual(ticks[0]["ask_price"], 0.51)

    def test_ccxt_facade_defaults_to_paper_and_fails_closed_for_live(self):
        exchange = NoryntaCcxtAdapter(client=self.client)
        symbol = "Event111:0/USDC"

        result = exchange.create_order(
            symbol,
            "limit",
            "buy",
            3,
            0.49,
            {"idempotencyKey": "paper:test:1"},
        )
        self.assertEqual(result["id"], "paper-1")
        self.assertEqual(self.client.paper_orders[0][1], "paper:test:1")
        self.assertNotIn("side", self.client.paper_orders[0][0])

        with self.assertRaisesRegex(ValueError, "opens buy positions only"):
            exchange.create_order(
                symbol,
                "limit",
                "sell",
                3,
                0.49,
                {"idempotencyKey": "paper:test:2"},
            )

        with self.assertRaisesRegex(ValueError, "signedOrder"):
            exchange.create_order(
                symbol,
                "limit",
                "buy",
                3,
                0.49,
                {"paper": False, "idempotencyKey": "live:test:1"},
            )

        live = exchange.create_order(
            symbol,
            "limit",
            "buy",
            3,
            0.49,
            {
                "paper": False,
                "signedOrder": {
                    "signature": "caller-supplied",
                    "eventPubkey": "Event111",
                    "outcomeIndex": 0,
                    "side": "buy",
                    "priceCents": 49,
                    "sizeShares": 3,
                },
                "idempotencyKey": "live:test:1",
            },
        )
        self.assertEqual(live["id"], "live-1")

        with self.assertRaisesRegex(ValueError, "priceCents"):
            exchange.create_order(
                symbol,
                "limit",
                "buy",
                3,
                0.49,
                {
                    "paper": False,
                    "signedOrder": {"priceCents": 50},
                    "idempotencyKey": "live:test:2",
                },
            )

    def test_cli_lists_adapters_and_exports_without_third_party_frameworks(self):
        with patch("builtins.print") as print_mock:
            self.assertEqual(main(["list"]), 0)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertIn("ccxt", payload)

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "nested" / "freqtrade.csv"
            with patch("norynta.frameworks.NoryntaClient", return_value=self.client):
                self.assertEqual(main([
                    "--base-url",
                    "https://example.test",
                    "export",
                    "freqtrade",
                    "Event111",
                    "--output",
                    str(output),
                ]), 0)
            text = output.read_text()
            self.assertIn("date,open,high,low,close,volume", text)
            self.assertIn("0.49,0.51,0.49,0.51,5.0", text)
            self.assertEqual(list(output.parent.glob(f".{output.name}.*")), [])

            for framework, expected_header in {
                "backtesting": "Date,Open,High,Low,Close,Volume",
                "vnpy": "gateway_name,symbol,exchange,datetime,interval",
                "qlib": "instrument,datetime,open,high,low,close,volume,factor",
                "finrl": "date,tic,open,high,low,close,volume,day",
                "jesse": "timestamp,open,close,high,low,volume",
                "openbb": "date,open,high,low,close,volume,vwap,symbol",
                "lumibot": "date,open,high,low,close,volume",
                "quantstats": "date,return",
                "tensortrade": "timestamp,symbol,open,high,low,close,volume,return",
                "zipline": "date,symbol,open,high,low,close,volume,dividend,split",
                "octobot": "timestamp,open,high,low,close,volume",
            }.items():
                destination = Path(tmp) / f"{framework}.csv"
                with self.subTest(framework=framework):
                    with patch("norynta.frameworks.NoryntaClient", return_value=self.client):
                        self.assertEqual(main([
                            "--base-url",
                            "https://example.test",
                            "export",
                            framework,
                            "Event111",
                            "--output",
                            str(destination),
                        ]), 0)
                    self.assertIn(expected_header, destination.read_text())

    def test_doctor_fails_when_server_manifest_is_missing_a_local_adapter(self):
        with patch("norynta.frameworks.NoryntaClient", return_value=self.client):
            with patch("builtins.print") as print_mock:
                self.assertEqual(main([
                    "--base-url",
                    "https://example.test",
                    "doctor",
                ]), 0)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertTrue(payload["contractAligned"])

        with patch.object(
            self.client,
            "discover",
            return_value={
                "compatibility": {
                    "ossAdapters": {
                        name: {}
                        for name in FRAMEWORK_ADAPTERS
                        if name != "jesse"
                    },
                },
            },
        ):
            with patch("norynta.frameworks.NoryntaClient", return_value=self.client):
                with patch("builtins.print") as print_mock:
                    self.assertEqual(main(["doctor"]), 1)
        payload = json.loads(print_mock.call_args.args[0])
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["missingServerAdapters"], ["jesse"])


if __name__ == "__main__":
    unittest.main()
