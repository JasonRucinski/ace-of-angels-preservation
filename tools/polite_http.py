"""One polite way to fetch from archive.org and the Wayback Machine.

Every research tool that downloads or queries goes through `polite_get` (or
`polite_open` to stream a large file, or `Polite.call` for a caller that keeps
its own connection). It

- sends one User-Agent that names the project and nothing about the user;
- waits at least `min_interval` seconds between requests to the same host;
- on HTTP 429 or 5xx, or a dropped connection, waits and tries again with
  exponential backoff, honouring a `Retry-After` header;
- gives up after `retries` further attempts by raising the last error, so a
  caller can leave its work queued instead of marking it done.

Tests pass a fake `opener`, `sleep` and `clock`; nothing here is exercised
against the real network by the test suite.
"""
import email.utils
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "ace-of-angels-preservation/1.0 (archive research; paced requests)"
MIN_INTERVAL = 2.0   # seconds between requests to one host
RETRIES = 5          # further attempts after the first one fails
BASE_DELAY = 5.0     # first backoff, doubled after each failure
MAX_DELAY = 600.0    # cap for both the backoff and a server's Retry-After


def retryable(error):
    """True for errors worth waiting out: throttling, server trouble, a dropped connection."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code == 429 or 500 <= error.code < 600
    return isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError))


def retry_after(error, now=None):
    """Seconds asked for by a Retry-After header (delta or HTTP date), else None."""
    headers = getattr(error, "headers", None)
    value = headers.get("Retry-After") if headers is not None else None
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when is None:
        return None
    return max(0.0, when.timestamp() - (time.time() if now is None else now))


class Polite:
    """Pacing and backoff shared by every request made through one instance."""

    def __init__(self, min_interval=MIN_INTERVAL, retries=RETRIES, base_delay=BASE_DELAY,
                 max_delay=MAX_DELAY, opener=None, sleep=time.sleep, clock=time.monotonic,
                 log=None):
        self.min_interval = min_interval
        self.retries = retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.opener = opener or urllib.request.build_opener()
        self.sleep = sleep
        self.clock = clock
        self.log = log or (lambda message: print(message, file=sys.stderr, flush=True))
        self.last = {}  # host -> clock() of the last request sent to it

    def _pace(self, host):
        last = self.last.get(host)
        if last is not None:
            wait = self.min_interval - (self.clock() - last)
            if wait > 0:
                self.sleep(wait)
        self.last[host] = self.clock()

    def call(self, url, send):
        """Run send(url) paced for url's host, retrying retryable errors with backoff."""
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
        delay = self.base_delay
        for attempt in range(self.retries + 1):
            self._pace(host)
            try:
                return send(url)
            except Exception as error:
                if not retryable(error) or attempt == self.retries:
                    raise
                asked = retry_after(error)
                wait = min(self.max_delay, max(delay, asked or 0.0))
                if isinstance(error, urllib.error.HTTPError):
                    error.close()
                    what = f"HTTP {error.code}"
                else:
                    what = type(error).__name__
                self.log(f"   {what}; retry {attempt + 1}/{self.retries} in {wait:g}s: {url[:90]}")
                self.sleep(wait)
                delay = min(self.max_delay, delay * 2)

    def open(self, url, headers=None, timeout=120):
        """Open url and return the response for streaming; the caller closes it."""
        def send(u):
            request = urllib.request.Request(u, headers={**(headers or {}), "User-Agent": USER_AGENT})
            return self.opener.open(request, timeout=timeout)
        return self.call(url, send)

    def get(self, url, headers=None, timeout=120):
        """Return the body of url."""
        with self.open(url, headers=headers, timeout=timeout) as response:
            return response.read()


_default = Polite()


def polite_open(url, headers=None, timeout=120):
    """Open url through the shared, paced client; the caller closes the response."""
    return _default.open(url, headers=headers, timeout=timeout)


def polite_get(url, headers=None, timeout=120):
    """Return the body of url, fetched through the shared, paced client."""
    return _default.get(url, headers=headers, timeout=timeout)
