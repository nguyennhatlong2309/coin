import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

PROPOSALS_FILE = Path(__file__).parent.parent / "data" / "proposals.json"

class ProposalManager:
    """
    Manages pending AI-generated trade proposals awaiting user approval or rejection.
    """
    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or PROPOSALS_FILE
        self.proposals: Dict[str, Dict[str, Any]] = {}
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    self.proposals = json.load(f)
            except Exception:
                self.proposals = {}
        else:
            self.save()

    def save(self):
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(self.proposals, f, indent=2, ensure_ascii=False)

    def add_proposal(
        self,
        coin: str,
        side: str,
        price: float,
        leverage: int,
        stake_amount: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        liquidation_price: Optional[float],
        timeframe: str = "1h",
        edge: float = 0.0,
        reasoning: str = "",
        analysis_summary: Optional[Dict[str, str]] = None,
        signal_dna: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Creates a new trade proposal in PENDING status.
        """
        clean_coin = coin.upper().replace("USDT", "").strip()
        timestamp = int(time.time())
        prop_id = f"prop_{clean_coin}_{side}_{timestamp}"

        # Risk-to-Reward calculation
        rr_ratio = 2.0
        if stop_loss and take_profit and price > 0:
            sl_dist = abs(price - stop_loss)
            tp_dist = abs(take_profit - price)
            if sl_dist > 0:
                rr_ratio = round(tp_dist / sl_dist, 2)

        position_size = round(stake_amount * leverage, 2)

        proposal = {
            "id": prop_id,
            "coin": clean_coin,
            "symbol": f"{clean_coin}USDT",
            "side": side.upper(), # LONG or SHORT
            "timeframe": timeframe,
            "price": price,
            "leverage": leverage,
            "stake_amount": round(stake_amount, 2),
            "position_size": position_size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "liquidation_price": liquidation_price,
            "risk_reward_ratio": rr_ratio,
            "edge": round(edge, 4),
            "edge_percent": f"{edge * 100:+.1f}%",
            "reasoning": reasoning,
            "analysis_summary": analysis_summary or {},
            "signal_dna": signal_dna or {},
            "status": "PENDING", # PENDING, APPROVED, REJECTED
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        self.proposals[prop_id] = proposal
        self.save()
        return proposal

    def get_pending(self) -> List[Dict[str, Any]]:
        """Returns all pending proposals sorted newest first."""
        pending = [p for p in self.proposals.values() if p.get("status") == "PENDING"]
        pending.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return pending

    def get_all(self, limit: int = 30) -> List[Dict[str, Any]]:
        all_props = list(self.proposals.values())
        all_props.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return all_props[:limit]

    def get(self, prop_id: str) -> Optional[Dict[str, Any]]:
        return self.proposals.get(prop_id)

    def update_status(self, prop_id: str, status: str) -> bool:
        if prop_id in self.proposals:
            self.proposals[prop_id]["status"] = status
            self.save()
            return True
        return False

    def remove(self, prop_id: str) -> bool:
        if prop_id in self.proposals:
            del self.proposals[prop_id]
            self.save()
            return True
        return False

    def clear_pending_for_coin(self, coin: str):
        clean = coin.upper().replace("USDT", "").strip()
        to_remove = [k for k, v in self.proposals.items() if v.get("status") == "PENDING" and v.get("coin", "").upper() == clean]
        for k in to_remove:
            del self.proposals[k]
        if to_remove:
            self.save()

    def clear_all(self):
        self.proposals = {}
        self.save()
