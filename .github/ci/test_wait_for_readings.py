"""Offline tests: no services or network required."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from wait_for_readings import wait_for_readings


class ReadinessTests(unittest.TestCase):
    def run_poll(self, responses):
        # One request per simulated second; no wall-clock waiting.
        with (
            patch("wait_for_readings.time.monotonic", side_effect=range(1000)),
            patch("wait_for_readings.time.sleep"),
            patch("wait_for_readings.urllib.request.urlopen", side_effect=responses) as request,
        ):
            wait_for_readings()
        return request.call_count

    @staticmethod
    def response(points):
        return io.StringIO(json.dumps(points))

    def ready(self):
        return self.response([{"updatedAt": "2026-11-12T00:00:00Z"}] * 5)

    def test_all_five_ready(self):
        self.assertEqual(self.run_poll([self.ready()]), 1)

    def test_partial_readings_retry(self):
        partial = [{"updatedAt": "now"}] * 4 + [{"updatedAt": None}]
        self.assertEqual(self.run_poll([self.response(partial), self.ready()]), 2)

    def test_wrong_count_retries(self):
        self.assertEqual(self.run_poll([self.response([{"updatedAt": "now"}]), self.ready()]), 2)

    def test_invalid_shape_retries(self):
        self.assertEqual(self.run_poll([self.response([None] * 5), self.ready()]), 2)

    def test_malformed_json_retries(self):
        self.assertEqual(self.run_poll([io.StringIO("not json"), self.ready()]), 2)

    def test_connection_failure_retries(self):
        self.assertEqual(self.run_poll([urllib.error.URLError("starting"), self.ready()]), 2)

    def test_deadline_fails(self):
        with self.assertRaisesRegex(SystemExit, "Timed out after 120 seconds"):
            self.run_poll([self.response([]) for _ in range(100)])


if __name__ == "__main__":
    unittest.main()
