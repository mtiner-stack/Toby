"""
Trailing Stop - Tiered dynamic stops.
Hard stop: -5% from entry (always active from entry)
Trailing activates once position hits +1% gain:
  Tier 1 (1-12% peak gain): trail 3% behind peak
  Tier 2 (12-20% peak gain): trail 5% behind peak  
  Tier 3 (20%+ peak gain): trail 5% behind peak
"""
from utils.logger import get_logger

log = get_logger("trailing_stop")

class TrailingStopManager:
    def update(self, trade, current_price):
        if current_price <= 0 or trade.entry_price <= 0:
            return False, ""

        trade.current_price = current_price
        trade.pnl = (current_price - trade.entry_price) * trade.qty * 100

        # Only update peak if price is genuinely higher
        if current_price > trade.peak_price:
            trade.peak_price = current_price

        entry = trade.entry_price
        peak = trade.peak_price
        loss_pct = (entry - current_price) / entry
        peak_gain_pct = (peak - entry) / entry

        # HARD STOP: -5% from entry, always active
        if loss_pct >= 0.05:
            log.info("Hard stop -5% | entry=" + str(round(entry,2)) + " current=" + str(round(current_price,2)))
            return True, "hard_stop_5pct"

        # TRAILING: only after peak has reached at least +1% above entry
        if peak_gain_pct >= 0.01:
            if peak_gain_pct >= 0.12:
                trail_stop = peak * 0.95   # trail 5% behind peak
                tier = "tier2_12pct+"
            else:
                trail_stop = peak * 0.97   # trail 3% behind peak
                tier = "tier1_1-12pct"

            if current_price <= trail_stop:
                gain_at_close = round(((current_price - entry) / entry) * 100, 1)
                log.info("Trailing stop " + tier + " | peak_gain=" + str(round(peak_gain_pct*100,1)) + "% close_at=" + str(gain_at_close) + "%")
                return True, "trailing_" + tier

        return False, ""

trailing_stop_manager = TrailingStopManager()
