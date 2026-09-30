import requests

import config
import db
from logger import get_logger
from rate_limit import wrap_request

logger = get_logger(__name__)


def format_signal(asset_symbol, exchange, currency, signal_row):
    currency_symbol = "₦" if currency == "NGN" else "$"
    icon = "🟢 BUY" if signal_row["signal"].lower() == "buy" else "🔴 SELL"
    return (
        f"{icon} — {asset_symbol} ({exchange})\n"
        f"Entry: {currency_symbol}{signal_row['entry_price']:.2f} | "
        f"SL: {currency_symbol}{signal_row['stop_loss']:.2f} | "
        f"TP: {currency_symbol}{signal_row['take_profit']:.2f}\n"
        f"Reason: {signal_row['reason']}"
    )


def send_telegram(text):
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.warning("Telegram tokens missing, skipping push")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        wrap_request(url)
        response = requests.post(
            url,
            json={"chat_id": config.TELEGRAM_CHAT_ID, "text": text},
            timeout=10,
        )
        return response.status_code == 200
    except requests.RequestException as error:
        logger.exception("Telegram error: %s", error)
        return False


def send_pending_alerts():
    with db.get_conn() as conn:
        cur = conn.cursor()
        pending = cur.execute(
            """
            SELECT s.id, s.signal, s.entry_price, s.stop_loss, s.take_profit, s.reason,
                   a.symbol, a.exchange, a.currency
            FROM signals s
            JOIN assets a ON s.asset_id = a.id
            WHERE s.notified = 0
            """
        ).fetchall()

        for row in pending:
            message = format_signal(row["symbol"], row["exchange"], row["currency"], row)
            if send_telegram(message):
                cur.execute("UPDATE signals SET notified = 1 WHERE id = ?", (row["id"],))


def main():
    send_pending_alerts()


if __name__ == "__main__":
    main()