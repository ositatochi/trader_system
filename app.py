from pathlib import Path
import os
import secrets
from datetime import date

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

import adapters.crypto
import adapters.ngx
import analyzer
import backtest as backtest_service
import config
import db
import diagnostics
import news
import scheduler

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
BASE_DIR = Path(__file__).parent


@app.route("/")
def index():
    with db.get_conn() as conn:
        stock_signals = conn.execute(
            """
            SELECT s.*, a.symbol, a.exchange, a.currency, a.asset_type
            FROM signals s JOIN assets a ON s.asset_id = a.id
            WHERE a.asset_type = 'stock' ORDER BY s.id DESC LIMIT 10
            """
        ).fetchall()
        crypto_signals = conn.execute(
            """
            SELECT s.*, a.symbol, a.exchange, a.currency, a.asset_type
            FROM signals s JOIN assets a ON s.asset_id = a.id
            WHERE a.asset_type = 'crypto' ORDER BY s.id DESC LIMIT 10
            """
        ).fetchall()
    return render_template(
        "index.html", stock_signals=stock_signals, crypto_signals=crypto_signals
    )


@app.route("/assets")
def assets():
    with db.get_conn() as conn:
        rows = conn.execute(
            """
            SELECT a.*,
                   (SELECT close FROM prices WHERE asset_id = a.id
                    ORDER BY timestamp DESC LIMIT 1) AS last_close
            FROM assets a WHERE a.active = 1 ORDER BY a.asset_type, a.symbol
            """
        ).fetchall()
    stocks = [row for row in rows if row["asset_type"] == "stock"]
    cryptos = [row for row in rows if row["asset_type"] == "crypto"]
    return render_template("assets.html", stocks=stocks, cryptos=cryptos)


@app.route("/watchlist")
def watchlist():
    with db.get_conn() as conn:
        assets = conn.execute(
            """
            SELECT a.*,
                   (SELECT close FROM prices WHERE asset_id = a.id
                    ORDER BY timestamp DESC LIMIT 1) AS last_close
            FROM assets a ORDER BY a.asset_type, a.symbol
            """
        ).fetchall()
    return render_template("watchlist.html", assets=assets)


@app.route("/watchlist/add", methods=["POST"])
def watchlist_add():
    symbol = request.form.get("symbol", "").strip().upper()
    asset_type = request.form.get("asset_type", "")
    exchange = request.form.get("exchange", "").strip().upper()
    currency = request.form.get("currency", "").strip().upper()
    if not symbol or len(symbol) > 32 or asset_type not in ("stock", "crypto") or not exchange or not currency:
        flash("Provide a symbol, stock/crypto type, exchange, and currency.", "error")
        return redirect(url_for("watchlist"))

    try:
        with db.get_conn() as conn:
            conn.execute(
                "INSERT INTO assets (symbol, name, asset_type, exchange, currency, active) VALUES (?, ?, ?, ?, ?, 1)",
                (symbol, symbol, asset_type, exchange, currency),
            )
    except Exception as error:
        flash(f"Could not add {symbol}: {error}", "error")
        return redirect(url_for("watchlist"))

    try:
        if asset_type == "crypto":
            result = adapters.crypto.fetch_prices(symbol)
        else:
            result = adapters.ngx.fetch_prices(symbol)
        flash(f"Added {symbol}; fetched {result['rows']} price rows.", "success")
    except Exception as error:
        flash(f"Added {symbol}, but its initial fetch failed: {error}", "error")
    return redirect(url_for("watchlist"))


@app.route("/watchlist/toggle/<int:asset_id>", methods=["POST"])
def watchlist_toggle(asset_id):
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE assets SET active = CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?",
            (asset_id,),
        )
    flash("Watchlist status updated.", "success")
    return redirect(url_for("watchlist"))


@app.route("/watchlist/delete/<int:asset_id>", methods=["POST"])
def watchlist_delete(asset_id):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    flash("Asset deleted.", "success")
    return redirect(url_for("watchlist"))


@app.route("/backtest", methods=["GET"])
def backtest_page():
    with db.get_conn() as conn:
        assets = conn.execute("SELECT id, symbol, asset_type FROM assets ORDER BY symbol").fetchall()
    result = None
    asset_id = request.args.get("asset_id", type=int)
    strategy_name = request.args.get("strategy", config.ENABLED_STRATEGIES[0])
    if asset_id:
        try:
            result = backtest_service.run_backtest(
                asset_id, strategy_name, request.args.get("start_date"), request.args.get("end_date")
            )
        except ValueError as error:
            flash(str(error), "error")
    return render_template(
        "backtest.html", assets=assets, strategies=analyzer.STRATEGIES,
        selected_asset=asset_id, selected_strategy=strategy_name, result=result,
    )


@app.route("/backtest/run", methods=["POST"])
def backtest_run():
    return redirect(url_for(
        "backtest_page",
        asset_id=request.form.get("asset_id", type=int),
        strategy=request.form.get("strategy"),
        start_date=request.form.get("start_date") or None,
        end_date=request.form.get("end_date") or None,
    ))


@app.route("/api/backtest")
def backtest_api():
    asset_id = request.args.get("asset_id", type=int)
    strategy_name = request.args.get("strategy", "")
    if not asset_id:
        return jsonify({"error": "asset_id is required"}), 400
    try:
        result = backtest_service.run_backtest(
            asset_id, strategy_name, request.args.get("start_date"), request.args.get("end_date")
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result)


@app.route("/asset/<int:asset_id>")
def asset_detail(asset_id):
    with db.get_conn() as conn:
        asset = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if asset is None:
            abort(404)
        prices = conn.execute(
            "SELECT * FROM prices WHERE asset_id = ? ORDER BY timestamp DESC LIMIT 30",
            (asset_id,),
        ).fetchall()
        indicators = conn.execute(
            "SELECT * FROM indicators WHERE asset_id = ? ORDER BY timestamp DESC LIMIT 1",
            (asset_id,),
        ).fetchone()
        signals = conn.execute(
            "SELECT * FROM signals WHERE asset_id = ? ORDER BY id DESC LIMIT 20",
            (asset_id,),
        ).fetchall()
    return render_template(
        "asset.html", asset=asset, prices=prices, indicators=indicators, signals=signals
    )


@app.route("/api/asset/<int:asset_id>/series")
def asset_series(asset_id):
    with db.get_conn() as conn:
        asset = conn.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if asset is None:
            abort(404)
        rows = conn.execute(
            """
            SELECT p.timestamp, p.close, p.volume,
                   i.ema_20, i.ema_50, i.rsi_14
            FROM prices p
            LEFT JOIN indicators i
              ON i.asset_id = p.asset_id AND i.timestamp = p.timestamp
            WHERE p.asset_id = ?
            ORDER BY p.timestamp ASC
            """,
            (asset_id,),
        ).fetchall()
    return jsonify(
        {
            "timestamps": [row["timestamp"] for row in rows],
            "close": [row["close"] for row in rows],
            "ema20": [row["ema_20"] for row in rows],
            "ema50": [row["ema_50"] for row in rows],
            "rsi14": [row["rsi_14"] for row in rows],
            "volume": [row["volume"] for row in rows],
        }
    )


@app.route("/api/asset/<int:asset_id>/news")
def asset_news(asset_id):
    with db.get_conn() as conn:
        asset = conn.execute("SELECT id FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if asset is None:
            abort(404)
        items = conn.execute(
            "SELECT title, link, published, sentiment FROM news_cache WHERE asset_id = ? ORDER BY fetched_at DESC, id DESC LIMIT 10",
            (asset_id,),
        ).fetchall()
    return jsonify([dict(item) for item in items])


@app.route("/signals")
def signals():
    with db.get_conn() as conn:
        all_signals = conn.execute(
            """
            SELECT s.*, a.symbol, a.exchange, a.currency, a.asset_type
            FROM signals s JOIN assets a ON s.asset_id = a.id
            ORDER BY s.id DESC LIMIT 100
            """
        ).fetchall()
    return render_template("signals.html", signals=all_signals)


@app.route("/portfolio", methods=["GET"])
def portfolio():
    with db.get_conn() as conn:
        assets = conn.execute(
            "SELECT id, symbol, asset_type, currency FROM assets WHERE active = 1 ORDER BY symbol"
        ).fetchall()
        positions = conn.execute(
            """
            SELECT p.*, a.symbol, a.asset_type, a.currency,
                   (SELECT close FROM prices WHERE asset_id = p.asset_id
                    ORDER BY timestamp DESC LIMIT 1) AS last_close
            FROM positions p JOIN assets a ON a.id = p.asset_id
            ORDER BY p.id DESC
            """
        ).fetchall()

    open_positions = []
    closed_positions = []
    open_value = unrealized_pnl = realized_pnl = winners = 0.0
    closed_count = 0
    for position in positions:
        item = dict(position)
        if item["status"] == "open":
            mark = item["last_close"] if item["last_close"] is not None else item["entry_price"]
            direction = 1 if item["side"] == "long" else -1
            item["pnl"] = (mark - item["entry_price"]) * item["quantity"] * direction
            item["mark_price"] = mark
            open_value += abs(mark * item["quantity"])
            unrealized_pnl += item["pnl"]
            open_positions.append(item)
        else:
            direction = 1 if item["side"] == "long" else -1
            item["pnl"] = (item["exit_price"] - item["entry_price"]) * item["quantity"] * direction
            realized_pnl += item["pnl"]
            winners += item["pnl"] > 0
            closed_count += 1
            closed_positions.append(item)

    summary = {
        "open_value": open_value,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "win_rate": (winners / closed_count * 100) if closed_count else 0,
    }
    return render_template(
        "portfolio.html",
        assets=assets,
        open_positions=open_positions,
        closed_positions=closed_positions,
        summary=summary,
        today=date.today().isoformat(),
    )


@app.route("/portfolio/add", methods=["POST"])
def portfolio_add():
    try:
        asset_id = int(request.form["asset_id"])
        side = request.form["side"]
        entry_price = float(request.form["entry_price"])
        quantity = float(request.form["quantity"])
        entry_date = date.fromisoformat(request.form["entry_date"]).isoformat()
        if side not in ("long", "short") or entry_price <= 0 or quantity <= 0:
            raise ValueError("Choose a side and enter positive price and quantity values.")
        with db.get_conn() as conn:
            asset = conn.execute("SELECT id FROM assets WHERE id = ? AND active = 1", (asset_id,)).fetchone()
            if asset is None:
                raise ValueError("Select an active asset.")
            conn.execute(
                "INSERT INTO positions (asset_id, side, entry_price, quantity, entry_date, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (asset_id, side, entry_price, quantity, entry_date, request.form.get("notes", "").strip()),
            )
        flash("Position added.", "success")
    except (KeyError, TypeError, ValueError) as error:
        flash(f"Could not add position: {error}", "error")
    return redirect(url_for("portfolio"))


@app.route("/portfolio/close/<int:pos_id>", methods=["POST"])
def portfolio_close(pos_id):
    try:
        exit_price = float(request.form["exit_price"])
        exit_date = date.fromisoformat(request.form["exit_date"]).isoformat()
        if exit_price <= 0:
            raise ValueError("Exit price must be positive.")
        with db.get_conn() as conn:
            cursor = conn.execute(
                "UPDATE positions SET exit_price = ?, exit_date = ?, status = 'closed' WHERE id = ? AND status = 'open'",
                (exit_price, exit_date, pos_id),
            )
            if not cursor.rowcount:
                raise ValueError("Open position not found.")
        flash("Position closed.", "success")
    except (KeyError, TypeError, ValueError) as error:
        flash(f"Could not close position: {error}", "error")
    return redirect(url_for("portfolio"))


@app.route("/portfolio/delete/<int:pos_id>", methods=["POST"])
def portfolio_delete(pos_id):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM positions WHERE id = ?", (pos_id,))
    flash("Position deleted.", "success")
    return redirect(url_for("portfolio"))


@app.route("/diagnostics", methods=["GET", "POST"])
def diagnostics_page():
    output = diagnostics.run_diagnostics() if request.method == "POST" else None
    snapshot = output or diagnostics.database_snapshot()
    env = {
        "NGN_API_KEY": bool(config.NGN_API_KEY),
        "TELEGRAM_BOT_TOKEN": bool(config.TELEGRAM_BOT_TOKEN),
        "TELEGRAM_CHAT_ID": bool(config.TELEGRAM_CHAT_ID),
    }
    return render_template(
        "diagnostics.html",
        env=env,
        counts=snapshot["counts"],
        latest=snapshot["latest"],
        output=output,
    )


@app.route("/crawl-now", methods=["POST"])
def crawl_now():
    totals = {"NGX": 0, "Crypto": 0}
    for label, fetch in (
        ("NGX", lambda: adapters.ngx.fetch_prices(config.NGX_WATCHLIST)),
        ("Crypto", lambda: adapters.crypto.fetch_prices(config.CRYPTO_WATCHLIST)),
    ):
        try:
            result = fetch()
            totals[label] = result["rows"]
        except Exception as error:
            flash(f"{label} crawl failed: {error}", "error")
    flash(
        f"Crawl complete: {totals['NGX']} NGX and {totals['Crypto']} crypto rows inserted.",
        "success",
    )
    return redirect(url_for("diagnostics_page"))


@app.route("/manifest.json")
def manifest():
    return send_from_directory(BASE_DIR / "static", "manifest.json")


@app.route("/refresh", methods=["POST"])
def refresh():
    scheduler.run_daily()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)