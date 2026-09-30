import db

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    name TEXT,
    asset_type TEXT NOT NULL CHECK(asset_type IN ('stock', 'crypto')),
    exchange TEXT NOT NULL,
    currency TEXT NOT NULL,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    UNIQUE(asset_id, timestamp),
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS indicators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    ema_20 REAL,
    ema_50 REAL,
    rsi_14 REAL,
    macd REAL,
    macd_signal REAL,
    UNIQUE(asset_id, timestamp),
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    signal TEXT NOT NULL CHECK(signal IN ('buy', 'sell', 'hold')),
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    reason TEXT,
    notified INTEGER DEFAULT 0,
    FOREIGN KEY(asset_id) REFERENCES assets(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    side TEXT CHECK(side IN ('long', 'short')),
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    entry_date TEXT NOT NULL,
    exit_price REAL,
    exit_date TEXT,
    status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed')),
    notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_prices_asset_ts ON prices(asset_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status);
"""


def main():
    conn = db.get_conn()
    with conn:
        conn.executescript(SCHEMA)
    conn.close()
    print("DB initialized.")


if __name__ == "__main__":
    main()