from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import threading

@dataclass
class Trade:
    symbol: str
    contract: str
    side: str
    qty: int
    entry_price: float
    current_price: float = 0.0
    stop_price: float = 0.0
    take_profit: float = 0.0
    peak_price: float = 0.0
    status: str = "open"
    pnl: float = 0.0
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None
    close_reason: str = ""

class BotState:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.paused = False
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.open_trades = {}
        self.closed_trades = []
        self.kill_switch = False
        self.last_ai_analysis = ""
        self.market_regime = "unknown"
        self.goal_hit = False
        self.conservative_mode = False

    def add_trade(self, trade):
        with self._lock:
            self.open_trades[trade.contract] = trade

    def close_trade(self, contract, reason, exit_price):
        with self._lock:
            t = self.open_trades.pop(contract, None)
            if t:
                t.status = "closed"
                t.close_reason = reason
                t.closed_at = datetime.now()
                t.pnl = (exit_price - t.entry_price) * t.qty * 100
                self.daily_pnl += t.pnl
                self.closed_trades.append(t)
                return t
        return None

    def to_dict(self):
        with self._lock:
            return {
                "running": self.running,
                "paused": self.paused,
                "kill_switch": self.kill_switch,
                "daily_pnl": round(self.daily_pnl, 2),
                "daily_trades": self.daily_trades,
                "open_trades": [
                    {"symbol": t.symbol, "contract": t.contract, "side": t.side,
                     "qty": t.qty, "entry": t.entry_price, "current": t.current_price,
                     "stop": t.stop_price, "tp": t.take_profit, "pnl": round(t.pnl, 2)}
                    for t in self.open_trades.values()
                ],
                "recent_closed": [
                    {"symbol": t.symbol, "contract": t.contract,
                     "pnl": round(t.pnl, 2), "reason": t.close_reason}
                    for t in self.closed_trades[-10:]
                ],
                "market_regime": self.market_regime,
                "last_ai_analysis": self.last_ai_analysis,
            }

state = BotState()
