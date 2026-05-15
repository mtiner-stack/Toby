"""
Market Data — Polygon.io REST + WebSocket feeds.
Provides price snapshots, technical indicators, VIX.
"""
import requests
import numpy as np
from datetime import datetime, timedelta
from utils.logger import get_logger
import config

log = get_logger("market_data")

BASE = "https://api.polygon.io"

class MarketData:
    def __init__(self):
        self.key = config.POLYGON_API_KEY

    def _get(self, path: str, params: dict = {}) -> dict:
        params["apiKey"] = self.key
        r = requests.get(f"{BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_snapshot(self, symbol: str) -> dict:
        """Full market snapshot for one ticker."""
        try:
            data = self._get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
            snap = data.get("ticker", {})
            day = snap.get("day", {})
            prev = snap.get("prevDay", {})
            price = snap.get("lastTrade", {}).get("p", 0)

            return {
                "symbol": symbol,
                "price": price,
                "open": day.get("o", 0),
                "high": day.get("h", 0),
                "low": day.get("l", 0),
                "volume": day.get("v", 0),
                "prev_close": prev.get("c", 0),
                "day_change_pct": ((price - prev.get("c", price)) / prev.get("c", 1)) * 100,
                "vwap": day.get("vw", 0),
            }
        except Exception as e:
            log.error(f"Snapshot error for {symbol}: {e}")
            return {}

    def get_bars(self, symbol: str, minutes: int = 5, limit: int = 50) -> list:
        """Get recent OHLCV bars."""
        try:
            end = datetime.now()
            start = end - timedelta(hours=6)
            data = self._get(
                f"/v2/aggs/ticker/{symbol}/range/{minutes}/minute/"
                f"{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
                {"adjusted": "true", "sort": "asc", "limit": limit}
            )
            return data.get("results", [])
        except Exception as e:
            log.error(f"Bars error for {symbol}: {e}")
            return []

    def get_technicals(self, symbol: str) -> dict:
        """Compute RSI and MACD from recent bars."""
        bars = self.get_bars(symbol, minutes=5, limit=50)
        if len(bars) < 20:
            return {"rsi": 50, "macd": 0, "macd_signal": 0, "trend": "unknown", "volume_ratio": 1.0}

        closes = np.array([b["c"] for b in bars])
        volumes = np.array([b["v"] for b in bars])

        # RSI-14
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses[-14:])
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))

        # MACD (12/26/9)
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd_line = ema12[-1] - ema26[-1]
        signal_line = self._ema(ema12 - ema26, 9)[-1]

        # Volume ratio vs 20-bar avg
        vol_ratio = volumes[-1] / np.mean(volumes[-20:]) if len(volumes) >= 20 else 1.0

        # Simple trend: price above/below 20-bar EMA
        ema20 = self._ema(closes, 20)[-1]
        trend = "up" if closes[-1] > ema20 else "down"

        return {
            "rsi": round(rsi, 1),
            "macd": round(macd_line, 4),
            "macd_signal": round(signal_line, 4),
            "trend": trend,
            "volume_ratio": round(vol_ratio, 2),
            "support": round(min(closes[-20:]), 2),
            "resistance": round(max(closes[-20:]), 2),
        }

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        k = 2 / (period + 1)
        ema = np.zeros(len(data))
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = data[i] * k + ema[i-1] * (1 - k)
        return ema

    def get_vix(self) -> float:
        """Fetch VIX level."""
        try:
            snap = self._get("/v2/snapshot/locale/us/markets/stocks/tickers/VIXY")
            return snap.get("ticker", {}).get("lastTrade", {}).get("p", 20.0)
        except:
            return 20.0  # Default to moderate if unavailable

market_data = MarketData()
