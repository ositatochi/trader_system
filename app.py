from pathlib import Path
import os
import secrets

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, url_for

import adapters.crypto
import adapters.ngx
import config
import db
import diagnostics
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