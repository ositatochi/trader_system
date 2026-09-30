import json
from datetime import date, datetime, timedelta

import db


def compute_metrics(days=30):
    days = max(1, min(int(days), 365))
    with db.get_conn() as conn:
        signals = conn.execute(
            """
            SELECT s.id, s.asset_id, s.timestamp, s.entry_price, s.signal,
                   s.strategy, s.strategies_json, a.symbol
            FROM signals s JOIN assets a ON a.id = s.asset_id
            WHERE s.signal IN ('buy', 'sell')
            ORDER BY s.id
            """
        ).fetchall()
        price_cache = {}
        metrics = {}

        for signal in signals:
            try:
                signal_time = datetime.fromisoformat(signal["timestamp"].replace("Z", "+00:00"))
            except (TypeError, ValueError):
                try:
                    signal_time = datetime.combine(date.fromisoformat(signal["timestamp"][:10]), datetime.min.time())
                except (TypeError, ValueError):
                    continue
            start = signal_time.date().isoformat()
            end = (signal_time.date() + timedelta(days=days)).isoformat()
            if signal["asset_id"] not in price_cache:
                price_cache[signal["asset_id"]] = conn.execute(
                    "SELECT timestamp, high, low, close FROM prices WHERE asset_id = ? ORDER BY timestamp",
                    (signal["asset_id"],),
                ).fetchall()
            future = [row for row in price_cache[signal["asset_id"]] if start < str(row["timestamp"])[:10] <= end]
            try:
                strategy_votes = json.loads(signal["strategies_json"] or "[]")
            except (TypeError, ValueError):
                strategy_votes = []
            if not strategy_votes and signal["strategy"]:
                strategy_votes = [
                    {"strategy": name, "signal": signal["signal"], "entry_price": signal["entry_price"]}
                    for name in signal["strategy"].split(",") if name
                ]

            for vote in strategy_votes:
                name = vote.get("strategy")
                side = vote.get("signal")
                entry = vote.get("entry_price") or signal["entry_price"]
                if not name or side not in ("buy", "sell") or not entry:
                    continue
                item = metrics.setdefault(name, {"strategy": name, "signals": 0, "evaluated": 0, "winners": 0, "moves": []})
                item["signals"] += 1
                if not future:
                    continue
                item["evaluated"] += 1
                favorable = max((row["high"] for row in future if row["high"] is not None), default=None) if side == "buy" else min((row["low"] for row in future if row["low"] is not None), default=None)
                direction = 1 if side == "buy" else -1
                if favorable is not None and (favorable - entry) * direction > 0:
                    item["winners"] += 1
                final_close = future[-1]["close"]
                if final_close is not None:
                    item["moves"].append((final_close - entry) / entry * 100 * direction)

    output = []
    for item in metrics.values():
        moves = item.pop("moves")
        item["win_rate"] = item["winners"] / item["evaluated"] * 100 if item["evaluated"] else 0
        item["avg_move"] = sum(moves) / len(moves) if moves else 0
        item["best"] = max(moves) if moves else 0
        item["worst"] = min(moves) if moves else 0
        output.append(item)
    return {"days": days, "strategies": sorted(output, key=lambda item: item["strategy"])}