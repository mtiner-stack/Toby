import os
from dotenv import load_dotenv

load_dotenv()

# Alpaca
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# Polygon
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Trading params
SYMBOLS = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA"]
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", 500))
MAX_POSITION_SIZE = float(os.getenv("MAX_POSITION_SIZE", 1000))
MAX_OPEN_TRADES = int(os.getenv("MAX_OPEN_TRADES", 3))
TRADE_LOOP_INTERVAL = int(os.getenv("TRADE_LOOP_INTERVAL", 30))  # seconds

# Risk
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", 0.30))       # 30% stop
TAKE_PROFIT_PCT = float(os.getenv("TAKE_PROFIT_PCT", 0.50))   # 50% target
TRAILING_STOP_PCT = float(os.getenv("TRAILING_STOP_PCT", 0.15))

# Dashboard
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", 5000))
