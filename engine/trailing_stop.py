"""
Simple stop management.
Hard stop: -5% from entry
Take profit: +20% from entry
No trailing until price feed is confirmed reliable.
"""
from utils.logger import get_logger

log = get_logger("trailing_stop")

class TrailingStopManager:
    def update(self, trade, current_price):
        if current_price <= 0 or trade.entry_price <= 0:
            return False, ""

        trade.current_price = current_price
        trade.pnl = (current_price - trade.entry_price) * trade.qty * 100

        if current_price > trade.peak_price:
            trade.peak_price = current_price

        loss_pct = (trade.entry_price - current_price) / trade.entry_price
        gain_pct = (current_price - trade.entry_price) / trade.entry_price

        if loss_pct >= 0.05:
            log.info("Hard stop -5% on " + trade.contract + " | entry=" + str(round(trade.entry_price,2)) + " current=" + str(round(current_price,2)))
            return True, "hard_stop_5pct"

        if gain_pct >= 0.20:
            log.info("Take profit +20% on " + trade.contract)
            return True, "take_profit_20pct"

        return False, ""

trailing_stop_manager = TrailingStopManager()
