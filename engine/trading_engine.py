"""
Trading Engine - High-speed scalping architecture.
"""
import time, threading
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
        self.bias = {}
        self.bias_set = False
        self.last_prices = {}
        self.last_scan = {}

    def run(self):
        state.running = True
        telegram.send("*Toby is online.* High-speed scalping mode active.")
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
        if hour == 9 and minute == 29 and not self.bias_set:
            self._set_opening_bias()
        if hour < 9 or (hour == 9 and minute < 30):
            log.info("Market not open yet " + now_et.strftime("%H:%M ET"))
            time.sleep(10)
            return
        if (hour == 15 and minute >= 45) or hour >= 16:
            self._close_all_eod()
            time.sleep(60)
            return
        if state.goal_hit:
            time.sleep(2)
            return
        if state.daily_pnl >= DAILY_GOAL:
            state.goal_hit = True
            telegram.send("*Daily goal hit!* P&L: $" + str(round(state.daily_pnl, 2)) + "\nTrailing winners. No new positions.")
            return
        if state.daily_pnl <= -config.MAX_DAILY_LOSS:
            if not state.paused:
                state.paused = True
                telegram.send("Daily loss limit hit. Shutting down for today.")
            time.sleep(5)
            return
        is_power_hour = (hour == 9 and minute >= 30)
        if hour >= 10 and not state.conservative_mode:
            state.conservative_mode = True
            telegram.send("10am - P&L: $" + str(round(state.daily_pnl, 2)) + ". Switching to conservative mode.")
        if len(state.open_trades) < config.MAX_OPEN_TRADES:
            for symbol in config.SYMBOLS:
                if state.kill_switch or len(state.open_trades) >= config.MAX_OPEN_TRADES:
                    break
                self._evaluate_symbol(symbol, is_power_hour)
        time.sleep(5 if is_power_hour else 30)

    def _set_opening_bias(self):
        log.info("Setting opening bias...")
        telegram.send("Pre-market analysis running...")
        self.bias_set = True
        for symbol in config.SYMBOLS:
            try:
                snap = market_data.get_snapshot(symbol)
                tech = market_data.get_technicals(symbol)
                vix = market_data.get_vix()
                snapshot = {**snap, **tech, "vix": vix, "open_positions": 0, "daily_pnl": 0, "pre_market": True, "conservative_mode": False, "goal_hit": False}
                signal = ai_brain.analyze(snapshot)
                self.bias[symbol] = "call" if signal["action"] == "buy_call" else ("put" if signal["action"] == "buy_put" else None)
            except Exception as e:
                log.error("Bias error " + symbol + ": " + str(e))
                self.bias[symbol] = None
        parts = [s + ": " + (b or "neutral") for s, b in self.bias.items()]
        telegram.send("*Opening Bias*\n" + " | ".join(parts) + "\nReady to trade at 9:30!")

    def _evaluate_symbol(self, symbol, is_power_hour):
        try:
            last = self.last_scan.get(symbol, 0)
            if time.time() - last < (5 if is_power_hour else 30):
                return
            self.last_scan[symbol] = time.time()
            snap = market_data.get_snapshot(symbol)
            if not snap or not snap.get("price"):
                return
            price = snap["price"]
            prev_price = self.last_prices.get(symbol, price)
            self.last_prices[symbol] = price
            vix = market_data.get_vix()
            tech = market_data.get_technicals(symbol)
            signal = self._compute_signal(symbol, snap, tech, vix, is_power_hour, prev_price)
            if signal["action"] == "no_trade":
                log.info(symbol + ": " + signal["reasoning"])
                return
            state.last_ai_analysis = signal["reasoning"]
            state.market_regime = signal["market_regime"]
            contract_info = options_scanner.find_contract(symbol, signal, price)
            if not contract_info:
                return
            buying_power = order_manager.get_buying_power()
            qty = options_scanner.calc_qty(contract_info["mid_price"], buying_power, len(state.open_trades), is_power_hour)
            cost = contract_info["mid_price"] * 100 * qty
            allowed, risk_reason = risk_engine.check_trade_allowed(symbol, cost, signal)
            if not allowed:
                log.info(symbol + ": blocked - " + risk_reason)
                return
            trade = order_manager.buy_option(symbol, contract_info["ticker"], qty, signal)
            if trade:
                telegram.send("*Trade Fired* " + symbol + " " + contract_info["type"].upper() + "\nStrike: $" + str(contract_info["strike"]) + " | Qty: " + str(qty) + " | Entry: $" + str(round(trade.entry_price, 2)) + "\nStop: $" + str(round(trade.stop_price, 2)) + " | TP: $" + str(round(trade.take_profit, 2)) + "\n_" + signal["reasoning"] + "_")
        except Exception as e:
            log.error("Error evaluating " + symbol + ": " + str(e))

    def _compute_signal(self, symbol, snap, tech, vix, is_power_hour, prev_price):
        price = snap["price"]
        day_change_pct = snap.get("day_change_pct", 0)
        rsi = tech.get("rsi", 50)
        macd = tech.get("macd", 0)
        macd_sig = tech.get("macd_signal", 0)
        vol_ratio = tech.get("volume_ratio", 1.0)
        vwap = snap.get("vwap", price)
        bias = self.bias.get(symbol)
        momentum = price - prev_price
        cs, ps = 0, 0
        if day_change_pct > 0.3: cs += 2
        elif day_change_pct < -0.3: ps += 2
        if price > vwap: cs += 1
        else: ps += 1
        if macd > macd_sig: cs += 1
        else: ps += 1
        if rsi > 55: cs += 1
        elif rsi < 45: ps += 1
        if vol_ratio > 1.5:
            if cs >= ps: cs += 2
            else: ps += 2
        if momentum > 0.05: cs += 2
        elif momentum < -0.05: ps += 2
        if bias == "call": cs += 2
        elif bias == "put": ps += 2
        total = cs + ps
        if total == 0:
            return {"action": "no_trade", "confidence": 0, "reasoning": "No signals", "market_regime": "unknown"}
        if cs > ps:
            action, conf = "buy_call", cs / (total + 2)
        elif ps > cs:
            action, conf = "buy_put", ps / (total + 2)
        else:
            return {"action": "no_trade", "confidence": 0, "reasoning": "Tied signals", "market_regime": "ranging"}
        min_conf = 0.55 if is_power_hour else 0.70
        if state.conservative_mode: min_conf = 0.75
        if conf < min_conf:
            return {"action": "no_trade", "confidence": conf, "reasoning": "Conf " + str(round(conf*100)) + "% below threshold | " + str(cs) + "c/" + str(ps) + "p", "market_regime": "ranging"}
        regime = "volatile" if vix > 25 else ("trending_up" if cs > ps else "trending_down")
        return {"action": action, "symbol": symbol, "confidence": round(conf, 2),
                "reasoning": str(cs) + "c/" + str(ps) + "p | RSI:" + str(rsi) + " | Vol:" + str(round(vol_ratio,1)) + "x | Gap:" + str(round(day_change_pct,2)) + "% | Mom:" + str(round(momentum,3)),
                "market_regime": regime, "urgency": "high" if is_power_hour else "medium",
                "suggested_strike": "ATM" if is_power_hour else "1_OTM", "suggested_expiry": "0DTE"}

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
                snap = market_data.get_snapshot(trade.symbol)
                current_price = snap.get("price", trade.current_price) if snap else trade.current_price
                should_close, reason = trailing_stop_manager.update(trade, current_price)
                if should_close:
                    exit_price = order_manager.close_position(contract, trade.qty)
                    closed = state.close_trade(contract, reason, exit_price)
                    if closed:
                        emoji = "✅" if closed.pnl > 0 else "❌"
                        telegram.send(emoji + " *Closed* " + contract + "\n" + reason + " | P&L: $" + str(round(closed.pnl, 2)) + " | Daily: $" + str(round(state.daily_pnl, 2)))
            except Exception as e:
                log.error("Monitor error " + contract + ": " + str(e))

    def _close_all_eod(self):
        if state.open_trades:
            order_manager.close_all()
            for contract in list(state.open_trades.keys()):
                state.close_trade(contract, "eod_close", 0)
            telegram.send("Market closed. Daily P&L: $" + str(round(state.daily_pnl, 2)))
        self.bias_set = False
        self.bias = {}
        state.goal_hit = False
        state.conservative_mode = False

    def _shutdown(self):
        order_manager.close_all()
        summary = ai_brain.summarize_session([{"symbol": t.symbol, "pnl": t.pnl, "reason": t.close_reason} for t in state.closed_trades], state.daily_pnl)
        telegram.send("Toby shutting down.\nDaily P&L: $" + str(round(state.daily_pnl, 2)) + "\n\n" + summary)
        state.running = False

engine = TradingEngine()
