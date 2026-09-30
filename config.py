import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

NGN_API_KEY = os.getenv("NGN_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
NGX_SCRAPE_FALLBACK = True
REQUEST_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (trader-bot/0.1)"

_ngx_raw = os.getenv("NGX_WATCHLIST", "DANGCEM,MTNN,AIRTELAFRI,GTCO,ZENITHBANK")
NGX_WATCHLIST = [symbol.strip() for symbol in _ngx_raw.split(",") if symbol.strip()]

_crypto_raw = os.getenv("CRYPTO_WATCHLIST", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
CRYPTO_WATCHLIST = [symbol.strip() for symbol in _crypto_raw.split(",") if symbol.strip()]

DB_PATH = Path(__file__).parent / "trader.db"

SIGNAL_RULES = {
    "stock": {"stop_loss_pct": 3.0, "take_profit_pct": 6.0, "min_volume": 100000},
    "crypto": {"stop_loss_pct": 2.0, "take_profit_pct": 5.0, "min_volume": 0},
}