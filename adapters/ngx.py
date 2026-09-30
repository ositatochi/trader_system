import requests

import config
import db
from adapters.common import get_or_create_asset, upsert_price


def fetch_prices(symbols=None):
    if symbols is None:
        symbols = config.NGX_WATCHLIST

    inserted_count = 0
    headers = {}
    if config.NGN_API_KEY:
        headers["Authorization"] = f"Bearer {config.NGN_API_KEY}"

    with db.get_conn() as conn:
        for symbol in symbols:
            try:
                url = f"https://ngnmarket.com/api/companies/{symbol}/chart"
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code != 200:
                    print(f"[NGX] Skipping {symbol}: status {response.status_code}")
                    continue

                data = response.json()
                items = data if isinstance(data, list) else data.get("data", [])
                asset_id = get_or_create_asset(
                    conn, symbol, exchange="NGX", currency="NGN", asset_type="stock"
                )

                for item in items:
                    timestamp = item.get("date") or item.get("timestamp")
                    if timestamp:
                        inserted_count += upsert_price(
                            conn,
                            asset_id,
                            timestamp,
                            item.get("open", 0),
                            item.get("high", 0),
                            item.get("low", 0),
                            item.get("close", 0),
                            item.get("volume", 0),
                        )
            except (requests.RequestException, ValueError, TypeError, KeyError) as error:
                print(f"[NGX] Failed fetching {symbol}: {error}")

    return inserted_count