# test_transport.py — network trouble must be retried, then surfaced as TransportError,
# and must never masquerade as a clean response.
#
# These tests monkeypatch the single HTTP round-trip (_request_once) and the sleep, so they
# run offline and fast.
#
# Run from the attacker-agent dir:  python3 -m unittest discover -s tests -v
import unittest

from lib import target
from lib.target import TransportError


class SendRetry(unittest.TestCase):
    def setUp(self):
        self._once = target._request_once
        self._sleep = target.time.sleep
        self._retries = target.MAX_RETRIES
        target.time.sleep = lambda *_: None  # don't actually wait on backoff
        target.MAX_RETRIES = 3

    def tearDown(self):
        target._request_once = self._once
        target.time.sleep = self._sleep
        target.MAX_RETRIES = self._retries

    def test_retries_then_succeeds(self):
        calls = {"n": 0}

        def flaky(url, body, method):
            calls["n"] += 1
            if calls["n"] < 3:
                raise TransportError("target unreachable: connection refused", retryable=True)
            return 200, '{"ok": true}'

        target._request_once = flaky
        self.assertEqual(target._send("http://127.0.0.1:9/x", None, "GET"), {"ok": True})
        self.assertEqual(calls["n"], 3)

    def test_non_retryable_raises_immediately(self):
        calls = {"n": 0}

        def hard_fail(url, body, method):
            calls["n"] += 1
            raise TransportError("target HTTP 404: not found", retryable=False)

        target._request_once = hard_fail
        with self.assertRaises(TransportError):
            target._send("http://127.0.0.1:9/x", None, "GET")
        self.assertEqual(calls["n"], 1)  # not retried

    def test_retryable_gives_up_after_max_retries(self):
        calls = {"n": 0}

        def always_down(url, body, method):
            calls["n"] += 1
            raise TransportError("target unreachable: timed out", retryable=True)

        target._request_once = always_down
        with self.assertRaises(TransportError):
            target._send("http://127.0.0.1:9/x", None, "GET")
        self.assertEqual(calls["n"], target.MAX_RETRIES + 1)  # initial try + retries

    def test_non_json_200_is_transport_error_not_result(self):
        target._request_once = lambda url, body, method: (200, "not json at all")
        with self.assertRaises(TransportError):
            target._send("http://127.0.0.1:9/x", None, "GET")


class TransportErrorShape(unittest.TestCase):
    def test_carries_retryable_and_retry_after(self):
        e = TransportError("rate limited", retryable=True, retry_after=2.2)
        self.assertTrue(e.retryable)
        self.assertEqual(e.retry_after, 2.2)

    def test_defaults_are_not_retryable(self):
        e = TransportError("boom")
        self.assertFalse(e.retryable)
        self.assertIsNone(e.retry_after)


if __name__ == "__main__":
    unittest.main()
