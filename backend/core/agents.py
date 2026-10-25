import math
import random
from typing import Dict, Any, List, Optional
from .news_fetcher import search_google_news
from .portfolio import PortfolioManager, normalize_price_precision
from .quant_indicators import analyze_quant_structure, detect_volatility_dynamics
from ..config import (
    KELLY_FRACTION, 
    MAX_PORTFOLIO_PER_TRADE, 
    MIN_EDGE_THRESHOLD,
    DEFAULT_LEVERAGE,
    MAX_LEVERAGE,
    DEFAULT_SL_PERCENT,
    DEFAULT_TP_PERCENT
)
from .trading_memory import TradingMemoryManager
from .strategy_profiles import strategy_manager
from .session_manager import get_current_session, evaluate_session_gate

def run_bull_bear_debate(
    selected_coin: str,
    chosen_side: str,
    quant_res: Dict[str, Any],
    orderbook_ratio: float,
    news_score: int,
    recent_lessons: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Skill: Adversarial Bull vs Bear Debate (Tranh Biện Đối Kháng AI)
    Inspired by TauricResearch/TradingAgents:
    - Bull Researcher: Đưa ra luận cứ bảo vệ phe LONG hoặc cơ hội tăng giá.
    - Bear Researcher: Đóng vai 'Luật sư của Quỷ' (Devil's Advocate), phản bác rủi ro, bẫy giá.
    - Research Manager: Tổng kết phán quyết tranh biện (Debate Verdict).
    """
    trend_desc = quant_res.get("trend_desc", "")
    rsi = quant_res.get("rsi", 50)
    vsa = quant_res.get("vsa", {})
    smc = quant_res.get("smc", {})

    # 1. Bull Case
    bull_points = []
    if chosen_side == "LONG":
        bull_points.append(f"Cấu trúc kỹ thuật ủng hộ: {trend_desc}. RSI(14)={rsi} nằm trong vùng mở rộng tốt.")
        if smc.get("detected") and "BULLISH" in smc.get("pattern", ""):
            bull_points.append(f"Dấu chân cá mập: {smc['description']}.")
        if vsa.get("signal") in ["BULLISH_EXPANSION", "STOPPING_VOLUME", "NO_SUPPLY"]:
            bull_points.append(f"VSA dòng tiền: {vsa['description']}.")
        if orderbook_ratio >= 1.02:
            bull_points.append(f"Sổ lệnh L2: Lực mua áp đảo (Bid/Ask {orderbook_ratio:.2f}x).")
        if news_score > 0:
            bull_points.append(f"Tin tức hỗ trợ (+{news_score} điểm).")
    else:
        bull_points.append(f"Cảnh báo phe Bò: Dù tín hiệu SHORT, cần lưu ý các vùng hỗ trợ EMA và lực đỡ tiềm năng.")

    bull_case = " ".join(bull_points) if bull_points else f"Phe Bò ghi nhận động lực kiểm định ngưỡng cản của {selected_coin}."

    # 2. Bear Case (Devil's Advocate / Phản biện rủi ro)
    bear_points = []
    if chosen_side == "SHORT":
        bear_points.append(f"Cấu trúc kỹ thuật suy yếu: {trend_desc}. Phe Bán kiểm soát thế trận.")
        if smc.get("detected") and "BEARISH" in smc.get("pattern", ""):
            bear_points.append(f"Bẫy thanh khoản cá mập: {smc['description']}.")
        if vsa.get("signal") in ["BEARISH_EXPANSION", "ABSORPTION_TRAP", "NO_DEMAND"]:
            bear_points.append(f"VSA cảnh báo xả: {vsa['description']}.")
        if orderbook_ratio <= 0.98:
            bear_points.append(f"Sổ lệnh L2: Áp lực bán đè nặng (Bid/Ask {orderbook_ratio:.2f}x).")
    else:
        # Cross-examining LONG:
        bear_points.append(f"Phản biện rủi ro lệnh LONG: RSI={rsi} tiệm cận vùng cản. Cần đề phòng bẫy rút râu quét stop-loss trước khi đảo chiều.")
        if orderbook_ratio < 1.0:
            bear_points.append(f"Cảnh báo sổ lệnh: Phe Bán vẫn đang treo tường Ask dày đặc ({orderbook_ratio:.2f}x).")
        if recent_lessons:
            bear_points.append(f"Lưu ý bài học quá khứ: {recent_lessons[0].get('takeaway', '')}")

    bear_case = " ".join(bear_points) if bear_points else f"Phe Gấu nhắc nhở tuân thủ tuyệt đối quy tắc cắt lỗ, đề phòng biến động bất ngờ."

    # 3. Debate Verdict
    if chosen_side == "LONG":
        verdict = "BULL_DOMINANT" if (smc.get("detected") or orderbook_ratio >= 1.08) else "BULL_MODERATE"
        verdict_text = "Phe Bò chiếm ưu thế rõ rệt dựa trên dữ liệu dòng tiền và SMC."
    elif chosen_side == "SHORT":
        verdict = "BEAR_DOMINANT" if (smc.get("detected") or orderbook_ratio <= 0.92) else "BEAR_MODERATE"
        verdict_text = "Phe Gấu chiếm ưu thế áp đảo, cấu trúc giá nghiêng về giảm."
    else:
        verdict = "BALANCED"
        verdict_text = "Hai phe cân bằng, thị trường lưỡng lự chưa rõ xu hướng."

    return {
        "bull_case": bull_case,
        "bear_case": bear_case,
        "verdict": verdict,
        "verdict_text": verdict_text
    }

class SwarmEngine:
    def __init__(self, portfolio: PortfolioManager, crypto_service=None, proposal_manager=None):
        self.portfolio = portfolio
        self.crypto_service = crypto_service
        self.proposal_manager = proposal_manager
        self.memory_manager = TradingMemoryManager()

    def run_crypto_cycle(
        self,
        target_coin: Optional[str] = None,
        timeframe: str = "1m",
        max_leverage: Optional[int] = None,
        max_stake: Optional[float] = None,
        custom_sl_pct: Optional[float] = None,
        custom_tp_pct: Optional[float] = None,
        as_proposal: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a 4-Agent Swarm cycle specifically targeted on a Crypto coin:
        1. Spotter Agent: Selects coin from user's watchlist, inspects 24h liquidity & order book depth.
        2. Researcher Agent: Queries live Google News RSS for coin catalysts and regulatory news.
        3. The Pricer Agent: Weighs orderbook depth bias + momentum + news sentiment to compute directional edge.
        4. Kelly Risk Agent: Computes Quarter-Kelly allocation & executes mock crypto trade.
        """
        if not self.crypto_service:
            self.portfolio.log_thought("Spotter", "WARN", "CryptoService not configured.")
            return {"status": "no_crypto_service"}

        watchlist = self.crypto_service.watchlist
        if not watchlist:
            self.portfolio.log_thought("Spotter", "WARN", "Watchlist is empty. Add coins to enable Crypto Swarm scan.")
            return {"status": "empty_watchlist"}

        # 0. ACTIVE STRATEGY PROFILE & CURRENT TRADING SESSION RETRIEVAL
        active_strat = strategy_manager.get_active_strategy()
        session_info = get_current_session()

        # 1. SPOTTER AGENT
        active_coins = [c for c in watchlist if self.crypto_service.active_status.get(c, True)]
        if not active_coins:
            active_coins = watchlist

        # Lấy danh sách coin khuyến nghị của chiến lược (nếu có, để cộng điểm ưu tiên)
        strat_coins = active_strat.get("target_coins", [])

        # Identify coins that already have active open positions
        open_positions = self.portfolio.state.get("open_positions", {})
        open_symbols = {
            pos.get("symbol", "").upper()
            for pos in open_positions.values()
            if pos.get("symbol")
        }

        # Identify coins that already have pending proposals
        pending_symbols = set()
        if self.proposal_manager:
            pending_symbols = {
                p.get("coin", "").upper()
                for p in self.proposal_manager.get_pending()
                if p.get("coin")
            }

        occupied_symbols = open_symbols | pending_symbols

        if target_coin:
            clean_target = target_coin.strip().upper().replace("USDT", "")
            if clean_target not in [c.upper() for c in watchlist]:
                self.crypto_service.add_coin(clean_target)
                watchlist = self.crypto_service.watchlist
            selected_coin = clean_target

            # If user explicitly scanned a coin that is already active
            if selected_coin in open_symbols:
                existing_pos = next(
                    (p for p in open_positions.values() if p.get("symbol", "").upper() == selected_coin),
                    None
                )
                side_info = f"{existing_pos['outcome']} {existing_pos.get('leverage', 1)}x" if existing_pos else "ĐANG MỞ"
                self.portfolio.log_thought(
                    "Spotter",
                    "WARN",
                    f"Từ chối quét {selected_coin}: Đồng coin này hiện đã có vị thế mở ({side_info}). Hãy đóng vị thế cũ trước khi quét mới."
                )
                return {
                    "status": "position_already_open",
                    "coin": selected_coin,
                    "existing_position": existing_pos
                }

            # Anti-Chop Cooldown Check cho mục tiêu thủ công
            is_cooling, rem_sec, cool_reason = self.memory_manager.is_coin_in_cooldown(selected_coin)
            if is_cooling:
                self.portfolio.log_thought("Risk Guard", "WARN", cool_reason)
                return {
                    "status": "hold",
                    "coin": selected_coin,
                    "reason": cool_reason
                }

            # If coin already has a stale pending proposal, clear it so fresh scan produces real-time up-to-date data!
            if selected_coin in pending_symbols and self.proposal_manager:
                self.proposal_manager.clear_pending_for_coin(selected_coin)
                self.portfolio.log_thought(
                    "Spotter",
                    "INFO",
                    f"Làm mới đề xuất cho {selected_coin}: Hủy đề xuất chờ duyệt cũ để cập nhật dữ liệu nến và giá thời gian thực."
                )
        else:
            # Auto-scan mode: Lọc bỏ các coin đang có vị thế mở, đề xuất chờ, HOẶC đang trong Cooldown chống càn quét
            available_coins = []
            for c in active_coins:
                c_clean = c.upper().replace("USDT", "").strip()
                if c_clean in occupied_symbols:
                    continue
                is_cooling, rem_sec, cool_reason = self.memory_manager.is_coin_in_cooldown(c_clean)
                if is_cooling:
                    continue
                available_coins.append(c)

            if not available_coins:
                cooling_coins = [c for c in active_coins if self.memory_manager.is_coin_in_cooldown(c.upper().replace("USDT", "").strip())[0]]
                cool_msg = f" (Trong đó {len(cooling_coins)} coin đang nghỉ Cooldown sau lệnh thua: {', '.join(cooling_coins)})" if cooling_coins else ""
                self.portfolio.log_thought(
                    "Spotter",
                    "INFO",
                    f"Tất cả {len(active_coins)} đồng coin đều đã có lệnh mở hoặc đang trong thời gian nghỉ Cooldown bảo toàn vốn{cool_msg}. Tạm dừng mở mới."
                )
                return {
                    "status": "all_coins_occupied",
                    "occupied_symbols": list(occupied_symbols),
                    "cooling_symbols": cooling_coins
                }

            # Lấy danh sách 3 coin gần nhất vừa đóng lệnh để kích hoạt cơ chế Xoay Vòng Chống Độc Quyền (Anti-Monopoly Rotation)
            recent_trades = self.portfolio.state.get("trades_history", [])
            last_traded_coins = [t.get("symbol", "").upper() for t in recent_trades[:3] if t.get("symbol")]

            # Quét xung lực & dự đoán biến động trên tất cả coin khả dụng kết hợp Trí nhớ AI 3 Ngăn
            strat_badge = active_strat.get("badge", "Sniper")
            session_badge = session_info.get("badge", "Phiên")
            self.portfolio.log_thought(
                "Spotter",
                "INFO",
                f"[{session_badge}] Bắt đầu quét xung lực {len(available_coins)} coin khả dụng: {', '.join(available_coins)} (Chiến lược: {strat_badge} | {session_info['time_range']})"
            )

            ranked_candidates = []
            for c in available_coins:
                c_clean = c.upper().replace("USDT", "").strip()
                c_klines = self.crypto_service.fetch_klines(c, interval=timeframe, limit=30)
                c_candles = c_klines.get("candles", []) if isinstance(c_klines, dict) else []
                if c_candles and len(c_candles) >= 15:
                    c_depth = self.crypto_service.fetch_coin_depth(c, limit=10)
                    c_ratio = c_depth.get("bid_ask_ratio", 1.0) if "error" not in c_depth else 1.0
                    v_dyn = detect_volatility_dynamics(c_candles, c_ratio)
                    base_vsi = v_dyn["vsi_score"]
                else:
                    v_dyn = {"state": "LOW_VOLATILITY", "vsi_score": 40.0, "description": "Ít dữ liệu"}
                    base_vsi = 40.0

                # Điều chỉnh độ ưu tiên lựa chọn theo Trí Nhớ Phân Lập (Ngăn 1):
                track = self.memory_manager.get_symbol_track_record(c_clean)
                priority_score = base_vsi

                # 0. Ưu tiên cộng điểm (+10) nếu đồng coin nằm trong danh mục trọng tâm của chiến lược hiện tại
                if strat_coins and c_clean in [sc.upper() for sc in strat_coins]:
                    priority_score += 10.0

                # 1. Nếu coin đang dính chuỗi thua hoặc DEFENSE_LOCK -> Phạt nặng để AI KHÔNG tiếp tục đâm đầu vào!
                if track.get("status") == "DEFENSE_LOCK" or track.get("loss_streak", 0) >= 2:
                    priority_score -= 60.0
                elif track.get("loss_streak", 0) == 1:
                    priority_score -= 20.0
                elif track.get("status") == "HEALTHY":
                    priority_score += 15.0

                # 2. Cơ chế Xoay Vòng Chống Độc Quyền (Anti-Monopoly Rotation):
                # Nếu coin này vừa khớp lệnh gần đây, trừ điểm để luân chuyển sang các coin khác trong Watchlist
                if c_clean in last_traded_coins:
                    priority_score -= 35.0

                ranked_candidates.append((c, priority_score, base_vsi, v_dyn))

            ranked_candidates.sort(key=lambda x: x[1], reverse=True)
            selected_coin = ranked_candidates[0][0]
            top_priority = ranked_candidates[0][1]
            top_vsi = ranked_candidates[0][2]
            top_dyn = ranked_candidates[0][3]
            score_summary = " | ".join([f"{c}: {p:.0f}đ" for c, p, _, _ in ranked_candidates[:4]])
            self.portfolio.log_thought(
                "Spotter",
                "SUCCESS",
                f"[Săn Biến Động] Đã chọn mục tiêu tối ưu: {selected_coin}/USDT (Điểm: {top_priority:.0f} | VSI: {top_vsi:.0f}/100 - {top_dyn.get('description', '')}) [Xếp hạng: {score_summary}]"
            )

        # Force live real-time ticker from Binance API (no stale cache)
        ticker = self.crypto_service.fetch_coin_ticker(selected_coin, force_refresh=True)
        if not ticker:
            self.portfolio.log_thought("Spotter", "WARN", f"Không thể lấy bảng giá trực tiếp từ Binance cho {selected_coin}.")
            return {"status": "ticker_error"}

        depth = self.crypto_service.fetch_coin_depth(selected_coin, limit=15)
        ratio = depth.get("bid_ask_ratio", 1.0) if "error" not in depth else 1.0
        depth_sentiment = depth.get("depth_sentiment", "Neutral Depth") if "error" not in depth else "N/A"

        self.portfolio.log_thought(
            "Spotter",
            "INFO",
            f"Đã khóa mục tiêu: {selected_coin}/USDT | Giá: {ticker['price_formatted']} | Thanh khoản 24h: {ticker['liquidity_formatted']} ({ticker['tier']}) | Sổ lệnh: {depth_sentiment} (Tỷ số {ratio})"
        )

        # 2. RESEARCHER AGENT
        articles = search_google_news(f"{selected_coin} crypto market", max_results=3)
        if articles:
            headlines_summary = " | ".join([f"[{a['source']}] {a['title'][:55]}..." for a in articles[:2]])
        else:
            headlines_summary = f"Không có cảnh báo tin tức đột biến cho {selected_coin} trong 12h qua."

        self.portfolio.log_thought(
            "Researcher",
            "INFO",
            f"Đã thu nạp {len(articles)} tin tức mới cho {selected_coin}: {headlines_summary}"
        )

        # 3. THE PRICER AGENT (100% Deterministic Quant & VSA Engine)
        pos_words = {"surge", "record", "rally", "gain", "breakout", "bull", "accumulate", "etf", "approve", "high", "growth", "pump", "support"}
        neg_words = {"drop", "crash", "plunge", "decline", "fall", "dump", "bear", "selloff", "reject", "sec", "ban", "risk", "liquidate"}

        news_score = 0
        for art in articles:
            text = (art.get("title", "") + " " + art.get("snippet", "")).lower()
            news_score += sum(1 for w in pos_words if w in text)
            news_score -= sum(1 for w in neg_words if w in text)

        # Fetch real candles from Binance for Trend, RSI and VSA Volume Analysis
        klines = self.crypto_service.fetch_klines(selected_coin, interval=timeframe, limit=60)
        candles = klines.get("candles", []) if isinstance(klines, dict) and "candles" in klines else []

        # Tích hợp Dữ liệu Nến Đa Khung Thời Gian (1H Macro + 15M Structure + 1M Trigger)
        mtf_data = None
        if active_strat.get("multi_timeframe"):
            mtf_data = self.crypto_service.fetch_multi_timeframe_klines(selected_coin)

        quant_res = analyze_quant_structure(
            candles=candles,
            orderbook_ratio=ratio,
            news_sentiment=news_score,
            mtf_data=mtf_data,
            use_patterns=active_strat.get("candlestick_patterns", True)
        )

        chosen_side = quant_res["chosen_side"]
        chosen_prob = quant_res["chosen_prob"]
        edge = quant_res["edge"]
        trend_desc = quant_res.get("trend_desc", "Trung tính")
        quant_summary = quant_res.get("summary", "")

        self.portfolio.log_thought(
            "The Pricer",
            "INFO",
            f"Định giá Định Lượng ({selected_coin}) [{active_strat['badge']}]: Tín hiệu={chosen_side} (P_fair={int(chosen_prob*100)}% | Lợi thế={edge:+.1%}) | {quant_summary}"
        )

        # Log nhận diện Mô hình Nến Price Action (Pinbar / Engulfing / Marubozu)
        pat_data = quant_res.get("candlestick_pattern", {})
        if pat_data.get("detected"):
            self.portfolio.log_thought(
                "The Pricer",
                "SUCCESS" if pat_data["signal"] in ["BULLISH", "BEARISH"] else "INFO",
                f"[Mô Hình Nến Price Action] {pat_data['description']}"
            )

        # Log Hợp lưu Đa Khung Thời Gian (1H - 15M - 1M)
        mtf_info = quant_res.get("multi_timeframe", {})
        if mtf_info.get("is_confluent"):
            self.portfolio.log_thought(
                "The Pricer",
                "SUCCESS",
                f"[Hợp Lưu Đa Khung 1H-15M-1M] {mtf_info['description']} (Điểm hợp lưu: {mtf_info['confluence_score']:+.2f})"
            )

        smc_data = quant_res.get("smc", {})
        if smc_data.get("detected"):
            self.portfolio.log_thought(
                "The Pricer",
                "INFO",
                f"[SMC Smart Money] {smc_data['description']}"
            )

        vol_data = quant_res.get("volatility", {})
        if vol_data.get("state") in ["ACTIVE_SURGE", "PREDICTED_BREAKOUT"]:
            self.portfolio.log_thought(
                "The Pricer",
                "SUCCESS",
                f"[Phát Hiện Biến Động] {vol_data['description']}"
            )

        # 3.4 SIGNAL DNA FINGERPRINT & META-LEARNING EVALUATION (Kiến Trúc Trí Nhớ 3 Ngăn Phân Lập)
        vsa_data = quant_res.get("vsa", {})
        signal_dna = self.memory_manager.build_signal_dna(
            side=chosen_side,
            quant_res=quant_res,
            orderbook_ratio=ratio,
            smc_data=smc_data,
            vsa_data=vsa_data,
            coin=selected_coin
        )

        meta_eval = self.memory_manager.evaluate_signal_dna(signal_dna, coin=selected_coin)
        edge_adj = meta_eval.get("edge_adjustment", 0.0)
        edge = round(edge + edge_adj, 4)

        # 3.5 ADVERSARIAL BULL VS BEAR DEBATE (TradingAgents Architecture)
        recent_lessons = self.memory_manager.get_recent_lessons(symbol=selected_coin, limit=3)
        track_record = self.memory_manager.get_symbol_track_record(symbol=selected_coin)

        debate = run_bull_bear_debate(
            selected_coin=selected_coin,
            chosen_side=chosen_side,
            quant_res=quant_res,
            orderbook_ratio=ratio,
            news_score=news_score,
            recent_lessons=recent_lessons
        )

        self.portfolio.log_thought(
            "Bull Analyst",
            "INFO",
            f"[Tranh Luận Phe Bò] {debate['bull_case']}"
        )
        self.portfolio.log_thought(
            "Bear Analyst",
            "WARN" if chosen_side == "LONG" else "INFO",
            f"[Tranh Luận Phe Gấu] {debate['bear_case']}"
        )
        self.portfolio.log_thought(
            "Research Manager",
            "SUCCESS",
            f"[Tổng Hợp Tranh Biện] {debate['verdict_text']}"
        )

        # Kiểm tra trí nhớ quá khứ & Học tăng cường (Trading Memory Meta-Learning 3 Ngăn)
        coin_ev = meta_eval.get("coin_eval", {})
        strat_ev = meta_eval.get("strategy_eval", {})

        if coin_ev.get("status") == "DEFENSE_LOCK":
            self.portfolio.log_thought(
                "Memory",
                "WARN",
                f"[Trí Nhớ Phân Lập Coin] {coin_ev.get('advice')}"
            )
        elif coin_ev.get("status") == "HEALTHY":
            self.portfolio.log_thought(
                "Memory",
                "SUCCESS",
                f"[Trí Nhớ Phân Lập Coin] {coin_ev.get('advice')}"
            )

        if strat_ev.get("status") == "PROVEN_EDGE":
            self.portfolio.log_thought(
                "Memory",
                "SUCCESS",
                f"[Trí Nhớ Chiến Thuật] {strat_ev.get('advice')}"
            )
        elif strat_ev.get("status") == "UNDERPERFORMING":
            self.portfolio.log_thought(
                "Memory",
                "WARN",
                f"[Trí Nhớ Chiến Thuật] {strat_ev.get('advice')}"
            )

        if meta_eval.get("status") == "WIN_AMPLIFIER":
            self.portfolio.log_thought(
                "Memory",
                "SUCCESS",
                f"[Tự Học Mẫu Hình Vàng] {meta_eval['advice']}"
            )
        elif meta_eval.get("status") == "ALPHA_DECAY":
            self.portfolio.log_thought(
                "Memory",
                "WARN",
                f"[Cảnh Báo Suy Giảm Hiệu Quả - Alpha Decay] {meta_eval['advice']}"
            )
        elif meta_eval.get("status") == "LOSS_TRAP":
            self.portfolio.log_thought(
                "Memory",
                "WARN",
                f"[Nhận Diện Bẫy Thua Quá Khứ] {meta_eval['advice']}"
            )

        if recent_lessons:
            latest_l = recent_lessons[0]
            self.portfolio.log_thought(
                "Memory",
                "INFO",
                f"[Trí Nhớ AI ({selected_coin})] Bài học gần nhất: {latest_l['lesson']} -> Ghi nhớ: {latest_l['takeaway']}"
            )
        if track_record.get("loss_streak", 0) >= 2:
            self.portfolio.log_thought(
                "Memory",
                "WARN",
                f"[Trí Nhớ AI] {track_record['advice']}"
            )

        # 4. KELLY RISK AGENT
        summary = self.portfolio.get_summary()
        total_equity = summary["total_equity"]
        cash = summary["cash_balance"]

        # 4.0 KIỂM TRA CẦU CHÌ AN TOÀN NGÀY (Daily Circuit Breaker)
        daily_metrics = summary.get("daily_metrics", {})
        if daily_metrics.get("circuit_breaker_active", False):
            cb_msg = (
                f"🚨 [CẦU CHÌ AN TOÀN NGÀY ĐANG NGẮT] Thua lỗ hôm nay chạm giới hạn -{daily_metrics.get('max_drawdown_pct', 8.0)}% "
                f"(-${abs(daily_metrics.get('daily_pnl', 0.0)):,.2f} USD). Dừng mở vị thế mới đến 07:00 sáng mai để bảo toàn vốn tích lũy!"
            )
            self.portfolio.log_thought("Risk Guard", "WARN", cb_msg)
            return {
                "status": "hold",
                "coin": selected_coin,
                "side": chosen_side,
                "edge": edge,
                "reason": cb_msg
            }

        # 4.0.1 LUẬT KHÓA LỢI NHUẬN BẢO VỆ THÀNH QUẢ NGÀY (Daily Target Profit Lock)
        if daily_metrics.get("profit_lock_active", False):
            lock_msg = (
                f"🔒 [LUẬT KHÓA LÃI BẢO VỆ VỐN] Mục tiêu lợi nhuận ngày (+{daily_metrics.get('target_profit_pct', 20.0)}%) "
                f"đã hoàn thành xuất sắc! Hệ thống tự động đóng băng mở lệnh mới đến 07:00 sáng mai để bảo toàn 100% tiền lãi vào két!"
            )
            self.portfolio.log_thought("Risk Guard", "SUCCESS", lock_msg)
            return {
                "status": "hold",
                "coin": selected_coin,
                "side": chosen_side,
                "edge": edge,
                "reason": lock_msg
            }

        strat_min_edge = active_strat.get("min_edge", MIN_EDGE_THRESHOLD)

        # 4.1 KIỂM TRA BỘ LỌC PHIÊN GIAO DỊCH THẾ GIỚI (Session Strategy Gate)
        has_super_confluence = bool(mtf_info.get("is_confluent"))
        has_smc_sweep = bool(smc_data.get("pattern") in ["BULLISH_SWEEP", "BEARISH_SWEEP"] or pat_data.get("pattern") in ["CONFIRMED_PINBAR", "TWEEZER_BOTTOM", "TWEEZER_TOP"])
        strat_key = signal_dna.get("strategy", "MOMENTUM_BREAKOUT")
        session_allowed, session_reason = evaluate_session_gate(
            session_info,
            strat_key,
            edge,
            has_super_confluence=has_super_confluence,
            has_smc_sweep=has_smc_sweep
        )

        if not session_allowed:
            self.portfolio.log_thought("Kelly Risk", "WARN", session_reason)
            return {
                "status": "hold",
                "coin": selected_coin,
                "side": chosen_side,
                "edge": edge,
                "reason": session_reason
            }

        # 4.1.1 MACRO 1H ADVISORY (Tham khảo xu hướng 1H, không cấm cản lệnh Scalping 1m/5m)
        macro_1h = mtf_info.get("macro_1h_trend", "SIDEWAYS")
        if (chosen_side == "SHORT" and macro_1h in ["BULLISH", "BULLISH_RECOVERY"]) or \
           (chosen_side == "LONG" and macro_1h in ["BEARISH", "BEARISH_PULLBACK"]):
            # Cảnh báo tham khảo, giảm nhẹ edge nhưng KHÔNG cấm cản để bot linh hoạt ăn sóng hồi
            edge = round(edge * 0.90, 4)

        effective_min_edge = strat_min_edge + session_info.get("min_edge_bonus", 0.0)

        if chosen_side == "HOLD" or edge < effective_min_edge:
            if meta_eval.get("status") == "LOSS_TRAP":
                reason = f"Bộ Não AI đã gắn cờ BẪY THUA QUÁ KHỨ ({meta_eval.get('badge')}). Tự động VETO lệnh để bảo toàn vốn!"
            else:
                reason = (
                    f"[{session_info['badge']}] Thị trường {selected_coin} đi ngang hoặc lợi thế ({edge:+.1%}) chưa vượt ngưỡng an toàn "
                    f"({effective_min_edge:.1%}) của phiên {session_info['name']} (Chiến lược: {active_strat['badge']}). Giữ nguyên tiền mặt."
                )
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                reason
            )
            return {
                "status": "hold",
                "coin": selected_coin,
                "side": chosen_side,
                "edge": edge,
                "reason": reason
            }

        # Kelly: f* = (b*p - q)/b, for 1:1 payout assumption b=1 => f* = 2p - 1
        kelly_fractional = max(0.0, (2 * chosen_prob - 1) * KELLY_FRACTION)
        final_stake_fraction = min(MAX_PORTFOLIO_PER_TRADE, kelly_fractional)

        stake_range = active_strat.get("stake_percent_range", [0.15, 0.20])
        if active_strat.get("id") == "MICRO_SNIPER_SMC" or total_equity <= 30.0:
            # High-Aggression Micro account ($10 budget): allocate 35% - 50% ($3.50 - $5.00)
            if final_stake_fraction < stake_range[0]:
                final_stake_fraction = 0.40 # Target 40% margin ($4.00 on a $10 budget)
            elif final_stake_fraction > stake_range[1]:
                final_stake_fraction = stake_range[1]
        elif final_stake_fraction < stake_range[0]:
            final_stake_fraction = stake_range[0]

        stake_dollars = round(total_equity * final_stake_fraction, 2)
        if (active_strat.get("id") == "MICRO_SNIPER_SMC" or total_equity <= 30.0) and stake_dollars < 3.50 and cash >= 3.50:
            stake_dollars = 3.50

        if max_stake and max_stake > 0:
            stake_dollars = round(min(max_stake, cash), 2)
        else:
            stake_dollars = min(stake_dollars, cash)

        # Ngăn 1 Trí Nhớ AI: Quy tắc phòng vệ phân lập riêng từng coin (Isolated Risk Shield)
        is_coin_defense = meta_eval.get("coin_defense_lock", False) or (track_record.get("loss_streak", 0) >= 2)
        if is_coin_defense:
            stake_dollars = round(stake_dollars * 0.50, 2)
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"[Phòng Vệ Phân Lập Cho {selected_coin}] Hạ 50% vốn cược (${stake_dollars:.2f}) và khống chế đòn bẩy tối đa 10x do {selected_coin} đang có chuỗi thua {track_record.get('loss_streak', 0)} lệnh. Cơ chế phân lập 3 ngăn bảo đảm KHÔNG ảnh hưởng bất kỳ coin nào khác!"
            )

        # Ngăn 3 Trí Nhớ AI: Phòng vệ suy giảm hiệu quả toàn cầu (Alpha Decay)
        if meta_eval.get("status") == "ALPHA_DECAY":
            stake_dollars = round(stake_dollars * 0.75, 2)
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"[Phòng Vệ Alpha Decay] Hạ thêm 25% vốn (${stake_dollars:.2f}) & khống chế đòn bẩy tối đa 10x do mẫu hình đang dính chuỗi suy giảm hiệu quả."
            )

        # 4.2 ĐIỀU CHỈNH QUY MÔ VỐN CƯỢC THEO PHIÊN GIAO DỊCH THẾ GIỚI
        session_stake_mult = session_info.get("stake_multiplier", 1.0)
        if session_stake_mult < 1.0:
            orig_stake = stake_dollars
            # Sàn tối thiểu $2.50 để đảm bảo khi thắng có tiền thật, không bị cược nhí $1.29
            min_stake_floor = min(2.50, cash)
            stake_dollars = max(min_stake_floor, round(stake_dollars * session_stake_mult, 2))
            self.portfolio.log_thought(
                "Kelly Risk",
                "INFO",
                f"[{session_info['badge']}] Điều chỉnh vốn cược từ ${orig_stake:.2f} xuống ${stake_dollars:.2f} (x{session_stake_mult}) theo phiên {session_info['name']} (Sàn tối thiểu: ${min_stake_floor:.2f})."
            )

        # 4.2.1 BẢO VỆ THÀNH QUẢ KHI ĐÃ ĐẠT MỤC TIÊU NGÀY (+20% DAILY TARGET)
        if daily_metrics.get("target_reached", False):
            orig_stk = stake_dollars
            stake_dollars = max(1.0, round(stake_dollars * 0.50, 2))
            self.portfolio.log_thought(
                "Risk Guard",
                "INFO",
                f"🛡️ [Bảo Vệ Thành Quả Ngày] Hôm nay đã đạt mục tiêu (+{daily_metrics.get('daily_roi_percent', 0.0):.1f}%): Giảm 50% vốn cược (${orig_stk:.2f} -> ${stake_dollars:.2f}) để giữ tiền."
            )

        if stake_dollars < 0.5 or cash < 0.5:
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"Vốn tính toán ${stake_dollars:.2f} không đủ hoặc số dư tiền mặt thấp (dưới $0.50). Đứng ngoài."
            )
            return {"status": "insufficient_capital"}

        # Adaptive Margin Leverage based on active strategy profile & statistical edge
        strat_lev = active_strat.get("leverage", DEFAULT_LEVERAGE)
        strat_max_lev = active_strat.get("max_leverage", MAX_LEVERAGE)
        target_lev = max_leverage if (max_leverage and max_leverage > 0) else strat_lev
        target_lev = min(target_lev, strat_max_lev)

        # Giới hạn đòn bẩy chỉ cho meme coin nhỏ PEPE/SHIB/FLOKI, trong khi DOGE/SOL/SUI được đòn bẩy tối đa 20x - 25x
        cat_key, _ = self.memory_manager.classify_coin_category(selected_coin)
        if cat_key == "MEME_HIGH_VOLATILITY" and selected_coin not in ["DOGE"]:
            target_lev = min(target_lev, 5)

        # Tăng chỉ số liều đòn bẩy cho các coin thanh khoản cao (SOL, DOGE, SUI)
        if edge >= 0.06:
            leverage = target_lev # 20x - 25x kịch trần
        elif edge >= 0.045:
            leverage = max(12, int(target_lev * 0.85)) # 17x - 20x
        else:
            leverage = max(8, int(target_lev * 0.70)) # 14x - 17x

        # Khống chế đòn bẩy nếu đồng coin này đang bị DEFENSE_LOCK hoặc mẫu hình bị Alpha Decay
        if is_coin_defense or meta_eval.get("status") == "ALPHA_DECAY":
            leverage = min(leverage, 10)

        # 4.3 KHỐNG CHẾ ĐÒN BẨY TỐI ĐA THEO PHIÊN GIAO DỊCH THẾ GIỚI
        session_lev_cap = session_info.get("leverage_cap", strat_max_lev)
        if leverage > session_lev_cap:
            self.portfolio.log_thought(
                "Kelly Risk",
                "INFO",
                f"[{session_info['badge']}] Siết đòn bẩy từ {leverage}x xuống {session_lev_cap}x để bảo vệ an toàn trước các pha quét râu."
            )
            leverage = session_lev_cap

        # Khống chế đòn bẩy tối đa 10x khi đã đạt mục tiêu lợi nhuận ngày
        if daily_metrics.get("target_reached", False):
            if leverage > 10:
                self.portfolio.log_thought(
                    "Risk Guard",
                    "INFO",
                    f"🛡️ [Bảo Vệ Thành Quả Ngày] Khống chế đòn bẩy tối đa 10x (từ {leverage}x xuống 10x) để bảo toàn thành quả ngày."
                )
                leverage = 10

        leverage = max(1, min(strat_max_lev, leverage))

        # Stop-Loss & Take-Profit targets calibrated to active strategy profile
        strat_sl = active_strat.get("sl_percent", DEFAULT_SL_PERCENT)
        strat_tp = active_strat.get("tp_percent", DEFAULT_TP_PERCENT)
        sl_pct = custom_sl_pct if (custom_sl_pct and custom_sl_pct > 0) else strat_sl
        tp_pct = custom_tp_pct if (custom_tp_pct and custom_tp_pct > 0) else strat_tp

        curr_price = candles[-1]["close"] if (candles and len(candles) > 0 and candles[-1].get("close")) else ticker["price"]
        curr_price_formatted = self.crypto_service.format_price(curr_price)
        prec = normalize_price_precision(curr_price)

        if chosen_side == "SHORT":
            liq_price = round(curr_price * (1.0 + (1.0 / leverage) * 0.95), prec)
            if liq_price <= curr_price:
                liq_price = curr_price * (1.0 + (1.0 / leverage) * 0.95)
            stop_loss = round(curr_price * (1.0 + sl_pct), prec)
            if stop_loss >= liq_price:
                stop_loss = round(curr_price * (1.0 + (1.0 / leverage) * 0.75), prec)
            if stop_loss <= curr_price:
                stop_loss = curr_price * (1.0 + sl_pct)
            take_profit = round(curr_price * (1.0 - tp_pct), prec)
            if take_profit >= curr_price:
                take_profit = curr_price * (1.0 - tp_pct)
        else:
            liq_price = round(curr_price * (1.0 - (1.0 / leverage) * 0.95), prec)
            if liq_price >= curr_price:
                liq_price = curr_price * (1.0 - (1.0 / leverage) * 0.95)
            stop_loss = round(curr_price * (1.0 - sl_pct), prec)
            if stop_loss <= liq_price:
                stop_loss = round(curr_price * (1.0 - (1.0 / leverage) * 0.75), prec)
            if stop_loss >= curr_price:
                stop_loss = curr_price * (1.0 - sl_pct)
            take_profit = round(curr_price * (1.0 + tp_pct), prec)
            if take_profit <= curr_price:
                take_profit = curr_price * (1.0 + tp_pct)

        # Tối ưu hóa điểm Cắt Lỗ & Chốt Lời theo Râu Nến Pinbar Price Action & SMC Quét Thanh Khoản trên khung 15M
        effective_ideal_sl = quant_res.get("ideal_sl") or pat_data.get("ideal_sl") or smc_data.get("ideal_sl")
        rr_mult = 2.0 # 15M Day-Scalp: Tỷ lệ R:R 1:2.0 chuẩn mực (Ăn sóng 2.5% - 4.0%, SL 1.2% - 1.8%)
        if effective_ideal_sl and not custom_sl_pct:
            source_tag = pat_data.get("pattern", "SMC") if pat_data.get("detected") else "SMC"
            if chosen_side == "LONG" and effective_ideal_sl < curr_price and effective_ideal_sl > liq_price:
                dist_pct = (curr_price - effective_ideal_sl) / curr_price
                if 0.0080 <= dist_pct <= 0.035: # Khoảng SL 0.8% - 3.5% cho nến 15m
                    stop_loss = effective_ideal_sl
                    sl_pct = dist_pct
                    tp_pct = max(0.025, min(0.050, sl_pct * rr_mult))
                    take_profit = round(curr_price * (1.0 + tp_pct), prec)
                    self.portfolio.log_thought(
                        "Kelly Risk",
                        "SUCCESS",
                        f"[15M Day-Scalp SMC] Cắt Lỗ theo swing đáy nến 15m {source_tag}: SL=${stop_loss:,.4f} (-{sl_pct*100:.2f}%) | TP=${take_profit:,.4f} (+{tp_pct*100:.2f}%) | R:R 1:{rr_mult:.1f}"
                    )
            elif chosen_side == "SHORT" and effective_ideal_sl > curr_price and effective_ideal_sl < liq_price:
                dist_pct = (effective_ideal_sl - curr_price) / curr_price
                if 0.0080 <= dist_pct <= 0.035:
                    stop_loss = effective_ideal_sl
                    sl_pct = dist_pct
                    tp_pct = max(0.025, min(0.050, sl_pct * rr_mult))
                    take_profit = round(curr_price * (1.0 - tp_pct), prec)
                    self.portfolio.log_thought(
                        "Kelly Risk",
                        "SUCCESS",
                        f"[15M Day-Scalp SMC] Cắt Lỗ theo swing đỉnh nến 15m {source_tag}: SL=${stop_loss:,.4f} (-{sl_pct*100:.2f}%) | TP=${take_profit:,.4f} (+{tp_pct*100:.2f}%) | R:R 1:{rr_mult:.1f}"
                    )
        elif not custom_tp_pct:
            # 15M Day-Scalp tiêu chuẩn: SL 1.5%, TP 3.0% (R:R 1:2.0)
            tp_pct = max(0.025, min(0.045, sl_pct * rr_mult))
            if chosen_side == "SHORT":
                take_profit = round(curr_price * (1.0 - tp_pct), prec)
            else:
                take_profit = round(curr_price * (1.0 + tp_pct), prec)

        self.portfolio.log_thought(
            "Kelly Risk",
            "INFO",
            f"Quản trị Rủi ro ({selected_coin}): Đòn bẩy {leverage}x | Ký quỹ: ${stake_dollars:.2f} | Cắt lỗ (SL): ${stop_loss:,.4f} (-{sl_pct*100:.1f}%) | Chốt lời (TP): ${take_profit:,.4f} (+{tp_pct*100:.1f}%) | Giá thanh lý: ${liq_price:,.4f}"
        )

        pat_desc = f" | Nến: {pat_data['pattern']}" if pat_data.get('detected') else ""
        smc_desc = f" | SMC: {smc_data['pattern']}" if smc_data.get('detected') else ""
        session_tag = f"[{session_info['badge']}]"
        reasoning = (
            f"[{active_strat['badge']} | {session_info['badge']}] Tín hiệu Alpha: {chosen_side} {leverage}x trên {selected_coin} (Lợi thế: {edge:+.1%}). "
            f"Ký quỹ: ${stake_dollars:.2f} (Vị thế: ${stake_dollars*leverage:.2f}). "
            f"SL: ${stop_loss:,.4f} (-{sl_pct*100:.1f}%) | TP: ${take_profit:,.4f} (+{tp_pct*100:.1f}%)"
            f"{pat_desc}{smc_desc}"
        )

        analysis_summary = {
            "strategy": f"{active_strat['badge']} ({active_strat['name']})",
            "session": f"{session_info['badge']} ({session_info['name']} - {session_info['time_range']})",
            "spotter": f"Khối lượng 24h: {ticker.get('liquidity_formatted', 'Tốt')} | Sổ lệnh L2: {ratio:.2f}x ({depth_sentiment})",
            "researcher": f"Tâm lý tin tức: {'Tích cực' if news_score > 0 else ('Tiêu cực' if news_score < 0 else 'Trung tính')} ({len(articles)} tin)",
            "pricer": f"{trend_desc} | RSI: {quant_res.get('rsi', 50)} | VSA: {quant_res.get('vsa', {}).get('pattern', 'NORMAL')} | Xác suất {chosen_side}: {int(chosen_prob*100)}% (Lợi thế: {edge:+.1%})",
            "debate": f"Bò: {debate['bull_case'][:70]}... | Gấu: {debate['bear_case'][:70]}... -> Phán quyết: {debate['verdict_text']}",
            "kelly": f"Ký quỹ đề xuất ${stake_dollars:.2f} (Đòn bẩy {leverage}x - Chế độ: {session_info['risk_mode']})"
        }
        if pat_data.get("detected"):
            analysis_summary["candlestick"] = f"{pat_data['pattern']}: {pat_data['description']}"
        if mtf_info.get("is_confluent"):
            analysis_summary["multi_timeframe"] = mtf_info["description"]
        if smc_data.get("detected"):
            analysis_summary["smc"] = smc_data.get("description", "")
        if recent_lessons:
            analysis_summary["memory"] = f"Bài học {selected_coin}: {recent_lessons[0].get('takeaway', '')}"
        analysis_summary["dna"] = f"{signal_dna['display_label']} | {meta_eval.get('badge', '')}"
        signal_dna["session"] = {
            "id": session_info["id"],
            "name": session_info["name"],
            "badge": session_info["badge"],
            "risk_mode": session_info["risk_mode"]
        }

        # If proposal mode is requested (or default), put into the approval queue
        if as_proposal and self.proposal_manager:
            proposal = self.proposal_manager.add_proposal(
                coin=selected_coin,
                side=chosen_side,
                price=curr_price,
                leverage=leverage,
                stake_amount=stake_dollars,
                stop_loss=stop_loss,
                take_profit=take_profit,
                liquidation_price=liq_price,
                timeframe=timeframe,
                edge=edge,
                reasoning=reasoning,
                analysis_summary=analysis_summary,
                signal_dna=signal_dna
            )
            self.portfolio.log_thought(
                "Kelly Risk",
                "SUCCESS",
                f"ĐÃ TẠO ĐỀ XUẤT CHỜ DUYỆT: {chosen_side} {leverage}x ${stake_dollars:.2f} của {selected_coin}/USDT @ {curr_price_formatted} (SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f})"
            )
            return {
                "status": "proposed",
                "proposal": proposal,
                "coin": selected_coin,
                "side": chosen_side,
                "edge": edge
            }

        success = self.portfolio.execute_trade(
            market_id=f"crypto_{ticker['symbol']}",
            question=f"{selected_coin}/USDT ({chosen_side})",
            outcome=chosen_side,
            price=curr_price,
            stake_amount=stake_dollars,
            reasoning=reasoning,
            asset_type="crypto",
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            symbol=selected_coin,
            signal_dna=signal_dna
        )

        if success:
            self.portfolio.log_thought(
                "Executor",
                "TRADE",
                f"[{session_info['badge']}] KHỚP LỆNH MARGIN: {chosen_side} {leverage}x ${stake_dollars:.2f} của {selected_coin}/USDT @ {curr_price_formatted} (Vị thế: ${stake_dollars*leverage:.2f} | SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f})"
            )

        return {
            "status": "traded",
            "coin": selected_coin,
            "side": chosen_side,
            "price": curr_price,
            "stake": stake_dollars,
            "leverage": leverage,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "liquidation_price": liq_price,
            "edge": edge
        }

    def run_cycle(
        self,
        markets: Optional[List[Dict[str, Any]]] = None,
        target_coin: Optional[str] = None,
        timeframe: str = "1m",
        max_leverage: Optional[int] = None,
        max_stake: Optional[float] = None,
        custom_sl_pct: Optional[float] = None,
        custom_tp_pct: Optional[float] = None,
        as_proposal: bool = False
    ) -> Dict[str, Any]:
        """
        Executes 1 cycle. If target_coin or active crypto watchlist is available, runs crypto cycle.
        Otherwise falls back to prediction markets.
        """
        if target_coin or (self.crypto_service and self.crypto_service.watchlist):
            return self.run_crypto_cycle(
                target_coin=target_coin,
                timeframe=timeframe,
                max_leverage=max_leverage,
                max_stake=max_stake,
                custom_sl_pct=custom_sl_pct,
                custom_tp_pct=custom_tp_pct,
                as_proposal=as_proposal
            )

        # Fallback to binary prediction markets
        if not markets:
            self.portfolio.log_thought("Spotter", "WARN", "No active prediction markets available to inspect.")
            return {"status": "no_markets"}

        viable_markets = [
            m for m in markets
            if 0.12 <= m.get("probability_yes", 0.5) <= 0.88 and m.get("volume", 0) > 50
        ]
        target = random.choice(viable_markets or markets)
        m_id = target["id"]
        question = target["question"]
        p_market_yes = target["probability_yes"]
        p_market_no = target["probability_no"]

        self.portfolio.log_thought(
            "Spotter",
            "INFO",
            f"Locked target: '{question}' (Odds: YES {int(p_market_yes*100)}% | NO {int(p_market_no*100)}% | Vol: ${target.get('volume', 0):,.0f})"
        )

        articles = search_google_news(question, max_results=3)
        p_fair_yes = min(0.92, max(0.08, round(p_market_yes + random.gauss(0, 0.03), 3)))
        p_fair_no = round(1.0 - p_fair_yes, 3)
        edge_yes = round(p_fair_yes - p_market_yes, 3)
        edge_no = round(p_fair_no - p_market_no, 3)

        side = "YES" if edge_yes >= edge_no else "NO"
        edge = max(edge_yes, edge_no)
        price = p_market_yes if side == "YES" else p_market_no

        if edge < MIN_EDGE_THRESHOLD:
            self.portfolio.log_thought("Kelly Risk", "WARN", f"Edge ({edge:+.1%}) below threshold. Holding.")
            return {"status": "hold"}

        summary = self.portfolio.get_summary()
        stake = min(summary["cash_balance"], round(summary["total_equity"] * 0.15, 2))
        if stake < 0.5:
            return {"status": "insufficient_capital"}

        self.portfolio.execute_trade(
            market_id=m_id,
            question=question,
            outcome=side,
            price=price,
            stake_amount=stake,
            reasoning=f"Statistical Edge: {edge:+.1%} on {side}.",
            asset_type="prediction"
        )
        return {"status": "traded", "market": target, "side": side, "stake": stake}
