import json
import os
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

MEMORY_FILE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "trading_memory.json")

class TradingMemoryManager:
    """
    Skill: 3-Compartment Hierarchical Quant Memory & Meta-Learning Engine (Kiến Trúc Trí Nhớ 3 Ngăn Phân Lập)
    Inspired by TauricResearch/TradingAgents & Deep Learning Meta-Heuristics:
    
    1. Ngăn 1: Trí Nhớ Phân Lập Từng Đồng Coin (symbol_matrix)
       - Mỗi đồng coin (DOGE, PEPE, SOL, SUI, BNB, EDU, LSK) có hồ sơ PnL, Winrate, chuỗi thua độc lập.
       - Cơ chế Isolated Risk Shield: Thua lỗ ở PEPE/DOGE TUYỆT ĐỐI không lây lan hay siết đòn bẩy của SOL/BNB.
       
    2. Ngăn 2: Trí Nhớ Từng Chiến Thuật (strategy_matrix)
       - Đánh giá hiệu suất từng trường phái:
         * SMC_SWEEP (Săn râu quét thanh khoản)
         * FVG_RETEST (Lấp khoảng trống giá Fair Value Gap)
         * MOMENTUM_BREAKOUT (Bứt phá xung lực EMA & VSA)
         * RANGE_SCALP (Lướt sóng biên độ sideway)
         
    3. Ngăn 3: Trí Nhớ Quy Luật Toàn Cầu (pattern_matrix)
       - Duy trì ma trận trọng số thời gian (Time-Decay gamma=0.75), nhận diện Alpha Decay và Bẫy Thua (Loss Trap).
       
    4. Multi-Tier Confluence Evaluation:
       - Tự động cộng hưởng 3 ngăn để điều chỉnh Edge và ra quyết định quản trị vốn Kelly chính xác.
    """
    def __init__(self, memory_file: str = MEMORY_FILE_PATH):
        self.memory_file = memory_file
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        if not os.path.exists(self.memory_file):
            default_data = {
                "version": "3.0",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_settled_trades": 0,
                "strategy_matrix": {},
                "symbol_matrix": {},
                "pattern_matrix": {},
                "reflections": []
            }
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=2, ensure_ascii=False)

    def _load_data(self) -> Dict[str, Any]:
        try:
            with open(self.memory_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "pattern_matrix" not in data:
                    data["pattern_matrix"] = {}
                if "strategy_matrix" not in data:
                    data["strategy_matrix"] = {}
                if "symbol_matrix" not in data:
                    data["symbol_matrix"] = {}
                if "reflections" not in data:
                    data["reflections"] = []
                return data
        except Exception:
            return {
                "version": "3.0",
                "total_settled_trades": 0,
                "strategy_matrix": {},
                "symbol_matrix": {},
                "pattern_matrix": {},
                "reflections": []
            }

    def _save_data(self, data: Dict[str, Any]):
        try:
            with open(self.memory_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[TradingMemory] Lỗi lưu file: {e}")

    @staticmethod
    def classify_strategy(smc_pattern: str, vsa_signal: str, rsi_zone: str) -> Tuple[str, str]:
        """
        Phân loại chiến thuật định lượng chuẩn hóa:
        - SMC_SWEEP: Săn râu quét thanh khoản
        - FVG_RETEST: Lấp khoảng trống giá
        - MOMENTUM_BREAKOUT: Bứt phá xung lực & khối lượng VSA
        - RANGE_SCALP: Lướt sóng dao động biên độ
        """
        smc = (smc_pattern or "").upper()
        vsa = (vsa_signal or "").upper()
        rsi = (rsi_zone or "").upper()

        if "SWEEP" in smc:
            return "SMC_SWEEP", "SMC Liquidity Sweep (Săn râu quét thanh khoản)"
        elif "FVG" in smc:
            return "FVG_RETEST", "SMC FVG Retest (Lấp khoảng trống giá)"
        elif any(kw in vsa for kw in ["EXPANSION", "CLIMAX", "ABSORPTION"]) or rsi in ["HIGH_MOMENTUM", "BULL_MOMENTUM"]:
            return "MOMENTUM_BREAKOUT", "Momentum Breakout (Bứt phá xung lực & VSA)"
        else:
            return "RANGE_SCALP", "Range Scalp (Lướt sóng dao động biên độ)"

    @staticmethod
    def classify_coin_category(coin: str) -> Tuple[str, str]:
        """
        Phân loại nhóm tài sản để phân lập rủi ro:
        - MEME_HIGH_VOLATILITY: DOGE, PEPE, SHIB, FLOKI, BONK, WIF, MEME...
        - MAJOR_CRYPTO: BTC, ETH, BNB, SOL
        - ALTCOIN: EDU, LSK, SUI, AVAX, NEAR, PIXEL...
        """
        c = (coin or "").upper().replace("USDT", "").strip()
        if c in ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "MEME", "BOME", "NEIRO"]:
            return "MEME_HIGH_VOLATILITY", "Meme Coin Biến Động Cao"
        elif c in ["BTC", "ETH", "BNB", "SOL"]:
            return "MAJOR_CRYPTO", "Coin Trụ Vốn Hóa Lớn"
        else:
            return "ALTCOIN", "Altcoin Tiềm Năng"

    @staticmethod
    def calculate_decayed_win_rate(recent_outcomes: List[bool], decay_factor: float = 0.75) -> float:
        """
        Tính toán tỷ lệ thắng có trọng số thời gian (Exponential Recency Weighting / Time-Decay).
        Mỗi lệnh lùi về quá khứ sẽ có trọng số giảm theo decay_factor (mặc định 0.75).
        Lệnh gần nhất index=0 có trọng số cao nhất (1.0).
        """
        if not recent_outcomes:
            return 0.0
        weights = [decay_factor ** i for i in range(len(recent_outcomes))]
        total_weight = sum(weights)
        if total_weight <= 0:
            return 0.0
        weighted_wins = sum(w for w, outcome in zip(weights, recent_outcomes) if outcome)
        return round((weighted_wins / total_weight) * 100, 1)

    @staticmethod
    def calculate_streaks(recent_outcomes: List[bool]) -> Dict[str, int]:
        """
        Tính chuỗi thua liên tiếp (recent_loss_streak) và chuỗi thắng liên tiếp (recent_win_streak)
        bắt đầu từ lệnh gần đây nhất (index 0).
        """
        loss_streak = 0
        for o in recent_outcomes:
            if not o:
                loss_streak += 1
            else:
                break

        win_streak = 0
        for o in recent_outcomes:
            if o:
                win_streak += 1
            else:
                break

        return {"recent_loss_streak": loss_streak, "recent_win_streak": win_streak}

    @classmethod
    def build_signal_dna(
        cls,
        side: str,
        quant_res: Dict[str, Any],
        orderbook_ratio: float,
        smc_data: Optional[Dict[str, Any]] = None,
        vsa_data: Optional[Dict[str, Any]] = None,
        coin: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Trích xuất DNA Tín Hiệu (Signal DNA) lúc mở lệnh để làm cơ sở học máy và đối soát.
        Bổ sung phân loại chiến thuật (Strategy) và nhóm tài sản (Coin Category).
        """
        side = side.upper() if side else "LONG"
        smc = smc_data or quant_res.get("smc", {})
        vsa = vsa_data or quant_res.get("vsa", {})
        rsi = float(quant_res.get("rsi", 50.0))
        ratio = float(orderbook_ratio or 1.0)
        trend = quant_res.get("trend_desc", "Trung tính")

        # 1. Phân loại SMC
        smc_pattern = smc.get("pattern", "NONE") if smc.get("detected") else "NONE"
        smc_desc = smc.get("description", "Không phát hiện bẫy SMC") if smc.get("detected") else "Chuẩn định lượng"

        # 2. Phân loại Orderbook Bias
        if ratio >= 1.25:
            orderbook_bias = "STRONG_BID"
            orderbook_desc = f"Lực Mua Áp Đảo ({ratio:.2f}x)"
        elif ratio >= 1.05:
            orderbook_bias = "MODERATE_BID"
            orderbook_desc = f"Phe Mua Chiếm Ưu Thế ({ratio:.2f}x)"
        elif ratio <= 0.80:
            orderbook_bias = "STRONG_ASK"
            orderbook_desc = f"Tường Bán Đè Giá ({ratio:.2f}x)"
        elif ratio <= 0.95:
            orderbook_bias = "MODERATE_ASK"
            orderbook_desc = f"Phe Bán Chiếm Ưu Thế ({ratio:.2f}x)"
        else:
            orderbook_bias = "NEUTRAL"
            orderbook_desc = f"Cân Bằng Cung Cầu ({ratio:.2f}x)"

        # 3. Phân loại RSI Zone
        if rsi < 35:
            rsi_zone = "OVERSOLD"
            rsi_desc = f"Quá Bán (RSI {rsi:.1f})"
        elif rsi <= 55:
            rsi_zone = "BULL_MOMENTUM"
            rsi_desc = f"Xung Lực Tăng Sớm (RSI {rsi:.1f})"
        elif rsi <= 65:
            rsi_zone = "HIGH_MOMENTUM"
            rsi_desc = f"Xung Lực Cao (RSI {rsi:.1f})"
        else:
            rsi_zone = "OVERBOUGHT"
            rsi_desc = f"Quá Mua Rủi Ro (RSI {rsi:.1f})"

        # 4. Phân loại VSA
        vsa_signal = vsa.get("signal", "NORMAL")

        # 5. Phân loại Chiến thuật & Nhóm Coin
        strat_key, strat_label = cls.classify_strategy(smc_pattern, vsa_signal, rsi_zone)
        coin_clean = (coin or "UNKNOWN").upper().replace("USDT", "").strip()
        cat_key, cat_label = cls.classify_coin_category(coin_clean)

        # 6. Xây dựng Pattern Key chuẩn hóa
        if smc_pattern != "NONE":
            pattern_key = f"{side}:{smc_pattern}:{orderbook_bias}"
            display_label = f"{side} + {smc_pattern.replace('_', ' ')} + {orderbook_desc}"
        else:
            pattern_key = f"{side}:{rsi_zone}:{orderbook_bias}"
            display_label = f"{side} + {rsi_desc} + {orderbook_desc}"

        return {
            "pattern_key": pattern_key,
            "display_label": display_label,
            "side": side,
            "smc_pattern": smc_pattern,
            "smc_desc": smc_desc,
            "orderbook_bias": orderbook_bias,
            "orderbook_ratio": round(ratio, 2),
            "orderbook_desc": orderbook_desc,
            "rsi_value": round(rsi, 1),
            "rsi_zone": rsi_zone,
            "rsi_desc": rsi_desc,
            "vsa_signal": vsa_signal,
            "trend_desc": trend,
            "coin": coin_clean,
            "coin_category": cat_key,
            "coin_category_label": cat_label,
            "strategy": strat_key,
            "strategy_label": strat_label
        }

    # =========================================================================
    # NGĂN 1: TRÍ NHỚ PHÂN LẬP TỪNG ĐỒNG COIN (SYMBOL MATRIX)
    # =========================================================================
    def update_symbol_matrix(self, coin: str, is_win: bool, pnl_percent: float, strategy: Optional[str] = None):
        """
        Cập nhật trí nhớ riêng cho từng đồng coin để cô lập rủi ro hoàn toàn.
        """
        if not coin or coin.upper() == "UNKNOWN":
            return

        clean_sym = coin.upper().replace("USDT", "").strip()
        data = self._load_data()
        matrix = data.get("symbol_matrix", {})

        cat_key, cat_label = self.classify_coin_category(clean_sym)
        entry = matrix.get(clean_sym, {
            "symbol": clean_sym,
            "category": cat_key,
            "category_label": cat_label,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "decayed_win_rate": 0.0,
            "recent_outcomes": [],
            "recent_loss_streak": 0,
            "recent_win_streak": 0,
            "total_pnl_percent": 0.0,
            "avg_pnl_percent": 0.0,
            "best_strategy": strategy or "RANGE_SCALP",
            "status": "NEUTRAL",
            "defense_warning": None,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        entry["total_trades"] += 1
        if is_win:
            entry["wins"] += 1
        else:
            entry["losses"] += 1
            entry["last_loss_time"] = time.time()

        recent_outcomes = entry.get("recent_outcomes", [])
        recent_outcomes.insert(0, bool(is_win))
        if len(recent_outcomes) > 10:
            recent_outcomes = recent_outcomes[:10]
        entry["recent_outcomes"] = recent_outcomes

        decayed_wr = self.calculate_decayed_win_rate(recent_outcomes, decay_factor=0.75)
        entry["decayed_win_rate"] = decayed_wr

        streaks = self.calculate_streaks(recent_outcomes)
        loss_streak = streaks["recent_loss_streak"]
        win_streak = streaks["recent_win_streak"]
        entry["recent_loss_streak"] = loss_streak
        entry["recent_win_streak"] = win_streak

        entry["total_pnl_percent"] = round(entry.get("total_pnl_percent", 0.0) + pnl_percent, 2)
        entry["win_rate"] = round((entry["wins"] / entry["total_trades"]) * 100, 1)
        entry["avg_pnl_percent"] = round(entry["total_pnl_percent"] / entry["total_trades"], 2)
        entry["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if strategy and is_win:
            entry["best_strategy"] = strategy

        # Phân loại trạng thái Coin:
        # Nếu chuỗi thua >= 2 hoặc tỷ lệ thắng suy giảm rớt dưới 35% -> Kích hoạt DEFENSE_LOCK cho riêng coin này!
        if loss_streak >= 2 or (entry["total_trades"] >= 3 and decayed_wr < 35.0):
            entry["status"] = "DEFENSE_LOCK"
            entry["defense_warning"] = (
                f"CẢNH BÁO PHÒNG VỆ RIÊNG {clean_sym}: Đang dính chuỗi thua {loss_streak} lệnh gần đây (Tỷ lệ thắng thực tế {decayed_wr}%). "
                f"Tự động siết đòn bẩy và giảm 50% vốn cược cho riêng đồng {clean_sym} (hoàn toàn không ảnh hưởng tới các coin khác)!"
            )
        elif entry["win_rate"] >= 60.0 and loss_streak == 0:
            entry["status"] = "HEALTHY"
            entry["defense_warning"] = None
        else:
            entry["status"] = "NEUTRAL"
            entry["defense_warning"] = None

        matrix[clean_sym] = entry
        data["symbol_matrix"] = matrix
        self._save_data(data)

    def is_coin_in_cooldown(self, coin: str) -> Tuple[bool, int, str]:
        """
        Anti-Chop / Revenge Trading Cooldown:
        Kiểm tra đồng coin có đang trong thời gian nghỉ ngơi cưỡng bức sau khi dính cắt lỗ hay không.
        - Dính 1 SL: Cooldown 20 phút (1200s)
        - Dính >= 2 SL liên tiếp: Cooldown 45 phút (2700s)
        """
        if not coin or coin.upper() == "UNKNOWN":
            return False, 0, ""
        clean_sym = coin.upper().replace("USDT", "").strip()
        data = self._load_data()
        matrix = data.get("symbol_matrix", {})
        entry = matrix.get(clean_sym)
        if not entry:
            return False, 0, ""

        last_loss = entry.get("last_loss_time")
        if not last_loss:
            return False, 0, ""

        loss_streak = entry.get("recent_loss_streak", 0)
        if loss_streak <= 0:
            return False, 0, ""

        cooldown_sec = 2700 if loss_streak >= 2 else 1200
        elapsed = time.time() - float(last_loss)
        if elapsed < cooldown_sec:
            rem_sec = int(cooldown_sec - elapsed)
            rem_min = max(1, rem_sec // 60)
            reason = (
                f"🛡️ [Anti-Chop Cooldown] Đồng {clean_sym} vừa dính cắt lỗ ({loss_streak} lệnh liên tiếp). "
                f"Tự động khóa coin này thêm {rem_min} phút ({rem_sec}s) để bảo toàn vốn và tránh bão giá/sideway!"
            )
            return True, rem_sec, reason

        return False, 0, ""

    # =========================================================================
    # NGĂN 2: TRÍ NHỚ TỪNG CHIẾN THUẬT (STRATEGY MATRIX)
    # =========================================================================
    def update_strategy_matrix(self, strategy_key: str, is_win: bool, pnl_percent: float, coin: Optional[str] = None):
        """
        Cập nhật trí nhớ hiệu suất từng chiến thuật định lượng.
        """
        if not strategy_key:
            strategy_key = "RANGE_SCALP"

        data = self._load_data()
        matrix = data.get("strategy_matrix", {})

        _, display_label = self.classify_strategy(strategy_key, "", "")
        entry = matrix.get(strategy_key, {
            "strategy_key": strategy_key,
            "display_label": display_label,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "decayed_win_rate": 0.0,
            "recent_outcomes": [],
            "recent_loss_streak": 0,
            "recent_win_streak": 0,
            "total_pnl_percent": 0.0,
            "avg_pnl_percent": 0.0,
            "best_coin": coin or "UNKNOWN",
            "status": "CALIBRATING",
            "edge_adjustment": 0.0,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        entry["total_trades"] += 1
        if is_win:
            entry["wins"] += 1
        else:
            entry["losses"] += 1
            entry["last_loss_time"] = time.time()

        recent_outcomes = entry.get("recent_outcomes", [])
        recent_outcomes.insert(0, bool(is_win))
        if len(recent_outcomes) > 10:
            recent_outcomes = recent_outcomes[:10]
        entry["recent_outcomes"] = recent_outcomes

        decayed_wr = self.calculate_decayed_win_rate(recent_outcomes, decay_factor=0.75)
        entry["decayed_win_rate"] = decayed_wr

        streaks = self.calculate_streaks(recent_outcomes)
        loss_streak = streaks["recent_loss_streak"]
        win_streak = streaks["recent_win_streak"]
        entry["recent_loss_streak"] = loss_streak
        entry["recent_win_streak"] = win_streak

        entry["total_pnl_percent"] = round(entry.get("total_pnl_percent", 0.0) + pnl_percent, 2)
        entry["win_rate"] = round((entry["wins"] / entry["total_trades"]) * 100, 1)
        entry["avg_pnl_percent"] = round(entry["total_pnl_percent"] / entry["total_trades"], 2)
        entry["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if coin and is_win:
            entry["best_coin"] = coin

        # Phân loại trạng thái Chiến thuật:
        if entry["total_trades"] >= 2 and entry["win_rate"] >= 60.0 and decayed_wr >= 55.0:
            entry["status"] = "PROVEN_EDGE"
            entry["edge_adjustment"] = 0.025
        elif entry["total_trades"] >= 2 and (entry["win_rate"] <= 35.0 or decayed_wr <= 35.0):
            entry["status"] = "UNDERPERFORMING"
            entry["edge_adjustment"] = -0.03
        else:
            entry["status"] = "CALIBRATING"
            entry["edge_adjustment"] = 0.0

        matrix[strategy_key] = entry
        data["strategy_matrix"] = matrix
        self._save_data(data)

    # =========================================================================
    # NGĂN 3: TRÍ NHỚ QUY LUẬT TOÀN CẦU (PATTERN MATRIX)
    # =========================================================================
    def update_pattern_matrix(self, signal_dna: Dict[str, Any], is_win: bool, pnl_percent: float):
        """
        Cập nhật ma trận xác suất mẫu hình dựa trên kết quả lệnh thực tế,
        tính toán Time-Decay để nhận diện Alpha Decay / Đổi chế độ thị trường.
        """
        if not signal_dna or not signal_dna.get("pattern_key"):
            return

        key = signal_dna["pattern_key"]
        data = self._load_data()
        matrix = data.get("pattern_matrix", {})

        entry = matrix.get(key, {
            "pattern_key": key,
            "display_label": signal_dna.get("display_label", key),
            "side": signal_dna.get("side", "LONG"),
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "decayed_win_rate": 0.0,
            "recent_outcomes": [],
            "recent_loss_streak": 0,
            "recent_win_streak": 0,
            "total_pnl_percent": 0.0,
            "avg_pnl_percent": 0.0,
            "status": "EXPLORATORY",
            "edge_boost": 0.0,
            "decay_warning": None,
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        entry["total_trades"] += 1
        if is_win:
            entry["wins"] += 1
        else:
            entry["losses"] += 1
            entry["last_loss_time"] = time.time()

        recent_outcomes = entry.get("recent_outcomes", [])
        recent_outcomes.insert(0, bool(is_win))
        if len(recent_outcomes) > 10:
            recent_outcomes = recent_outcomes[:10]
        entry["recent_outcomes"] = recent_outcomes

        decayed_wr = self.calculate_decayed_win_rate(recent_outcomes, decay_factor=0.75)
        entry["decayed_win_rate"] = decayed_wr

        streaks = self.calculate_streaks(recent_outcomes)
        loss_streak = streaks["recent_loss_streak"]
        win_streak = streaks["recent_win_streak"]
        entry["recent_loss_streak"] = loss_streak
        entry["recent_win_streak"] = win_streak

        entry["total_pnl_percent"] = round(entry.get("total_pnl_percent", 0.0) + pnl_percent, 2)
        entry["win_rate"] = round((entry["wins"] / entry["total_trades"]) * 100, 1)
        entry["avg_pnl_percent"] = round(entry["total_pnl_percent"] / entry["total_trades"], 2)
        entry["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 1. ALPHA_DECAY
        if entry["total_trades"] >= 2 and entry["win_rate"] >= 60.0 and (loss_streak >= 2 or decayed_wr < 50.0):
            entry["status"] = "ALPHA_DECAY"
            entry["edge_boost"] = -0.02
            entry["decay_warning"] = (
                f"CẢNH BÁO SUY GIẢM HIỆU QUẢ: Từng có tỷ lệ thắng tổng thể {entry['win_rate']}%, "
                f"nhưng đang thua {loss_streak} lệnh liên tiếp gần đây (Tỷ lệ thắng gần đây: {decayed_wr}%). "
                f"Thị trường có thể đã đổi cấu trúc!"
            )
        # 2. WIN_AMPLIFIER
        elif entry["total_trades"] >= 2 and entry["win_rate"] >= 65.0 and decayed_wr >= 65.0 and loss_streak == 0:
            entry["status"] = "WIN_AMPLIFIER"
            entry["edge_boost"] = 0.05 if decayed_wr >= 80.0 else 0.035
            entry["decay_warning"] = None
        # 3. LOSS_TRAP
        elif entry["total_trades"] >= 2 and (entry["win_rate"] <= 35.0 or decayed_wr <= 35.0):
            entry["status"] = "LOSS_TRAP"
            entry["edge_boost"] = -0.06
            entry["decay_warning"] = None
        # 4. BALANCED
        elif entry["total_trades"] >= 2:
            entry["status"] = "BALANCED"
            entry["edge_boost"] = 0.0
            entry["decay_warning"] = None
        else:
            entry["status"] = "EXPLORATORY"
            entry["edge_boost"] = 0.0
            entry["decay_warning"] = None

        matrix[key] = entry
        data["pattern_matrix"] = matrix
        self._save_data(data)

    # =========================================================================
    # MULTI-TIER CONFLUENCE EVALUATION (HỘI TỤ ĐÁNH GIÁ 3 NGĂN)
    # =========================================================================
    def evaluate_signal_dna(self, signal_dna: Dict[str, Any], coin: Optional[str] = None) -> Dict[str, Any]:
        """
        Hội đồng đánh giá hợp nhất 3 Ngăn Trí Nhớ:
        - Tier 1: Kiểm tra riêng đồng Coin (Ngăn 1). Nếu coin dính chuỗi thua, phòng vệ riêng cho coin đó.
        - Tier 2: Kiểm tra hiệu suất Chiến thuật (Ngăn 2). Cộng Edge nếu chiến thuật có lịch sử thắng cao.
        - Tier 3: Kiểm tra Mẫu hình toàn cầu (Ngăn 3). Nhận diện Alpha Decay và Bẫy Thua (Loss Trap).
        """
        data = self._load_data()
        sym_matrix = data.get("symbol_matrix", {})
        strat_matrix = data.get("strategy_matrix", {})
        pat_matrix = data.get("pattern_matrix", {})

        target_coin = (coin or (signal_dna.get("coin") if signal_dna else "UNKNOWN")).upper().replace("USDT", "").strip()
        strat_key = signal_dna.get("strategy", "RANGE_SCALP") if signal_dna else "RANGE_SCALP"
        pat_key = signal_dna.get("pattern_key", "") if signal_dna else ""

        # --- 1. Tier 1: Coin Profile Check ---
        coin_entry = sym_matrix.get(target_coin)
        coin_status = "NEUTRAL"
        coin_defense_lock = False
        coin_edge_adj = 0.0
        coin_advice = f"Đồng {target_coin}: Vận hành bình thường theo kỷ luật vốn."

        if coin_entry:
            coin_loss_streak = coin_entry.get("recent_loss_streak", 0)
            coin_decayed_wr = coin_entry.get("decayed_win_rate", 50.0)
            if coin_entry.get("status") == "DEFENSE_LOCK" or coin_loss_streak >= 2:
                coin_status = "DEFENSE_LOCK"
                coin_defense_lock = True
                coin_edge_adj = -0.02
                coin_advice = (
                    f"🛡️ [Phòng Thủ Phân Lập Riêng {target_coin}] Đang dính chuỗi {coin_loss_streak} SL gần nhất. "
                    f"Giảm 50% khối lượng cược và siết đòn bẩy cho riêng {target_coin}! KHÔNG ảnh hưởng coin khác."
                )
            elif coin_entry.get("status") == "HEALTHY" and coin_entry.get("win_rate", 0) >= 65.0:
                coin_status = "HEALTHY"
                coin_edge_adj = +0.015
                coin_advice = (
                    f"⭐ [Phong Độ Cao Riêng {target_coin}] Tỷ lệ thắng {coin_entry['win_rate']:.1f}% "
                    f"({coin_entry['wins']}/{coin_entry['total_trades']} lệnh). Tối ưu hóa điểm vào lệnh."
                )

        # --- 2. Tier 2: Strategy Profile Check ---
        strat_entry = strat_matrix.get(strat_key)
        strat_status = "CALIBRATING"
        strat_edge_adj = 0.0
        strat_advice = f"Chiến thuật {strat_key}: Đang kiểm định định lượng."

        if strat_entry:
            strat_status = strat_entry.get("status", "CALIBRATING")
            strat_edge_adj = strat_entry.get("edge_adjustment", 0.0)
            if strat_status == "PROVEN_EDGE":
                strat_advice = (
                    f"🎯 [Chiến Thuật Vàng] {strat_entry['display_label']} đạt tỷ lệ thắng {strat_entry['win_rate']:.1f}% "
                    f"(Gần đây: {strat_entry['decayed_win_rate']:.1f}%). Thưởng thêm +{strat_edge_adj*100:.1f}% Edge!"
                )
            elif strat_status == "UNDERPERFORMING":
                strat_advice = (
                    f"⚠️ [Chiến Thuật Bị Phạt] {strat_entry['display_label']} đang có hiệu suất thấp ({strat_entry['win_rate']:.1f}%). "
                    f"Trừ {abs(strat_edge_adj)*100:.1f}% Edge để hạn chế vào lệnh rủi ro."
                )

        # --- 3. Tier 3: Global Pattern Matrix Check ---
        pat_entry = pat_matrix.get(pat_key)
        pat_status = "NEUTRAL"
        pat_edge_adj = 0.0
        pat_advice = "Mẫu hình tiêu chuẩn."
        badge = "⚪ TÍN HIỆU TIÊU CHUẨN"

        if pat_entry and pat_entry.get("total_trades", 0) >= 2:
            pat_status = pat_entry.get("status", "BALANCED")
            pat_edge_adj = pat_entry.get("edge_boost", 0.0)
            wr = pat_entry.get("win_rate", 50.0)
            decayed_wr = pat_entry.get("decayed_win_rate", wr)
            loss_streak = pat_entry.get("recent_loss_streak", 0)

            if pat_status == "ALPHA_DECAY":
                badge = f"⚡ SUY GIẢM HIỆU QUẢ (ALPHA DECAY: {loss_streak} SL)"
                pat_advice = (
                    f"[Cảnh Báo Đổi Chế Độ Thị Trường] Mẫu hình '{pat_entry['display_label']}' từng thắng {wr:.1f}%, "
                    f"nhưng thua {loss_streak} lệnh gần đây (Tỷ lệ thắng gần đây {decayed_wr:.1f}%). Trừ {abs(pat_edge_adj)*100:.1f}% Edge!"
                )
            elif pat_status == "WIN_AMPLIFIER":
                badge = f"🎯 MẪU HÌNH VÀNG (+{pat_edge_adj*100:.1f}% EDGE)"
                pat_advice = (
                    f"[Khuếch Đại Tín Hiệu Thắng] Mẫu hình '{pat_entry['display_label']}' phong độ cao "
                    f"(Tổng {wr:.1f}% | Gần đây {decayed_wr:.1f}%). Thưởng thêm +{pat_edge_adj*100:.1f}% Edge!"
                )
            elif pat_status == "LOSS_TRAP":
                badge = f"⚠️ BẪY THUA QUÁ KHỨ ({pat_edge_adj*100:.1f}% EDGE)"
                pat_advice = (
                    f"[Cảnh Báo Bẫy Thua] Mẫu hình '{pat_entry['display_label']}' có tỷ lệ dính SL cao ({100-wr:.1f}%). VETO hoặc HOLD bảo toàn vốn!"
                )
            else:
                badge = "⚖️ MẪU HÌNH CÂN BẰNG"
                pat_advice = f"Mẫu hình '{pat_entry['display_label']}' cân bằng (Thắng {wr:.1f}%)."
        else:
            # Fallback rules nếu chưa có pattern cụ thể
            side = signal_dna.get("side", "LONG") if signal_dna else "LONG"
            if side == "LONG" and signal_dna and signal_dna.get("rsi_zone") == "OVERBOUGHT" and signal_dna.get("orderbook_bias") in ["STRONG_ASK", "MODERATE_ASK"]:
                pat_status = "LOSS_TRAP"
                pat_edge_adj = -0.06
                badge = "⚠️ BẪY ĐU ĐỈNH (LOSS TRAP)"
                pat_advice = "[Cảnh Báo Bẫy Thua] Dấu hiệu LONG khi RSI quá mua (>65) gặp tường Bán đè giá. Tự động trừ -6.0% Lợi thế!"
            else:
                badge = "⚪ TÍN HIỆU TIÊU CHUẨN"
                pat_advice = "Tín hiệu mới chưa ghi nhận bẫy quá khứ, áp dụng quản trị vốn mặc định."

        # --- 4. Synthesis & Edge Confluence ---
        raw_combined_edge = coin_edge_adj + strat_edge_adj + pat_edge_adj
        # Giới hạn biến động Edge trong khoảng an toàn [-0.08, +0.08]
        combined_edge = max(-0.08, min(0.08, round(raw_combined_edge, 4)))

        # Xác định Primary Status
        if pat_status == "LOSS_TRAP":
            overall_status = "LOSS_TRAP"
        elif coin_status == "DEFENSE_LOCK":
            overall_status = "COIN_DEFENSE"
            badge = f"🛡️ PHÒNG THỦ RIÊNG {target_coin}"
        elif pat_status == "ALPHA_DECAY":
            overall_status = "ALPHA_DECAY"
        elif pat_status == "WIN_AMPLIFIER" or strat_status == "PROVEN_EDGE":
            overall_status = "WIN_AMPLIFIER"
        else:
            overall_status = "BALANCED"

        combined_advice = f"{pat_advice} | {strat_advice} | {coin_advice}"

        return {
            "status": overall_status,
            "edge_adjustment": combined_edge,
            "coin_defense_lock": coin_defense_lock,
            "badge": badge,
            "advice": combined_advice,
            "coin_eval": {
                "symbol": target_coin,
                "category": coin_entry.get("category", "ALTCOIN") if coin_entry else "ALTCOIN",
                "status": coin_status,
                "win_rate": coin_entry.get("win_rate", 50.0) if coin_entry else 50.0,
                "decayed_win_rate": coin_entry.get("decayed_win_rate", 50.0) if coin_entry else 50.0,
                "recent_loss_streak": coin_entry.get("recent_loss_streak", 0) if coin_entry else 0,
                "advice": coin_advice
            },
            "strategy_eval": {
                "strategy_key": strat_key,
                "status": strat_status,
                "win_rate": strat_entry.get("win_rate", 50.0) if strat_entry else 50.0,
                "decayed_win_rate": strat_entry.get("decayed_win_rate", 50.0) if strat_entry else 50.0,
                "edge_adjustment": strat_edge_adj,
                "advice": strat_advice
            },
            "pattern_eval": {
                "status": pat_status,
                "edge_adjustment": pat_edge_adj,
                "display_label": signal_dna.get("display_label", pat_key) if signal_dna else pat_key,
                "advice": pat_advice
            }
        }

    # =========================================================================
    # GHI NHẬN BÀI HỌC VÀ CẬP NHẬT CẢ 3 NGĂN TRÍ NHỚ
    # =========================================================================
    def record_trade_reflection(
        self,
        trade_data: Dict[str, Any],
        signal_dna: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Phân tích kết quả lệnh vừa đóng và tạo bài học tự phản tỉnh (Reflection),
        đồng thời cập nhật đồng bộ CẢ 3 NGĂN:
        1. Ngăn 1: update_symbol_matrix(coin)
        2. Ngăn 2: update_strategy_matrix(strategy)
        3. Ngăn 3: update_pattern_matrix(signal_dna)
        """
        raw_sym = trade_data.get("symbol", "COIN")
        sym = raw_sym.upper().replace("USDT", "").strip()
        outcome = trade_data.get("action", "").replace("CLOSE_", "")
        pnl = float(trade_data.get("pnl", 0.0))
        pnl_pct = float(trade_data.get("pnl_percent", 0.0))
        reason = trade_data.get("reason", "MANUAL")
        leverage = trade_data.get("leverage", 1)
        entry_p = float(trade_data.get("entry_price", trade_data.get("price", 0.0)))
        exit_p = float(trade_data.get("exit_price", trade_data.get("price", 0.0)))

        is_win = (pnl > 0.0001) and (reason not in ["STOP_LOSS", "LIQUIDATION"])

        # Phân tích nguyên nhân gốc rễ (Root-Cause Attribution)
        if is_win:
            if reason == "TAKE_PROFIT":
                if signal_dna and signal_dna.get("smc_pattern") != "NONE":
                    root_cause = f"Thắng nhờ bẫy SMC {signal_dna.get('smc_pattern')}: Râu nến quét thanh khoản tạo điểm vào SL cực hẹp, xung lực phi thẳng tới TP (+{pnl_pct:.1f}%)."
                elif signal_dna and signal_dna.get("orderbook_bias") in ["STRONG_BID", "STRONG_ASK"]:
                    root_cause = f"Thắng nhờ dòng tiền lớn: Lực gom/xả Orderbook {signal_dna.get('orderbook_ratio', 1.0):.2f}x tạo đà bứt phá mạnh (+{pnl_pct:.1f}%)."
                else:
                    root_cause = f"Thắng nhờ kỷ luật R:R: Tín hiệu đồng thuận đưa giá chạm trúng đích chốt lời (+{pnl_pct:.1f}%)."
                lesson = f"Thắng lớn ({pnl:+,.2f}$ / {pnl_pct:+.1f}%): Lệnh {outcome} {sym} chạm trúng mốc Chốt lời (TP). Tỷ lệ R:R được duy trì nghiêm ngặt."
                takeaway = "Tiếp tục giữ kỷ luật điểm TP theo cấu trúc thanh khoản, không chốt non."
            else:
                root_cause = f"Chốt lời chủ động an toàn (+{pnl_pct:.1f}%): Nhận diện xung lực suy kiệt để bảo toàn vốn."
                lesson = f"Chốt lời thành công ({pnl:+,.2f}$ / {pnl_pct:+.1f}%): Vị thế {outcome} {sym} đóng xanh an toàn theo chiến thuật chủ động."
                takeaway = "Bảo toàn lợi nhuận tốt khi xung lực thị trường có dấu hiệu suy kiệt."
        else:
            if reason == "STOP_LOSS":
                if signal_dna and signal_dna.get("rsi_zone") == "OVERBOUGHT" and outcome == "LONG":
                    root_cause = "Thua do bẫy đu đỉnh (FOMO): Mở LONG ở vùng RSI quá mua (>65), giá kiệt sức mua và bị cá mập quét râu ngược."
                elif signal_dna and signal_dna.get("orderbook_bias") in ["STRONG_ASK", "MODERATE_ASK"] and outcome == "LONG":
                    root_cause = "Thua do cản tàu tường Bán: Mở LONG khi phe Bán đang treo tường Ask dày đặc, áp lực xả đè bẹp lực cầu."
                elif signal_dna and signal_dna.get("orderbook_bias") in ["STRONG_BID", "MODERATE_BID"] and outcome == "SHORT":
                    root_cause = "Thua do cản xe tăng phe Mua: Mở SHORT khi tường Mua đang gom hàng áp đảo, giá bị đẩy vọt lên."
                else:
                    root_cause = "Thua do biến động bất ngờ: Thị trường đảo chiều quét qua ngưỡng cắt lỗ để tái tích lũy."
                lesson = f"Cắt lỗ an toàn ({pnl:+,.2f}$ / {pnl_pct:+.1f}%): Lệnh {outcome} {sym} dính SL do giá đảo chiều. Tấm khiên SL đã bảo vệ vốn."
                takeaway = "SL đã làm tròn nhiệm vụ bảo vệ tài khoản. Cần rà soát kỹ cản EMA và sổ lệnh trước khi vào lệnh tiếp."
            elif reason == "LIQUIDATION":
                root_cause = "Thua do buông thả rủi ro: Không đặt Stop-Loss trên vị thế đòn bẩy cao."
                lesson = f"CẢNH BÁO NGUY HIỂM ({pnl:+,.2f}$): Vị thế {outcome} {sym} bị thanh lý do bỏ qua ngưỡng cắt lỗ."
                takeaway = "TUYỆT ĐỐI KHÔNG thả rông lệnh với đòn bẩy cao. Mọi lệnh Scalp bắt buộc phải có Hard SL."
            else:
                root_cause = f"Cắt lỗ chủ động (-{abs(pnl_pct):.1f}%): Vị thế đi ngược dự báo ban đầu, chủ động đóng sớm để hạn chế rủi ro."
                lesson = f"Thua lỗ ({pnl:+,.2f}$ / {pnl_pct:+.1f}%): Đóng lệnh {outcome} {sym} khi vị thế đi ngược kỳ vọng ban đầu."
                takeaway = "Cắt lỗ chủ động là hành động dũng cảm để giữ tiền cho cơ hội kế tiếp."

        # Hoàn thiện thông tin DNA nếu thiếu coin hoặc chiến thuật
        if signal_dna:
            if not signal_dna.get("coin"):
                signal_dna["coin"] = sym
            if not signal_dna.get("strategy"):
                strat_k, strat_l = self.classify_strategy(
                    signal_dna.get("smc_pattern", ""),
                    signal_dna.get("vsa_signal", ""),
                    signal_dna.get("rsi_zone", "")
                )
                signal_dna["strategy"] = strat_k
                signal_dna["strategy_label"] = strat_l

        reflection_item = {
            "id": f"ref_{int(datetime.now().timestamp())}_{sym}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "symbol": sym,
            "side": outcome,
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
            "reason": reason,
            "leverage": leverage,
            "entry_price": entry_p,
            "exit_price": exit_p,
            "is_win": is_win,
            "signal_dna": signal_dna or {},
            "root_cause": root_cause,
            "lesson": lesson,
            "takeaway": takeaway
        }

        data = self._load_data()
        data["total_settled_trades"] = data.get("total_settled_trades", 0) + 1
        data["reflections"].insert(0, reflection_item)
        
        # Giữ tối đa 100 bài học gần nhất
        if len(data["reflections"]) > 100:
            data["reflections"] = data["reflections"][:100]

        self._save_data(data)

        # CẬP NHẬT ĐỒNG BỘ CẢ 3 NGĂN:
        # 1. Ngăn 1: Cập nhật Trí nhớ riêng cho từng đồng coin
        self.update_symbol_matrix(sym, is_win, pnl_pct, strategy=(signal_dna.get("strategy") if signal_dna else None))

        # 2. Ngăn 2: Cập nhật Trí nhớ riêng cho từng chiến thuật
        strat_key = signal_dna.get("strategy", "RANGE_SCALP") if signal_dna else "RANGE_SCALP"
        self.update_strategy_matrix(strat_key, is_win, pnl_pct, coin=sym)

        # 3. Ngăn 3: Cập nhật Ma trận mẫu hình toàn cầu
        if signal_dna:
            self.update_pattern_matrix(signal_dna, is_win, pnl_pct)

        return reflection_item

    def get_pattern_insights(self) -> Dict[str, Any]:
        """
        Trích xuất danh sách các mẫu hình toàn cầu (Ngăn 3).
        """
        data = self._load_data()
        matrix = data.get("pattern_matrix", {})
        all_patterns = list(matrix.values())

        win_amplifiers = [p for p in all_patterns if p.get("status") == "WIN_AMPLIFIER"]
        win_amplifiers.sort(key=lambda x: (x.get("decayed_win_rate", x.get("win_rate", 0)), x.get("win_rate", 0)), reverse=True)

        alpha_decaying = [p for p in all_patterns if p.get("status") == "ALPHA_DECAY"]
        alpha_decaying.sort(key=lambda x: (x.get("recent_loss_streak", 0), -x.get("decayed_win_rate", 0)), reverse=True)

        loss_traps = [p for p in all_patterns if p.get("status") == "LOSS_TRAP"]
        loss_traps.sort(key=lambda x: (x.get("win_rate", 0), -x.get("total_trades", 0)))

        return {
            "win_amplifiers": win_amplifiers,
            "alpha_decaying": alpha_decaying,
            "loss_traps": loss_traps,
            "total_patterns_tracked": len(all_patterns),
            "patterns": all_patterns
        }

    def get_recent_lessons(self, symbol: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Lấy các bài học kinh nghiệm gần nhất (theo từng đồng coin hoặc toàn danh mục).
        """
        data = self._load_data()
        reflections = data.get("reflections", [])
        if symbol:
            clean_sym = symbol.upper().replace("USDT", "").strip()
            matched = [r for r in reflections if r.get("symbol", "").upper() == clean_sym]
            return matched[:limit]
        return reflections[:limit]

    def get_symbol_track_record(self, symbol: str) -> Dict[str, Any]:
        """
        Đánh giá lịch sử hiệu suất của một đồng coin cụ thể từ Ngăn 1 (symbol_matrix).
        """
        clean_sym = symbol.upper().replace("USDT", "").strip()
        data = self._load_data()
        sym_matrix = data.get("symbol_matrix", {})
        is_cooling, rem_sec, cool_reason = self.is_coin_in_cooldown(clean_sym)

        if clean_sym in sym_matrix:
            entry = sym_matrix[clean_sym]
            return {
                "total": entry["total_trades"],
                "wins": entry["wins"],
                "losses": entry["losses"],
                "win_rate": entry["win_rate"],
                "decayed_win_rate": entry["decayed_win_rate"],
                "loss_streak": entry["recent_loss_streak"],
                "win_streak": entry["recent_win_streak"],
                "status": "COOLDOWN_LOCK" if is_cooling else entry["status"],
                "advice": cool_reason or entry["defense_warning"] or f"Đồng {clean_sym} hoạt động ổn định (Tỷ lệ thắng {entry['win_rate']}%).",
                "is_in_cooldown": is_cooling,
                "cooldown_remaining_sec": rem_sec,
                "cooldown_reason": cool_reason,
                "latest_lesson": ""
            }

        # Fallback to reflections
        lessons = self.get_recent_lessons(symbol=symbol, limit=10)
        if not lessons:
            return {"total": 0, "win_streak": 0, "loss_streak": 0, "advice": "Chưa có dữ liệu quá khứ cho đồng coin này."}

        losses = [l for l in lessons if not l.get("is_win", False)]
        wins = [l for l in lessons if l.get("is_win", False)]

        loss_streak = 0
        for l in lessons:
            if not l.get("is_win", False):
                loss_streak += 1
            else:
                break

        advice = "Hiệu suất ổn định."
        if loss_streak >= 2:
            advice = f"CẢNH BÁO PHÒNG THỦ: Đồng {clean_sym} đã dính cắt lỗ {loss_streak} lệnh liên tiếp gần đây. Cần siết chặt khối lượng và đòn bẩy!"

        return {
            "total": len(lessons),
            "wins": len(wins),
            "losses": len(losses),
            "loss_streak": loss_streak,
            "advice": advice,
            "latest_lesson": lessons[0]["lesson"] if lessons else ""
        }

    def get_summary(self) -> Dict[str, Any]:
        """
        Xuất toàn bộ cấu trúc Trí nhớ 3 Ngăn cho API và giao diện Dashboard.
        """
        data = self._load_data()
        reflections = data.get("reflections", [])
        total = len(reflections)
        wins = sum(1 for r in reflections if r.get("is_win", False))
        losses = total - wins
        win_rate = (wins / total * 100) if total > 0 else 0.0

        insights = self.get_pattern_insights()

        # Danh sách Strategy Matrix
        strat_matrix = data.get("strategy_matrix", {})
        strategy_list = list(strat_matrix.values())
        strategy_list.sort(key=lambda x: (x.get("decayed_win_rate", x.get("win_rate", 0)), x.get("win_rate", 0)), reverse=True)

        # Danh sách Symbol Matrix
        sym_matrix = data.get("symbol_matrix", {})
        symbol_list = list(sym_matrix.values())
        symbol_list.sort(key=lambda x: x.get("total_trades", 0), reverse=True)

        return {
            "version": data.get("version", "3.0"),
            "total_settled_trades": data.get("total_settled_trades", total),
            "total_reflections": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "strategy_matrix": strategy_list,
            "symbol_matrix": symbol_list,
            "win_amplifiers": insights["win_amplifiers"],
            "alpha_decaying": insights["alpha_decaying"],
            "loss_traps": insights["loss_traps"],
            "total_patterns_tracked": insights["total_patterns_tracked"],
            "recent_reflections": reflections[:15]
        }
