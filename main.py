"""
Toby — 0DTE Options Scalping Bot
Entry point: starts dashboard, telegram, and trading engine.
"""
import threading
from utils.logger import get_logger
from controls.telegram_bot import telegram
from dashboard.app import run_dashboard
from engine.trading_engine import engine

log = get_logger("main")

def main():
    log.info("=" * 50)
    log.info("  TOBY — Options Scalping Bot  ")
    log.info("=" * 50)

    # Start Telegram polling
    telegram.start_polling()

    # Start dashboard in background thread
    dash_thread = threading.Thread(target=run_dashboard, daemon=True)
    dash_thread.start()
    log.info("Dashboard running at http://localhost:5000")

    # Start trading engine (blocking main thread)
    engine.run()

if __name__ == "__main__":
    main()
