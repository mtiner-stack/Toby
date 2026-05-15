import requests, numpy as np
from datetime import datetime, timedelta
from utils.logger import get_logger
import config

log = get_logger("market_data")
ALPACA_DATA_URL = "https://data.alpaca.markets"

class MarketData:
    def __init__(self):
        self.headers = {"APCA-API-KEY-ID": config.ALPACA_API_KEY, "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY}

    def _get(self, path, params={}):
        r = requests.get(f"{ALPACA_DATA_URL}{path}", headers=self.headers, params=params, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_snapshot(self, symbol):
        try:
            data = self._get(f"/v2/stocks/{symbol}/snapshot")
            price = data.get("latestTrade", {}).get("p", 0)
            daily = data.get("dailyBar", {})
            prev_close = data.get("prevDailyBar", {}).get("c", price)
            return {"symbol": symbol, "price": price, "open": daily.get("o",0), "high": daily.get("h",0), "low": daily.get("l",0), "volume": daily.get("v",0), "prev_close": prev_close, "day_change_pct": ((price-prev_close)/prev_close*100) if prev_close else 0, "vwap": daily.get("vw",0)}
        except Exception as e:
            log.error(f"Snapshot error for {symbol}: {e}")
            return {}

    def get_bars(self, symbol, timeframe="5Min", limit=50):
        try:
            end = datetime.utcnow()
            start = end - timedelta(hours=8)
            data = self._get(f"/v2/stocks/{symbol}/bars", {"timeframe": timeframe, "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "limit": limit, "feed": "sip"})
            return data.get("bars", [])
        except Exception as e:
            log.error(f"Bars error for {symbol}: {e}")
            return []

    def get_technicals(self, symbol):
        bars = self.get_bars(symbol, limit=50)
        if len(bars) < 20:
            return {"rsi": 50, "macd": 0, "macd_signal": 0, "trend": "unknown", "volume_ratio": 1.0, "support": 0, "resistance": 0}
        closes = np.array([b["c"] for b in bars])
        volumes = np.array([b["v"] for b in bars])
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-14:])
        avg_loss = np.mean(losses[-14:])
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        macd_line = ema12[-1] - ema26[-1]
        signal_line = self._ema(ema12 - ema26, 9)[-1]
        vol_ratio = volumes[-1] / np.mean(volumes[-20:]) if len(volumes) >= 20 else 1.0
        ema20 = self._ema(closes, 20)[-1]
        trend = "up" if closes[-1] > ema20 else "down"
        return {"rsi": round(rsi,1), "macd": round(macd_line,4), "macd_signal": round(signal_line,4), "trend": trend, "volume_ratio": round(vol_ratio,2), "support": round(float(np.min(closes[-20:])),2), "resistance": round(float(np.max(closes[-20:])),2)}

    def _ema(self, data, period):
        k = 2 / (period + 1)
        ema = np.zeros(len(data))
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = data[i] * k + ema[i-1] * (1 - k)
        return ema

    def get_vix(self):
        try:
            return self._get("/v2/stocks/VIXY/snapshot").get("latestTrade", {}).get("p", 20.0)
        except:
            return 20.0

market_data = MarketData()
