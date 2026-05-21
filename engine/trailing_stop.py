"""
Trailing Stop - Tiered dynamic stops.
Hard stop: -5% from entry (cannot be overridden)
Trailing only activates after +1% gain:
  Tier 1 (1-12% gain): trail 3% behind peak
  Tier 2 (12-20% gain): trail 5% behind peak
  Tier 3 (20%+ gain): trail 5% behind peak
"""
from utils.logger import get_logger

log = get_logger("trailing_stop")

class TrailingStopManager:
    def update(self, trade, current_price):
        if current_price <= 0:
            return False, ""

        trade.current_price = current_price
        trade.pnl = (current_price - trade.entry_price) * trade.qty * 100

        entry = trade.entry_price
        if entry <= 0:
            return False, ""

        # Update peak price
        if current_price > trade.peak_price:
            trade.peak_price = current_price

        loss_pct = (entry - current_price) / entry
        peak_gain_pct = (trade.peak_price - entry) / entry
        current_gain_pct = (current_price - entry) / entry

        # HARD STOP: -5% from entry — always checked first, cannot be overridden
        if loss_pct >= 0.05:
            log.info("Hard stop -5% on " + trade.contract + " | current=" + str(round(current_price, 2)) + " entry=" + str(round(entry, 2)))
            return True, "hard_stop_5pct"

        # TRAILING STOPS — only activate after position reaches +1% gain
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
                log.info("Trailing stop " + tier + " | peak=" + str(round(peak_gain_pct*100,1)) + "% current=" + str(round(current_gain_pct*100,1)) + "%")
                return True, "trailing_" + tier

        return False, ""

trailing_stop_manager = TrailingStopManager()
