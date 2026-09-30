from datetime import datetime, timezone

import requests

import config
import db
from adapters.common import get_or_create_asset, upsert_price


def fetch_prices(symbols=None):
    if symbols is None:
        symbols = config.CRYPTO_WATCHLIST

    inserted_count = 0
    with db.get_conn() as conn:
        for symbol in symbols:
            try:
                response = requests.get(
                    "https://api.binance.com/api/v3/klines",
                    params={"symbol": symbol, "interval": "1d", "limit": 200},
                    timeout=10,
                )
                if response.status_code != 200:
                    print(f"[Crypto] Skipping {symbol}: status {response.status_code}")
                    continue

                asset_id = get_or_create_asset(
                    conn,
                    symbol,
                    exchange="BINANCE",
                    currency="USDT",
                    asset_type="crypto",
                )
                for candle in response.json():
                    timestamp = datetime.fromtimestamp(
                        candle[0] / 1000, tz=timezone.utc
                    ).strftime("%Y-%m-%d")
                    inserted_count += upsert_price(
                        conn,
                        asset_id,
                        timestamp,
                        candle[1],
                        candle[2],
                        candle[3],
                        candle[4],
                        candle[5],
                    )
            except (requests.RequestException, ValueError, TypeError, IndexError) as error:
                print(f"[Crypto] Failed fetching {symbol}: {error}")

    return inserted_count