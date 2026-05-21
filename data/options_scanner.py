"""
Options Scanner — finds the right 0DTE contract given a signal.
Uses Polygon options chain data.
"""
import requests
from datetime import datetime
from utils.logger import get_logger
import config

log = get_logger("options")
BASE = "https://api.polygon.io"

class OptionsScanner:
    def __init__(self):
        self.key = config.POLYGON_API_KEY

    def find_contract(self, symbol: str, signal: dict, current_price: float) :
        """
        Find the best 0DTE contract matching the signal.
        Returns contract info dict or None.
        """
        option_type = "call" if signal["action"] == "buy_call" else "put"
        strike_pref = signal.get("suggested_strike", "ATM")
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            params = {
                "underlying_ticker": symbol,
                "contract_type": option_type,
                "expiration_date": today,
                "limit": 20,
                "sort": "strike_price",
                "order": "asc",
                "apiKey": self.key,
            }
            r = requests.get(f"{BASE}/v3/reference/options/contracts", params=params, timeout=10)
            r.raise_for_status()
            contracts = r.json().get("results", [])

            if not contracts:
                log.warning(f"No 0DTE {option_type} contracts found for {symbol}")
                return None

            # Pick strike
            target_strike = self._pick_strike(current_price, contracts, strike_pref, option_type)
            if not target_strike:
                return None

            # Get live quote
            ticker = target_strike["ticker"]
            quote = self._get_quote(ticker)
            if not quote:
                return None

            mid = (quote.get("bid", 0) + quote.get("ask", 0)) / 2
            if mid <= 0.10:
                log.warning(f"Contract {ticker} too cheap (${mid:.2f}), skipping")
                return None

            return {
                "ticker": ticker,
                "strike": target_strike["strike_price"],
                "type": option_type,
                "mid_price": round(mid, 2),
                "bid": quote.get("bid"),
                "ask": quote.get("ask"),
                "expiry": today,
            }

        except Exception as e:
            log.error(f"Options scan failed for {symbol}: {e}")
            return None

    def _pick_strike(self, price: float, contracts: list, preference: str, opt_type: str) :
        """Select nearest ATM or OTM strike."""
        strikes = sorted(contracts, key=lambda c: abs(c["strike_price"] - price))

        if preference == "ATM":
            return strikes[0] if strikes else None
        elif preference == "1_OTM":
            # For calls: higher strike; for puts: lower strike
            otm = [c for c in contracts if
                   (opt_type == "call" and c["strike_price"] > price) or
                   (opt_type == "put" and c["strike_price"] < price)]
            otm.sort(key=lambda c: abs(c["strike_price"] - price))
            return otm[0] if otm else strikes[0]
        else:
            return strikes[0]

    def _get_quote(self, ticker: str) -> dict:
        try:
            r = requests.get(
                f"{BASE}/v3/quotes/{ticker}",
                params={"limit": 1, "apiKey": self.key},
                timeout=8
            )
            results = r.json().get("results", [])
            if results:
                q = results[-1]
                return {"bid": q.get("bid_price", 0), "ask": q.get("ask_price", 0)}
        except Exception as e:
            log.error(f"Quote error for {ticker}: {e}")
        return {}

    def calc_qty(self, mid_price: float, buying_power: float, open_trades: int, is_power_hour: bool) -> int:
        """
        Dynamically size position based on available buying power.
        Power hour: deploy 25-35% of buying power split across up to 3 trades.
        After 10am: deploy 10-15% max per trade.
        """
        if mid_price <= 0 or buying_power <= 0:
            return 0

        cost_per = mid_price * 100
        max_concurrent = 3

        if is_power_hour:
            # Use 30% of buying power total, split across max 3 trades
            total_allocation = buying_power * 0.30
            per_trade = total_allocation / max(1, max_concurrent - open_trades)
        else:
            # Conservative: 12% of buying power per trade
            per_trade = buying_power * 0.12

        qty = int(per_trade / cost_per)
        return max(1, min(qty, 50))  # 1-50 contracts

options_scanner = OptionsScanner()
