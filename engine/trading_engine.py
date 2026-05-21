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
                buying_power = order_manager.get_buying_power()
                per_contract_budget = (buying_power * 0.15) / 2
                call_signal = {"action": "buy_call", "confidence": 1.0, "suggested_strike": "1_OTM", "suggested_expiry": "0DTE", "reasoning": "Mechanical open entry - OTM call", "mid_price": call_contract["mid_price"] if call_contract else 1.0}
                call_contract = options_scanner.find_contract(symbol, call_signal, price)
                if call_contract:
                    call_qty = max(1, int(per_contract_budget / (call_contract["mid_price"] * 100)))
                    call_trade = order_manager.buy_option(symbol, call_contract["ticker"], call_qty, call_signal)
                    if call_trade:
                        telegram.send("CALL entered: " + symbol + " $" + str(call_contract["strike"]) + " x" + str(call_qty) + " @ $" + str(round(call_trade.entry_price, 2)) + "\nStop: -5% = $" + str(round(call_trade.stop_price, 2)))
                put_signal = {"action": "buy_put", "confidence": 1.0, "suggested_strike": "1_OTM", "suggested_expiry": "0DTE", "reasoning": "Mechanical open entry - OTM put", "mid_price": put_contract["mid_price"] if put_contract else 1.0}
                put_contract = options_scanner.find_contract(symbol, put_signal, price)
                if put_contract:
                    put_qty = max(1, int(per_contract_budget / (put_contract["mid_price"] * 100)))
                    put_trade = order_manager.buy_option(symbol, put_contract["ticker"], put_qty, put_signal)
                    if put_trade:
                        telegram.send("PUT entered: " + symbol + " $" + str(put_contract["strike"]) + " x" + str(put_qty) + " @ $" + str(round(put_trade.entry_price, 2)) + "\nStop: -5% = $" + str(round(put_trade.stop_price, 2)))
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
        for contract, trade in list(state.open_trades.items()):
            try:
                # Get the actual option contract price, not the underlying stock price
                current_price = self._get_option_price(contract, trade)
                should_close, reason = trailing_stop_manager.update(trade, current_price)
                if should_close:
                    exit_price = order_manager.close_position(contract, trade.qty)
                    closed = state.close_trade(contract, reason, exit_price)
                    if closed:
                        emoji = "✅" if closed.pnl > 0 else "❌"
                        pnl_pct = round(((closed.pnl / (closed.entry_price * closed.qty * 100)) * 100), 1) if closed.entry_price > 0 else 0
                        telegram.send(emoji + " *Closed* " + contract + "\n" + reason + " | P&L: $" + str(round(closed.pnl, 2)) + " (" + str(pnl_pct) + "%)\nDaily: $" + str(round(state.daily_pnl, 2)))
            except Exception as e:
                log.error("Monitor error " + contract + ": " + str(e))


    def _get_option_price(self, contract, trade):
        """Fetch current mid price of the option contract from Polygon."""
        try:
            import requests, config
            polygon_ticker = "O:" + contract if not contract.startswith("O:") else contract
            r = requests.get(
                "https://api.polygon.io/v3/quotes/" + polygon_ticker,
                params={"limit": 1, "apiKey": config.POLYGON_API_KEY},
                timeout=5
            )
            results = r.json().get("results", [])
            if results:
                q = results[-1]
                bid = q.get("bid_price", 0)
                ask = q.get("ask_price", 0)
                if bid and ask:
                    return (bid + ask) / 2
        except Exception as e:
            log.error("Option price fetch error for " + contract + ": " + str(e))
        return trade.current_price

    def set_symbols(self, symbols):
        self.active_symbols = symbols
        log.info("Active symbols set to: " + str(symbols))

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
