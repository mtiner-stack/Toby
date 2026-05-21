"""
Trailing Stop - Tiered dynamic stops.
Hard stop: -5% from entry (cannot be overridden)
Tier 1 (1-12% gain): trail 3% behind peak
Tier 2 (12-20% gain): trail 5% behind peak
Tier 3 (20%+ gain): trail 5% behind peak
"""
from utils.state import Trade
from utils.logger import get_logger

log = get_logger("trailing_stop")

class TrailingStopManager:
    def update(self, trade, current_price):
        trade.current_price = current_price
        trade.pnl = (current_price - trade.entry_price) * trade.qty * 100
        entry = trade.entry_price
        if entry <= 0:
            return False, ""
        gain_pct = (current_price - entry) / entry
        loss_pct = (entry - current_price) / entry
        if current_price > trade.peak_price:
            trade.peak_price = current_price
        peak_gain_pct = (trade.peak_price - entry) / entry
        if loss_pct >= 0.05:
            log.info("Hard stop -5% on " + trade.contract)
            return True, "hard_stop_5pct"
        if peak_gain_pct >= 0.01:
            if peak_gain_pct >= 0.20:
                trail_stop = trade.peak_price * 0.95
                tier = "tier3_20pct+"
            elif peak_gain_pct >= 0.12:
                trail_stop = trade.peak_price * 0.95
                tier = "tier2_12-20pct"
            else:
                trail_stop = trade.peak_price * 0.97
                tier = "tier1_1-12pct"
            if current_price <= trail_stop:
                log.info("Trailing stop " + tier + " on " + trade.contract)
                return True, "trailing_" + tier
        return False, ""

trailing_stop_manager = TrailingStopManager()
