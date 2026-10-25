import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

STRATEGY_FILE = Path(__file__).resolve().parent.parent / "data" / "active_strategy.json"

STRATEGY_REGISTRY: Dict[str, Dict[str, Any]] = {
    "MICRO_SNIPER_SMC": {
        "id": "MICRO_SNIPER_SMC",
        "name": "🎯 Bắn Tỉa Sóng 15M SMC ($10 - Đòn Bẩy 10x)",
        "badge": "🌊 15M DAY SCALP",
        "target_capital": "Vốn $10 – $50",
        "description": "Chiến lược 15M Day-Scalp chất lượng cao. Khung 15M + 1H lọc sạch sóng nhiễu, bắt trọn Liquidity Sweep và FVG retest. Đòn bẩy 10x an toàn, SL 1.5% sau cản cứng nến 15m, TP 3.0% (R:R 1:2.0). Đánh ít lệnh (2-4 lệnh/ngày) nhưng chắc tay, không overtrading.",
        "target_coins": ["BTC", "ETH", "SOL"],
        "capital_budget": 10.00,
        "stake_percent_range": [0.25, 0.40],
        "default_stake": 2.50,
        "leverage": 10,
        "max_leverage": 15,
        "sl_percent": 0.015,
        "tp_percent": 0.030,
        "min_edge": 0.040,
        "multi_timeframe": True,
        "candlestick_patterns": True,
        "strategy_category": "SMC_SWEEP"
    },
    "CLASSIC_QUANT_SCALPER": {
        "id": "CLASSIC_QUANT_SCALPER",
        "name": "📊 Scalping Động Lượng Cổ Điển ($50 - $300)",
        "badge": "📈 CLASSIC SCALPER",
        "target_capital": "Vốn vừa $50 – $300",
        "description": "Chiến lược cũ tiêu chuẩn. Quét nến 1M/5M theo xu hướng EMA20/50 + RSI14 + Bứt phá khối lượng VSA. Đòn bẩy 10x-15x, phân bổ Quarter-Kelly (15% - 20% vốn/lệnh), SL 0.8%, TP 1.6% (R:R = 1:2).",
        "target_coins": ["BTC", "ETH", "SOL", "DOGE", "SUI"],
        "capital_budget": 50.00,
        "stake_percent_range": [0.15, 0.20],
        "default_stake": 8.00,
        "leverage": 10,
        "max_leverage": 15,
        "sl_percent": 0.008,
        "tp_percent": 0.016,
        "min_edge": 0.040,
        "multi_timeframe": False,
        "candlestick_patterns": False,
        "strategy_category": "MOMENTUM_BREAKOUT"
    },
    "CONSERVATIVE_SWING_DEFENDER": {
        "id": "CONSERVATIVE_SWING_DEFENDER",
        "name": "🛡️ Phòng Vệ Xu Hướng Vĩ Mô ($500 - $5,000+)",
        "badge": "🏛️ MACRO DEFENDER",
        "target_capital": "Vốn lớn $500 – $5,000+",
        "description": "Dành cho số tiền lớn cần sự an toàn tuyệt đối. Đánh theo sóng lớn 1H và 4H của BTC và ETH. Đòn bẩy thấp 3x-5x, SL rộng theo ATR 1.8%, TP 4.5% (R:R = 1:2.5). Không bao giờ cháy tài khoản.",
        "target_coins": ["BTC", "ETH", "SOL"],
        "capital_budget": 500.00,
        "stake_percent_range": [0.05, 0.10],
        "default_stake": 25.00,
        "leverage": 5,
        "max_leverage": 5,
        "sl_percent": 0.018,
        "tp_percent": 0.045,
        "min_edge": 0.035,
        "multi_timeframe": True,
        "candlestick_patterns": True,
        "strategy_category": "RANGE_SCALP"
    }
}

class StrategyProfileManager:
    """
    Quản trị Chiến Lược Đa Tầng (Multi-Strategy Profile Manager)
    Cho phép lưu trữ, chuyển đổi qua lại giữa các chiến lược khác nhau tùy theo quy mô vốn của người dùng:
    - Vốn $10: Chế độ Bắn Tỉa Cá Mập SMC (MICRO_SNIPER_SMC)
    - Vốn $50 - $300: Chế độ Scalping Cổ Điển (CLASSIC_QUANT_SCALPER)
    - Vốn $500+: Chế độ Phòng Vệ Xu Hướng Vĩ Mô (CONSERVATIVE_SWING_DEFENDER)
    """
    def __init__(self, file_path: Path = STRATEGY_FILE):
        self.file_path = file_path
        self._active_strategy_id = "MICRO_SNIPER_SMC"
        self.load()

    def load(self):
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sid = data.get("active_strategy_id", "MICRO_SNIPER_SMC")
                    if sid in STRATEGY_REGISTRY:
                        self._active_strategy_id = sid
            except Exception:
                self.save()
        else:
            self.save()

    def save(self):
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump({
                    "active_strategy_id": self._active_strategy_id,
                    "active_strategy": STRATEGY_REGISTRY.get(self._active_strategy_id, {}),
                    "available_strategies": list(STRATEGY_REGISTRY.keys())
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[StrategyProfileManager] Save error: {e}")

    def get_active_strategy(self) -> Dict[str, Any]:
        return STRATEGY_REGISTRY.get(self._active_strategy_id, STRATEGY_REGISTRY["MICRO_SNIPER_SMC"])

    def set_active_strategy(self, strategy_id: str) -> bool:
        sid = strategy_id.upper().strip()
        if sid in STRATEGY_REGISTRY:
            self._active_strategy_id = sid
            self.save()
            return True
        return False

    def list_strategies(self) -> List[Dict[str, Any]]:
        result = []
        for sid, strat in STRATEGY_REGISTRY.items():
            s_copy = dict(strat)
            s_copy["is_active"] = (sid == self._active_strategy_id)
            result.append(s_copy)
        return result

# Singleton Instance
strategy_manager = StrategyProfileManager()
