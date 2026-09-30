import adapters.crypto
import adapters.ngx
import alerter
import analyzer
import config


def run_daily():
    print("crawling NGX...")
    adapters.ngx.fetch_prices(config.NGX_WATCHLIST)
    print("crawling crypto...")
    adapters.crypto.fetch_prices(config.CRYPTO_WATCHLIST)
    print("analyzing...")
    analyzer.analyze_all()
    print("sending alerts...")
    alerter.send_pending_alerts()
    print("done")


def main():
    run_daily()


if __name__ == "__main__":
    main()