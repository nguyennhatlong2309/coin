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
            val = pos["shares"] * pos["current_price"]
            positions_value += val
            cost = pos["shares"] * pos["entry_price"]
            unrealized_pnl += (val - cost)

        total_equity = cash + positions_value
        total_pnl = (total_equity - INITIAL_CAPITAL)
        pnl_percent = (total_pnl / INITIAL_CAPITAL) * 100

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
            "recent_trades": trades[:10],
            "thought_logs": self.state["thought_logs"][:25]
        }

    def execute_trade(self, market_id: str, question: str, outcome: str, price: float, stake_amount: float, reasoning: str) -> bool:
        """
        Executes a mock trade: buys shares of YES or NO.
        """
        if stake_amount <= 0 or stake_amount > self.state["cash_balance"]:
            return False

        shares = round(stake_amount / price, 2)
        cost = round(shares * price, 2)

        if cost > self.state["cash_balance"]:
            cost = self.state["cash_balance"]
            shares = round(cost / price, 2)

        self.state["cash_balance"] -= cost

        position_key = f"{market_id}_{outcome}"
        if position_key in self.state["open_positions"]:
            pos = self.state["open_positions"][position_key]
            total_shares = pos["shares"] + shares
            avg_price = (pos["shares"] * pos["entry_price"] + cost) / total_shares
            pos["shares"] = round(total_shares, 2)
            pos["entry_price"] = round(avg_price, 3)
            pos["current_price"] = price
        else:
            self.state["open_positions"][position_key] = {
                "id": position_key,
                "market_id": market_id,
                "question": question,
                "outcome": outcome, # YES / NO
                "shares": shares,
                "entry_price": price,
                "current_price": price,
                "cost_basis": cost,
                "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

        trade_record = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "action": f"BUY_{outcome}",
            "market_id": market_id,
            "question": question,
            "shares": shares,
            "price": price,
            "total_amount": cost,
            "reasoning": reasoning
        }
        self.state["trades_history"].insert(0, trade_record)
        self.save()
        return True

    def update_position_prices(self, markets_map: Dict[str, Dict[str, Any]]):
        """Updates open position prices based on latest market odds."""
        updated = False
        for pos_key, pos in list(self.state["open_positions"].items()):
            m_id = pos["market_id"]
            if m_id in markets_map:
                market = markets_map[m_id]
                new_price = market["probability_yes"] if pos["outcome"] == "YES" else market["probability_no"]
                if pos["current_price"] != new_price:
                    pos["current_price"] = new_price
                    updated = True
        if updated:
            self.save()
