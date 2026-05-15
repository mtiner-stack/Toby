from utils.logger import get_logger
from utils.state import state
from datetime import datetime
import pytz
import config

log = get_logger("risk")
ET = pytz.timezone("America/New_York")

class RiskEngine:
    def check_trade_allowed(self, symbol, cost, signal):
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

    def check_market_conditions(self, vix):
        now_et = datetime.now(ET)
        hour = now_et.hour
        minute = now_et.minute
        log.info(f"Market time check: {now_et.strftime('%H:%M ET')} | VIX: {vix:.1f}")
        if hour < 9 or (hour == 9 and minute < 30):
            return False, f"Market not open yet ({now_et.strftime('%H:%M ET')})"
        if (hour == 15 and minute >= 45) or hour >= 16:
            return False, f"Too close to market close ({now_et.strftime('%H:%M ET')})"
        if vix > 35:
            return False, f"VIX too high ({vix:.1f})"
        return True, "OK"

risk_engine = RiskEngine()
