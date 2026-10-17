import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
from ..config import PORTFOLIO_FILE, INITIAL_CAPITAL

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
            asset_type = pos.get("asset_type", "prediction")
            outcome = pos.get("outcome", "YES")
            shares = pos["shares"]
            curr_p = pos["current_price"]
            entry_p = pos["entry_price"]
            cost = pos.get("cost_basis", shares * entry_p)

            if asset_type == "crypto" and outcome == "SHORT":
                val = cost + (entry_p - curr_p) * shares
            else:
                val = shares * curr_p

            positions_value += val
            unrealized_pnl += (val - cost)

        total_equity = cash + positions_value
        total_pnl = (total_equity - INITIAL_CAPITAL)
        pnl_percent = (total_pnl / INITIAL_CAPITAL) * 100 if INITIAL_CAPITAL > 0 else 0.0

        trades = self.state["trades_history"]
        win_count = sum(1 for t in trades if t.get("pnl", 0) > 0)
        total_closed = sum(1 for t in trades if "pnl" in t and t.get("action") == "CLOSE")
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0

        return {
            "cash_balance": round(cash, 2),
            "positions_value": round(positions_value, 2),
            "total_equity": round(total_equity, 2),
            "total_pnl": round(total_pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
            "realized_pnl": round(self.state["realized_pnl"], 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "open_positions": list(self.state["open_positions"].values()),
            "total_open_count": len(self.state["open_positions"]),
            "trades_count": len(trades),
            "win_rate": round(win_rate, 1),
            "recent_trades": trades[:15],
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
        asset_type: str = "prediction"
    ) -> bool:
        """
        Executes a mock trade for Prediction Market (YES/NO) or Crypto (LONG/SHORT/BUY).
        """
        if stake_amount <= 0 or stake_amount > self.state["cash_balance"] or price <= 0:
            return False

        # Precision handling
        if asset_type == "crypto":
            if price > 100:
                shares = round(stake_amount / price, 6)
            elif price > 1:
                shares = round(stake_amount / price, 4)
            else:
                shares = round(stake_amount / price, 2)
        else:
            shares = round(stake_amount / price, 2)

        cost = round(shares * price, 2)
        if cost > self.state["cash_balance"]:
            cost = round(self.state["cash_balance"], 2)
            shares = round(cost / price, 6 if asset_type == "crypto" else 2)

        if cost <= 0:
            return False

        self.state["cash_balance"] = round(self.state["cash_balance"] - cost, 2)

        position_key = f"{market_id}_{outcome}"
        if position_key in self.state["open_positions"]:
            pos = self.state["open_positions"][position_key]
            total_shares = pos["shares"] + shares
            avg_price = (pos["shares"] * pos["entry_price"] + cost) / total_shares
            pos["shares"] = round(total_shares, 6 if asset_type == "crypto" else 2)
            pos["entry_price"] = round(avg_price, 4)
            pos["current_price"] = price
            pos["cost_basis"] = round(pos.get("cost_basis", 0) + cost, 2)
        else:
            self.state["open_positions"][position_key] = {
                "id": position_key,
                "market_id": market_id,
                "question": question,
                "asset_type": asset_type,
                "outcome": outcome, # YES/NO or LONG/SHORT
                "shares": shares,
                "entry_price": price,
                "current_price": price,
                "cost_basis": cost,
                "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        action_name = f"BUY_{outcome}" if not outcome.startswith("BUY") else outcome
        trade_record = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "action": action_name,
            "market_id": market_id,
            "asset_type": asset_type,
            "question": question,
            "shares": shares,
            "price": price,
            "total_amount": cost,
            "reasoning": reasoning
        }
        self.state["trades_history"].insert(0, trade_record)
        self.save()
        return True

    def update_position_prices(
        self,
        markets_map: Optional[Dict[str, Dict[str, Any]]] = None,
        crypto_prices: Optional[Dict[str, float]] = None
    ):
        """Updates open position prices based on prediction odds and crypto live prices."""
        updated = False
        markets_map = markets_map or {}
        crypto_prices = crypto_prices or {}

        for pos_key, pos in list(self.state["open_positions"].items()):
            m_id = pos["market_id"]
            asset_type = pos.get("asset_type", "prediction")

            if asset_type == "crypto":
                # Match symbol e.g. crypto_BTCUSDT -> BTCUSDT or BTC
                clean_sym = m_id.replace("crypto_", "")
                if clean_sym in crypto_prices:
                    new_p = crypto_prices[clean_sym]
                    if pos["current_price"] != new_p:
                        pos["current_price"] = new_p
                        updated = True
            elif m_id in markets_map:
                market = markets_map[m_id]
                new_price = market["probability_yes"] if pos["outcome"] == "YES" else market["probability_no"]
                if pos["current_price"] != new_price:
                    pos["current_price"] = new_price
                    updated = True

        if updated:
            self.save()

