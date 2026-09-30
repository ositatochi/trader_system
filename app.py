from pathlib import Path

from flask import Flask, abort, redirect, render_template, send_from_directory, url_for

import db
import scheduler

app = Flask(__name__)
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


@app.route("/manifest.json")
def manifest():
    return send_from_directory(BASE_DIR / "static", "manifest.json")


@app.route("/refresh", methods=["POST"])
def refresh():
    scheduler.run_daily()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)