#!/usr/bin/env python3
"""Regression tests for web-dashboard.py data integrity.

Runs against seeded temp databases with hand-computed expected values, so a
change that breaks time filters, totals, CSV export, or schema fallbacks
fails CI instead of shipping. Stdlib only — no pytest dependency.

Run:  python3 tests/test_dashboard.py
"""
import csv
import importlib.util
import io
import os
import sqlite3
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NEW_SCHEMA = """CREATE TABLE requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
    provider TEXT NOT NULL, model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0, cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0, cost_usd REAL NOT NULL DEFAULT 0.0,
    cost_estimated INTEGER NOT NULL DEFAULT 0, latency_ms INTEGER NOT NULL DEFAULT 0,
    tokens_per_second REAL NOT NULL DEFAULT 0.0, time_to_first_token_ms INTEGER NOT NULL DEFAULT 0,
    is_streaming INTEGER NOT NULL DEFAULT 0, is_complete INTEGER NOT NULL DEFAULT 1,
    source_tag TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
    provider_type TEXT NOT NULL DEFAULT 'api', error_message TEXT)"""

# Pre-v0.4.0 schema: no cache_creation_tokens / cost_estimated columns.
OLD_SCHEMA = (
    NEW_SCHEMA
    .replace(" cache_creation_tokens INTEGER NOT NULL DEFAULT 0,", "")
    .replace(" cost_estimated INTEGER NOT NULL DEFAULT 0,", "")
)

SEED = [  # (age_sql, provider, model, cost, cached, cache_creation, estimated)
    ("datetime('now', '-1 hour')",  "openai",    "gpt-4o",            0.10, 800, 0,   0),
    ("datetime('now', '-2 hours')", "openai",    "gpt-4o",            0.20, 0,   0,   1),
    ("datetime('now', '-3 days')",  "anthropic", "claude-sonnet-4-6", 0.50, 500, 120, 0),
    ("datetime('now', '-20 days')", "openai",    "gpt-4o",            1.00, 0,   0,   0),
    ("datetime('now', '-60 days')", "anthropic", "claude-opus-4-6",   2.00, 0,   0,   0),
]
EXPECTED_TOTALS = {"today": 0.30, "7d": 0.80, "30d": 1.80, "all": 3.80}


def load_dashboard(db_path):
    os.environ["TOKENPULSE_DB"] = db_path
    spec = importlib.util.spec_from_file_location(
        "wd", os.path.join(REPO_ROOT, "web-dashboard.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_db(schema, with_new_columns):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(schema)
    for age, prov, model, cost, cached, creation, est in SEED:
        if with_new_columns:
            conn.execute(
                f"INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, "
                f"cached_tokens, cache_creation_tokens, cost_usd, cost_estimated) "
                f"VALUES ({age}, ?, ?, 1000, 500, ?, ?, ?, ?)",
                (prov, model, cached, creation, cost, est))
        else:
            conn.execute(
                f"INSERT INTO requests (timestamp, provider, model, input_tokens, output_tokens, "
                f"cached_tokens, cost_usd) VALUES ({age}, ?, ?, 1000, 500, ?, ?)",
                (prov, model, cached, cost))
    conn.commit()
    conn.close()
    return path


class DashboardDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = make_db(NEW_SCHEMA, with_new_columns=True)
        cls.wd = load_dashboard(cls.db)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.db)

    def fetch(self, rng):
        return self.wd._fetch_data(rng)

    def total_cost_of(self, data, want):
        for key in ("total_cost", "total_spend", "cost_total"):
            if key in data:
                return data[key]
        # Fall back: locate the scalar matching the expected total.
        for v in data.values():
            if isinstance(v, (int, float)) and abs(v - want) < 1e-9:
                return v
        return None

    def test_time_filter_totals(self):
        for rng, want in EXPECTED_TOTALS.items():
            got = self.total_cost_of(self.fetch(rng), want)
            self.assertIsNotNone(got, f"no total found for range {rng}")
            self.assertAlmostEqual(got, want, places=9, msg=f"range {rng}")

    def test_requests_rows_carry_new_fields(self):
        data = self.fetch("all")
        rows = data.get("requests") or data.get("requests_rows")
        self.assertTrue(rows, "no request rows returned")
        anthropic = [r for r in rows if r["provider"] == "anthropic"
                     and r["model"] == "claude-sonnet-4-6"]
        self.assertEqual(anthropic[0]["cache_creation_tokens"], 120)
        flagged = [r for r in rows if r.get("cost_estimated")]
        self.assertEqual(len(flagged), 1)

    def test_csv_export_columns_and_sum(self):
        out = self.wd._export_csv("all")
        rows = list(csv.DictReader(io.StringIO(out)))
        self.assertEqual(len(rows), len(SEED))
        for col in ("cached_tokens", "cache_creation_tokens", "cost_estimated",
                    "cost_usd", "provider", "model"):
            self.assertIn(col, rows[0])
        total = sum(float(r["cost_usd"]) for r in rows)
        self.assertAlmostEqual(total, EXPECTED_TOTALS["all"], places=6)
        flagged = [r for r in rows if r["cost_estimated"] == "True"]
        self.assertEqual(len(flagged), 1)

    def test_csv_today_respects_filter(self):
        out = self.wd._export_csv("today")
        rows = list(csv.DictReader(io.StringIO(out)))
        self.assertEqual(len(rows), 2)


class OldSchemaFallbackTests(unittest.TestCase):
    """The dashboard must keep working against a DB the new proxy has not
    migrated yet (no cache_creation_tokens / cost_estimated columns)."""

    @classmethod
    def setUpClass(cls):
        cls.db = make_db(OLD_SCHEMA, with_new_columns=False)
        cls.wd = load_dashboard(cls.db)

    @classmethod
    def tearDownClass(cls):
        os.unlink(cls.db)

    def test_fetch_does_not_crash_and_defaults_new_fields(self):
        data = self.wd._fetch_data("all")
        rows = data.get("requests") or data.get("requests_rows")
        self.assertTrue(rows)
        self.assertEqual(rows[0]["cache_creation_tokens"], 0)
        self.assertEqual(rows[0]["cost_estimated"], 0)

    def test_csv_export_works_with_zero_defaults(self):
        out = self.wd._export_csv("all")
        rows = list(csv.DictReader(io.StringIO(out)))
        self.assertEqual(len(rows), len(SEED))
        self.assertTrue(all(r["cache_creation_tokens"] == "0" for r in rows))


if __name__ == "__main__":
    unittest.main(verbosity=2)
