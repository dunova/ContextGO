#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import autoresearch_contextgo as ar


class AutoResearchTests(unittest.TestCase):
    def test_append_log_replaces_same_round(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "log.tsv"
            state_path = Path(tmpdir) / "latest.json"
            payload = {
                "timestamp": "2026-03-26T10:00:00",
                "dimensions": {"stability": 100, "recall": 100, "token_efficiency": 90},
                "total_score": 98.0,
            }
            payload2 = {
                "timestamp": "2026-03-26T10:05:00",
                "dimensions": {"stability": 100, "recall": 100, "token_efficiency": 95},
                "total_score": 99.0,
            }
            with mock.patch.object(ar, "LOG_PATH", log_path):
                with mock.patch.object(ar, "STATE_PATH", state_path):
                    ar.append_log(8, payload, "KEEP", "first")
                    ar.append_log(8, payload2, "KEEP", "second")
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertIn("second", lines[1])
            latest = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(latest["total_score"], 99.0)


if __name__ == "__main__":
    unittest.main()
