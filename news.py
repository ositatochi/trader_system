import re
from datetime import datetime, timezone

import feedparser
import requests

import config
import db

FEEDS = {
    "crypto": (
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
        "https://decrypt.co/feed",
    ),
    "stock": (
        "https://nairametrics.com/feed/",
        "https://businessday.ng/feed/",
        "https://punchng.com/topics/business/feed/",
    ),
}
POSITIVE_WORDS = ("up", "surge", "rally", "beat", "growth")
NEGATIVE_WORDS = ("down", "drop", "miss", "fall", "loss")


def _sentiment(text):
    normalized = text.lower()
    positive = sum(len(re.findall(rf"\b{re.escape(word)}\b", normalized)) for word in POSITIVE_WORDS)
    negative = sum(len(re.findall(rf"\b{re.escape(word)}\b", normalized)) for word in NEGATIVE_WORDS)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def fetch_news(symbol, asset_type):
    results = []
    symbol_match = re.compile(rf"(?<![A-Z0-9]){re.escape(symbol)}(?![A-Z0-9])", re.IGNORECASE)
    for url in FEEDS.get(asset_type, FEEDS["stock"]):
        try:
            response = requests.get(
                url,
                headers={"User-Agent": config.USER_AGENT},
                timeout=config.REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            for entry in parsed.entries:
                title = entry.get("title", "").strip()
                summary = re.sub(r"<[^>]+>", " ", entry.get("summary", ""))
                searchable = f"{title} {summary}"
                link = entry.get("link", "").strip()
                if not link or not symbol_match.search(searchable):
                    continue
                published = entry.get("published") or entry.get("updated") or ""
                results.append(
                    {
                        "title": title,
                        "link": link,
                        "published": published,
                        "sentiment": _sentiment(searchable),
                    }
                )
        except (requests.RequestException, ValueError, TypeError) as error:
            print(f"[News] symbol={symbol} endpoint={url} error={error}")

    unique = {item["link"]: item for item in results}
    return sorted(unique.values(), key=lambda item: item["published"], reverse=True)[:10]


def refresh_news_for_assets():
    with db.get_conn() as conn:
        assets = conn.execute("SELECT id, symbol, asset_type FROM assets WHERE active = 1").fetchall()

    inserted = 0
    for asset in assets:
        try:
            items = fetch_news(asset["symbol"], asset["asset_type"])
            with db.get_conn() as conn:
                for item in items:
                    cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO news_cache
                            (asset_id, title, link, published, sentiment)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (asset["id"], item["title"], item["link"], item["published"], item["sentiment"]),
                    )
                    inserted += cursor.rowcount
        except Exception as error:
            print(f"[News] symbol={asset['symbol']} refresh error={error}")
    print(f"[News] inserted={inserted}")
    return inserted