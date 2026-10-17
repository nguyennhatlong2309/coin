import json
import logging
import time
import httpx
from typing import Dict, Any, List, Optional
from ..config import WATCHLIST_FILE, DEFAULT_WATCHLIST

logger = logging.getLogger(__name__)

class CryptoService:
    def __init__(self):
        self.file_path = WATCHLIST_FILE
        self.watchlist: List[str] = list(DEFAULT_WATCHLIST)
        self.active_status: Dict[str, bool] = {c: True for c in self.watchlist}
        self.cache_time = 0.0
        self.cached_tickers: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.watchlist = data.get("coins", list(DEFAULT_WATCHLIST))
                    self.active_status = data.get("active", {c: True for c in self.watchlist})
                    # Ensure all coins have active status
                    for c in self.watchlist:
                        if c not in self.active_status:
                            self.active_status[c] = True
            except Exception as e:
                logger.warning(f"Failed to load watchlist: {e}")
                self.save()
        else:
            self.save()

    def save(self):
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({
                    "coins": self.watchlist,
                    "active": self.active_status,
                    "updated_at": time.time()
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving watchlist: {e}")

    @staticmethod
    def normalize_symbol(coin: str) -> str:
        c = coin.strip().upper()
        if not c.endswith("USDT"):
            return f"{c}USDT"
        return c

    @staticmethod
    def get_coin_base(symbol: str) -> str:
        s = symbol.upper()
        if s.endswith("USDT"):
            return s[:-4]
        return s

    def fetch_coin_ticker(self, coin: str) -> Optional[Dict[str, Any]]:
        """Fetch 24hr stats & liquidity for a single coin from Binance public API."""
        symbol = self.normalize_symbol(coin)
        base = self.get_coin_base(symbol)
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return None
                data = resp.json()
                
                last_price = float(data.get("lastPrice", 0))
                change_pct = float(data.get("priceChangePercent", 0))
                quote_volume = float(data.get("quoteVolume", 0)) # 24h volume in USDT (Liquidity indicator)
                base_volume = float(data.get("volume", 0))
                bid_price = float(data.get("bidPrice", 0))
                ask_price = float(data.get("askPrice", 0))
                spread = max(0.0, ask_price - bid_price)
                spread_bps = (spread / last_price * 10000) if last_price > 0 else 0

                # Determine liquidity tier
                if quote_volume >= 250_000_000:
                    tier = "MEGA TIER (Top 1% Depth)"
                    tier_badge = "badge-mega"
                elif quote_volume >= 50_000_000:
                    tier = "DEEP TIER (High Liquidity)"
                    tier_badge = "badge-deep"
                elif quote_volume >= 10_000_000:
                    tier = "SOLID TIER (Good Depth)"
                    tier_badge = "badge-solid"
                else:
                    tier = "LIGHT TIER (Moderate Depth)"
                    tier_badge = "badge-light"

                # Pretty format liquidity
                if quote_volume >= 1_000_000_000:
                    liq_str = f"${quote_volume / 1_000_000_000:.2f}B USDT"
                elif quote_volume >= 1_000_000:
                    liq_str = f"${quote_volume / 1_000_000:.1f}M USDT"
                else:
                    liq_str = f"${quote_volume / 1_000:.0f}K USDT"

                return {
                    "symbol": symbol,
                    "coin": base,
                    "price": last_price,
                    "price_formatted": self.format_price(last_price),
                    "change_24h": round(change_pct, 2),
                    "high_24h": float(data.get("highPrice", 0)),
                    "low_24h": float(data.get("lowPrice", 0)),
                    "liquidity_usdt": quote_volume,
                    "liquidity_formatted": liq_str,
                    "base_volume": base_volume,
                    "bid_price": bid_price,
                    "ask_price": ask_price,
                    "spread": spread,
                    "spread_bps": round(spread_bps, 2),
                    "tier": tier,
                    "tier_badge": tier_badge,
                    "is_active": self.active_status.get(base, True)
                }
        except Exception as e:
            logger.warning(f"Error fetching ticker for {symbol}: {e}")
            return None

    def fetch_coin_depth(self, coin: str, limit: int = 15) -> Dict[str, Any]:
        """Fetch real-time order book depth & bid/ask pressure ratio."""
        symbol = self.normalize_symbol(coin)
        base = self.get_coin_base(symbol)
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit={limit}"
        
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return {"error": "Unable to fetch order book depth"}
                data = resp.json()
                
                bids_raw = data.get("bids", [])
                asks_raw = data.get("asks", [])
                
                total_bid_usd = sum(float(p) * float(q) for p, q in bids_raw)
                total_ask_usd = sum(float(p) * float(q) for p, q in asks_raw)
                
                ratio = (total_bid_usd / total_ask_usd) if total_ask_usd > 0 else 1.0
                
                if ratio >= 1.25:
                    depth_sentiment = "BULLISH DEPTH (Heavy Buy Orders)"
                    sentiment_color = "highlight-green"
                elif ratio <= 0.80:
                    depth_sentiment = "BEARISH DEPTH (Heavy Sell Wall)"
                    sentiment_color = "highlight-red"
                else:
                    depth_sentiment = "BALANCED DEPTH (Neutral Spread)"
                    sentiment_color = "highlight-gold"

                return {
                    "symbol": symbol,
                    "coin": base,
                    "total_bid_usd": round(total_bid_usd, 2),
                    "total_ask_usd": round(total_ask_usd, 2),
                    "bid_ask_ratio": round(ratio, 2),
                    "depth_sentiment": depth_sentiment,
                    "sentiment_color": sentiment_color,
                    "top_bids": [{"price": float(p), "qty": float(q), "total": round(float(p)*float(q), 1)} for p, q in bids_raw[:5]],
                    "top_asks": [{"price": float(p), "qty": float(q), "total": round(float(p)*float(q), 1)} for p, q in asks_raw[:5]]
                }
        except Exception as e:
            logger.warning(f"Error fetching depth for {symbol}: {e}")
            return {"error": str(e)}

    def fetch_all_watchlist(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch tickers for all coins in user's watchlist (with 2-sec caching)."""
        now = time.time()
        if not force_refresh and (now - self.cache_time < 2.0) and self.cached_tickers:
            return self.cached_tickers

        results = []
        for coin in self.watchlist:
            ticker = self.fetch_coin_ticker(coin)
            if ticker:
                results.append(ticker)
        
        self.cached_tickers = results
        self.cache_time = now
        return results

    def add_coin(self, raw_coin: str) -> Dict[str, Any]:
        """Validate coin against Binance, add to watchlist if valid."""
        clean = raw_coin.strip().upper()
        if not clean:
            return {"success": False, "message": "Coin symbol cannot be empty."}
        
        base = self.get_coin_base(clean)
        if base in self.watchlist:
            return {"success": False, "message": f"{base} is already in your watchlist."}

        # Check if valid on Binance Spot
        symbol = f"{base}USDT"
        test_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        try:
            with httpx.Client(timeout=4.0) as client:
                resp = client.get(test_url)
                if resp.status_code == 200:
                    self.watchlist.append(base)
                    self.active_status[base] = True
                    self.save()
                    return {"success": True, "message": f"Successfully added {base}/USDT to Watchlist!", "coin": base}
                else:
                    return {"success": False, "message": f"Symbol '{base}' is not traded on Binance Spot (Pair: {symbol})."}
        except Exception as e:
            return {"success": False, "message": f"Network error checking Binance: {e}"}

    def remove_coin(self, raw_coin: str) -> Dict[str, Any]:
        base = self.get_coin_base(raw_coin.strip().upper())
        if base in self.watchlist:
            self.watchlist.remove(base)
            if base in self.active_status:
                del self.active_status[base]
            self.save()
            return {"success": True, "message": f"Removed {base} from watchlist."}
        return {"success": False, "message": f"{base} not found in watchlist."}

    def toggle_coin(self, raw_coin: str) -> Dict[str, Any]:
        base = self.get_coin_base(raw_coin.strip().upper())
        if base in self.watchlist:
            current = self.active_status.get(base, True)
            self.active_status[base] = not current
            self.save()
            return {"success": True, "is_active": self.active_status[base]}
        return {"success": False, "message": "Coin not found"}

    @staticmethod
    def format_price(price: float) -> str:
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.3f}"
        elif price >= 0.001:
            return f"${price:.6f}"
        else:
            return f"${price:.8f}"
