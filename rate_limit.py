import threading
import time
from urllib.parse import urlparse

from logger import get_logger

logger = get_logger(__name__)
_lock = threading.Lock()
_buckets = {}
_last_request = {}
_CAPACITY = 2.0
_REFILL_RATE = 2.0
_NGN_MIN_INTERVAL = 15.0


def wrap_request(url):
    host = urlparse(url).hostname or "unknown"
    with _lock:
        now = time.monotonic()
        tokens, updated_at = _buckets.get(host, (_CAPACITY, now))
        tokens = min(_CAPACITY, tokens + (now - updated_at) * _REFILL_RATE)
        token_wait = max(0.0, (1.0 - tokens) / _REFILL_RATE)
        interval_wait = 0.0
        if host == "api.ngnmarket.com" and host in _last_request:
            interval_wait = max(0.0, _NGN_MIN_INTERVAL - (now - _last_request[host]))
        wait = max(token_wait, interval_wait)
        if wait:
            logger.info("Rate limit host=%s wait=%.2fs", host, wait)
            time.sleep(wait)
            now = time.monotonic()
            tokens = min(_CAPACITY, tokens + (now - updated_at) * _REFILL_RATE)
        _buckets[host] = (max(0.0, tokens - 1.0), now)
        _last_request[host] = now