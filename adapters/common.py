def get_or_create_asset(conn, symbol, exchange, currency, asset_type, name=""):
    cur = conn.cursor()
    cur.execute("SELECT id FROM assets WHERE symbol = ?", (symbol,))
    row = cur.fetchone()
    if row:
        return row["id"]

    cur.execute(
        """
        INSERT INTO assets (symbol, name, asset_type, exchange, currency, active)
        VALUES (?, ?, ?, ?, ?, 1)
        """,
        (symbol, name or symbol, asset_type, exchange, currency),
    )
    conn.commit()
    return cur.lastrowid


def upsert_price(conn, asset_id, timestamp, open_price, high, low, close, volume):
    cur = conn.cursor()
    cur.execute(
        """
        INSERT OR IGNORE INTO prices (asset_id, timestamp, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            asset_id,
            timestamp,
            safe_float(open_price),
            safe_float(high),
            safe_float(low),
            safe_float(close),
            safe_float(volume),
        ),
    )
    conn.commit()
    return cur.rowcount


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default