"""
Trailing stop manager — updates peak price and computes dynamic stops.
"""
from utils.state import Trade
import config

class TrailingStopManager:
    def update(self, trade: Trade, current_price: float) -> tuple[bool, str]:
        """
        Update trade with current price. Returns (should_close, reason).
        """
        trade.current_price = current_price
        trade.pnl = (current_price - trade.entry_price) * trade.qty * 100

        # Update peak
        if current_price > trade.peak_price:
            trade.peak_price = current_price

        # Hard stop loss
        if current_price <= trade.stop_price:
            return True, "stop_loss"

        # Take profit
        if current_price >= trade.take_profit:
            return True, "take_profit"

        # Trailing stop — only kicks in after 10% gain
        gain_pct = (trade.peak_price - trade.entry_price) / trade.entry_price
        if gain_pct >= 0.10:
            trail_stop = trade.peak_price * (1 - config.TRAILING_STOP_PCT)
            if current_price <= trail_stop:
                return True, "trailing_stop"

        return False, ""

trailing_stop_manager = TrailingStopManager()
