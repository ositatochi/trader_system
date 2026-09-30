import requests

import config
import db
from cache import get_or_fetch
from logger import get_logger
from rate_limit import wrap_request

logger = get_logger(__name__)


def _request(url, **kwargs):
    wrap_request(url)
    return requests.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=config.REQUEST_TIMEOUT,
        **kwargs,
    )


def ngx_summary():
    changes = []
    with db.get_conn() as conn:
        assets = conn.execute(
            "SELECT id, symbol FROM assets WHERE active = 1 AND asset_type = 'stock'"
        ).fetchall()
        for asset in assets:
            prices = conn.execute(
                "SELECT close, timestamp FROM prices WHERE asset_id = ? ORDER BY timestamp DESC, id DESC LIMIT 2",
                (asset["id"],),
            ).fetchall()
            if len(prices) < 2 or not prices[1]["close"]:
                continue
            change = (prices[0]["close"] - prices[1]["close"]) / prices[1]["close"] * 100
            changes.append({"symbol": asset["symbol"], "change_pct": change})

    gainers = sum(item["change_pct"] > 0 for item in changes)
    losers = sum(item["change_pct"] < 0 for item in changes)
    return {
        "assets": len(changes),
        "gainers": gainers,
        "losers": losers,
        "unchanged": len(changes) - gainers - losers,
        "asi_proxy_change_pct": sum(item["change_pct"] for item in changes) / len(changes) if changes else 0,
        "top_mover": max(changes, key=lambda item: abs(item["change_pct"])) if changes else None,
    }


def crypto_summary():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        response = get_or_fetch(url, 300, lambda: _request(url))
        response.raise_for_status()
        tickers = response.json()
        watchlist = set(config.CRYPTO_WATCHLIST)
        tracked = [item for item in tickers if item.get("symbol") in watchlist]
        changes = [
            {"symbol": item["symbol"], "change_pct": float(item["priceChangePercent"]), "last_price": float(item["lastPrice"])}
            for item in tracked
        ]
        return {
            "assets": len(changes),
            "gainers": sum(item["change_pct"] > 0 for item in changes),
            "losers": sum(item["change_pct"] < 0 for item in changes),
            "top_movers": sorted(changes, key=lambda item: abs(item["change_pct"]), reverse=True)[:5],
        }
    except (requests.RequestException, ValueError, TypeError, KeyError) as error:
        logger.warning("Crypto ticker overview unavailable: %s", error)
        return {"assets": 0, "gainers": 0, "losers": 0, "top_movers": [], "error": str(error)}


def fear_greed():
    url = "https://api.alternative.me/fng/?limit=1&format=json"
    try:
        response = get_or_fetch(url, 1800, lambda: _request(url))
        response.raise_for_status()
        record = response.json()["data"][0]
        return {"value": int(record["value"]), "classification": record["value_classification"]}
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError) as error:
        logger.info("Fear & Greed unavailable: %s", error)
        return None


def market_overview():
    ngx = ngx_summary()
    crypto = crypto_summary()
    with db.get_conn() as conn:
        total_assets = conn.execute("SELECT COUNT(*) FROM assets WHERE active = 1").fetchone()[0]
    return {
        "total_assets": total_assets,
        "ngx": ngx,
        "crypto": crypto,
        "fear_greed": fear_greed(),
    }