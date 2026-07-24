import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from norynta import NoryntaOrderBookReconciler


class NoryntaOrderBookReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.now = [100.0]
        self.book = NoryntaOrderBookReconciler(
            "Event111:0/USDC",
            monotonic_clock=lambda: self.now[0],
        )

    def test_applies_snapshots_deltas_deletes_and_global_sequence_gaps(self):
        self.assertEqual(
            self.book.apply(
                "snapshot",
                {
                    "sequence": "100",
                    "sequenceConsistency": "transactional",
                    "truncated": True,
                    "bids": [[49, 2], [48, 3]],
                    "asks": [[51, 4], [52, 5]],
                },
            ),
            "applied",
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {
                    "sequence": "109",
                    "sequenceConsistency": "transactional",
                    "bids": [
                        {"priceCents": 49, "sizeShares": 0},
                        {"priceCents": 50, "sizeShares": 6},
                    ],
                    "asks": [{"priceCents": 51, "sizeShares": 7}],
                },
            ),
            "applied",
        )

        state = self.book.state()
        self.assertEqual(state["sequence"], "109")
        self.assertEqual(state["bids"], [[0.5, 6.0], [0.48, 3.0]])
        self.assertEqual(state["asks"], [[0.51, 7.0], [0.52, 5.0]])
        self.assertTrue(state["truncated"])
        self.assertFalse(state["needsResync"])

    def test_requires_resync_for_ambiguous_or_invalid_stream_state(self):
        delta = {"sequence": "2", "bids": [[49, 1]], "asks": []}
        self.assertEqual(self.book.apply("delta", delta), "resync_required")
        self.assertIn("before", self.book.resync_reason or "")

        self.assertEqual(
            self.book.apply(
                "snapshot",
                {"sequence": "10", "bids": [[49, 1]], "asks": [[51, 1]]},
            ),
            "applied",
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {"sequence": "10", "bids": [[49, 2]], "asks": []},
            ),
            "resync_required",
        )
        self.assertIn("conflicts", self.book.resync_reason or "")

        self.assertEqual(
            self.book.apply(
                "snapshot",
                {"sequence": "11", "bids": [[49, 1]], "asks": [[51, 1]]},
            ),
            "applied",
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {"sequence": "9", "bids": [], "asks": []},
            ),
            "resync_required",
        )
        self.assertIn("regressed", self.book.resync_reason or "")

        self.assertEqual(
            self.book.apply(
                "snapshot",
                {"sequence": "12", "bids": [[101, 1]], "asks": []},
            ),
            "resync_required",
        )
        self.assertIn("invalid price level", self.book.resync_reason or "")

    def test_ignores_idempotent_same_sequence_delta_and_tracks_staleness(self):
        self.book.apply(
            "snapshot",
            {"sequence": "10", "bids": [[49, 1]], "asks": [[51, 1]]},
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {"sequence": "10", "bids": [[49, 1]], "asks": []},
            ),
            "ignored",
        )
        self.now[0] = 129.0
        self.assertFalse(self.book.is_stale(30))
        self.now[0] = 131.0
        self.assertTrue(self.book.is_stale(30))
        with self.assertRaises(ValueError):
            self.book.is_stale(-1)

    def test_revision_chain_detects_missed_same_market_delta(self):
        first_revision = "a" * 64
        self.assertEqual(
            self.book.apply(
                "snapshot",
                {
                    "sequence": "10",
                    "bookRevision": first_revision,
                    "bids": [[49, 1]],
                    "asks": [[51, 1]],
                },
            ),
            "applied",
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {
                    "sequence": "20",
                    "previousBookRevision": "b" * 64,
                    "bookRevision": "c" * 64,
                    "bids": [[49, 2]],
                    "asks": [],
                },
            ),
            "resync_required",
        )
        self.assertIn("previous revision", self.book.resync_reason or "")

    def test_fault_injection_rejects_duplicates_reordering_and_corruption(self):
        revision_a = "a" * 64
        revision_b = "b" * 64
        revision_c = "c" * 64
        self.assertEqual(
            self.book.apply(
                "snapshot",
                {
                    "sequence": "100",
                    "bookRevision": revision_a,
                    "bids": [[49, 1]],
                    "asks": [[51, 1]],
                },
            ),
            "applied",
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {
                    "sequence": "110",
                    "previousBookRevision": revision_a,
                    "bookRevision": revision_b,
                    "bids": [[49, 2]],
                    "asks": [],
                },
            ),
            "applied",
        )
        self.assertEqual(
            self.book.apply(
                "delta",
                {
                    "sequence": "110",
                    "previousBookRevision": revision_a,
                    "bookRevision": revision_b,
                    "bids": [[49, 2]],
                    "asks": [],
                },
            ),
            "resync_required",
        )

        repaired = NoryntaOrderBookReconciler("Event111:0/USDC")
        repaired.apply(
            "snapshot",
            {
                "sequence": "100",
                "bookRevision": revision_a,
                "bids": [[49, 1]],
                "asks": [[51, 1]],
            },
        )
        self.assertEqual(
            repaired.apply(
                "delta",
                {
                    "sequence": "120",
                    "previousBookRevision": revision_b,
                    "bookRevision": revision_c,
                    "bids": [],
                    "asks": [[51, 2]],
                },
            ),
            "resync_required",
        )
        self.assertEqual(
            repaired.apply(
                "snapshot",
                {
                    "sequence": "120",
                    "bookRevision": "not-a-checksum",
                    "bids": [[49, 1]],
                    "asks": [[51, 2]],
                },
            ),
            "resync_required",
        )


if __name__ == "__main__":
    unittest.main()
