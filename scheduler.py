import adapters.crypto
import adapters.ngx
import alerter
import analyzer
import config
import news


def run_daily():
    stages = (
        ("NGX", lambda: adapters.ngx.fetch_prices(config.NGX_WATCHLIST)),
        ("Crypto", lambda: adapters.crypto.fetch_prices(config.CRYPTO_WATCHLIST)),
        ("Analyzer", analyzer.analyze_all),
        ("Alerter", alerter.send_pending_alerts),
        ("News", news.refresh_news_for_assets),
    )
    for name, stage in stages:
        print(f"[{name}] Starting")
        try:
            result = stage()
            print(f"[{name}] Complete: {result}")
        except Exception as error:
            print(f"[{name}] ERROR: {error}")
    print("[Scheduler] Done")


def main():
    run_daily()


if __name__ == "__main__":
    main()