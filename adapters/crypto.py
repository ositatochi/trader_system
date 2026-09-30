from datetime import datetime, timezone

import requests

import config
import db
from adapters.common import get_or_create_asset, upsert_price
from cache import get_or_fetch
from logger import get_logger
from rate_limit import wrap_request

logger = get_logger(__name__)


def _request(url, **kwargs):
    wrap_request(url)
    return requests.get(url, **kwargs)


def fetch_prices(symbols=None):
    if symbols is None:
        symbols = config.CRYPTO_WATCHLIST
    if isinstance(symbols, str):
        symbols = [symbols]

    results = []
    with db.get_conn() as conn:
        for symbol in symbols:
            endpoint = "https://api.binance.com/api/v3/klines"
            params = {"symbol": symbol, "interval": "1d", "limit": 200}
            cache_url = requests.Request("GET", endpoint, params=params).prepare().url
            response = None
            try:
                response = get_or_fetch(
                    cache_url,
                    300,
                    lambda: _request(
                        endpoint,
                        params=params,
                        headers={"User-Agent": config.USER_AGENT},
                        timeout=config.REQUEST_TIMEOUT,
                    ),
                )
                snippet = response.text[:200]
                if response.status_code != 200:
                    error = f"HTTP {response.status_code}"
                    logger.warning("symbol=%s endpoint=%s status=%s error=%s", symbol, endpoint, response.status_code, error)
                    results.append(
                        {
                            "symbol": symbol,
                            "rows": 0,
                            "error": error,
                            "responses": [{"endpoint": endpoint, "status": response.status_code, "snippet": snippet, "error": error}],
                        }
                    )
                    continue

                candles = response.json()
                asset_id = get_or_create_asset(
                    conn,
                    symbol,
                    exchange="BINANCE",
                    currency="USDT",
                    asset_type="crypto",
                )
                inserted = 0
                for candle in candles:
                    timestamp = datetime.fromtimestamp(
                        candle[0] / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                    inserted += upsert_price(
                        conn,
                        asset_id,
                        timestamp,
                        candle[1],
                        candle[2],
                        candle[3],
                        candle[4],
                        candle[5],
                    )
                results.append(
                    {
                        "symbol": symbol,
                        "rows": inserted,
                        "error": None if candles else "API returned no candles",
                        "responses": [{"endpoint": endpoint, "status": response.status_code, "snippet": snippet, "error": None if candles else "API returned no candles"}],
                    }
                )
                if not candles:
                    logger.warning("symbol=%s endpoint=%s status=%s error=API returned no candles", symbol, endpoint, response.status_code)
            except (requests.RequestException, ValueError, TypeError, IndexError) as error:
                status = response.status_code if response is not None else None
                snippet = response.text[:200] if response is not None else ""
                logger.exception("symbol=%s endpoint=%s status=%s error=%s", symbol, endpoint, status, error)
                results.append(
                    {
                        "symbol": symbol,
                        "rows": 0,
                        "error": str(error),
                        "responses": [{"endpoint": endpoint, "status": status, "snippet": snippet, "error": str(error)}],
                    }
                )

    if len(results) == 1:
        return results[0]
    return {
        "symbol": ",".join(result["symbol"] for result in results),
        "rows": sum(result["rows"] for result in results),
        "error": "; ".join(result["error"] for result in results if result["error"])
        or None,
        "responses": [response for result in results for response in result["responses"]],
        "results": results,
    }