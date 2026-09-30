import re
from datetime import datetime, timezone

import requests

import config
import db
from adapters.common import get_or_create_asset, upsert_price


def fetch_prices(symbols=None):
    if symbols is None:
        symbols = config.NGX_WATCHLIST
    if isinstance(symbols, str):
        symbols = [symbols]

    results = []
    headers = {}
    if config.NGN_API_KEY:
        headers["Authorization"] = f"Bearer {config.NGN_API_KEY}"

    with db.get_conn() as conn:
        for symbol in symbols:
            results.append(_fetch_symbol(conn, symbol, headers))

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


def _fetch_symbol(conn, symbol, headers):
    endpoints = []
    errors = []
    items = []
    api_url = f"https://api.ngnmarket.com/v1/companies/{symbol}/chart"
    response = None
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        snippet = response.text[:200]
        endpoints.append(
            {"endpoint": api_url, "status": response.status_code, "snippet": snippet, "error": None}
        )
        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, list):
                items = payload
            elif isinstance(payload, dict):
                items = payload.get("data") or payload.get("prices") or payload.get("results") or []
            if not isinstance(items, list):
                items = []
        else:
            error = f"HTTP {response.status_code}"
            errors.append(error)
            print(
                f"[NGX] symbol={symbol} endpoint={api_url} "
                f"status={response.status_code} error={error}"
            )
    except (requests.RequestException, ValueError, TypeError) as error:
        status = response.status_code if response is not None else None
        snippet = response.text[:200] if response is not None else ""
        endpoints.append(
            {"endpoint": api_url, "status": status, "snippet": snippet, "error": str(error)}
        )
        errors.append(str(error))
        print(f"[NGX] symbol={symbol} endpoint={api_url} status={status} error={error}")

    inserted = 0
    asset_id = None
    if items:
        asset_id = get_or_create_asset(
            conn, symbol, exchange="NGX", currency="NGN", asset_type="stock"
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("date") or item.get("timestamp")
            close = item.get("close") or item.get("price")
            if timestamp and close is not None:
                inserted += upsert_price(
                    conn,
                    asset_id,
                    timestamp,
                    item.get("open", close),
                    item.get("high", close),
                    item.get("low", close),
                    close,
                    item.get("volume", 0),
                )
    else:
        if not errors:
            errors.append("API returned no price rows")
        api_status = endpoints[0]["status"] if endpoints else None
        api_error = "; ".join(errors)
        print(
            f"[NGX] symbol={symbol} endpoint={api_url} status={api_status} "
            f"error={api_error}; trying scrape"
        )

        scrape_url = f"https://afx.kwayisi.org/ngx/{symbol.lower()}.html"
        scrape_response = None
        try:
            scrape_response = requests.get(scrape_url, timeout=10)
            status = scrape_response.status_code
            snippet = scrape_response.text[:200]
            price = _extract_latest_price(scrape_response.text) if status == 200 else None
            scrape_error = None
            if status != 200:
                scrape_error = f"HTTP {status}"
            elif price is None:
                scrape_error = "latest price not found in page"
            endpoints.append(
                {"endpoint": scrape_url, "status": status, "snippet": snippet, "error": scrape_error}
            )
            if price is not None:
                asset_id = asset_id or get_or_create_asset(
                    conn, symbol, exchange="NGX", currency="NGN", asset_type="stock"
                )
                inserted += upsert_price(
                    conn,
                    asset_id,
                    datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                    price,
                    price,
                    price,
                    price,
                    0,
                )
                errors = []
            else:
                errors.append(scrape_error)
                print(
                    f"[NGX] symbol={symbol} endpoint={scrape_url} status={status} error={scrape_error}"
                )
        except (requests.RequestException, ValueError, TypeError) as error:
            status = scrape_response.status_code if scrape_response is not None else None
            snippet = scrape_response.text[:200] if scrape_response is not None else ""
            endpoints.append(
                {"endpoint": scrape_url, "status": status, "snippet": snippet, "error": str(error)}
            )
            errors.append(str(error))
            print(f"[NGX] symbol={symbol} endpoint={scrape_url} status={status} error={error}")

    return {
        "symbol": symbol,
        "rows": inserted,
        "error": "; ".join(errors) or None,
        "responses": endpoints,
    }


def _extract_latest_price(page):
    patterns = (
        r"(?:latest|last|current)(?:\s+share)?\s+price\D{0,30}([\d,]+(?:\.\d+)?)",
        r"(?:price|close)[^\d]{0,30}([\d,]+(?:\.\d+)?)",
        r"(?:₦|NGN\s*)\s*([\d,]+(?:\.\d+)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, page, flags=re.IGNORECASE)
        if match:
            try:
                price = float(match.group(1).replace(",", ""))
                if price > 0:
                    return price
            except ValueError:
                continue
    return None