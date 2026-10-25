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
        self.cached_tickers_map: Dict[str, Dict[str, Any]] = {}
        self.all_tickers_cache: List[Dict[str, Any]] = []
        self.all_tickers_cache_time = 0.0
        self.klines_cache: Dict[str, Dict[str, Any]] = {}
        self.client = httpx.Client(timeout=4.0, headers={"User-Agent": "quant-desk/1.0"})
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.watchlist = data.get("coins", list(DEFAULT_WATCHLIST))
                    self.active_status = data.get("active", {c: True for c in self.watchlist})
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

    def _parse_ticker_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        symbol = data.get("symbol", "")
        base = self.get_coin_base(symbol)
        last_price = float(data.get("lastPrice", 0))
        change_pct = float(data.get("priceChangePercent", 0))
        quote_volume = float(data.get("quoteVolume", 0)) # 24h volume in USDT
        base_volume = float(data.get("volume", 0))
        bid_price = float(data.get("bidPrice", 0))
        ask_price = float(data.get("askPrice", 0))
        spread = max(0.0, ask_price - bid_price)
        spread_bps = (spread / last_price * 10000) if last_price > 0 else 0

        # Determine liquidity tier
        if quote_volume >= 250_000_000:
            tier = "MEGA TIER (Thanh Khoản Khổng Lồ)"
            tier_badge = "badge-mega"
        elif quote_volume >= 50_000_000:
            tier = "DEEP TIER (Thanh Khoản Sâu)"
            tier_badge = "badge-deep"
        elif quote_volume >= 10_000_000:
            tier = "SOLID TIER (Thanh Khoản Tốt)"
            tier_badge = "badge-solid"
        else:
            tier = "LIGHT TIER (Thanh Khoản Vừa)"
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

    def fetch_coin_ticker(self, coin: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """Fetch 24hr stats & liquidity for a single coin, with quick cache fallback."""
        symbol = self.normalize_symbol(coin)
        base = self.get_coin_base(symbol)
        
        # Check cache if fresh (within 2 seconds) and not forced
        if not force_refresh and (time.time() - self.cache_time < 2.0) and base in self.cached_tickers_map:
            return self.cached_tickers_map[base]

        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={symbol}"
        try:
            resp = self.client.get(url)
            if resp.status_code == 200:
                parsed = self._parse_ticker_data(resp.json())
                self.cached_tickers_map[base] = parsed
                self.cached_tickers_map[symbol] = parsed
                return parsed
        except Exception as e:
            logger.warning(f"Error fetching ticker for {symbol}: {e}")

        if base in self.cached_tickers_map:
            return self.cached_tickers_map[base]
        return None

    def fetch_coin_depth(self, coin: str, limit: int = 15) -> Dict[str, Any]:
        """Fetch real-time order book depth & bid/ask pressure ratio."""
        symbol = self.normalize_symbol(coin)
        base = self.get_coin_base(symbol)
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit={limit}"
        
        try:
            resp = self.client.get(url)
            if resp.status_code != 200:
                return {"error": "Không thể kết nối sổ lệnh L2 Binance"}
            data = resp.json()
            
            bids_raw = data.get("bids", [])
            asks_raw = data.get("asks", [])
            
            total_bid_usd = sum(float(p) * float(q) for p, q in bids_raw)
            total_ask_usd = sum(float(p) * float(q) for p, q in asks_raw)
            
            ratio = (total_bid_usd / total_ask_usd) if total_ask_usd > 0 else 1.0
            
            if ratio >= 1.25:
                depth_sentiment = "LỰC MUA ÁP ĐẢO (Bò Gom Hàng)"
                sentiment_color = "highlight-green"
            elif ratio <= 0.80:
                depth_sentiment = "TƯỜNG BÁN ĐÈ GIÁ (Gấu Xả Hàng)"
                sentiment_color = "highlight-red"
            else:
                depth_sentiment = "CÂN BẰNG CUNG CẦU (Giằng Co)"
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

    def fetch_klines(self, coin: str, interval: str = "1h", limit: int = 100) -> Dict[str, Any]:
        """
        Fetch OHLCV candlestick data and volume for charts from Binance public API.
        Intervals: 15m, 1h, 4h, 1d
        """
        valid_intervals = {"1s", "1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"}
        if interval not in valid_intervals:
            interval = "1m"

        symbol = self.normalize_symbol(coin)
        base = self.get_coin_base(symbol)

        # Caching logic based on timeframe TTL
        cache_key = f"{symbol}_{interval}_{min(limit, 300)}"
        ttl = 50.0 if interval == "1h" else (20.0 if interval == "15m" else 3.0)
        cached = self.klines_cache.get(cache_key)
        if cached and (time.time() - cached.get("ts", 0) < ttl):
            return cached["data"]

        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={min(limit, 300)}"

        try:
            resp = self.client.get(url)
            if resp.status_code != 200:
                return {"error": f"Failed to fetch klines from Binance: HTTP {resp.status_code}"}
            raw = resp.json()

            candles = []
            volumes = []
            for item in raw:
                t_sec = int(item[0]) // 1000
                o = float(item[1])
                h = float(item[2])
                l = float(item[3])
                c = float(item[4])
                quote_vol = float(item[7]) # Quote volume in USDT (liquidity)

                is_bull = c >= o
                candles.append({
                    "time": t_sec,
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c
                })
                volumes.append({
                    "time": t_sec,
                    "value": quote_vol,
                    "color": "rgba(16, 185, 129, 0.5)" if is_bull else "rgba(239, 68, 68, 0.5)"
                })

            result = {
                "coin": base,
                "symbol": symbol,
                "interval": interval,
                "candles": candles,
                "volumes": volumes,
                "last_price": candles[-1]["close"] if candles else 0,
                "count": len(candles)
            }
            self.klines_cache[cache_key] = {"ts": time.time(), "data": result}
            return result
        except Exception as e:
            logger.warning(f"Error fetching klines for {symbol}: {e}")
            if cached:
                return cached["data"]
            return {"error": str(e)}

    def fetch_multi_timeframe_klines(self, coin: str) -> Dict[str, Any]:
        """
        Thu thập dữ liệu nến 3 tầng đa khung thời gian phục vụ Chiến Lược Bắn Tỉa Cá Mập:
        - 1H: Khung vĩ mô (Macro Trend & Đỉnh/Đáy ngày)
        - 15M: Khung cấu trúc (Market Structure & FVG)
        - 1M: Khung bóp cò (Trigger Entry & Pinbar Sweeps)
        """
        k1m = self.fetch_klines(coin, interval="1m", limit=60)
        k15m = self.fetch_klines(coin, interval="15m", limit=40)
        k1h = self.fetch_klines(coin, interval="1h", limit=40)

        return {
            "coin": coin.upper().replace("USDT", ""),
            "klines_1m": k1m.get("candles", []) if isinstance(k1m, dict) else [],
            "klines_15m": k15m.get("candles", []) if isinstance(k15m, dict) else [],
            "klines_1h": k1h.get("candles", []) if isinstance(k1h, dict) else [],
            "last_price": k1m.get("last_price", 0.0) if isinstance(k1m, dict) else 0.0
        }

    def fetch_all_watchlist(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Fetch tickers for all coins in user's watchlist using fast batch endpoint (with 2.5-sec caching)."""
        now = time.time()
        if not force_refresh and (now - self.cache_time < 2.5) and self.cached_tickers:
            return self.cached_tickers

        if not self.watchlist:
            return []

        symbols = [self.normalize_symbol(c) for c in self.watchlist]
        url = "https://api.binance.com/api/v3/ticker/24hr"

        try:
            param_str = json.dumps(symbols, separators=(',', ':'))
            resp = self.client.get(url, params={"symbols": param_str})
            if resp.status_code == 200:
                raw_list = resp.json()
                results = []
                for item in raw_list:
                    parsed = self._parse_ticker_data(item)
                    results.append(parsed)
                    self.cached_tickers_map[parsed["coin"]] = parsed
                    self.cached_tickers_map[parsed["symbol"]] = parsed
                self.cached_tickers = results
                self.cache_time = now
                return results
        except Exception as e:
            logger.warning(f"Batch ticker fetch error: {e}")

        # Fallback to cached if available
        if self.cached_tickers:
            return self.cached_tickers

        # Fallback to single fetch if batch endpoint fails
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
            return {"success": False, "message": "Mã coin không được để trống."}
        
        base = self.get_coin_base(clean)
        if base in self.watchlist:
            return {"success": False, "message": f"{base} đã có sẵn trong danh sách theo dõi."}

        # Check if valid on Binance Spot
        symbol = f"{base}USDT"
        test_url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        try:
            resp = self.client.get(test_url)
            if resp.status_code == 200:
                self.watchlist.append(base)
                self.active_status[base] = True
                self.save()
                return {"success": True, "message": f"Đã thêm thành công {base}/USDT vào Danh Sách Theo Dõi!", "coin": base}
            else:
                return {"success": False, "message": f"Mã '{base}' không được giao dịch trên Binance Spot (Cặp: {symbol})."}
        except Exception as e:
            return {"success": False, "message": f"Lỗi kết nối sàn Binance: {e}"}

    def remove_coin(self, raw_coin: str) -> Dict[str, Any]:
        base = self.get_coin_base(raw_coin.strip().upper())
        if base in self.watchlist:
            self.watchlist.remove(base)
            if base in self.active_status:
                del self.active_status[base]
            self.save()
            return {"success": True, "message": f"Đã xóa {base} khỏi danh sách theo dõi."}
        return {"success": False, "message": f"{base} không tìm thấy trong danh sách."}


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

    @staticmethod
    def format_volume(volume: float) -> str:
        if volume >= 1_000_000_000:
            return f"${volume / 1_000_000_000:.2f}B"
        elif volume >= 1_000_000:
            return f"${volume / 1_000_000:.1f}M"
        elif volume >= 1_000:
            return f"${volume / 1_000:.0f}K"
        return f"${volume:.0f}"

    def get_all_usdt_tickers(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and (now - self.all_tickers_cache_time < 90.0) and self.all_tickers_cache:
            return self.all_tickers_cache

        url = "https://api.binance.com/api/v3/ticker/24hr"
        try:
            resp = self.client.get(url)
            if resp.status_code == 200:
                raw_list = resp.json()
                results = []
                for item in raw_list:
                    symbol = item.get("symbol", "")
                    if not symbol.endswith("USDT"):
                        continue
                    # Ignore leveraged tokens (UP/DOWN/BEAR/BULL) and stablecoin pairs
                    base = self.get_coin_base(symbol)
                    if base in {"USDC", "FDUSD", "TUSD", "BUSD", "EUR", "DAI", "USDP", "AEUR"}:
                        continue
                    if any(symbol.endswith(suffix) for suffix in ["UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT"]):
                        continue
                    
                    price = float(item.get("lastPrice", 0))
                    if price <= 0:
                        continue
                    change_pct = float(item.get("priceChangePercent", 0))
                    quote_vol = float(item.get("quoteVolume", 0))
                    
                    results.append({
                        "symbol": symbol,
                        "coin": base,
                        "price": price,
                        "price_formatted": self.format_price(price),
                        "change_pct": round(change_pct, 2),
                        "quote_volume": quote_vol,
                        "volume_formatted": self.format_volume(quote_vol)
                    })
                
                # Sort descending by 24h quote volume
                results.sort(key=lambda x: x["quote_volume"], reverse=True)
                self.all_tickers_cache = results
                self.all_tickers_cache_time = now
                return results
        except Exception as e:
            logger.warning(f"Error fetching all 24hr tickers: {e}")

        return self.all_tickers_cache

    def search_coins(self, query: str = "", limit: int = 15) -> List[Dict[str, Any]]:
        all_tickers = self.get_all_usdt_tickers()
        q = (query or "").strip().upper()

        if not q:
            selected = all_tickers[:limit]
        else:
            exact = []
            starts = []
            contains = []
            for item in all_tickers:
                coin = item["coin"]
                if coin == q:
                    exact.append(item)
                elif coin.startswith(q):
                    starts.append(item)
                elif q in coin:
                    contains.append(item)
            selected = (exact + starts + contains)[:limit]

        out = []
        for item in selected:
            d = dict(item)
            d["in_watchlist"] = d["coin"] in self.watchlist
            out.append(d)
        return out

