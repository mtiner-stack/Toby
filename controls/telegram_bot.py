"""
Telegram Bot — runtime controls and notifications.
Commands: /status /pause /resume /kill /positions /pnl /help
"""
import threading
import requests
from utils.logger import get_logger
from utils.state import state
import config

log = get_logger("telegram")

class TelegramBot:
    def __init__(self):
        self.token = config.TELEGRAM_BOT_TOKEN
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0
        self._running = False

    def send(self, message: str):
        if not self.token or not self.chat_id:
            log.debug(f"Telegram not configured. Message: {message}")
            return
        try:
            requests.post(f"{self.base}/sendMessage", json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown"
            }, timeout=5)
        except Exception as e:
            log.error(f"Telegram send error: {e}")

    def start_polling(self):
        self._running = True
        thread = threading.Thread(target=self._poll_loop, daemon=True)
        thread.start()
        log.info("Telegram polling started.")

    def _poll_loop(self):
        while self._running:
            try:
                updates = self._get_updates()
                for update in updates:
                    self._handle(update)
            except Exception as e:
                log.error(f"Telegram poll error: {e}")
            import time; time.sleep(2)

    def _get_updates(self) -> list:
        r = requests.get(f"{self.base}/getUpdates", params={
            "offset": self.last_update_id + 1,
            "timeout": 10
        }, timeout=15)
        updates = r.json().get("result", [])
        if updates:
            self.last_update_id = updates[-1]["update_id"]
        return updates

    def _handle(self, update: dict):
        msg = update.get("message", {})
        raw_text = msg.get("text", "").strip()
        text = raw_text.lower()
        chat_id = str(msg.get("chat", {}).get("id", ""))

        # Only respond to configured chat
        if chat_id != str(self.chat_id):
            return

        log.info(f"Telegram command: {text}")

        if text == "/status":
            d = state.to_dict()
            reply = (
                f"🤖 *Toby Status*\n"
                f"Running: {d['running']} | Paused: {d['paused']}\n"
                f"Kill switch: {d['kill_switch']}\n"
                f"Daily P&L: ${d['daily_pnl']:.2f}\n"
                f"Open trades: {len(d['open_trades'])}\n"
                f"Regime: {d['market_regime']}\n"
                f"AI: _{d['last_ai_analysis']}_"
            )
        elif text == "/pause":
            state.paused = True
            reply = "⏸ Bot paused. No new trades. Existing positions still managed."
        elif text == "/resume":
            state.paused = False
            reply = "▶️ Bot resumed."
        elif text == "/kill":
            state.kill_switch = True
            state.paused = True
            reply = "🔴 KILL SWITCH ACTIVATED. Closing all positions."
            from engine.order_manager import order_manager
            order_manager.close_all()
        elif text == "/positions":
            d = state.to_dict()
            if not d["open_trades"]:
                reply = "No open positions."
            else:
                lines = ["📊 *Open Positions*"]
                for t in d["open_trades"]:
                    pnl_emoji = "🟢" if t["pnl"] >= 0 else "🔴"
                    lines.append(f"{pnl_emoji} {t['symbol']} | {t['contract']}\nQty: {t['qty']} | Entry: ${t['entry']:.2f} | P&L: ${t['pnl']:.2f}")
                reply = "\n".join(lines)
        elif text == "/pnl":
            d = state.to_dict()
            reply = f"💰 Daily P&L: *${d['daily_pnl']:.2f}*\nTrades today: {d['daily_trades']}"
        elif text == "/help":
            reply = (
                "📋 *Toby Commands*\n"
                "/status — full bot status\n"
                "/positions — open trades\n"
                "/pnl — daily P&L\n"
                "/pause — pause new trades\n"
                "/resume — resume trading\n"
                "/kill — emergency stop all"
            )
        else:
            reply = self._chat(raw_text)

        self.send(reply)


    def _chat(self, text: str) -> str:
        try:
            import anthropic
            import config
            from utils.state import state
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            d = state.to_dict()
            context = f"""You are Toby, an autonomous 0DTE options scalping bot. 
Current status: Running={d["running"]}, Paused={d["paused"]}, Kill switch={d["kill_switch"]}
Daily P&L: ${d["daily_pnl"]:.2f}
Open trades: {len(d["open_trades"])}
Daily trades: {d["daily_trades"]}
Market regime: {d["market_regime"]}
Last AI analysis: {d["last_ai_analysis"]}
Recent closed trades: {d["recent_closed"]}

Answer the user concisely in 2-3 sentences. You can explain your decisions, current market view, or status."""
            r = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=200,
                system=context,
                messages=[{"role": "user", "content": text}]
            )
            return r.content[0].text.strip()
        except Exception as e:
            return f"Sorry, I couldn't process that: {e}"


    def _chat(self, text: str) -> str:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            d = state.to_dict()
            context = f"""You are Toby, an autonomous 0DTE options scalping bot talking to your owner via Telegram.
Status: Running={d["running"]}, Paused={d["paused"]}, P&L=${d["daily_pnl"]:.2f}, Open trades={len(d["open_trades"])}, Regime={d["market_regime"]}
Last analysis: {d["last_ai_analysis"]}
Be conversational and concise, 2-3 sentences max."""
            r = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system=context,
                messages=[{"role": "user", "content": text}]
            )
            return r.content[0].text.strip()
        except Exception as e:
            return f"Sorry, could not process that right now."


    def _chat(self, text: str) -> str:
        try:
            import anthropic
            from datetime import datetime
            import pytz
            ET = pytz.timezone("America/New_York")
            now_et = datetime.now(ET)
            time_str = now_et.strftime("%A %B %d %Y, %I:%M %p ET")
            market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            is_weekend = now_et.weekday() >= 5
            if is_weekend:
                market_status = "Market is closed (weekend)"
            elif now_et < market_open:
                mins = int((market_open - now_et).total_seconds() / 60)
                market_status = f"Market opens in {mins} minutes"
            elif now_et > market_close:
                market_status = "Market is closed for today"
            else:
                market_status = "Market is OPEN"

            client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
            d = state.to_dict()
            context = f"""You are Toby, an autonomous 0DTE options scalping bot talking to your owner via Telegram.
Current time: {time_str}
Market status: {market_status}
Bot status: Running={d["running"]}, Paused={d["paused"]}, Kill switch={d["kill_switch"]}
Daily P&L: ${d["daily_pnl"]:.2f} | Open trades: {len(d["open_trades"])} | Total trades today: {d["daily_trades"]}
Market regime: {d["market_regime"]}
Last analysis: {d["last_ai_analysis"]}
Recent closed trades: {d["recent_closed"]}
Be conversational and concise, 2-3 sentences max. Always use the actual current time above."""
            r = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=300,
                system=context,
                messages=[{"role": "user", "content": text}]
            )
            return r.content[0].text.strip()
        except Exception as e:
            log.error(f"Chat error: {e}")
            return "Sorry, could not process that right now."

telegram = TelegramBot()
