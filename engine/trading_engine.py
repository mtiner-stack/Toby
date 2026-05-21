"""
Trading Engine - Mechanical scalping at 9:31am ET.
Buys 1 OTM call + 1 OTM put simultaneously at open.
Pure rules-based - no AI autonomy at execution time.
"""
import time
import threading
from datetime import datetime
import pytz
from utils.logger import get_logger
from utils.state import state
from engine.risk_engine import risk_engine
from engine.ai_brain import ai_brain
from engine.trailing_stop import trailing_stop_manager
from engine.order_manager import order_manager
from data.market_data import market_data
from data.options_scanner import options_scanner
from controls.telegram_bot import telegram
import config

log = get_logger("engine")
ET = pytz.timezone("America/New_York")
DAILY_GOAL = 10000

class TradingEngine:
    def __init__(self):
        self.entry_fired = False
        self.active_symbols = list(config.SYMBOLS)

    def run(self):
        state.running = True
        telegram.send("*Toby is online.* Mechanical scalping mode. Will enter at 9:31 ET.")
        threading.Thread(target=self._position_monitor_loop, daemon=True).start()
        try:
            while state.running:
                self._tick()
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _tick(self):
        if state.kill_switch or state.paused:
            time.sleep(1)
            return
        now_et = datetime.now(ET)
        hour, minute = now_et.hour, now_et.minute
        if hour == 0 and minute == 0:
            self.entry_fired = False
            state.goal_hit = False
            state.conservative_mode = False
        if hour < 9 or (hour == 9 and minute < 30):
            log.info("Market not open yet " + now_et.strftime("%H:%M ET"))
            time.sleep(15)
            return
        if (hour == 15 and minute >= 45) or hour >= 16:
            self._close_all_eod()
            time.sleep(60)
            return
        if state.goal_hit or state.kill_switch:
            time.sleep(2)
            return
        if state.daily_pnl <= -config.MAX_DAILY_LOSS:
            if not state.paused:
                state.paused = True
                telegram.send("Daily loss limit hit $" + str(round(state.daily_pnl, 2)) + ". Closing all and stopping.")
                order_manager.close_all()
            time.sleep(5)
            return
        if state.daily_pnl >= DAILY_GOAL:
            state.goal_hit = True
            telegram.send("*Daily goal hit!* $" + str(round(state.daily_pnl, 2)) + "\nTrailing all winners. No new entries.")
            time.sleep(2)
            return
        if hour == 9 and minute >= 31 and not self.entry_fired:
            self._execute_open_entries()
        time.sleep(5)

    def _execute_open_entries(self):
        self.entry_fired = True
        log.info("Executing mechanical open entries...")
        telegram.send("*9:31 ET - Executing open entries*\nBuying OTM call + put for: " + ", ".join(self.active_symbols))
        for symbol in self.active_symbols:
            try:
                snap = market_data.get_snapshot(symbol)
                if not snap or not snap.get("price"):
                    log.error("No price data for " + symbol)
                    continue
                price = snap["price"]
                call_signal = {"action": "buy_call", "confidence": 1.0, "suggested_strike": "1_OTM", "suggested_expiry": "0DTE", "reasoning": "Mechanical open entry - OTM call"}
                call_contract = options_scanner.find_contract(symbol, call_signal, price)
                if call_contract:
                    call_signal["mid_price"] = call_contract["mid_price"]
                    call_trade = order_manager.buy_option(symbol, call_contract["ticker"], 1, call_signal)
                    if call_trade:
                        telegram.send("CALL entered: " + symbol + " $" + str(call_contract["strike"]) + " x1 @ $" + str(round(call_trade.entry_price, 2)) + "\nStop: -5% = $" + str(round(call_trade.stop_price, 2)))
                put_signal = {"action": "buy_put", "confidence": 1.0, "suggested_strike": "1_OTM", "suggested_expiry": "0DTE", "reasoning": "Mechanical open entry - OTM put"}
                put_contract = options_scanner.find_contract(symbol, put_signal, price)
                if put_contract:
                    put_signal["mid_price"] = put_contract["mid_price"]
                    put_trade = order_manager.buy_option(symbol, put_contract["ticker"], 1, put_signal)
                    if put_trade:
                        telegram.send("PUT entered: " + symbol + " $" + str(put_contract["strike"]) + " x1 @ $" + str(round(put_trade.entry_price, 2)) + "\nStop: -5% = $" + str(round(put_trade.stop_price, 2)))
            except Exception as e:
                log.error("Open entry error for " + symbol + ": " + str(e))
                telegram.send("Error entering " + symbol + ": " + str(e))

    def _position_monitor_loop(self):
        while state.running:
            try:
                self._manage_open_positions()
            except Exception as e:
                log.error("Monitor error: " + str(e))
            time.sleep(2)

    def _manage_open_positions(self):
        try:
            alpaca_positions = {p.symbol: p for p in order_manager.api.list_positions()}
        except Exception as e:
            log.error("Could not fetch Alpaca positions: " + str(e))
            return

        for contract, trade in list(state.open_trades.items()):
            try:
                alpaca_symbol = contract.replace("O:", "")
                pos = alpaca_positions.get(alpaca_symbol)
                if pos is None:
                    state.close_trade(contract, "already_closed", trade.entry_price)
                    continue
                current_price = float(pos.current_price or 0)
                if current_price <= 0:
                    continue
                should_close, reason = trailing_stop_manager.update(trade, current_price)
                if should_close:
                    exit_price = order_manager.close_position(contract, trade.qty)
                    closed = state.close_trade(contract, reason, exit_price or current_price)
                    if closed:
                        emoji = "✅" if closed.pnl > 0 else "❌"
                        pnl_pct = round(((current_price - trade.entry_price) / trade.entry_price) * 100, 1) if trade.entry_price > 0 else 0
                        pnl_dollar = round(float(pos.unrealized_pl or 0), 2)
                        telegram.send(emoji + " *Closed* " + alpaca_symbol + "\n" + reason + " | P&L: $" + str(pnl_dollar) + " (" + str(pnl_pct) + "%)\nDaily: $" + str(round(state.daily_pnl, 2)))
            except Exception as e:
                log.error("Monitor error " + contract + ": " + str(e))

    def set_symbols(self, symbols):
        self.active_symbols = symbols

    def _close_all_eod(self):
        if state.open_trades:
            order_manager.close_all()
            for contract in list(state.open_trades.keys()):
                state.close_trade(contract, "eod_close", 0)
            telegram.send("Market closed. All positions closed.\nDaily P&L: $" + str(round(state.daily_pnl, 2)))
        self.entry_fired = False
        state.goal_hit = False
        state.conservative_mode = False

    def _shutdown(self):
        order_manager.close_all()
        summary = ai_brain.summarize_session([{"symbol": t.symbol, "pnl": t.pnl, "reason": t.close_reason} for t in state.closed_trades], state.daily_pnl)
        telegram.send("Toby shutting down.\nDaily P&L: $" + str(round(state.daily_pnl, 2)) + "\n\n" + summary)
        state.running = False

engine = TradingEngine()
