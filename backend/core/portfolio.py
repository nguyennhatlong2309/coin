import json
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from ..config import (
    PORTFOLIO_FILE, 
    INITIAL_CAPITAL, 
    DEFAULT_LEVERAGE, 
    MAX_LEVERAGE,
    DEFAULT_SL_PERCENT, 
    DEFAULT_TP_PERCENT, 
    MAINTENANCE_MARGIN_BUFFER
)

def get_trading_day_vn(now_dt: Optional[datetime] = None) -> str:
    """
    Xác định ngày giao dịch theo giờ Việt Nam (UTC+7) tương ứng với nến ngày Binance (reset lúc 07:00 AM VN / 00:00 UTC).
    Ví dụ:
    - 21:00 tối ngày 21/10/2026 -> Ngày giao dịch 2026-10-21.
    - 05:00 sáng ngày 22/10/2026 -> Vẫn thuộc ngày giao dịch 2026-10-21 (trước 07:00).
    - 07:01 sáng ngày 22/10/2026 -> Bắt đầu ngày giao dịch mới 2026-10-22.
    """
    vn_tz = timezone(timedelta(hours=7))
    dt = now_dt or datetime.now(vn_tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=vn_tz)
    else:
        dt = dt.astimezone(vn_tz)

    if dt.hour < 7:
        trade_dt = dt - timedelta(days=1)
    else:
        trade_dt = dt
    return trade_dt.strftime("%Y-%m-%d")

def normalize_price_precision(price: float) -> int:
    """
    Xác định số chữ số thập phân tối ưu theo độ lớn giá để tránh lỗi làm tròn triệt tiêu
    trên các đồng coin có giá trị siêu nhỏ như PEPE ($0.000004):
    - price >= 1000: 2 số thập phân (e.g. BTC $68,450.50)
    - 1 <= price < 1000: 4 số thập phân (e.g. SOL $154.2500)
    - 0.01 <= price < 1: 6 số thập phân (e.g. DOGE $0.142500)
    - 0.0001 <= price < 0.01: 8 số thập phân
    - price < 0.0001: 10 số thập phân (e.g. PEPE $0.0000041600)
    """
    if price >= 1000.0:
        return 2
    elif price >= 1.0:
        return 4
    elif price >= 0.01:
        return 6
    elif price >= 0.0001:
        return 8
    else:
        return 10

class PortfolioManager:
    def __init__(self):
        self.file_path = PORTFOLIO_FILE
        self.state = {
            "cash_balance": INITIAL_CAPITAL,
            "realized_pnl": 0.0,
            "open_positions": {}, # {market_id: {...}}
            "trades_history": [],
            "thought_logs": [],
            "last_updated": time.time()
        }
        self.load()

        # Khởi tạo kết nối sàn Binance Futures (Hỗ trợ Testnet & Real Money)
        try:
            from .binance_client import BinanceFuturesClient
            from ..config import TRADING_MODE, BINANCE_TESTNET_API_KEY, BINANCE_TESTNET_API_SECRET, BINANCE_REAL_API_KEY, BINANCE_REAL_API_SECRET
            mode = TRADING_MODE
            api_k = BINANCE_TESTNET_API_KEY if "TESTNET" in mode else BINANCE_REAL_API_KEY
            api_s = BINANCE_TESTNET_API_SECRET if "TESTNET" in mode else BINANCE_REAL_API_SECRET
            self.binance_client = BinanceFuturesClient(mode=mode, api_key=api_k, api_secret=api_s)
        except Exception as e:
            print(f"[Portfolio] Lỗi khởi tạo Binance client: {e}")
            self.binance_client = None

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception:
                self.save()
        else:
            self.save()

    def save(self):
        self.state["last_updated"] = time.time()
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def reset(self, initial_capital: Optional[float] = None):
        cap = float(initial_capital) if (initial_capital is not None and initial_capital > 0) else INITIAL_CAPITAL
        curr_day = get_trading_day_vn()
        self.state = {
            "cash_balance": round(cap, 2),
            "realized_pnl": 0.0,
            "open_positions": {},
            "trades_history": [],
            "thought_logs": [{
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "agent": "System",
                "level": "SUCCESS",
                "message": f"Đặt lại danh mục thành công. Vốn khởi tạo: ${cap:,.2f} USD."
            }],
            "daily_metrics": {
                "trading_day": curr_day,
                "start_equity": round(cap, 2),
                "target_profit_pct": 20.0,
                "max_drawdown_pct": 8.0,
                "circuit_breaker_active": False,
                "target_reached": False,
                "last_reset_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "last_updated": time.time()
        }
        self.save()
        return self.get_summary()

    def _ensure_daily_metrics(self, total_equity: float) -> Dict[str, Any]:
        """
        Quản lý và tính toán chỉ số Lãi/Lỗ trong ngày (Daily PnL / Daily ROI):
        - Reset tự động lúc 07:00 AM giờ Việt Nam (00:00 UTC theo nến ngày Binance).
        - Giám sát Cầu Chì An Toàn Ngày (Daily Circuit Breaker): Chặn mở vị thế nếu lỗ ngày chạm -8.0%.
        - Giám sát Mục Tiêu Lợi Nhuận Ngày (Daily Target): Kích hoạt Chế Độ Bảo Vệ Thành Quả nếu đạt +20.0%.
        """
        curr_day = get_trading_day_vn()
        daily = self.state.get("daily_metrics") or {}

        # Nếu chưa có metrics hoặc đã bước sang ngày giao dịch mới (sau 07:00 AM VN)
        if not daily or str(daily.get("trading_day", "")) < curr_day:
            if daily and daily.get("trading_day"):
                prev_day = daily.get("trading_day")
                prev_start = daily.get("start_equity", INITIAL_CAPITAL)
                prev_pnl = total_equity - prev_start
                prev_roi = (prev_pnl / prev_start * 100) if prev_start > 0 else 0.0
                self.log_thought(
                    "Risk Guard",
                    "SUCCESS" if prev_pnl >= 0 else "WARN",
                    f"📅 [Kết Chuyển Ngày {prev_day}] Chốt sổ ngày cũ (07:00 VN). PnL ngày: {prev_pnl:+,.2f} USD ({prev_roi:+.1f}%). Vốn mở ngày mới: ${total_equity:,.2f} USD."
                )

            start_eq = round(total_equity, 2) if (total_equity > 0) else INITIAL_CAPITAL
            # Nếu khởi tạo lần đầu cho ngày hôm nay và total_equity đã có lời từ vốn gốc $10
            if not daily and INITIAL_CAPITAL > 0:
                start_eq = INITIAL_CAPITAL

            daily = {
                "trading_day": curr_day,
                "start_equity": start_eq,
                "target_profit_pct": 20.0,
                "max_drawdown_pct": 8.0,
                "circuit_breaker_active": False,
                "target_reached": False,
                "profit_lock_active": False,
                "auto_lock_on_target": True,
                "last_reset_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.state["daily_metrics"] = daily
            self.save()

        start_eq = daily.get("start_equity", INITIAL_CAPITAL)
        if start_eq <= 0:
            start_eq = INITIAL_CAPITAL

        daily.setdefault("profit_lock_active", False)
        daily.setdefault("auto_lock_on_target", True)

        daily_pnl = round(total_equity - start_eq, 2)
        daily_roi = round((daily_pnl / start_eq) * 100, 2) if start_eq > 0 else 0.0
        target_pct = daily.get("target_profit_pct", 20.0)
        max_dd_pct = daily.get("max_drawdown_pct", 8.0)

        # Kiểm tra Cầu Chì An Toàn Ngày (Daily Circuit Breaker)
        if daily_roi <= -max_dd_pct and not daily.get("circuit_breaker_active"):
            daily["circuit_breaker_active"] = True
            self.log_thought(
                "Risk Guard",
                "WARN",
                f"🚨 [CẦU CHÌ AN TOÀN NGÀY ĐÃ NGẮT] Thua lỗ hôm nay chạm ngưỡng giới hạn: {daily_roi:+.1f}% (Lỗ -${abs(daily_pnl):,.2f} USD trên vốn ngày ${start_eq:,.2f}). Tự động ngắt mở lệnh mới đến 07:00 sáng mai!"
            )
            self.save()
        elif daily_roi > -max_dd_pct and daily.get("circuit_breaker_active"):
            # Tự động gỡ bỏ cầu chì khi tài khoản đã hồi phục trở lại ngưỡng an toàn hoặc có lãi
            daily["circuit_breaker_active"] = False
            self.log_thought(
                "Risk Guard",
                "SUCCESS",
                f"✅ [TỰ ĐỘNG MỞ LẠI CẦU CHÌ] Tài khoản đã hồi phục an toàn: PnL {daily_roi:+.1f}% (+${daily_pnl:,.2f} USD). Mở khóa tiếp tục săn mồi!"
            )
            self.save()

        # Kiểm tra Mục Tiêu Lợi Nhuận Ngày (Daily Profit Target Reached)
        if daily_roi >= target_pct and not daily.get("target_reached"):
            daily["target_reached"] = True
            daily["profit_lock_active"] = True
            self.log_thought(
                "Risk Guard",
                "SUCCESS",
                f"🏆 [ĐẠT MỤC TIÊU LỢI NHUẬN NGÀY] Lãi hôm nay đã đạt {daily_roi:+.1f}% (+${daily_pnl:,.2f} USD)! "
                f"KÍCH HOẠT LUẬT KHÓA LÃI BẢO VỆ VỐN: Tự động ngắt toàn bộ lệnh mở mới đến 07:00 sáng mai để bảo toàn 100% lợi nhuận vào két!"
            )
            self.save()

        daily_summary = dict(daily)
        daily_summary["daily_pnl"] = daily_pnl
        daily_summary["daily_roi_percent"] = daily_roi
        daily_summary["current_equity"] = round(total_equity, 2)
        daily_summary["reset_hour_vn"] = "07:00 AM VN (00:00 UTC)"
        return daily_summary

    def log_thought(self, agent: str, level: str, message: str):
        log_entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "agent": agent,
            "level": level, # INFO, SUCCESS, WARN, TRADE
            "message": message
        }
        self.state["thought_logs"].insert(0, log_entry)
        # Keep only latest 100 logs
        self.state["thought_logs"] = self.state["thought_logs"][:100]
        self.save()

    def get_summary(self) -> Dict[str, Any]:
        cash = self.state["cash_balance"]
        positions_value = 0.0
        unrealized_pnl = 0.0

        for pos in self.state["open_positions"].values():
            outcome = pos.get("outcome", "LONG")
            shares = pos.get("shares", 0.0)
            curr_p = pos.get("current_price", 0.0)
            entry_p = pos.get("entry_price", 0.0)
            margin = pos.get("margin", pos.get("cost_basis", shares * entry_p))

            if outcome == "SHORT" or outcome == "NO":
                pnl = (entry_p - curr_p) * shares
            else:
                pnl = (curr_p - entry_p) * shares

            # Current equity value of position cannot be less than 0
            val = max(0.0, margin + pnl)
            positions_value += val
            unrealized_pnl += pnl

        total_equity = cash + positions_value
        total_pnl = (total_equity - INITIAL_CAPITAL)
        pnl_percent = (total_pnl / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0

        trades = self.state["trades_history"]
        win_count = sum(1 for t in trades if t.get("pnl", 0) > 0)
        total_closed = sum(1 for t in trades if "pnl" in t and "CLOSE" in t.get("action", ""))
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0

        formatted_trades = []
        for t in trades[:30]:
            trade_copy = dict(t)
            if "price" not in trade_copy or trade_copy["price"] is None:
                trade_copy["price"] = trade_copy.get("exit_price") or trade_copy.get("entry_price") or 0.0
            if "total_amount" not in trade_copy or trade_copy["total_amount"] is None:
                trade_copy["total_amount"] = trade_copy.get("margin") or 0.0
            if "reasoning" not in trade_copy or not trade_copy["reasoning"]:
                r = trade_copy.get("reason", "MANUAL")
                pnl = trade_copy.get("pnl", 0.0)
                pnl_pct = trade_copy.get("pnl_percent", 0.0)
                trade_copy["reasoning"] = f"Đóng vị thế ({r}): PnL {pnl:+,.2f} USD ({pnl_pct:+.1f}%)"
            formatted_trades.append(trade_copy)

        trading_mode = self.binance_client.mode if self.binance_client else "PAPER"
        binance_configured = self.binance_client.is_configured if self.binance_client else False

        return {
            "cash_balance": round(self.state["cash_balance"], 2),
            "positions_value": round(positions_value, 2),
            "total_equity": round(total_equity, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
            "realized_pnl": round(self.state.get("realized_pnl", 0.0), 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "open_positions": list(self.state["open_positions"].values()),
            "total_open_count": len(self.state["open_positions"]),
            "trades_count": len(trades),
            "win_rate": round(win_rate, 1),
            "recent_trades": formatted_trades,
            "thought_logs": self.state["thought_logs"][:30],
            "trading_memory": self._get_memory_summary_safe(),
            "trading_mode": trading_mode,
            "binance_configured": binance_configured,
            "binance_mode": trading_mode,
            "current_session": self._get_session_summary_safe(),
            "daily_metrics": self._ensure_daily_metrics(total_equity)
        }

    def _get_session_summary_safe(self) -> Dict[str, Any]:
        try:
            from .session_manager import get_current_session
            return get_current_session()
        except Exception:
            return {
                "id": "UNKNOWN",
                "name": "Phiên Tiêu Chuẩn",
                "badge": "⏱️ PHIÊN TIÊU CHUẨN",
                "risk_mode": "BALANCED"
            }

    def _get_memory_summary_safe(self) -> Dict[str, Any]:
        try:
            from .trading_memory import TradingMemoryManager
            return TradingMemoryManager().get_summary()
        except Exception:
            return {"total_reflections": 0, "win_rate": 0.0, "recent_reflections": []}

    def get_trades_history(
        self,
        limit: int = 50,
        offset: int = 0,
        symbol: Optional[str] = None,
        filter_type: Optional[str] = "all"
    ) -> Dict[str, Any]:
        trades = self.state.get("trades_history", [])
        
        # Lấy danh sách toàn bộ các đồng coin đã từng khớp lệnh
        symbols_set = set()
        for t in trades:
            s = t.get("symbol")
            if not s and t.get("question"):
                s = t["question"].split(" ")[0].replace("/USDT", "").replace("crypto_", "")
            if s:
                symbols_set.add(s.upper())
        available_symbols = sorted(list(symbols_set))

        clean_sym = symbol.strip().upper() if symbol and symbol.strip().upper() != "ALL" else None
        clean_filter = (filter_type or "all").lower().strip()

        filtered = []
        for t in trades:
            sym = t.get("symbol")
            if not sym and t.get("question"):
                sym = t["question"].split(" ")[0].replace("/USDT", "").replace("crypto_", "")
            sym_upper = (sym or "").upper()

            if clean_sym and sym_upper != clean_sym:
                continue

            action = (t.get("action") or "").upper()
            is_close = "CLOSE" in action
            is_open = "OPEN" in action
            pnl = t.get("pnl")

            if clean_filter == "close" and not is_close:
                continue
            elif clean_filter == "open" and not is_open:
                continue
            elif clean_filter == "win":
                if not is_close or pnl is None or pnl <= 0:
                    continue
            elif clean_filter == "loss":
                if not is_close or pnl is None or pnl >= 0:
                    continue

            trade_copy = dict(t)
            if "price" not in trade_copy or trade_copy["price"] is None:
                trade_copy["price"] = trade_copy.get("exit_price") or trade_copy.get("entry_price") or 0.0
            if "total_amount" not in trade_copy or trade_copy["total_amount"] is None:
                trade_copy["total_amount"] = trade_copy.get("margin") or 0.0
            if "reasoning" not in trade_copy or not trade_copy["reasoning"]:
                r = trade_copy.get("reason", "MANUAL")
                p = trade_copy.get("pnl", 0.0)
                p_pct = trade_copy.get("pnl_percent", 0.0)
                trade_copy["reasoning"] = f"Đóng vị thế ({r}): PnL {p:+,.2f} USD ({p_pct:+.1f}%)"
            filtered.append(trade_copy)

        win_count = sum(1 for t in filtered if t.get("pnl") is not None and t.get("pnl") > 0)
        loss_count = sum(1 for t in filtered if t.get("pnl") is not None and t.get("pnl") < 0)
        total_pnl = sum(t.get("pnl", 0.0) for t in filtered if t.get("pnl") is not None and "CLOSE" in (t.get("action") or ""))
        total_closed = win_count + loss_count
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0

        total_filtered = len(filtered)
        if limit and limit > 0:
            sliced = filtered[offset : offset + limit]
        else:
            sliced = filtered[offset:]

        return {
            "total_count": len(trades),
            "filtered_count": total_filtered,
            "limit": limit,
            "offset": offset,
            "symbols": available_symbols,
            "trades": sliced,
            "stats": {
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": round(win_rate, 1),
                "realized_pnl": round(total_pnl, 2)
            }
        }

    def execute_trade(
        self,
        market_id: str,
        question: str,
        outcome: str,
        price: float,
        stake_amount: float,
        reasoning: str,
        asset_type: str = "crypto",
        leverage: int = DEFAULT_LEVERAGE,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        symbol: Optional[str] = None,
        signal_dna: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Executes a mock trade supporting Margin Leverage (1x to 10x),
        Stop-Loss, Take-Profit, and Liquidation thresholds.
        """
        if stake_amount <= 0 or stake_amount > self.state["cash_balance"] or price <= 0:
            return False

        clean_symbol = (symbol or question.split("/")[0].replace("crypto_", "").strip()).upper()

        # Hard Risk Guard: Prevent duplicate positions for the same crypto symbol
        if asset_type == "crypto":
            for existing_pos in self.state["open_positions"].values():
                if existing_pos.get("symbol", "").upper() == clean_symbol:
                    self.log_thought(
                        "Risk Guard",
                        "WARN",
                        f"Từ chối mở lệnh: Đồng {clean_symbol} hiện đã có vị thế mở ({existing_pos.get('outcome')} {existing_pos.get('leverage')}x). Chặn mở trùng vị thế để bảo toàn vốn."
                    )
                    return False

            # Hard Risk Guard: Kiểm tra Cầu Chì Ngày và Luật Khóa Lợi Nhuận Ngày
            daily = self.state.get("daily_metrics") or {}
            if daily.get("profit_lock_active", False):
                self.log_thought(
                    "Risk Guard",
                    "WARN",
                    f"🔒 [LUẬT KHÓA LÃI BẢO VỆ VỐN] Từ chối mở lệnh {clean_symbol}: Đã đạt mục tiêu lợi nhuận ngày hôm nay (+{daily.get('target_profit_pct', 20.0)}%). Hệ thống khóa mở lệnh mới đến 07:00 sáng mai để bảo toàn 100% tiền lãi vào két!"
                )
                return False
            if daily.get("circuit_breaker_active", False):
                self.log_thought(
                    "Risk Guard",
                    "WARN",
                    f"🚨 [CẦU CHÌ AN TOÀN NGẮT] Từ chối mở lệnh {clean_symbol}: Thua lỗ hôm nay chạm giới hạn (-{daily.get('max_drawdown_pct', 8.0)}%). Dừng mở lệnh mới đến 07:00 sáng mai!"
                )
                return False

        leverage = max(1, min(MAX_LEVERAGE, leverage))
        margin = round(stake_amount, 2)
        position_size = round(margin * leverage, 2)

        # Precision handling for shares
        if asset_type == "crypto":
            if price > 100:
                shares = round(position_size / price, 6)
            elif price > 1:
                shares = round(position_size / price, 4)
            else:
                shares = round(position_size / price, 2)
        else:
            shares = round(position_size / price, 2)

        if shares <= 0:
            return False

        # Deduct margin from cash
        self.state["cash_balance"] = round(self.state["cash_balance"] - margin, 2)

        prec = normalize_price_precision(price)

        # Calculate Liquidation Price based on leverage and maintenance margin
        if outcome == "SHORT" or outcome == "NO":
            liq_price = round(price * (1.0 + (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), prec)
            # Strict safety invariant: Liq price for SHORT must be strictly > entry price!
            if liq_price <= price:
                liq_price = price * (1.0 + (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER)

            sl_price = stop_loss if stop_loss else round(price * (1.0 + DEFAULT_SL_PERCENT), prec)
            # Ensure SL triggers before liquidation on high leverage
            if sl_price >= liq_price:
                sl_price = round(price * (1.0 + (1.0 / leverage) * 0.75), prec)
            if sl_price <= price:
                sl_price = price * (1.0 + DEFAULT_SL_PERCENT)

            tp_price = take_profit if take_profit else round(price * (1.0 - DEFAULT_TP_PERCENT), prec)
            if tp_price >= price:
                tp_price = price * (1.0 - DEFAULT_TP_PERCENT)
        else:
            liq_price = round(price * (1.0 - (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), prec)
            # Strict safety invariant: Liq price for LONG must be strictly < entry price!
            if liq_price >= price:
                liq_price = price * (1.0 - (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER)

            sl_price = stop_loss if stop_loss else round(price * (1.0 - DEFAULT_SL_PERCENT), prec)
            # Ensure SL triggers before liquidation on high leverage
            if sl_price <= liq_price:
                sl_price = round(price * (1.0 - (1.0 / leverage) * 0.75), prec)
            if sl_price >= price:
                sl_price = price * (1.0 - DEFAULT_SL_PERCENT)

            tp_price = take_profit if take_profit else round(price * (1.0 + DEFAULT_TP_PERCENT), prec)
            if tp_price <= price:
                tp_price = price * (1.0 + DEFAULT_TP_PERCENT)

        clean_symbol = symbol or question.split("/")[0].replace("crypto_", "").strip()

        # Thực thi lệnh trực tiếp trên sàn Binance Futures (Testnet hoặc Real) nếu đã cấu hình API Key
        binance_order_id = None
        if self.binance_client and self.binance_client.is_configured and asset_type == "crypto":
            try:
                # 1. Đặt đòn bẩy trên sàn Binance
                self.binance_client.set_leverage(clean_symbol, leverage)
                # 2. Đặt chế độ ký quỹ cô lập ISOLATED
                self.binance_client.set_margin_type(clean_symbol, "ISOLATED")
                # 3. Chuẩn hóa khối lượng theo quy định sàn (đảm bảo notional >= 5 USDT)
                formatted_qty = self.binance_client.format_quantity(clean_symbol, position_size, price)
                # 4. Gửi lệnh Market Order trực tiếp lên sàn Binance
                b_res = self.binance_client.place_market_order(clean_symbol, outcome, formatted_qty)
                if b_res.get("success"):
                    binance_order_id = b_res.get("order_id")
                    executed_qty = b_res.get("executed_qty", formatted_qty)
                    if not executed_qty or executed_qty <= 0:
                        executed_qty = formatted_qty
                    avg_p = b_res.get("avg_price", price)
                    if avg_p > 0:
                        price = avg_p
                    shares = executed_qty
                    position_size = round(shares * price, 2)
                    self.log_thought(
                        "Executor",
                        "SUCCESS",
                        f"[Binance Live Testnet] Khớp lệnh THỰC TẾ thành công trên sàn Binance: {outcome} {shares} {clean_symbol} @ ${price:,.4f}! Mã lệnh: #{binance_order_id}"
                    )

                    # 5. Đặt lệnh Chốt lời (TP) và Cắt lỗ (SL) trực tiếp lên sàn Binance Futures
                    tp_sl_res = self.binance_client.place_tp_sl_orders(clean_symbol, outcome, tp_price, sl_price, shares)
                    tp_ok = tp_sl_res.get("tp", {}).get("success") if tp_sl_res.get("tp") else False
                    sl_ok = tp_sl_res.get("sl", {}).get("success") if tp_sl_res.get("sl") else False
                    if tp_ok or sl_ok:
                        self.log_thought(
                            "Executor",
                            "SUCCESS",
                            f"[Binance Live Testnet] Đã đặt lệnh điều kiện sàn thành công: TP @ ${tp_price:,.4f} {'(✓)' if tp_ok else ''} | SL @ ${sl_price:,.4f} {'(✓)' if sl_ok else ''}"
                        )
                    else:
                        err_msg = tp_sl_res.get("sl", {}).get("message") or tp_sl_res.get("tp", {}).get("message") or ""
                        self.log_thought(
                            "Executor",
                            "WARN",
                            f"[Binance Live Testnet] Lưu ý TP/SL sàn: {err_msg}. Bot tiếp tục duy trì giám sát cắt lời/lỗ nội bộ thời gian thực."
                        )
                else:
                    self.log_thought(
                        "Executor",
                        "WARN",
                        f"[Binance Live Testnet] Gửi lệnh sàn không thành công: {b_res.get('message')}. Duy trì ghi nhận mô phỏng nội bộ."
                    )
            except Exception as e:
                self.log_thought(
                    "Executor",
                    "WARN",
                    f"[Binance Live Testnet] Ngoại lệ khi gửi lệnh sàn: {e}. Duy trì ghi nhận mô phỏng."
                )

        # Generate unique ticket ID for each position to prevent accidental overwriting
        ticket_id = f"{market_id}_{outcome}_{int(datetime.now().timestamp())}"
        counter = 1
        base_ticket = ticket_id
        while ticket_id in self.state["open_positions"]:
            ticket_id = f"{base_ticket}_{counter}"
            counter += 1

        self.state["open_positions"][ticket_id] = {
            "id": ticket_id,
            "market_id": market_id,
            "symbol": clean_symbol,
            "question": question,
            "asset_type": asset_type,
            "outcome": outcome, # LONG / SHORT / YES / NO
            "leverage": leverage,
            "shares": shares,
            "entry_price": price,
            "current_price": price,
            "margin": margin,
            "cost_basis": margin,
            "position_size": position_size,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "liquidation_price": liq_price,
            "binance_order_id": binance_order_id,
            "signal_dna": signal_dna or {},
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        trade_record = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "action": f"OPEN_{outcome}_{leverage}X",
            "market_id": market_id,
            "symbol": clean_symbol,
            "asset_type": asset_type,
            "question": question,
            "shares": shares,
            "price": price,
            "leverage": leverage,
            "margin": margin,
            "total_amount": margin,
            "stop_loss": sl_price,
            "take_profit": tp_price,
            "liquidation_price": liq_price,
            "binance_order_id": binance_order_id,
            "reasoning": reasoning
        }
        self.state["trades_history"].insert(0, trade_record)
        self.save()
        return True

    def close_position(self, position_key: str, exit_price: float, reason: str = "MANUAL") -> bool:
        """
        Closes an open position, realizes PnL, refunds margin, and logs outcome.
        Reasons: 'TAKE_PROFIT', 'STOP_LOSS', 'LIQUIDATION', 'MANUAL', 'EMERGENCY'
        """
        target_key = position_key
        if target_key not in self.state["open_positions"]:
            for k, v in self.state["open_positions"].items():
                if v.get("id") == position_key or k.startswith(position_key) or v.get("market_id") == position_key:
                    target_key = k
                    break

        if target_key not in self.state["open_positions"]:
            return False

        pos = self.state["open_positions"].pop(target_key)
        outcome = pos.get("outcome", "LONG")
        shares = pos.get("shares", 0.0)
        entry_p = pos.get("entry_price", 0.0)
        margin = pos.get("margin", pos.get("cost_basis", 0.0))
        leverage = pos.get("leverage", 1)
        sym = pos.get("symbol", pos.get("market_id", ""))

        if outcome == "SHORT" or outcome == "NO":
            pnl = (entry_p - exit_price) * shares
        else:
            pnl = (exit_price - entry_p) * shares

        if reason == "LIQUIDATION":
            pnl = -margin
            return_cash = 0.0
        else:
            return_cash = max(0.0, margin + pnl)

        self.state["cash_balance"] = round(self.state["cash_balance"] + return_cash, 2)
        self.state["realized_pnl"] = round(self.state.get("realized_pnl", 0.0) + pnl, 2)

        pnl_pct = (pnl / margin * 100) if margin > 0 else 0.0
        trade_record = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "action": f"CLOSE_{outcome}",
            "market_id": pos["market_id"],
            "symbol": sym,
            "asset_type": pos.get("asset_type", "crypto"),
            "question": pos["question"],
            "shares": shares,
            "price": exit_price,
            "entry_price": entry_p,
            "exit_price": exit_price,
            "margin": margin,
            "total_amount": round(margin, 2),
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
            "reason": reason,
            "reasoning": f"Đóng vị thế ({reason}): PnL {pnl:+,.2f} USD ({pnl_pct:+.1f}%)"
        }
        self.state["trades_history"].insert(0, trade_record)

        # Đóng vị thế thực tế trên sàn Binance Futures nếu đã cấu hình
        if self.binance_client and self.binance_client.is_configured and pos.get("asset_type") == "crypto":
            try:
                c_res = self.binance_client.close_position(sym, outcome, shares)
                if c_res.get("success"):
                    # Tự động đồng bộ hóa giá khớp thực tế (Fill Price) và PnL từ sàn Binance Futures
                    real_fill_price = float(c_res.get("avg_price", 0.0))
                    if real_fill_price > 0 and abs(real_fill_price - exit_price) > 1e-6:
                        old_pnl = pnl
                        old_return_cash = return_cash

                        if outcome == "SHORT" or outcome == "NO":
                            real_pnl = (entry_p - real_fill_price) * shares
                        else:
                            real_pnl = (real_fill_price - entry_p) * shares

                        real_pnl_pct = (real_pnl / margin * 100) if margin > 0 else 0.0
                        real_return_cash = max(0.0, margin + real_pnl)

                        # Điều chỉnh chênh lệch số dư tiền mặt và PnL đã chốt
                        pnl_diff = real_pnl - old_pnl
                        cash_diff = real_return_cash - old_return_cash
                        self.state["cash_balance"] = round(self.state["cash_balance"] + cash_diff, 2)
                        self.state["realized_pnl"] = round(self.state.get("realized_pnl", 0.0) + pnl_diff, 2)

                        # Cập nhật lại bản ghi lịch sử giao dịch với giá sàn chuẩn xác
                        pnl = real_pnl
                        pnl_pct = real_pnl_pct
                        exit_price = real_fill_price
                        return_cash = real_return_cash

                        trade_record["price"] = real_fill_price
                        trade_record["exit_price"] = real_fill_price
                        trade_record["pnl"] = round(real_pnl, 2)
                        trade_record["pnl_percent"] = round(real_pnl_pct, 2)
                        trade_record["reasoning"] = f"Đóng vị thế ({reason} - Khớp sàn Binance): PnL {real_pnl:+,.2f} USD ({real_pnl_pct:+.1f}%)"

                    self.log_thought(
                        "Executor",
                        "SUCCESS",
                        f"[Binance Live Testnet] Đã đóng vị thế THỰC TẾ & khớp lệnh sàn: {outcome} {sym} @ ${exit_price:,.4f}! PnL thực tế: {pnl:+,.2f} USD ({pnl_pct:+.1f}%)"
                    )
                else:
                    self.log_thought(
                        "Executor",
                        "WARN",
                        f"[Binance Live Testnet] Thông báo đóng lệnh sàn: {c_res.get('message')}"
                    )
            except Exception as e:
                self.log_thought(
                    "Executor",
                    "WARN",
                    f"[Binance Live Testnet] Ngoại lệ khi đóng lệnh trên sàn: {e}"
                )

        log_level = "SUCCESS" if pnl >= 0 else ("WARN" if reason != "LIQUIDATION" else "ERROR")
        viet_reason = {
            "TAKE_PROFIT": "CHỐT LỜI THÀNH CÔNG (TP)",
            "STOP_LOSS": "CẮT LỖ AN TOÀN (SL)",
            "TRAILING_STOP": "CHỐT LÃI BẢO VỆ VỐN (TRAILING STOP)",
            "LIQUIDATION": "BỊ THANH LÝ VỊ THẾ (LIQUIDATED)",
            "MANUAL": "ĐÓNG LỆNH THỦ CÔNG",
            "EMERGENCY": "THOÁT HIỂM KHẨN CẤP"
        }.get(reason, reason)

        self.log_thought(
            "Portfolio",
            log_level,
            f"[{viet_reason}] {sym} ({outcome} {leverage}x): Đóng tại ${exit_price:,.4f}. PnL: {pnl:+,.2f} USD ({pnl_pct:+.1f}%), Hoàn vốn: ${return_cash:,.2f}"
        )

        # Ghi nhận bài học tự phản tỉnh (Trading Memory Self-Reflection & Meta-Learning)
        try:
            is_win = (pnl >= 0)
            from .trading_memory import TradingMemoryManager
            mem_mgr = TradingMemoryManager()
            trade_record_copy = dict(trade_record)
            trade_record_copy["leverage"] = leverage
            signal_dna = pos.get("signal_dna")
            ref = mem_mgr.record_trade_reflection(trade_record_copy, signal_dna=signal_dna)
            if ref and ref.get("lesson"):
                root_msg = f" | Chuẩn đoán: {ref.get('root_cause')}" if ref.get("root_cause") else ""
                self.log_thought(
                    "Memory",
                    "INFO" if is_win else "WARN",
                    f"[Trí Nhớ AI] {ref['lesson']}{root_msg} -> Bài học: {ref['takeaway']}"
                )
        except Exception as e:
            pass

        self.save()
        return True

    def update_position_prices(
        self,
        markets_map: Optional[Dict[str, Dict[str, Any]]] = None,
        crypto_prices: Optional[Dict[str, float]] = None
    ):
        """
        Cập nhật giá theo thời gian thực và quản trị rủi ro đa tầng:
        1. Multi-Tier Trailing Stop & Profit Lock (Bậc thang khóa lãi đa tầng cả LONG và SHORT):
           - Bậc 1 (Tiến độ >= 40% TP): Dời SL về Hòa Vốn (+/- 0.05% phí sàn). Vị thế an toàn 100% Risk-Free.
           - Bậc 2 (Tiến độ >= 65% TP): Kéo SL khóa chắc chắn +30% lợi nhuận mục tiêu.
           - Bậc 3 (Tiến độ >= 85% TP): Kéo SL khóa chắc chắn +60% lợi nhuận mục tiêu.
           - Quy tắc khóa 1 chiều (One-way Ratchet): SL chỉ dịch chuyển theo hướng có lợi, không nới lỏng.
        2. Tự động kích hoạt Take-Profit, Trailing Stop, Stop-Loss, hoặc Liquidation.
        """
        updated = False
        markets_map = markets_map or {}
        crypto_prices = crypto_prices or {}

        for pos_key, pos in list(self.state["open_positions"].items()):
            m_id = pos["market_id"]
            asset_type = pos.get("asset_type", "prediction")
            outcome = pos.get("outcome", "LONG")
            clean_sym = pos.get("symbol") or m_id.replace("crypto_", "").replace("USDT", "")

            curr_price = pos["current_price"]
            if asset_type == "crypto" and clean_sym in crypto_prices:
                new_p = crypto_prices[clean_sym]
                if curr_price != new_p:
                    pos["current_price"] = new_p
                    curr_price = new_p
                    updated = True
            elif m_id in markets_map:
                market = markets_map[m_id]
                new_p = market["probability_yes"] if outcome in ["YES", "LONG"] else market["probability_no"]
                if curr_price != new_p:
                    pos["current_price"] = new_p
                    curr_price = new_p
                    updated = True

            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            liq = pos.get("liquidation_price")
            entry_p = pos.get("entry_price", curr_price)
            prec = normalize_price_precision(entry_p)
            trail_tier = pos.get("trail_tier", 0)
            shares = pos.get("shares", 0.0)
            margin = pos.get("margin", 1.0)

            # Tính PnL và % ROI thực tế theo vốn ký quỹ
            if outcome in ["SHORT", "NO"]:
                unrealized_pnl = (entry_p - curr_price) * shares
            else:
                unrealized_pnl = (curr_price - entry_p) * shares
            pnl_pct = (unrealized_pnl / margin * 100.0) if margin > 0 else 0.0

            # ---------------- DYNAMIC DUAL-TRIGGER TRAILING STOP & PROFIT LOCK ----------------
            # Chiến lược 15M Day-Scalp: Khóa Hòa Vốn vững chãi (+0.15% phí sàn) & Khóa Lãi Bậc Thang
            if outcome in ["LONG", "YES"] and tp and tp > entry_p:
                tp_dist = tp - entry_p
                cur_gain = curr_price - entry_p
                progress = cur_gain / tp_dist if tp_dist > 0 else 0.0

                if (progress >= 0.85 or pnl_pct >= 25.0) and trail_tier < 3:
                    new_sl = round(entry_p + 0.75 * tp_dist, prec)
                    if sl is None or new_sl > sl:
                        pos["stop_loss"] = new_sl
                        pos["trail_tier"] = 3
                        updated = True
                        self.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"[{clean_sym} LONG] Khóa Siêu Lãi Bậc 3 (Tiến độ {progress*100:.0f}% / PnL {pnl_pct:+.1f}%): Dời SL lên ${new_sl:,.4f} để khóa chắc chắn +75% lợi nhuận mục tiêu!"
                        )
                elif (progress >= 0.70 or pnl_pct >= 18.0) and trail_tier < 2:
                    new_sl = round(entry_p + 0.50 * tp_dist, prec)
                    if sl is None or new_sl > sl:
                        pos["stop_loss"] = new_sl
                        pos["trail_tier"] = 2
                        updated = True
                        self.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"[{clean_sym} LONG] Khóa Lãi Đậm Bậc 2 (Tiến độ {progress*100:.0f}% / PnL {pnl_pct:+.1f}%): Dời SL lên ${new_sl:,.4f} để khóa chắc chắn +50% lợi nhuận mục tiêu!"
                        )
                elif (progress >= 0.40 or pnl_pct >= 12.0) and trail_tier < 1:
                    new_sl = round(entry_p * 1.0015, prec) # Hòa vốn + 0.15% biên lãi đệm phí sàn 15m
                    if sl is None or new_sl > sl:
                        pos["stop_loss"] = new_sl
                        pos["trail_tier"] = 1
                        updated = True
                        self.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"[{clean_sym} LONG] Khiên Bảo Vệ Hòa Vốn 15M (Tiến độ {progress*100:.0f}% / PnL {pnl_pct:+.1f}%): Dời SL lên ${new_sl:,.4f} (+0.15% Lãi Đệm), vị thế an toàn 100% Risk-Free!"
                        )

            elif outcome in ["SHORT", "NO"] and tp and tp < entry_p:
                tp_dist = entry_p - tp
                cur_gain = entry_p - curr_price
                progress = cur_gain / tp_dist if tp_dist > 0 else 0.0

                if (progress >= 0.85 or pnl_pct >= 25.0) and trail_tier < 3:
                    new_sl = round(entry_p - 0.75 * tp_dist, prec)
                    if sl is None or new_sl < sl:
                        pos["stop_loss"] = new_sl
                        pos["trail_tier"] = 3
                        updated = True
                        self.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"[{clean_sym} SHORT] Khóa Siêu Lãi Bậc 3 (Tiến độ {progress*100:.0f}% / PnL {pnl_pct:+.1f}%): Hạ SL xuống ${new_sl:,.4f} để khóa chắc chắn +75% lợi nhuận mục tiêu!"
                        )
                elif (progress >= 0.70 or pnl_pct >= 18.0) and trail_tier < 2:
                    new_sl = round(entry_p - 0.50 * tp_dist, prec)
                    if sl is None or new_sl < sl:
                        pos["stop_loss"] = new_sl
                        pos["trail_tier"] = 2
                        updated = True
                        self.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"[{clean_sym} SHORT] Khóa Lãi Đậm Bậc 2 (Tiến độ {progress*100:.0f}% / PnL {pnl_pct:+.1f}%): Hạ SL xuống ${new_sl:,.4f} để khóa chắc chắn +50% lợi nhuận mục tiêu!"
                        )
                elif (progress >= 0.40 or pnl_pct >= 12.0) and trail_tier < 1:
                    new_sl = round(entry_p * 0.9985, prec) # Hòa vốn - 0.15% biên lãi đệm phí sàn 15m
                    if sl is None or new_sl < sl:
                        pos["stop_loss"] = new_sl
                        pos["trail_tier"] = 1
                        updated = True
                        self.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"[{clean_sym} SHORT] Khiên Bảo Vệ Hòa Vốn 15M (Tiến độ {progress*100:.0f}% / PnL {pnl_pct:+.1f}%): Hạ SL xuống ${new_sl:,.4f} (+0.15% Lãi Đệm), vị thế an toàn 100% Risk-Free!"
                        )

            # ----------------- KIỂM TRA ĐIỀU KIỆN KÍCH HOẠT TP / SL / LIQUIDATION -----------------
            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            liq = pos.get("liquidation_price")

            if outcome in ["LONG", "YES"]:
                # Liquidation only valid if liq < entry_p
                if liq and (liq < entry_p) and curr_price <= liq:
                    self.close_position(pos_key, curr_price, reason="LIQUIDATION")
                    updated = True
                elif sl and curr_price <= sl:
                    reason = "TRAILING_STOP" if sl >= entry_p else "STOP_LOSS"
                    self.close_position(pos_key, curr_price, reason=reason)
                    updated = True
                elif tp and (tp > entry_p) and curr_price >= tp:
                    self.close_position(pos_key, curr_price, reason="TAKE_PROFIT")
                    updated = True

            elif outcome in ["SHORT", "NO"]:
                # Liquidation only valid if liq > entry_p
                if liq and (liq > entry_p) and curr_price >= liq:
                    self.close_position(pos_key, curr_price, reason="LIQUIDATION")
                    updated = True
                elif sl and curr_price >= sl:
                    reason = "TRAILING_STOP" if sl <= entry_p else "STOP_LOSS"
                    self.close_position(pos_key, curr_price, reason=reason)
                    updated = True
                elif tp and (tp < entry_p) and curr_price <= tp:
                    self.close_position(pos_key, curr_price, reason="TAKE_PROFIT")
                    updated = True

        if updated:
            self.save()

