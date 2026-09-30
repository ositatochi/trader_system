import json

import adapters.crypto
import adapters.ngx
import config
import db


def masked_status(value):
    if not value:
        return "missing"
    if len(value) <= 4:
        return "set (****)"
    return f"set ({value[:2]}{'*' * min(len(value) - 4, 12)}{value[-2:]})"


def database_snapshot():
    tables = ("assets", "prices", "indicators", "signals")
    with db.get_conn() as conn:
        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }
        latest = {
            table: [dict(row) for row in conn.execute(
                f"SELECT * FROM {table} ORDER BY id DESC LIMIT 5"
            ).fetchall()]
            for table in tables
        }
    return {"counts": counts, "latest": latest}


def run_diagnostics():
    ngx_symbol = config.NGX_WATCHLIST[0] if config.NGX_WATCHLIST else None
    crypto_symbol = config.CRYPTO_WATCHLIST[0] if config.CRYPTO_WATCHLIST else None
    results = []

    if ngx_symbol:
        results.append({"source": "NGX", **adapters.ngx.fetch_prices(ngx_symbol)})
    else:
        results.append({"source": "NGX", "symbol": None, "rows": 0, "error": "watchlist is empty", "responses": []})
    if crypto_symbol:
        results.append({"source": "Crypto", **adapters.crypto.fetch_prices(crypto_symbol)})
    else:
        results.append({"source": "Crypto", "symbol": None, "rows": 0, "error": "watchlist is empty", "responses": []})

    for result in results:
        print(f"[{result['source']}] symbol={result['symbol']} rows_inserted={result['rows']} error={result['error']}")
        for response in result["responses"]:
            print(
                f"[{result['source']}] endpoint={response['endpoint']} "
                f"status={response['status']} snippet={response['snippet'][:200]!r} "
                f"error={response['error']}"
            )

    env = {
        "NGN_API_KEY": masked_status(config.NGN_API_KEY),
        "TELEGRAM_BOT_TOKEN": masked_status(config.TELEGRAM_BOT_TOKEN),
        "TELEGRAM_CHAT_ID": masked_status(config.TELEGRAM_CHAT_ID),
    }
    snapshot = database_snapshot()
    print(f"Environment: {json.dumps(env)}")
    print(f"Database rows: {json.dumps(snapshot['counts'])}")
    return {"results": results, "env": env, **snapshot}


if __name__ == "__main__":
    run_diagnostics()