import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from ..config import (
    PORTFOLIO_FILE, 
    INITIAL_CAPITAL, 
    DEFAULT_LEVERAGE, 
    DEFAULT_SL_PERCENT, 
    DEFAULT_TP_PERCENT, 
    MAINTENANCE_MARGIN_BUFFER
)

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

    def reset(self):
        self.state = {
            "cash_balance": INITIAL_CAPITAL,
            "realized_pnl": 0.0,
            "open_positions": {},
            "trades_history": [],
            "thought_logs": [{
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "agent": "System",
                "level": "INFO",
                "message": f"Portfolio reset successfully. Initial capital established at ${INITIAL_CAPITAL:,.2f} USD."
            }],
            "last_updated": time.time()
        }
        self.save()
        return self.get_summary()

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
            "thought_logs": self.state["thought_logs"][:30]
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
        symbol: Optional[str] = None
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

        leverage = max(1, min(10, leverage))
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

        # Calculate Liquidation Price based on leverage and maintenance margin
        if outcome == "SHORT" or outcome == "NO":
            liq_price = round(price * (1.0 + (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), 6 if price < 1 else 4)
            sl_price = stop_loss if stop_loss else round(price * (1.0 + DEFAULT_SL_PERCENT), 6 if price < 1 else 4)
            tp_price = take_profit if take_profit else round(price * (1.0 - DEFAULT_TP_PERCENT), 6 if price < 1 else 4)
        else:
            liq_price = round(price * (1.0 - (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), 6 if price < 1 else 4)
            sl_price = stop_loss if stop_loss else round(price * (1.0 - DEFAULT_SL_PERCENT), 6 if price < 1 else 4)
            tp_price = take_profit if take_profit else round(price * (1.0 + DEFAULT_TP_PERCENT), 6 if price < 1 else 4)

        clean_symbol = symbol or question.split("/")[0].replace("crypto_", "").strip()
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

        log_level = "SUCCESS" if pnl >= 0 else ("WARN" if reason != "LIQUIDATION" else "ERROR")
        viet_reason = {
            "TAKE_PROFIT": "CHỐT LỜI THÀNH CÔNG (TP)",
            "STOP_LOSS": "CẮT LỖ AN TOÀN (SL)",
            "LIQUIDATION": "BỊ THANH LÝ VỊ THẾ (LIQUIDATED)",
            "MANUAL": "ĐÓNG LỆNH THỦ CÔNG",
            "EMERGENCY": "THOÁT HIỂM KHẨN CẤP"
        }.get(reason, reason)

        self.log_thought(
            "Portfolio",
            log_level,
            f"[{viet_reason}] {sym} ({outcome} {leverage}x): Đóng tại ${exit_price:,.4f}. PnL: {pnl:+,.2f} USD ({pnl_pct:+.1f}%), Hoàn vốn: ${return_cash:,.2f}"
        )
        self.save()
        return True

    def update_position_prices(
        self,
        markets_map: Optional[Dict[str, Dict[str, Any]]] = None,
        crypto_prices: Optional[Dict[str, float]] = None
    ):
        """
        Updates position prices and automatically triggers TP, SL, or Liquidation.
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

            # Automatic Take-Profit, Stop-Loss, and Liquidation checks
            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            liq = pos.get("liquidation_price")

            if outcome in ["LONG", "YES"]:
                if liq and curr_price <= liq:
                    self.close_position(pos_key, curr_price, reason="LIQUIDATION")
                    updated = True
                elif sl and curr_price <= sl:
                    self.close_position(pos_key, curr_price, reason="STOP_LOSS")
                    updated = True
                elif tp and curr_price >= tp:
                    self.close_position(pos_key, curr_price, reason="TAKE_PROFIT")
                    updated = True
            elif outcome in ["SHORT", "NO"]:
                if liq and curr_price >= liq:
                    self.close_position(pos_key, curr_price, reason="LIQUIDATION")
                    updated = True
                elif sl and curr_price >= sl:
                    self.close_position(pos_key, curr_price, reason="STOP_LOSS")
                    updated = True
                elif tp and curr_price <= tp:
                    self.close_position(pos_key, curr_price, reason="TAKE_PROFIT")
                    updated = True

        if updated:
            self.save()

