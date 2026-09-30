# Trader

Trader is a Flask and SQLite market-analysis dashboard for Nigerian equities and Binance crypto pairs. Version 0.3.0 adds portfolio management, multi-strategy analysis, backtesting, news sentiment, market overview, and progressive web app support.

## Quickstart

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set optional NGN Market and Telegram credentials in `.env`, then initialize and run:

```powershell
python init_db.py
python scheduler.py
python app.py
```

Open <http://localhost:5001>. The scheduler runs one cycle per invocation; use Windows Task Scheduler for recurring updates.

## Feature Matrix

| Feature | Page or route | Description |
| --- | --- | --- |
| Market overview | `/overview` | NGX breadth/ASI proxy, tracked crypto movers, and Fear & Greed |
| Signals | `/` and `/signals` | EMA, RSI, MACD, and Bollinger strategies with confidence scores |
| Interactive charts | `/asset/<id>` | Close price, EMA overlays, RSI thresholds, volume, and news |
| Portfolio | `/portfolio` | Open/closed positions, long/short P&L, risk sizing, filters, and CSV |
| Watchlist | `/watchlist` | Add, activate, deactivate, or delete tracked assets |
| Backtesting | `/backtest` | Strategy simulation with stop/target exits, equity curve, and metrics |
| Analytics | `/analytics` | Per-strategy signal win rate and price-move summary |
| Diagnostics | `/diagnostics` | Credential state, database counts, recent rows, and fetch output |
| PWA | `/manifest.json`, `/sw.js` | Install prompt, app shortcuts, shell cache, and offline fallback |
| Notifications | `/api/alerts/new` | Optional browser alerts and 60-second visible-tab signal refresh |

## Overview

`/overview` is the market summary page for tracked NGX breadth, a simple ASI proxy, tracked Binance movers, and the optional Fear & Greed index. The signals dashboard remains available at `/`.

## Charts

Asset detail pages provide price and EMA overlays, RSI threshold lines, and volume. Historical chart data is served by `/api/asset/<id>/series`.

## Portfolio

Track long and short positions, mark open P&L using the latest close, close/delete positions, and estimate quantity from account risk and stop distance. Filtered portfolio rows can be exported to CSV.

## Watchlist

Add assets at `/watchlist`; new symbols trigger a one-symbol fetch. Toggle assets inactive without deleting their history, or delete an asset and its related records.

## Backtest

Choose an asset, strategy, and date window at `/backtest`. Entries use the next candle open; stop loss is checked before take profit if both touch in one candle. Results exclude fees, slippage, and execution constraints.

## News

Asset pages show cached RSS stories matched to the ticker with a simple positive/negative/neutral word-count tag. The scheduler refreshes feeds for active assets.

## Analytics

`/analytics` measures strategy signal direction against subsequent highs/lows. Signals without later price bars are excluded from the win-rate denominator; this is not a realized-trade return report.

## PWA Install

On supported browsers the install button appears in the top bar after the browser signals that installation is available. The manifest includes direct shortcuts to Signals, Portfolio, and Watchlist.

## Service Worker

The worker caches the app shell and static assets, uses the network first for API requests and the dashboard, and returns a small offline page when a navigation cannot reach the server.

## Rate Limits

Requests use per-host pacing; NGN Market API calls are separated by at least 15 seconds. Successful HTTP responses are cached in SQLite to reduce repeated calls. Provider limits and terms may change.

## Logging

Application logs go to the console and `logs/trader.log`. The rotating log file is capped at 5 MB with three backups.

## No Data and Diagnostics

Open <http://localhost:5001/diagnostics> to check API status, environment settings, database counts, and recent rows. Click **Run Diagnostics** for a one-symbol fetch from each source.

No data usually means `NGN_API_KEY` is missing or invalid, an API response contains no usable price rows, or the crawler has not run. To fix it:

1. Copy `.env.example` to `.env` (`cp .env.example .env` in a POSIX shell, or `Copy-Item .env.example .env` in PowerShell) and set `NGN_API_KEY` from the NGN Market free tier at <https://ngnmarket.com>.
2. Run `python init_db.py`.
3. Run `python scheduler.py` and inspect the `[NGX]`, `[Crypto]`, and `[Analyzer]` logs.
4. Run `python app.py` and open <http://localhost:5001>.

NGX uses the NGN Market chart API and falls back to scraping the latest price from `afx.kwayisi.org` when the API fails or returns no rows. **POST `/crawl-now`** fetches watchlist prices without analyzing them.

## Theme and Install

Use the moon/sun toggle at the top-right of the navigation bar to switch between dark and light themes; the browser remembers the choice. Both themes use Nigerian/emerald green, with `#00a86b` as the primary dark-theme accent. On supported browsers, the install button appears in the top bar when the app can be installed. The service worker caches the app shell and provides a basic offline page; market APIs still require a network connection.

## Routes and APIs

- Pages: `/overview`, `/`, `/assets`, `/asset/<id>`, `/signals`, `/portfolio`, `/watchlist`, `/backtest`, `/analytics`, `/diagnostics`.
- Operations: `POST /refresh`, `POST /crawl-now`, `POST /portfolio/add`, `POST /portfolio/close/<id>`, `POST /portfolio/delete/<id>`, and watchlist add/toggle/delete routes.
- APIs: `/api/overview`, `/api/asset/<id>/series`, `/api/asset/<id>/news`, `/api/signals/latest`, `/api/alerts/new`, `/api/signals.csv`, `/api/portfolio.csv`, `/api/backtest`, and `/api/analytics`.

## Free-Tier Limits

- NGN Market: plan-dependent; the free tier is documented as 3,000 requests per month. Calls are spaced by at least 15 seconds and successful responses are cached.
- Binance market data: public endpoints do not require an API key; Binance request-weight limits still apply.
- Telegram Bot API: no API fee for ordinary bot messaging; Telegram usage limits apply.
- News RSS: public feeds are free to read; publisher terms and availability apply.

Limits can change; check each provider's current terms before relying on these estimates.

## Logging and Data

Logs are written to `logs/trader.log` with rotation at 5 MB and three backups. SQLite stores market data, positions, news, and API response cache in `trader.db`; runtime files are excluded from Git. Signals and analytics are informational, not investment advice. Backtest results do not model fees, slippage, or order execution.

## Screenshots

- Market overview: screenshot placeholder
- Portfolio: screenshot placeholder
- Asset charts: screenshot placeholder