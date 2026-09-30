import datetime

import pandas as pd
import pandas_ta_classic as ta

import config
import db


def compute_indicators(df):
    if len(df) < 50:
        return df

    df["ema_20"] = ta.ema(df["close"], length=20)
    df["ema_50"] = ta.ema(df["close"], length=50)
    df["rsi_14"] = ta.rsi(df["close"], length=14)

    macd_df = ta.macd(df["close"])
    if macd_df is not None and not macd_df.empty:
        df["macd"] = macd_df.iloc[:, 0]
        df["macd_signal"] = macd_df.iloc[:, 2]
    else:
        df["macd"] = None
        df["macd_signal"] = None

    return df


def generate_signal(df, asset_type):
    if len(df) < 2 or "ema_20" not in df.columns or df["ema_20"].isnull().all():
        return None

    last = df.iloc[-1]
    previous = df.iloc[-2]
    required = ("ema_20", "ema_50", "rsi_14", "macd", "macd_signal")
    if any(pd.isna(last[column]) for column in required) or any(
        pd.isna(previous[column]) for column in ("ema_20", "ema_50")
    ):
        return None

    rules = config.SIGNAL_RULES.get(asset_type, config.SIGNAL_RULES["stock"])
    if last["volume"] < rules.get("min_volume", 0):
        return None

    entry_price = float(last["close"])
    stop_loss_pct = rules["stop_loss_pct"] / 100.0
    take_profit_pct = rules["take_profit_pct"] / 100.0

    is_buy = (
        previous["ema_20"] <= previous["ema_50"]
        and last["ema_20"] > last["ema_50"]
        and last["rsi_14"] > 50
        and last["macd"] > last["macd_signal"]
    )
    if is_buy:
        return {
            "signal": "buy",
            "entry_price": entry_price,
            "stop_loss": entry_price * (1.0 - stop_loss_pct),
            "take_profit": entry_price * (1.0 + take_profit_pct),
            "reason": f"EMA20 crossed above EMA50, RSI {last['rsi_14']:.1f}, MACD Bullish",
        }

    is_sell = (
        previous["ema_20"] >= previous["ema_50"]
        and last["ema_20"] < last["ema_50"]
    )
    if is_sell:
        return {
            "signal": "sell",
            "entry_price": entry_price,
            "stop_loss": entry_price * (1.0 + stop_loss_pct),
            "take_profit": entry_price * (1.0 - take_profit_pct),
            "reason": "EMA20 crossed below EMA50",
        }

    return None


def analyze_all():
    signals_generated = 0
    with db.get_conn() as conn:
        cur = conn.cursor()
        assets = cur.execute(
            "SELECT id, symbol, asset_type FROM assets WHERE active = 1"
        ).fetchall()

        for asset in assets:
            query = """
                SELECT timestamp, open, high, low, close, volume
                FROM prices WHERE asset_id = ? ORDER BY timestamp ASC
            """
            df = pd.read_sql_query(query, conn, params=(asset["id"],))
            if len(df) < 50:
                continue

            df = compute_indicators(df)
            last_row = df.iloc[-1]
            cur.execute(
                """
                INSERT OR REPLACE INTO indicators
                    (asset_id, timestamp, ema_20, ema_50, rsi_14, macd, macd_signal)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["id"],
                    str(last_row["timestamp"]),
                    float(last_row["ema_20"]) if pd.notna(last_row["ema_20"]) else None,
                    float(last_row["ema_50"]) if pd.notna(last_row["ema_50"]) else None,
                    float(last_row["rsi_14"]) if pd.notna(last_row["rsi_14"]) else None,
                    float(last_row["macd"]) if pd.notna(last_row["macd"]) else None,
                    float(last_row["macd_signal"])
                    if pd.notna(last_row["macd_signal"])
                    else None,
                ),
            )

            signal = generate_signal(df, asset["asset_type"])
            if signal:
                timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                cur.execute(
                    """
                    INSERT INTO signals
                        (asset_id, timestamp, signal, entry_price, stop_loss,
                         take_profit, reason, notified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        asset["id"],
                        timestamp,
                        signal["signal"],
                        signal["entry_price"],
                        signal["stop_loss"],
                        signal["take_profit"],
                        signal["reason"],
                    ),
                )
                signals_generated += 1

    return signals_generated


def main():
    count = analyze_all()
    print(f"Analysis complete. Signals generated: {count}")


if __name__ == "__main__":
    main()