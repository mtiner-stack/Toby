"""
Trading Engine — the main loop.
Coordinates: market data → AI brain → risk check → order → position management.
"""
import time
from datetime import datetime
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

class TradingEngine:
    def run(self):
        state.running = True
        log.info("🚀 Toby is live.")
        telegram.send("🤖 *Toby is online.* Starting trading loop.")

        try:
            while state.running:
                if not state.paused and not state.kill_switch:
                    self._tick()
                elif state.paused:
                    log.info("Bot paused. Waiting...")
                time.sleep(config.TRADE_LOOP_INTERVAL)
        except KeyboardInterrupt:
            log.info("Shutdown requested.")
        finally:
            self._shutdown()

    def _tick(self):
        now = datetime.now()
        time_str = now.strftime("%H:%M")
        log.info(f"--- Tick {time_str} | P&L: ${state.daily_pnl:.2f} | Open: {len(state.open_trades)} ---")

        # 1. Manage existing positions first
        self._manage_open_positions()

        # 2. Daily loss breaker
        if state.daily_pnl <= -config.MAX_DAILY_LOSS:
            log.warning(f"Daily loss limit reached (${state.daily_pnl:.2f}). Standing down.")
            telegram.send(f"⛔ Daily loss limit hit: ${state.daily_pnl:.2f}. No new trades today.")
            state.paused = True
            return

        # 3. Scan for new trades
        vix = market_data.get_vix()
        market_ok, reason = risk_engine.check_market_conditions(vix)
        if not market_ok:
            log.info(f"Market gate: {reason}")
            return

        for symbol in config.SYMBOLS:
            if state.kill_switch:
                break
            self._evaluate_symbol(symbol, vix)

    def _evaluate_symbol(self, symbol: str, vix: float):
        try:
            snap = market_data.get_snapshot(symbol)
            if not snap:
                return
            tech = market_data.get_technicals(symbol)

            market_snapshot = {
                **snap,
                **tech,
                "vix": vix,
                "open_positions": len(state.open_trades),
                "daily_pnl": state.daily_pnl,
            }

            signal = ai_brain.analyze(market_snapshot)
            state.last_ai_analysis = signal.get("reasoning", "")
            state.market_regime = signal.get("market_regime", "unknown")

            if signal["action"] == "no_trade":
                log.info(f"{symbol}: AI says no trade — {signal.get('reasoning', '')}")
                return

            # Find contract
            contract_info = options_scanner.find_contract(symbol, signal, snap["price"])
            if not contract_info:
                return

            qty = options_scanner.calc_qty(contract_info["mid_price"])
            cost = contract_info["mid_price"] * 100 * qty

            # Risk gate
            allowed, risk_reason = risk_engine.check_trade_allowed(symbol, cost, signal)
            if not allowed:
                log.info(f"{symbol}: Risk blocked — {risk_reason}")
                return

            # Execute
            trade = order_manager.buy_option(symbol, contract_info["ticker"], qty, signal)
            if trade:
                msg = (
                    f"📈 *New Trade*\n"
                    f"Symbol: {symbol} {contract_info['type'].upper()}\n"
                    f"Contract: `{contract_info['ticker']}`\n"
                    f"Strike: ${contract_info['strike']} | Qty: {qty}\n"
                    f"Entry: ${trade.entry_price:.2f} | Cost: ${cost:.0f}\n"
                    f"Stop: ${trade.stop_price:.2f} | TP: ${trade.take_profit:.2f}\n"
                    f"AI: {signal.get('reasoning', '')}"
                )
                telegram.send(msg)

        except Exception as e:
            log.error(f"Error evaluating {symbol}: {e}")

    def _manage_open_positions(self):
        for contract, trade in list(state.open_trades.items()):
            try:
                # Get current price from Polygon
                snap = market_data.get_snapshot(trade.symbol)
                current_price = snap.get("price", trade.current_price)

                should_close, reason = trailing_stop_manager.update(trade, current_price)

                if should_close:
                    exit_price = order_manager.close_position(contract, trade.qty)
                    closed = state.close_trade(contract, reason, exit_price)
                    if closed:
                        emoji = "✅" if closed.pnl > 0 else "❌"
                        telegram.send(
                            f"{emoji} *Closed:* `{contract}`\n"
                            f"Reason: {reason}\n"
                            f"P&L: ${closed.pnl:.2f}"
                        )
            except Exception as e:
                log.error(f"Position management error for {contract}: {e}")

    def _shutdown(self):
        log.info("Shutting down. Closing all positions.")
        order_manager.close_all()
        summary = ai_brain.summarize_session(
            [{"symbol": t.symbol, "pnl": t.pnl, "reason": t.close_reason} for t in state.closed_trades],
            state.daily_pnl
        )
        telegram.send(f"🛑 *Toby shutting down.*\nDaily P&L: ${state.daily_pnl:.2f}\n\n{summary}")
        state.running = False

engine = TradingEngine()
