"""
Trading Engine - Mechanical strangle scalping at 9:31am ET.
Buys 1 OTM call + 1 OTM put as a PAIR.
Exits on combined P&L: stop -8%, take profit +15%, trail 5% behind peak after +10%.
"""
import time
import threading
from datetime import datetime
import pytz
from utils.logger import get_logger
from utils.state import state
from engine.risk_engine import risk_engine
from engine.ai_brain import ai_brain
from engine.trailing_stop import trailing_stop_manager, strangle_pair_manager
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
        telegram.send("*Toby is online.* Strangle scalping mode. Enters call+put pair at 9:31 ET.")
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
                telegram.send("Daily loss limit hit $" + str(round(state.daily_pnl, 2)) + ". Closing all.")
                order_manager.close_all()
            time.sleep(5)
            return
        if state.daily_pnl >= DAILY_GOAL:
            state.goal_hit = True
            telegram.send("*Daily goal hit!* $" + str(round(state.daily_pnl, 2)) + "\nNo new entries.")
            time.sleep(2)
            return
        if hour == 9 and minute >= 31 and not self.entry_fired:
            self._execute_open_entries()
        time.sleep(5)

    def _execute_open_entries(self):
        self.entry_fired = True
        log.info("Executing strangle entries...")
        telegram.send("*9:31 ET - Entering strangles*\nSymbols: " + ", ".join(self.active_symbols))
        for symbol in self.active_symbols:
            try:
                snap = market_data.get_snapshot(symbol)
                if not snap or not snap.get("price"):
                    telegram.send("No price data for " + symbol + ", skipping.")
                    continue
                price = snap["price"]
                call_signal = {"action": "buy_call", "confidence": 1.0, "suggested_strike": "1_OTM", "suggested_expiry": "0DTE", "reasoning": "Strangle call leg"}
                call_contract = options_scanner.find_contract(symbol, call_signal, price)
                put_signal = {"action": "buy_put", "confidence": 1.0, "suggested_strike": "1_OTM", "suggested_expiry": "0DTE", "reasoning": "Strangle put leg"}
                put_contract = options_scanner.find_contract(symbol, put_signal, price)
                if not call_contract or not put_contract:
                    telegram.send("Could not find contracts for " + symbol + ", skipping.")
                    continue
                call_signal["mid_price"] = call_contract["mid_price"]
                put_signal["mid_price"] = put_contract["mid_price"]
                call_trade = order_manager.buy_option(symbol, call_contract["ticker"], 1, call_signal)
                put_trade = order_manager.buy_option(symbol, put_contract["ticker"], 1, put_signal)
                if call_trade and put_trade:
                    total_cost = (call_trade.entry_price + put_trade.entry_price) * 100
                    strangle_pair_manager.register_pair(symbol, call_contract["ticker"], put_contract["ticker"])
                    telegram.send(
                        "*" + symbol + " Strangle Entered*\n" +
                        "CALL: $" + str(call_contract["strike"]) + " @ $" + str(round(call_trade.entry_price, 2)) + "\n" +
                        "PUT:  $" + str(put_contract["strike"]) + " @ $" + str(round(put_trade.entry_price, 2)) + "\n" +
                        "Total cost: $" + str(round(total_cost, 2)) + "\n" +
                        "Stop: -8% combined | TP: +15% combined | Trail: 5% behind peak after +10%"
                    )
                else:
                    telegram.send("Failed to enter one or both legs for " + symbol)
            except Exception as e:
                log.error("Strangle entry error for " + symbol + ": " + str(e))
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
            alpaca_symbol = contract.replace("O:", "")
            pos = alpaca_positions.get(alpaca_symbol)
            if pos is None:
                state.close_trade(contract, "already_closed", trade.entry_price)
                continue
            current_price = float(pos.current_price or 0)
            if current_price > 0:
                trailing_stop_manager.update(trade, current_price)
        for symbol in list(strangle_pair_manager.pairs.keys()):
            should_close, reason = strangle_pair_manager.check_pair(symbol, state.open_trades)
            if should_close:
                self._close_strangle(symbol, reason, alpaca_positions)

    def _close_strangle(self, symbol, reason, alpaca_positions):
        pair = strangle_pair_manager.pairs.get(symbol)
        if not pair:
            return
        total_pnl = 0
        for contract in [pair["call"], pair["put"]]:
            alpaca_symbol = contract.replace("O:", "")
            pos = alpaca_positions.get(alpaca_symbol)
            if pos:
                total_pnl += float(pos.unrealized_pl or 0)
            trade = state.open_trades.get(contract)
            if trade:
                exit_price = order_manager.close_position(contract, trade.qty)
                state.close_trade(contract, reason, exit_price or trade.current_price)
        strangle_pair_manager.remove_pair(symbol)
        emoji = "✅" if total_pnl > 0 else "❌"
        telegram.send(
            emoji + " *" + symbol + " Strangle Closed*\n" +
            "Reason: " + reason + "\n" +
            "Combined P&L: $" + str(round(total_pnl, 2)) + "\n" +
            "Daily P&L: $" + str(round(state.daily_pnl, 2))
        )

    def set_symbols(self, symbols):
        self.active_symbols = symbols

    def _close_all_eod(self):
        for symbol in list(strangle_pair_manager.pairs.keys()):
            pair = strangle_pair_manager.pairs[symbol]
            for contract in [pair["call"], pair["put"]]:
                trade = state.open_trades.get(contract)
                if trade:
                    order_manager.close_position(contract, trade.qty)
                    state.close_trade(contract, reason, trade.current_price)
            strangle_pair_manager.remove_pair(symbol)
        order_manager.close_all()
        telegram.send("Market closed. All strangles closed.\nDaily P&L: $" + str(round(state.daily_pnl, 2)))
        self.entry_fired = False
        state.goal_hit = False

    def _shutdown(self):
        order_manager.close_all()
        summary = ai_brain.summarize_session(
            [{"symbol": t.symbol, "pnl": t.pnl, "reason": t.close_reason} for t in state.closed_trades],
            state.daily_pnl
        )
        telegram.send("Toby shutting down.\nDaily P&L: $" + str(round(state.daily_pnl, 2)) + "\n\n" + summary)
        state.running = False

engine = TradingEngine()
