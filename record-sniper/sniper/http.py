"""Tiny stdlib HTTP helper with retries and polite rate-limit handling."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "RecordSniper/0.1 (+personal wantlist price alerts)"


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.status = status


def request(url: str, method: str = "GET", params: dict | None = None, headers: dict | None = None,
            data: bytes | dict | str | None = None, timeout: float = 20, retries: int = 3) -> bytes:
    if params:
        url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json, */*"}
    hdrs.update(headers or {})
    body: bytes | None
    if isinstance(data, dict):
        body = json.dumps(data).encode()
        hdrs.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        body = data.encode()
    else:
        body = data

    delay = 2.0
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            retryable = e.code == 429 or e.code >= 500
            if not retryable or attempt == retries:
                raise HttpError(e.code, url, text) from None
            wait = float(e.headers.get("Retry-After") or delay)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == retries:
                raise HttpError(0, url, str(e)) from None
            wait = delay
        time.sleep(min(wait, 60))
        delay *= 2
    raise AssertionError("unreachable")


def get_json(url: str, **kw):
    return json.loads(request(url, **kw) or b"null")
