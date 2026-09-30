import math
import statistics

import pandas as pd

import analyzer
import config
import db


def run_backtest(asset_id, strategy_name, start_date=None, end_date=None, initial_capital=10000):
    strategy = analyzer.STRATEGIES.get(strategy_name)
    if strategy is None:
        raise ValueError("Unknown strategy.")

    clauses = ["asset_id = ?"]
    params = [asset_id]
    if start_date:
        clauses.append("timestamp >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("timestamp <= ?")
        params.append(end_date)

    with db.get_conn() as conn:
        asset = conn.execute("SELECT id, symbol, asset_type FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if asset is None:
            raise ValueError("Asset not found.")
        prices = pd.read_sql_query(
            "SELECT timestamp, open, high, low, close, volume FROM prices WHERE "
            + " AND ".join(clauses)
            + " ORDER BY timestamp ASC",
            conn,
            params=params,
        )

    if prices.empty:
        return _summary(asset["symbol"], strategy_name, [], initial_capital)

    frame = analyzer.compute_indicators(prices)
    rules = config.SIGNAL_RULES.get(asset["asset_type"], config.SIGNAL_RULES["stock"])
    stop_fraction = rules["stop_loss_pct"] / 100
    target_fraction = rules["take_profit_pct"] / 100
    trades = []
    equity = initial_capital
    equity_curve = [{"timestamp": str(frame.iloc[0]["timestamp"]), "equity": equity}]
    index = 1

    while index < len(frame) - 1:
        signal = strategy(frame.iloc[:index], asset["asset_type"])
        if not signal:
            index += 1
            continue

        side = signal["signal"]
        entry_index = index
        entry_bar = frame.iloc[entry_index]
        entry_price = float(entry_bar["open"] if pd.notna(entry_bar["open"]) else entry_bar["close"])
        is_long = side == "buy"
        stop_price = entry_price * (1 - stop_fraction if is_long else 1 + stop_fraction)
        target_price = entry_price * (1 + target_fraction if is_long else 1 - target_fraction)
        exit_index = entry_index
        exit_price = float(entry_bar["close"])
        exit_reason = "end of data"

        for future_index in range(entry_index, len(frame)):
            bar = frame.iloc[future_index]
            low = float(bar["low"])
            high = float(bar["high"])
            if is_long and low <= stop_price:
                exit_index, exit_price, exit_reason = future_index, stop_price, "stop loss"
                break
            if not is_long and high >= stop_price:
                exit_index, exit_price, exit_reason = future_index, stop_price, "stop loss"
                break
            if is_long and high >= target_price:
                exit_index, exit_price, exit_reason = future_index, target_price, "take profit"
                break
            if not is_long and low <= target_price:
                exit_index, exit_price, exit_reason = future_index, target_price, "take profit"
                break
            exit_index, exit_price = future_index, float(bar["close"])

        trade_return = ((exit_price - entry_price) / entry_price) * (1 if is_long else -1)
        equity *= 1 + trade_return
        trades.append(
            {
                "entry_timestamp": str(frame.iloc[entry_index]["timestamp"]),
                "exit_timestamp": str(frame.iloc[exit_index]["timestamp"]),
                "signal": side,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "return_pct": trade_return * 100,
                "exit_reason": exit_reason,
            }
        )
        equity_curve.append({"timestamp": str(frame.iloc[exit_index]["timestamp"]), "equity": equity})
        index = max(exit_index + 1, entry_index + 1)

    return _summary(asset["symbol"], strategy_name, trades, initial_capital, equity_curve)


def _summary(symbol, strategy_name, trades, initial_capital, equity_curve=None):
    returns = [trade["return_pct"] / 100 for trade in trades]
    final_equity = (equity_curve[-1]["equity"] if equity_curve else initial_capital)
    values = [point["equity"] for point in (equity_curve or [{"equity": initial_capital}])]
    peak = initial_capital
    drawdowns = []
    for value in values:
        peak = max(peak, value)
        drawdowns.append((peak - value) / peak if peak else 0)
    deviation = statistics.stdev(returns) if len(returns) > 1 else 0
    sharpe = (statistics.mean(returns) / deviation * math.sqrt(252)) if deviation else 0
    return {
        "symbol": symbol,
        "strategy": strategy_name,
        "total_trades": len(trades),
        "win_rate": (sum(value > 0 for value in returns) / len(returns) * 100) if returns else 0,
        "avg_return": (statistics.mean(returns) * 100) if returns else 0,
        "max_drawdown": max(drawdowns, default=0) * 100,
        "sharpe": sharpe,
        "initial_capital": initial_capital,
        "final_equity": final_equity,
        "trades": trades,
        "equity_curve": equity_curve or [{"timestamp": "", "equity": initial_capital}],
    }


def print_summary(result):
    print(
        "Metric          Value\n"
        f"Trades          {result['total_trades']}\n"
        f"Win rate        {result['win_rate']:.2f}%\n"
        f"Average return  {result['avg_return']:.2f}%\n"
        f"Max drawdown    {result['max_drawdown']:.2f}%\n"
        f"Sharpe          {result['sharpe']:.2f}"
    )


if __name__ == "__main__":
    with db.get_conn() as conn:
        first = conn.execute("SELECT id FROM assets WHERE active = 1 ORDER BY id LIMIT 1").fetchone()
    if first:
        result = run_backtest(first["id"], config.ENABLED_STRATEGIES[0])
        print_summary(result)
    else:
        print("No active assets to backtest.")