import datetime
import json

import pandas as pd
import pandas_ta_classic as ta

import config
import db


def compute_indicators(df):
    if df.empty:
        return df

    df["ema_20"] = ta.ema(df["close"], length=20)
    df["ema_50"] = ta.ema(df["close"], length=50)
    df["ema_200"] = ta.ema(df["close"], length=200)
    df["rsi_14"] = ta.rsi(df["close"], length=14)

    macd_df = ta.macd(df["close"])
    if macd_df is not None and not macd_df.empty:
        df["macd"] = macd_df.iloc[:, 0]
        df["macd_signal"] = macd_df.iloc[:, 2]
    else:
        df["macd"] = None
        df["macd_signal"] = None

    middle = df["close"].rolling(20).mean()
    deviation = df["close"].rolling(20).std()
    df["bb_upper"] = middle + 2 * deviation
    df["bb_lower"] = middle - 2 * deviation
    df["volume_sma20"] = df["volume"].rolling(20).mean()
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr_14"] = true_range.rolling(14).mean()

    return df


def _make_signal(df, asset_type, side, reason):
    last = df.iloc[-1]
    entry_price = float(last["close"])
    rules = config.SIGNAL_RULES.get(asset_type, config.SIGNAL_RULES["stock"])
    stop_pct = rules["stop_loss_pct"] / 100
    target_pct = rules["take_profit_pct"] / 100
    buy = side == "buy"

    confirmations = [
        bool(pd.notna(last.get("ema_50")) and (last["close"] >= last["ema_50"] if buy else last["close"] <= last["ema_50"])),
        bool(pd.notna(last.get("rsi_14")) and (last["rsi_14"] >= 50 if buy else last["rsi_14"] <= 50)),
        bool(pd.notna(last.get("volume_sma20")) and last["volume"] >= last["volume_sma20"]),
        bool(pd.notna(last.get("atr_14")) and entry_price > 0 and 0 < last["atr_14"] / entry_price < 0.1),
    ]
    return {
        "signal": side,
        "entry_price": entry_price,
        "stop_loss": entry_price * (1 - stop_pct if buy else 1 + stop_pct),
        "take_profit": entry_price * (1 + target_pct if buy else 1 - target_pct),
        "reason": reason,
        "confidence": round(sum(confirmations) * 100 / len(confirmations)),
    }


def ema_cross_signal(df, asset_type="stock"):
    if len(df) < 2:
        return None
    last = df.iloc[-1]
    previous = df.iloc[-2]
    if any(pd.isna(last[column]) or pd.isna(previous[column]) for column in ("ema_20", "ema_50")):
        return None
    rules = config.SIGNAL_RULES.get(asset_type, config.SIGNAL_RULES["stock"])
    if last["volume"] < rules.get("min_volume", 0):
        return None
    if previous["ema_20"] <= previous["ema_50"] and last["ema_20"] > last["ema_50"] and last["rsi_14"] > 50 and last["macd"] > last["macd_signal"]:
        return _make_signal(df, asset_type, "buy", f"EMA20 crossed above EMA50, RSI {last['rsi_14']:.1f}, MACD bullish")
    if previous["ema_20"] >= previous["ema_50"] and last["ema_20"] < last["ema_50"]:
        return _make_signal(df, asset_type, "sell", "EMA20 crossed below EMA50")
    return None


def rsi_reversal_signal(df, asset_type="stock"):
    if df.empty or pd.isna(df.iloc[-1].get("rsi_14")):
        return None
    rsi = df.iloc[-1]["rsi_14"]
    if rsi < 30:
        return _make_signal(df, asset_type, "buy", f"RSI oversold at {rsi:.1f}")
    if rsi > 70:
        return _make_signal(df, asset_type, "sell", f"RSI overbought at {rsi:.1f}")
    return None


def macd_trend_signal(df, asset_type="stock"):
    if len(df) < 2:
        return None
    last, previous = df.iloc[-1], df.iloc[-2]
    columns = ("macd", "macd_signal", "ema_200")
    if any(pd.isna(last.get(column)) for column in columns) or any(
        pd.isna(previous.get(column)) for column in ("macd", "macd_signal")
    ):
        return None
    if previous["macd"] <= previous["macd_signal"] and last["macd"] > last["macd_signal"] and last["close"] > last["ema_200"]:
        return _make_signal(df, asset_type, "buy", "MACD crossed bullish above EMA200 trend")
    if previous["macd"] >= previous["macd_signal"] and last["macd"] < last["macd_signal"] and last["close"] < last["ema_200"]:
        return _make_signal(df, asset_type, "sell", "MACD crossed bearish below EMA200 trend")
    return None


def bollinger_signal(df, asset_type="stock"):
    if df.empty:
        return None
    last = df.iloc[-1]
    if pd.isna(last.get("bb_upper")) or pd.isna(last.get("bb_lower")) or pd.isna(last.get("volume_sma20")):
        return None
    volume_spike = last["volume"] >= last["volume_sma20"] * 1.5
    if volume_spike and last["close"] > last["bb_upper"]:
        return _make_signal(df, asset_type, "buy", "Close broke above upper Bollinger band with volume spike")
    if volume_spike and last["close"] < last["bb_lower"]:
        return _make_signal(df, asset_type, "sell", "Close broke below lower Bollinger band with volume spike")
    return None


STRATEGIES = {
    "ema_cross": ema_cross_signal,
    "rsi_reversal": rsi_reversal_signal,
    "macd_trend": macd_trend_signal,
    "bollinger_break": bollinger_signal,
}


def aggregate_signals(df, asset_type, strategy_names=None):
    names = strategy_names if strategy_names is not None else config.ENABLED_STRATEGIES
    outcomes = []
    for name in names:
        strategy = STRATEGIES.get(name)
        if strategy is None:
            continue
        result = strategy(df, asset_type)
        if result:
            outcomes.append({"strategy": name, **result})

    votes = {side: sum(item["signal"] == side for item in outcomes) for side in ("buy", "sell")}
    final_signal = "hold" if votes["buy"] == votes["sell"] else max(votes, key=votes.get)
    confidence = round(sum(item["confidence"] for item in outcomes) / len(outcomes)) if outcomes else 0
    supporting = [item for item in outcomes if item["signal"] == final_signal]
    representative = supporting[0] if supporting else None
    return {
        "signal": final_signal,
        "entry_price": representative["entry_price"] if representative else float(df.iloc[-1]["close"]),
        "stop_loss": representative["stop_loss"] if representative else None,
        "take_profit": representative["take_profit"] if representative else None,
        "reason": " | ".join(f"{item['strategy']}: {item['reason']}" for item in outcomes) or "No strategy triggered",
        "confidence": confidence,
        "strategy": ",".join(item["strategy"] for item in supporting),
        "strategies_json": json.dumps(outcomes),
        "strategies": outcomes,
    }


def generate_signal(df, asset_type):
    return ema_cross_signal(df, asset_type)


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
                print(
                    f"[Analyzer] symbol={asset['symbol']} bars={len(df)} "
                    "indicators=skipped signal=NONE"
                )
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

            signal = aggregate_signals(df, asset["asset_type"])
            signal_label = signal["signal"].upper()
            print(
                f"[Analyzer] symbol={asset['symbol']} bars={len(df)} "
                f"indicators=ok signal={signal_label}"
            )
            if signal["signal"] in ("buy", "sell"):
                timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                cur.execute(
                    """
                    INSERT INTO signals
                        (asset_id, timestamp, signal, entry_price, stop_loss,
                            take_profit, reason, notified, confidence, strategy, strategies_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                    """,
                    (
                        asset["id"],
                        timestamp,
                        signal["signal"],
                        signal["entry_price"],
                        signal["stop_loss"],
                        signal["take_profit"],
                        signal["reason"],
                        signal["confidence"],
                        signal["strategy"],
                        signal["strategies_json"],
                    ),
                )
                signals_generated += 1

    return signals_generated


def main():
    count = analyze_all()
    print(f"Analysis complete. Signals generated: {count}")


if __name__ == "__main__":
    main()