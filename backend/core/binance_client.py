import os
import time
import math
import hmac
import hashlib
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
import requests

class BinanceFuturesClient:
    """
    Skill: Binance Futures Live Execution Adapter (Testnet & Real Money)
    Hỗ trợ kết nối chính thức tới sàn giao dịch Binance Futures:
    1. Chế độ Testnet (https://testnet.binancefuture.com) với vốn ảo miễn phí $1,000 - $15,000 USDT.
    2. Chế độ Real Money (https://fapi.binance.com) khi người dùng sẵn sàng trade tiền thật.
    3. Tự động kiểm tra bộ lọc sàn: MIN_NOTIONAL (>= 5 USDT), LOT_SIZE (stepSize), PRICE_FILTER (tickSize).
    4. Tự động thiết lập đòn bẩy (Leverage) và Ký quỹ cô lập (Isolated Margin).
    """
    TESTNET_URL = "https://testnet.binancefuture.com"
    REAL_URL = "https://fapi.binance.com"

    def __init__(
        self,
        mode: str = "BINANCE_TESTNET",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None
    ):
        self.mode = mode.upper()
        self.api_key = api_key or os.getenv("BINANCE_TESTNET_API_KEY", "") if "TESTNET" in self.mode else (api_key or os.getenv("BINANCE_REAL_API_KEY", ""))
        self.api_secret = api_secret or os.getenv("BINANCE_TESTNET_API_SECRET", "") if "TESTNET" in self.mode else (api_secret or os.getenv("BINANCE_REAL_API_SECRET", ""))
        self.base_url = self.TESTNET_URL if "TESTNET" in self.mode else self.REAL_URL
        
        # In-memory cache for exchange filters & connection tests
        self._exchange_info_cache: Optional[Dict[str, Any]] = None
        self._exchange_info_time: float = 0.0
        self._symbol_rules: Dict[str, Dict[str, Any]] = {}
        self._cached_conn: Optional[Dict[str, Any]] = None
        self._cached_conn_time: float = 0.0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_secret and len(self.api_key) >= 10 and len(self.api_secret) >= 10)

    def update_credentials(self, mode: str, api_key: str, api_secret: str):
        self.mode = mode.upper()
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.base_url = self.TESTNET_URL if "TESTNET" in self.mode else self.REAL_URL
        self._symbol_rules.clear()
        self._cached_conn = None
        self._cached_conn_time = 0.0

    def _sign_params(self, params: Dict[str, Any]) -> Tuple[str, str]:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = 5000
        query_string = urllib.parse.urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return query_string, signature

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        params = params or {}
        headers = {}

        if signed:
            if not self.is_configured:
                return {
                    "success": False,
                    "error": "MISSING_KEYS",
                    "message": "Chưa cấu hình API Key và Secret Key. Vui lòng lấy khóa tại https://testnet.binancefuture.com và cài đặt vào hệ thống."
                }
            headers["X-MBX-APIKEY"] = self.api_key
            query_str, signature = self._sign_params(params)
            url = f"{url}?{query_str}&signature={signature}"
            req_params = None
        else:
            req_params = params

        try:
            resp = requests.request(method, url, params=req_params, headers=headers, timeout=10)
            data = resp.json()
            if resp.status_code >= 400:
                err_code = data.get("code", resp.status_code)
                err_msg = data.get("msg", str(data))
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "code": err_code,
                    "error": f"BINANCE_ERROR_{err_code}",
                    "message": f"Lỗi từ Binance API ({err_code}): {err_msg}"
                }
            return {"success": True, "data": data}
        except requests.exceptions.Timeout:
            return {"success": False, "error": "TIMEOUT", "message": "Hết thời gian chờ phản hồi từ máy chủ Binance (Timeout)."}
        except Exception as e:
            return {"success": False, "error": "NETWORK_ERROR", "message": f"Lỗi kết nối máy chủ Binance: {str(e)}"}

    def test_connection(self, force: bool = False) -> Dict[str, Any]:
        """
        Kiểm tra độ trễ mạng và xác thực khóa API kết nối tới Binance Futures (kèm cache 60s để tăng tốc tải trang).
        """
        now = time.time()
        if not force and self._cached_conn and (now - self._cached_conn_time < 60.0):
            return self._cached_conn

        # 1. Kiểm tra Ping công khai
        start_t = time.time()
        time_res = self._request("GET", "/fapi/v1/time", signed=False)
        latency_ms = int((time.time() - start_t) * 1000)
        if not time_res.get("success"):
            return {
                "success": False,
                "latency_ms": latency_ms,
                "message": f"Không thể kết nối máy chủ Binance: {time_res.get('message')}"
            }

        # 2. Nếu chưa có API key, thông báo trạng thái sẵn sàng nhập key
        if not self.is_configured:
            return {
                "success": True,
                "is_configured": False,
                "latency_ms": latency_ms,
                "mode": self.mode,
                "base_url": self.base_url,
                "message": f"Kết nối máy chủ Binance OK ({latency_ms}ms). Chưa cài đặt API Key & Secret Key."
            }

        # 3. Kiểm tra tài khoản bằng khóa API
        acc_res = self._request("GET", "/fapi/v2/account", signed=True)
        if not acc_res.get("success"):
            return {
                "success": False,
                "is_configured": True,
                "latency_ms": latency_ms,
                "error": acc_res.get("error"),
                "message": acc_res.get("message")
            }

        acc_data = acc_res.get("data", {})
        usdt_asset = next((a for a in acc_data.get("assets", []) if a.get("asset") == "USDT"), {})
        wallet_balance = float(usdt_asset.get("walletBalance", 0.0))
        available_balance = float(usdt_asset.get("availableBalance", 0.0))
        unrealized_pnl = float(usdt_asset.get("unrealizedProfit", 0.0))

        # Tính tổng giá trị danh mục quy đổi USD (khớp Margin Balance trên Binance web demo)
        total_equity_usd = wallet_balance
        assets_breakdown = {}
        for a in acc_data.get("assets", []):
            wb = float(a.get("walletBalance", 0.0))
            if wb > 0:
                sym_asset = a.get("asset")
                assets_breakdown[sym_asset] = wb
                if sym_asset == "USDC":
                    total_equity_usd += wb
                elif sym_asset not in ["USDT", "USDC"]:
                    try:
                        ticker_res = self._request("GET", "/fapi/v1/ticker/price", params={"symbol": f"{sym_asset}USDT"})
                        if ticker_res.get("success"):
                            p = float(ticker_res["data"].get("price", 0.0))
                            total_equity_usd += wb * p
                    except Exception:
                        pass

        mode_label = "Binance Futures Testnet (Mô phỏng chính thức)" if "TESTNET" in self.mode else "Binance Futures Real (Tiền thật)"
        conn_res = {
            "success": True,
            "is_configured": True,
            "mode": self.mode,
            "mode_label": mode_label,
            "base_url": self.base_url,
            "latency_ms": latency_ms,
            "wallet_balance": round(wallet_balance, 2),
            "available_balance": round(available_balance, 2),
            "total_equity_usd": round(total_equity_usd, 2),
            "assets_breakdown": assets_breakdown,
            "unrealized_pnl": round(unrealized_pnl, 2),
            "total_open_positions": len([p for p in acc_data.get("positions", []) if float(p.get("positionAmt", 0)) != 0]),
            "message": f"Xác thực thành công! Tổng Margin Balance: ${total_equity_usd:,.2f} USD (Gồm: ${available_balance:,.2f} USDT khả dụng để giao dịch, ${assets_breakdown.get('USDC', 0):,.2f} USDC, {assets_breakdown.get('BTC', 0)} BTC)."
        }
        self._cached_conn = conn_res
        self._cached_conn_time = now
        return conn_res

    def get_wallet_balance(self) -> Dict[str, Any]:
        """
        Lấy số dư ví USDT và lợi nhuận chưa chốt thời gian thực.
        """
        if not self.is_configured:
            return {"success": False, "wallet_balance": 0.0, "available_balance": 0.0, "unrealized_pnl": 0.0}

        res = self._request("GET", "/fapi/v2/balance", signed=True)
        if not res.get("success"):
            return res

        balances = res.get("data", [])
        usdt = next((b for b in balances if b.get("asset") == "USDT"), {})
        total_equity_usd = 0.0
        assets_breakdown = {}
        for b in balances:
            bal = float(b.get("balance", 0.0))
            if bal > 0:
                asset_name = b.get("asset")
                assets_breakdown[asset_name] = bal
                if asset_name in ["USDT", "USDC"]:
                    total_equity_usd += bal
                else:
                    try:
                        ticker_res = self._request("GET", "/fapi/v1/ticker/price", params={"symbol": f"{asset_name}USDT"})
                        if ticker_res.get("success"):
                            p = float(ticker_res["data"].get("price", 0.0))
                            total_equity_usd += bal * p
                    except Exception:
                        pass

        return {
            "success": True,
            "wallet_balance": float(usdt.get("balance", 0.0)),
            "available_balance": float(usdt.get("withdrawAvailable", usdt.get("balance", 0.0))),
            "total_equity_usd": round(total_equity_usd, 2),
            "assets_breakdown": assets_breakdown,
            "unrealized_pnl": float(usdt.get("crossUnPnl", 0.0))
        }

    def get_symbol_rules(self, symbol: str) -> Dict[str, Any]:
        """
        Lấy các quy tắc bước giá (tickSize), bước khối lượng (stepSize) và giá trị lệnh tối thiểu (minNotional).
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        now = time.time()
        if not self._exchange_info_cache or (now - self._exchange_info_time > 3600):
            res = self._request("GET", "/fapi/v1/exchangeInfo", signed=False)
            if res.get("success"):
                self._exchange_info_cache = res.get("data", {})
                self._exchange_info_time = now

        if sym in self._symbol_rules:
            return self._symbol_rules[sym]

        rules = {
            "symbol": sym,
            "tick_size": 0.0001,
            "price_precision": 4,
            "step_size": 1.0,
            "qty_precision": 0,
            "min_qty": 1.0,
            "min_notional": 5.0
        }

        if self._exchange_info_cache:
            sym_info = next((s for s in self._exchange_info_cache.get("symbols", []) if s.get("symbol") == sym), None)
            if sym_info:
                filters = sym_info.get("filters", [])
                lot_f = next((f for f in filters if f.get("filterType") == "LOT_SIZE"), {})
                price_f = next((f for f in filters if f.get("filterType") == "PRICE_FILTER"), {})
                notional_f = next((f for f in filters if f.get("filterType") == "MIN_NOTIONAL"), {})

                tick_str = price_f.get("tickSize", "0.0001")
                step_str = lot_f.get("stepSize", "1.0")
                
                rules["tick_size"] = float(tick_str)
                rules["step_size"] = float(step_str)
                rules["min_qty"] = float(lot_f.get("minQty", "1.0"))
                rules["min_notional"] = float(notional_f.get("notional", "5.0"))

                # Tính số chữ số thập phân
                if "." in tick_str:
                    rules["price_precision"] = len(tick_str.rstrip("0").split(".")[1])
                else:
                    rules["price_precision"] = 0

                if "." in step_str:
                    rules["qty_precision"] = len(step_str.rstrip("0").split(".")[1])
                else:
                    rules["qty_precision"] = 0

        self._symbol_rules[sym] = rules
        return rules

    def format_quantity(self, symbol: str, target_dollars: float, current_price: float) -> float:
        """
        Tính toán số lượng coin chuẩn hóa theo stepSize của Binance, đảm bảo không bị từ chối do lẻ số hoặc dưới minNotional.
        """
        rules = self.get_symbol_rules(symbol)
        min_notional = rules.get("min_notional", 5.0)

        # Đảm bảo tổng giá trị vị thế đạt tối thiểu min_notional (cộng thêm 10% biên an toàn = 5.5 USDT)
        eff_dollars = max(target_dollars, min_notional * 1.1)
        raw_qty = eff_dollars / current_price if current_price > 0 else 0.0

        step = rules.get("step_size", 1.0)
        precision = rules.get("qty_precision", 0)

        if step > 0:
            units = math.floor(raw_qty / step)
            rounded_qty = round(units * step, precision)
        else:
            rounded_qty = round(raw_qty, precision)

        # Đảm bảo >= min_qty
        min_qty = rules.get("min_qty", 1.0)
        if rounded_qty < min_qty:
            rounded_qty = min_qty

        # Đảm bảo giá trị thực tế sau làm tròn vẫn >= min_notional
        if rounded_qty * current_price < min_notional:
            rounded_qty += step
            rounded_qty = round(rounded_qty, precision)

        return rounded_qty

    def format_price(self, symbol: str, price: float) -> float:
        """
        Chuẩn hóa giá theo tickSize và price_precision của sàn Binance.
        """
        rules = self.get_symbol_rules(symbol)
        tick = rules.get("tick_size", 0.0001)
        prec = rules.get("price_precision", 4)
        if tick > 0:
            units = round(price / tick)
            return round(units * tick, prec)
        return round(price, prec)

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """
        Làm tròn số lượng coin theo stepSize và qty_precision của sàn.
        """
        rules = self.get_symbol_rules(symbol)
        step = rules.get("step_size", 1.0)
        prec = rules.get("qty_precision", 0)
        if step > 0:
            units = math.floor(quantity / step)
            rounded = round(units * step, prec)
        else:
            rounded = round(quantity, prec)
        if prec == 0:
            return float(int(rounded))
        return rounded

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Thiết lập đòn bẩy trên sàn Binance Futures trước khi đặt lệnh.
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"
        return self._request("POST", "/fapi/v1/leverage", {"symbol": sym, "leverage": int(leverage)}, signed=True)

    def set_margin_type(self, symbol: str, margin_type: str = "ISOLATED") -> Dict[str, Any]:
        """
        Thiết lập chế độ Ký quỹ Cô lập (ISOLATED) để bảo vệ tài khoản khỏi cháy chéo.
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"
        res = self._request("POST", "/fapi/v1/marginType", {"symbol": sym, "marginType": margin_type.upper()}, signed=True)
        # Mã lỗi -4046: "No need to change margin type" (đã là ISOLATED rồi) -> Coi như thành công
        if not res.get("success") and res.get("code") == -4046:
            return {"success": True, "message": "Đã ở chế độ ký quỹ cô lập ISOLATED."}
        return res

    def place_market_order(self, symbol: str, side: str, quantity: float, reduce_only: bool = False) -> Dict[str, Any]:
        """
        Gửi lệnh Market Order trực tiếp lên sàn Binance Futures (Hỗ trợ mở vị thế hoặc đóng vị thế reduceOnly).
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        side = side.upper()
        order_side = "BUY" if side in ["LONG", "BUY"] else "SELL"
        qty = self.round_quantity(sym, quantity)
        if qty <= 0:
            qty = quantity

        params = {
            "symbol": sym,
            "side": order_side,
            "type": "MARKET",
            "quantity": qty
        }
        if reduce_only:
            params["reduceOnly"] = "true"

        res = self._request("POST", "/fapi/v1/order", params=params, signed=True)
        if not res.get("success"):
            return res

        data = res.get("data", {})
        avg_price = float(data.get("avgPrice", 0.0))
        exec_qty_raw = float(data.get("executedQty", 0.0))
        orig_qty_raw = float(data.get("origQty", qty))
        executed_qty = exec_qty_raw if exec_qty_raw > 0 else orig_qty_raw
        order_id = str(data.get("orderId", ""))

        return {
            "success": True,
            "order_id": order_id,
            "symbol": sym,
            "side": order_side,
            "executed_qty": executed_qty,
            "avg_price": avg_price,
            "status": data.get("status", "FILLED"),
            "raw": data
        }

    def cancel_all_orders(self, symbol: str) -> Dict[str, Any]:
        """
        Hủy toàn bộ lệnh chờ thông thường và lệnh Algo (TP/SL) trên sàn Binance cho symbol này.
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        res1 = self._request("DELETE", "/fapi/v1/allOpenOrders", params={"symbol": sym}, signed=True)
        res2 = self._request("DELETE", "/fapi/v1/algoOpenOrders", params={"symbol": sym}, signed=True)
        return {"standard": res1, "algo": res2}

    def place_tp_sl_orders(self, symbol: str, side: str, tp_price: float, sl_price: float, quantity: Optional[float] = None) -> Dict[str, Any]:
        """
        Đặt lệnh Chốt Lời (Take Profit) và Cắt Lỗ (Stop Loss) trực tiếp trên sàn Binance Futures
        thông qua Binance Futures Algo Order API (/fapi/v1/algoOrder).
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        close_side = "SELL" if side.upper() in ["LONG", "BUY"] else "BUY"
        formatted_tp = self.format_price(sym, tp_price)
        formatted_sl = self.format_price(sym, sl_price)

        results = {"tp": None, "sl": None}

        # 1. Đặt Take Profit (TAKE_PROFIT_MARKET)
        if formatted_tp > 0:
            tp_params = {
                "algoType": "CONDITIONAL",
                "symbol": sym,
                "side": close_side,
                "type": "TAKE_PROFIT_MARKET",
                "triggerPrice": formatted_tp,
                "workingType": "MARK_PRICE",
                "closePosition": "true"
            }
            tp_res = self._request("POST", "/fapi/v1/algoOrder", params=tp_params, signed=True)
            if not tp_res.get("success") and quantity and quantity > 0:
                tp_params.pop("closePosition", None)
                tp_params["quantity"] = self.round_quantity(sym, quantity)
                tp_params["reduceOnly"] = "true"
                tp_res = self._request("POST", "/fapi/v1/algoOrder", params=tp_params, signed=True)
            results["tp"] = tp_res

        # 2. Đặt Stop Loss (STOP_MARKET)
        if formatted_sl > 0:
            sl_params = {
                "algoType": "CONDITIONAL",
                "symbol": sym,
                "side": close_side,
                "type": "STOP_MARKET",
                "triggerPrice": formatted_sl,
                "workingType": "MARK_PRICE",
                "closePosition": "true"
            }
            sl_res = self._request("POST", "/fapi/v1/algoOrder", params=sl_params, signed=True)
            if not sl_res.get("success") and quantity and quantity > 0:
                sl_params.pop("closePosition", None)
                sl_params["quantity"] = self.round_quantity(sym, quantity)
                sl_params["reduceOnly"] = "true"
                sl_res = self._request("POST", "/fapi/v1/algoOrder", params=sl_params, signed=True)
            results["sl"] = sl_res

        return results

    def close_position(self, symbol: str, side: Optional[str] = None, quantity: Optional[float] = None) -> Dict[str, Any]:
        """
        Đóng vị thế an toàn trên sàn Binance Futures:
        1. Hủy toàn bộ lệnh chờ (TP/SL) của cặp tiền này để tránh kích hoạt ngoài ý muốn.
        2. Truy vấn trực tiếp vị thế thực tế trên Binance (positionRisk).
        3. Nếu có vị thế trên sàn: Lấy chính xác khối lượng positionAmt và gửi lệnh đối ứng reduceOnly=True.
        4. Nếu không có vị thế trên sàn (đã đóng trước đó): Báo thành công, không bị lỗi.
        """
        sym = symbol.upper()
        if not sym.endswith("USDT"):
            sym = f"{sym}USDT"

        # 1. Hủy tất cả các lệnh mở (TP/SL) của symbol này trên sàn
        try:
            self.cancel_all_orders(sym)
        except Exception:
            pass

        # 2. Kiểm tra vị thế thực tế trên sàn Binance
        try:
            open_positions = self.get_open_positions()
            clean_sym = sym.replace("USDT", "")
            active_pos = next((p for p in open_positions if p.get("symbol") == clean_sym), None)

            if active_pos:
                actual_shares = active_pos.get("shares", 0.0)
                pos_side = active_pos.get("side", "LONG")
                close_side = "SELL" if pos_side.upper() == "LONG" else "BUY"
                formatted_qty = self.round_quantity(sym, actual_shares)
                if formatted_qty <= 0:
                    formatted_qty = actual_shares
                return self.place_market_order(sym, close_side, formatted_qty, reduce_only=True)
        except Exception as e:
            print(f"[BinanceClient] Lỗi truy vấn vị thế thực tế khi đóng: {e}")

        # Nếu trên sàn không thấy vị thế qua positionRisk nhưng caller truyền quantity > 0
        if quantity and quantity > 0 and side:
            close_side = "SELL" if side.upper() in ["LONG", "BUY"] else "BUY"
            formatted_qty = self.round_quantity(sym, quantity)
            if formatted_qty > 0:
                return self.place_market_order(sym, close_side, formatted_qty, reduce_only=True)

        return {"success": True, "message": f"Không có vị thế đang mở trên sàn Binance cho {sym}."}

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các vị thế đang mở thực tế trên Binance Futures.
        """
        res = self._request("GET", "/fapi/v2/positionRisk", signed=True)
        if not res.get("success"):
            return []

        active = []
        for p in res.get("data", []):
            amt = float(p.get("positionAmt", 0.0))
            if amt != 0:
                active.append({
                    "symbol": p.get("symbol", "").replace("USDT", ""),
                    "market_id": f"crypto_{p.get('symbol')}",
                    "side": "LONG" if amt > 0 else "SHORT",
                    "shares": abs(amt),
                    "entry_price": float(p.get("entryPrice", 0.0)),
                    "mark_price": float(p.get("markPrice", 0.0)),
                    "unrealized_pnl": float(p.get("unRealizedProfit", 0.0)),
                    "liquidation_price": float(p.get("liquidationPrice", 0.0)),
                    "leverage": int(p.get("leverage", 1)),
                    "isolated": p.get("isolated", True)
                })
        return active
