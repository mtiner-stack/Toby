"""
Risk Engine — always runs BEFORE any trade is placed.
Hard rules that override everything, including the AI.
"""
from utils.logger import get_logger
from utils.state import state
import config

log = get_logger("risk")

class RiskEngine:
    def check_trade_allowed(self, symbol: str, cost: float, signal: dict) -> tuple[bool, str]:
        """Returns (allowed, reason). Must pass ALL checks to trade."""

        if state.kill_switch:
            return False, "KILL SWITCH ACTIVE"

        if state.paused:
            return False, "Bot is paused"

        if state.daily_pnl <= -config.MAX_DAILY_LOSS:
            return False, f"Daily loss limit hit (${state.daily_pnl:.2f})"

        if len(state.open_trades) >= config.MAX_OPEN_TRADES:
            return False, f"Max open trades reached ({config.MAX_OPEN_TRADES})"

        if cost > config.MAX_POSITION_SIZE:
            return False, f"Position size ${cost:.2f} exceeds max ${config.MAX_POSITION_SIZE}"

        if symbol in [t.symbol for t in state.open_trades.values()]:
            return False, f"Already have open position in {symbol}"

        confidence = signal.get("confidence", 0)
        if confidence < 0.65:
            return False, f"AI confidence too low ({confidence:.0%})"

        log.info(f"Risk check PASSED for {symbol} | cost=${cost:.2f} | confidence={confidence:.0%}")
        return True, "OK"

    def check_market_conditions(self, vix: float, time_str: str) -> tuple[bool, str]:
        """Gate on macro conditions."""
        hour, minute = map(int, time_str.split(":"))

        # No trading first 15 min or last 30 min of session
        if (hour == 9 and minute < 45):
            return False, "Too early — market open volatility window"
        if (hour == 15 and minute >= 30) or hour >= 16:
            return False, "Too close to market close"

        if vix > 35:
            return False, f"VIX too high ({vix:.1f}) — extreme volatility, standing down"

        return True, "OK"

risk_engine = RiskEngine()
