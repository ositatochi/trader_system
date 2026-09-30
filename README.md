# Trader - Unified NGX + Crypto Analysis System

A Python, Flask, and SQLite decision-support system for Nigerian stocks (NGX) and Binance crypto pairs. It calculates technical indicators, generates BUY/SELL signals, and can send Telegram alerts.

## Features

- Unified tracking for NGX stocks and crypto assets.
- EMA crossover, RSI, and MACD analysis.
- Flask dashboard for assets, indicators, and signal history.
- Telegram signal notifications.

## Requirements

- Python 3.10 or newer
- A network connection for NGX and Binance market data
- Optional NGN Market API and Telegram credentials

## Quickstart

In PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your API key and Telegram values, then initialize the local database and start the dashboard:

```powershell
python init_db.py
python app.py
```

Open <http://localhost:5001>. Use the dashboard's **Refresh** button or run `python scheduler.py` to fetch prices, analyze assets, and send pending alerts. The scheduler script runs once per invocation; schedule it with Windows Task Scheduler for recurring updates.

## Configuration

`NGX_WATCHLIST` and `CRYPTO_WATCHLIST` are comma-separated symbol lists. Signal thresholds are defined in `config.py`. Telegram notifications are skipped until both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured.

## Notes

Signals are generated from historical daily candles and are informational, not financial advice. API availability, symbol support, and applicable market-data terms may vary. The SQLite database is created as `trader.db` in the project directory and is excluded from Git.