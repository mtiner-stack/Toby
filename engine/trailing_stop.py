"""
Strangle Pair Manager - manages call+put as a combined position.
Stop: -8% combined. Take profit: +15% combined. Trail: 5% behind peak after +10%.
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
        return False, ""

trailing_stop_manager = TrailingStopManager()


class StranglePairManager:
    def __init__(self):
        self.pairs = {}

    def register_pair(self, symbol, call_contract, put_contract):
        self.pairs[symbol] = {"call": call_contract, "put": put_contract, "peak_combined_value": None}
        log.info("Registered strangle pair for " + symbol)

    def check_pair(self, symbol, trades):
        if symbol not in self.pairs:
            return False, ""
        pair = self.pairs[symbol]
        call_trade = trades.get(pair["call"]) or trades.get(pair["call"].replace("O:", ""))
        put_trade = trades.get(pair["put"]) or trades.get(pair["put"].replace("O:", ""))
        if not call_trade or not put_trade:
            return False, ""
        total_cost = (call_trade.entry_price * call_trade.qty * 100) + (put_trade.entry_price * put_trade.qty * 100)
        if total_cost <= 0:
            return False, ""
        combined_value = (call_trade.current_price * call_trade.qty * 100) + (put_trade.current_price * put_trade.qty * 100)
        combined_pnl_pct = (combined_value - total_cost) / total_cost
        if pair["peak_combined_value"] is None or combined_value > pair["peak_combined_value"]:
            pair["peak_combined_value"] = combined_value
        peak_value = pair["peak_combined_value"]
        peak_gain_pct = (peak_value - total_cost) / total_cost
        log.info(symbol + " strangle pnl=" + str(round(combined_pnl_pct*100,1)) + "% peak=" + str(round(peak_gain_pct*100,1)) + "%")
        if combined_pnl_pct <= -0.08:
            return True, "strangle_stop_8pct"
        if combined_pnl_pct >= 0.15:
            return True, "strangle_take_profit_15pct"
        if peak_gain_pct >= 0.10 and combined_value <= peak_value * 0.95:
            return True, "strangle_trailing_5pct"
        return False, ""

    def remove_pair(self, symbol):
        if symbol in self.pairs:
            del self.pairs[symbol]

strangle_pair_manager = StranglePairManager()
