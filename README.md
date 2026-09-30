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

## Diagnostics and No Data

Open <http://localhost:5001/diagnostics> to view API credential status, database row counts, the latest rows, and detailed results from a one-symbol NGX and crypto fetch. Select **Run Diagnostics** to make those live requests and see HTTP status and response snippets.

No data usually means the NGN Market API key is missing or invalid, the API endpoint returned no usable price rows, or the crawler has not run yet. To initialize and fetch data:

1. Copy `.env.example` to `.env` (`cp .env.example .env` in a POSIX shell, or `Copy-Item .env.example .env` in PowerShell) and set `NGN_API_KEY` using the NGN Market free tier at <https://ngnmarket.com>.
2. Run `python init_db.py`.
3. Run `python scheduler.py` and inspect the `[NGX]`, `[Crypto]`, and `[Analyzer]` output.
4. Run `python app.py` and open <http://localhost:5001>.

When the NGN Market API fails or has no price rows, NGX fetching falls back to scraping the latest price from `afx.kwayisi.org`. The **POST `/crawl-now`** endpoint fetches all configured watchlist symbols without running analysis; the dashboard's Diagnostics page includes a crawl button and reports inserted-row counts.

## Theme

Use the moon/sun toggle at the top-left of the navigation bar to switch between dark and light themes. The selection is stored in the browser. The palette uses Nigerian/emerald green, with `#00a86b` as its dark-theme accent.

## Configuration

`NGX_WATCHLIST` and `CRYPTO_WATCHLIST` are comma-separated symbol lists. Signal thresholds are defined in `config.py`. Telegram notifications are skipped until both `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are configured.

## Notes

Signals are generated from historical daily candles and are informational, not financial advice. API availability, symbol support, and applicable market-data terms may vary. The SQLite database is created as `trader.db` in the project directory and is excluded from Git.