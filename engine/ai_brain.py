"""
AI Brain — uses Claude to analyze market data and generate trade signals.
Returns structured signal with direction, confidence, and reasoning.
"""
import json
import anthropic
from utils.logger import get_logger
import config

log = get_logger("ai_brain")

SYSTEM_PROMPT = """You are Toby, an elite 0DTE options scalping AI. You analyze real-time market data
and generate high-conviction trade signals. You are disciplined, unemotional, and risk-aware.

When given market data, respond ONLY with valid JSON in this exact format:
{
  "action": "buy_call" | "buy_put" | "no_trade",
  "symbol": "SPY",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "market_regime": "trending_up" | "trending_down" | "ranging" | "volatile",
  "urgency": "high" | "medium" | "low",
  "suggested_strike": "ATM" | "1_OTM" | "2_OTM",
  "suggested_expiry": "0DTE" | "1DTE"
}

Rules you never break:
- confidence below 0.65 = no_trade
- If VIX > 30, only trade with confidence > 0.80
- Never chase — if momentum is already extended, no_trade
- Preserve capital above all else
"""

class AIBrain:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self.model = "claude-sonnet-4-5"

    def analyze(self, market_snapshot: dict) -> dict:
        """
        market_snapshot should contain:
          - symbol, price, vix, rsi, macd, volume_ratio,
          - day_change_pct, support, resistance, trend
        """
        prompt = f"""Analyze this market snapshot and generate a trade signal:

{json.dumps(market_snapshot, indent=2)}

Current open positions: {market_snapshot.get('open_positions', 0)}
Daily P&L so far: ${market_snapshot.get('daily_pnl', 0):.2f}

Respond with JSON only."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.content[0].text.strip()
            signal = json.loads(raw)
            log.info(f"AI signal for {market_snapshot.get('symbol')}: {signal['action']} | confidence={signal['confidence']:.0%}")
            return signal
        except json.JSONDecodeError as e:
            log.error(f"AI returned invalid JSON: {e}")
            return {"action": "no_trade", "confidence": 0, "reasoning": "JSON parse error", "market_regime": "unknown"}
        except Exception as e:
            log.error(f"AI Brain error: {e}")
            return {"action": "no_trade", "confidence": 0, "reasoning": str(e), "market_regime": "unknown"}

    def summarize_session(self, closed_trades: list, daily_pnl: float) -> str:
        """End-of-day debrief from Claude."""
        prompt = f"""Session debrief for Toby scalping bot.

Daily P&L: ${daily_pnl:.2f}
Total trades: {len(closed_trades)}

Trade results:
{json.dumps(closed_trades, indent=2)}

Give a brief 3-4 sentence analysis of today's performance, what worked, what didn't, and one adjustment for tomorrow."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            return f"Session summary unavailable: {e}"

ai_brain = AIBrain()
