import json
from datetime import datetime, timezone

import requests

import db
from logger import get_logger

logger = get_logger(__name__)


class CachedResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def get_or_fetch(url, ttl_seconds, fetch_fn):
    now = datetime.now(timezone.utc)
    with db.get_conn() as conn:
        cached = conn.execute("SELECT body, fetched_at FROM api_cache WHERE url = ?", (url,)).fetchone()
    if cached:
        try:
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if (now - fetched_at).total_seconds() < ttl_seconds:
                logger.debug("Cache hit url=%s", url)
                return CachedResponse(200, cached["body"])
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid cache timestamp url=%s", url)

    response = fetch_fn()
    if response.status_code == 200:
        with db.get_conn() as conn:
            conn.execute(
                """
                INSERT INTO api_cache (url, body, fetched_at) VALUES (?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET body = excluded.body, fetched_at = excluded.fetched_at
                """,
                (url, response.text, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
    return response