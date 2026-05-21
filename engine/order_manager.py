"""
Order Manager — all Alpaca order execution lives here.
"""
import alpaca_trade_api as tradeapi
from utils.logger import get_logger
from utils.state import Trade, state
import config

log = get_logger("orders")

class OrderManager:
    def __init__(self):
        self.api = tradeapi.REST(
            config.ALPACA_API_KEY,
            config.ALPACA_SECRET_KEY,
            config.ALPACA_BASE_URL
        )

    def get_buying_power(self) -> float:
        try:
            account = self.api.get_account()
            return float(account.buying_power)
        except Exception as e:
            log.error("Could not fetch buying power: " + str(e))
            return 100000.0

    def buy_option(self, symbol: str, contract: str, qty: int, signal: dict) :
        """Submit a market buy for an options contract."""
        try:
            alpaca_symbol = contract.replace("O:", "")
            order = self.api.submit_order(
                symbol=alpaca_symbol,
                qty=qty,
                side="buy",
                type="market",
                time_in_force="day"
            )
            # Wait for fill with retries
            import time as _time
            entry_price = 0
            for _ in range(10):
                filled_order = self.api.get_order(order.id)
                if filled_order.filled_avg_price and float(filled_order.filled_avg_price) > 0:
                    entry_price = float(filled_order.filled_avg_price)
                    break
                _time.sleep(0.5)
            if entry_price == 0:
                # Fallback: use mid price from signal if available
                entry_price = signal.get("mid_price", 1.0)
                log.warning("Could not get fill price, using fallback: " + str(entry_price))

            trade = Trade(
                symbol=symbol,
                contract=contract,
                side="buy",
                qty=qty,
                entry_price=entry_price,
                peak_price=entry_price,
                stop_price=entry_price * (1 - config.STOP_LOSS_PCT),
                take_profit=entry_price * (1 + config.TAKE_PROFIT_PCT),
            )
            state.add_trade(trade)
            state.daily_trades += 1
            log.info(f"BOUGHT {qty}x {contract} @ ${entry_price:.2f}")
            return trade
        except Exception as e:
            log.error(f"Order failed for {contract}: {e}")
            return None

    def close_position(self, contract: str, qty: int) -> float:
        """Market sell to close."""
        try:
            alpaca_symbol = contract.replace("O:", "")
            order = self.api.submit_order(
                symbol=alpaca_symbol,
                qty=qty,
                side="sell",
                type="market",
                time_in_force="day"
            )
            filled = self.api.get_order(order.id)
            exit_price = float(filled.filled_avg_price or 0)
            log.info(f"CLOSED {contract} @ ${exit_price:.2f}")
            return exit_price
        except Exception as e:
            log.error(f"Close failed for {contract}: {e}")
            return 0.0

    def close_all(self):
        """Emergency: close everything."""
        log.warning("CLOSING ALL POSITIONS")
        try:
            self.api.close_all_positions()
        except Exception as e:
            log.error(f"close_all failed: {e}")

order_manager = OrderManager()
