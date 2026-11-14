"""tools/polite_http.py: pacing, backoff and giving up, with a fake opener.

No test here touches the network: every request goes to FakeOpener, sleeps
are recorded instead of taken, and socket connects are made to fail for the
whole run as a guard.

    python -I tools/test_polite_http.py
"""
import email.message
import email.utils
import io
import socket
import sys
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import polite_http  # noqa: E402


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


class Response(io.BytesIO):
    def __init__(self, body=b"ok"):
        super().__init__(body)
        self.status = 200


class FakeOpener:
    """Answers each open() with the next scripted outcome: bytes, a status code, or an exception."""

    def __init__(self, clock, outcomes):
        self.clock = clock
        self.outcomes = list(outcomes)
        self.requests = []  # (url, User-Agent, clock time)

    def open(self, request, timeout=None):
        self.requests.append((request.full_url, request.get_header("User-agent"), self.clock.now))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if isinstance(outcome, tuple):
            code, headers = outcome
            raise urllib.error.HTTPError(request.full_url, code, "scripted", headers, None)
        return Response(outcome)


def client(outcomes, **kwargs):
    clock = Clock()
    opener = FakeOpener(clock, outcomes)
    kwargs.setdefault("min_interval", 2.0)
    http = polite_http.Polite(opener=opener, sleep=clock.sleep, clock=clock.time,
                              log=lambda message: None, **kwargs)
    return http, opener, clock


def headers(**values):
    message = email.message.Message()
    for name, value in values.items():
        message[name.replace("_", "-")] = value
    return message


class Pacing(unittest.TestCase):
    def test_same_host_waits_min_interval(self):
        http, opener, clock = client([b"a", b"b", b"c"])
        for _ in range(3):
            http.get("https://archive.org/x")
        times = [t for _, _, t in opener.requests]
        self.assertEqual([b - a for a, b in zip(times, times[1:])], [2.0, 2.0])

    def test_other_host_is_not_delayed(self):
        http, opener, clock = client([b"a", b"b"])
        http.get("https://archive.org/x")
        http.get("https://web.archive.org/y")
        self.assertEqual(clock.slept, [])

    def test_time_already_passed_counts(self):
        http, opener, clock = client([b"a", b"b"])
        http.get("https://archive.org/x")
        clock.now += 5
        http.get("https://archive.org/y")
        self.assertEqual(clock.slept, [])

    def test_one_project_user_agent(self):
        http, opener, _ = client([b"a"])
        http.get("https://archive.org/x", headers={"User-Agent": "something else"})
        self.assertEqual(opener.requests[0][1], polite_http.USER_AGENT)
        self.assertNotIn("@", polite_http.USER_AGENT)


class Backoff(unittest.TestCase):
    def test_429_then_success_backs_off_exponentially(self):
        http, opener, clock = client([(429, headers()), (503, headers()), b"done"],
                                     base_delay=5.0, min_interval=0.0)
        self.assertEqual(http.get("https://archive.org/x"), b"done")
        self.assertEqual(clock.slept, [5.0, 10.0])

    def test_retry_after_seconds_is_honoured(self):
        http, opener, clock = client([(429, headers(Retry_After="42")), b"done"],
                                     base_delay=5.0, min_interval=0.0)
        http.get("https://archive.org/x")
        self.assertEqual(clock.slept, [42.0])

    def test_retry_after_http_date(self):
        when = email.utils.format_datetime(email.utils.localtime().replace(microsecond=0))
        error = urllib.error.HTTPError("u", 429, "x", headers(Retry_After=when), None)
        delay = polite_http.retry_after(error)
        self.assertIsNotNone(delay)
        self.assertLess(delay, 5)

    def test_retry_after_is_capped(self):
        http, opener, clock = client([(503, headers(Retry_After="99999")), b"done"],
                                     max_delay=600.0, min_interval=0.0)
        http.get("https://archive.org/x")
        self.assertEqual(clock.slept, [600.0])

    def test_dropped_connection_is_retried(self):
        http, opener, clock = client([ConnectionResetError("reset"), b"done"], min_interval=0.0)
        self.assertEqual(http.get("https://archive.org/x"), b"done")
        self.assertEqual(len(opener.requests), 2)

    def test_404_is_not_retried(self):
        http, opener, clock = client([(404, headers()), b"never"])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            http.get("https://archive.org/x")
        self.assertEqual(caught.exception.code, 404)
        self.assertEqual(len(opener.requests), 1)
        self.assertEqual(clock.slept, [])

    def test_other_errors_are_not_retried(self):
        http, opener, clock = client([ValueError("bad"), b"never"])
        with self.assertRaises(ValueError):
            http.get("https://archive.org/x")
        self.assertEqual(len(opener.requests), 1)


class GivingUp(unittest.TestCase):
    def test_gives_up_after_bounded_retries(self):
        http, opener, clock = client([(429, headers())] * 10, retries=3, base_delay=1.0,
                                     min_interval=0.0)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            http.get("https://archive.org/x")
        self.assertEqual(caught.exception.code, 429)
        self.assertEqual(len(opener.requests), 4)
        self.assertEqual(clock.slept, [1.0, 2.0, 4.0])

    def test_call_wraps_a_custom_sender(self):
        http, opener, clock = client([], retries=2, base_delay=1.0, min_interval=0.0)
        attempts = []

        def send(url):
            attempts.append(url)
            raise urllib.error.HTTPError(url, 503, "busy", headers(), None)

        with self.assertRaises(urllib.error.HTTPError):
            http.call("https://web.archive.org/web/1id_/x", send)
        self.assertEqual(len(attempts), 3)
        self.assertTrue(polite_http.retryable(urllib.error.HTTPError("u", 503, "x", None, None)))
        self.assertFalse(polite_http.retryable(urllib.error.HTTPError("u", 404, "x", None, None)))


class FakeConnection:
    """Stands in for restore_web_archive's kept-alive HTTPSConnection."""

    def __init__(self, status):
        self.status = status
        self.requests = 0

    def request(self, method, path, headers=None):
        self.requests += 1

    def getresponse(self):
        status = self.status

        class Reply:
            reason = "scripted"

            def __init__(self):
                self.status = status
                self.headers = headers()

            def read(self, *args):
                return b""
        return Reply()

    def close(self):
        pass


class RestoreWebArchive(unittest.TestCase):
    """A throttled capture stays pending; a real 404 is marked missing (R17)."""

    def mirror(self, status, tmp):
        import restore_web_archive as rwa
        self.addCleanup(setattr, rwa, "STORE", rwa.STORE)
        rwa.STORE = Path(tmp)
        clock = Clock()
        m = object.__new__(rwa.Mirror)
        m.rows = {}
        m.ledger_path = Path(tmp) / "ledger.json"
        m.http = polite_http.Polite(min_interval=0.0, retries=2, base_delay=1.0,
                                    sleep=clock.sleep, clock=clock.time, log=lambda message: None)
        m.connection = FakeConnection(status)
        return m

    def row(self):
        return {"url": "http://aceofangels.com/", "original": "http://www.aceofangels.com/",
                "timestamp": "20010127072200", "kind": "page", "state": "pending"}

    def test_throttled_row_stays_pending(self):
        import tempfile
        for status in (429, 503):
            with tempfile.TemporaryDirectory() as tmp:
                m, row = self.mirror(status, tmp), self.row()
                self.assertIs(m.fetch(row), False)
                self.assertEqual(row["state"], "pending")
                self.assertEqual(m.connection.requests, 3)  # first try plus two retries

    def test_not_found_is_missing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            m, row = self.mirror(404, tmp), self.row()
            self.assertIs(m.fetch(row), True)
            self.assertEqual(row["state"], "missing")
            self.assertEqual(m.connection.requests, 1)


def _no_network(*args, **kwargs):
    raise AssertionError("test_polite_http must not use the network")


if __name__ == "__main__":
    socket.socket.connect = _no_network
    socket.create_connection = _no_network
    unittest.main()
