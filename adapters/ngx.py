import re
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
        symbols = config.NGX_WATCHLIST
    if isinstance(symbols, str):
        symbols = [symbols]

    results = []
    headers = {}
    headers["User-Agent"] = config.USER_AGENT
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
        response = get_or_fetch(
            api_url,
            900,
            lambda: _request(api_url, headers=headers, timeout=config.REQUEST_TIMEOUT),
        )
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
            logger.warning("symbol=%s endpoint=%s status=%s error=%s", symbol, api_url, response.status_code, error)
    except (requests.RequestException, ValueError, TypeError) as error:
        status = response.status_code if response is not None else None
        snippet = response.text[:200] if response is not None else ""
        endpoints.append(
            {"endpoint": api_url, "status": status, "snippet": snippet, "error": str(error)}
        )
        errors.append(str(error))
        logger.exception("symbol=%s endpoint=%s status=%s error=%s", symbol, api_url, status, error)

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
        if not config.NGX_SCRAPE_FALLBACK:
            return {
                "symbol": symbol,
                "rows": 0,
                "error": "; ".join(errors),
                "responses": endpoints,
            }
        api_status = endpoints[0]["status"] if endpoints else None
        api_error = "; ".join(errors)
        logger.info("symbol=%s endpoint=%s status=%s error=%s; trying scrape", symbol, api_url, api_status, api_error)

        scrape_url = f"https://afx.kwayisi.org/ngx/{symbol.lower()}.html"
        scrape_response = None
        try:
            scrape_response = get_or_fetch(
                scrape_url,
                3600,
                lambda: _request(
                    scrape_url,
                    headers={"User-Agent": config.USER_AGENT},
                    timeout=config.REQUEST_TIMEOUT,
                ),
            )
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
                logger.warning("symbol=%s endpoint=%s status=%s error=%s", symbol, scrape_url, status, scrape_error)
        except (requests.RequestException, ValueError, TypeError) as error:
            status = scrape_response.status_code if scrape_response is not None else None
            snippet = scrape_response.text[:200] if scrape_response is not None else ""
            endpoints.append(
                {"endpoint": scrape_url, "status": status, "snippet": snippet, "error": str(error)}
            )
            errors.append(str(error))
            logger.exception("symbol=%s endpoint=%s status=%s error=%s", symbol, scrape_url, status, error)

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