import math
import random
from typing import Dict, Any, List, Optional
from .news_fetcher import search_google_news
from .portfolio import PortfolioManager
from .quant_indicators import analyze_quant_structure
from ..config import (
    KELLY_FRACTION, 
    MAX_PORTFOLIO_PER_TRADE, 
    MIN_EDGE_THRESHOLD,
    DEFAULT_LEVERAGE,
    DEFAULT_SL_PERCENT,
    DEFAULT_TP_PERCENT
)

class SwarmEngine:
    def __init__(self, portfolio: PortfolioManager, crypto_service=None, proposal_manager=None):
        self.portfolio = portfolio
        self.crypto_service = crypto_service
        self.proposal_manager = proposal_manager

    def run_crypto_cycle(
        self,
        target_coin: Optional[str] = None,
        timeframe: str = "1h",
        max_leverage: Optional[int] = None,
        max_stake: Optional[float] = None,
        custom_sl_pct: Optional[float] = None,
        custom_tp_pct: Optional[float] = None,
        as_proposal: bool = True
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

        # 1. SPOTTER AGENT
        active_coins = [c for c in watchlist if self.crypto_service.active_status.get(c, True)]
        if not active_coins:
            active_coins = watchlist

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

        if target_coin and target_coin.upper() in [c.upper() for c in watchlist]:
            selected_coin = target_coin.upper()
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
                    f"Từ chối quét {selected_coin}: Đồng coin này hiện đã có vị thế mở ({side_info}). Tuân thủ nguyên tắc Quản trị rủi ro Một Vị Thế (Single Position Policy) để chống dồn rủi ro."
                )
                return {
                    "status": "position_already_open",
                    "coin": selected_coin,
                    "existing_position": existing_pos
                }
            if selected_coin in pending_symbols:
                self.portfolio.log_thought(
                    "Spotter",
                    "WARN",
                    f"Đồng {selected_coin} hiện đã có một đề xuất giao dịch nằm trong danh sách chờ duyệt. Vui lòng phê duyệt hoặc từ chối đề xuất cũ trước khi quét mới."
                )
                return {
                    "status": "pending_proposal_exists",
                    "coin": selected_coin
                }
        else:
            # Auto-scan mode: Prioritize coins that DO NOT have an open position or pending proposal
            available_coins = [c for c in active_coins if c.upper() not in occupied_symbols]
            if not available_coins:
                self.portfolio.log_thought(
                    "Spotter",
                    "INFO",
                    f"Tất cả {len(active_coins)} đồng coin trong danh mục đều đã có vị thế mở ({len(open_symbols)}) hoặc đề xuất chờ duyệt ({len(pending_symbols)}). Tạm dừng mở mới để bảo toàn vốn và quản trị lệnh hiện tại."
                )
                return {
                    "status": "all_coins_occupied",
                    "occupied_symbols": list(occupied_symbols)
                }
            selected_coin = random.choice(available_coins)

        ticker = self.crypto_service.fetch_coin_ticker(selected_coin)
        if not ticker:
            self.portfolio.log_thought("Spotter", "WARN", f"Could not fetch Binance live ticker for {selected_coin}.")
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

        quant_res = analyze_quant_structure(
            candles=candles,
            orderbook_ratio=ratio,
            news_sentiment=news_score
        )

        chosen_side = quant_res["chosen_side"]
        chosen_prob = quant_res["chosen_prob"]
        edge = quant_res["edge"]
        trend_desc = quant_res.get("trend_desc", "Trung tính")
        quant_summary = quant_res.get("summary", "")

        self.portfolio.log_thought(
            "The Pricer",
            "INFO",
            f"Định giá Định Lượng ({selected_coin}): Tín hiệu={chosen_side} (P_fair={int(chosen_prob*100)}% | Lợi thế={edge:+.1%}) | {quant_summary}"
        )

        # 4. KELLY RISK AGENT
        summary = self.portfolio.get_summary()
        total_equity = summary["total_equity"]
        cash = summary["cash_balance"]

        if chosen_side == "HOLD" or edge < MIN_EDGE_THRESHOLD:
            reason = (
                f"Thị trường {selected_coin} đi ngang kẹp EMA hoặc lợi thế ({edge:+.1%}) chưa vượt ngưỡng an toàn ({MIN_EDGE_THRESHOLD:.1%}). "
                f"Giữ nguyên 100% tiền mặt để bảo toàn vốn."
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

        if final_stake_fraction < 0.015:
            final_stake_fraction = 0.02 # Minimum 2% position

        stake_dollars = round(total_equity * final_stake_fraction, 2)
        if max_stake and max_stake > 0:
            stake_dollars = round(min(max_stake, cash), 2)
        else:
            stake_dollars = min(stake_dollars, cash)

        if stake_dollars < 5.0 or cash < 5.0:
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"Vốn tính toán ${stake_dollars:.2f} không đủ hoặc số dư tiền mặt thấp. Đứng ngoài."
            )
            return {"status": "insufficient_capital"}

        # Adaptive Margin Leverage based on statistical edge
        if edge >= 0.08:
            leverage = 5
        elif edge >= 0.05:
            leverage = 3
        elif edge >= 0.04:
            leverage = 2
        else:
            leverage = DEFAULT_LEVERAGE

        if max_leverage and max_leverage > 0:
            leverage = min(leverage, max_leverage)

        # Stop-Loss & Take-Profit targets
        sl_pct = custom_sl_pct if (custom_sl_pct and custom_sl_pct > 0) else DEFAULT_SL_PERCENT
        tp_pct = custom_tp_pct if (custom_tp_pct and custom_tp_pct > 0) else DEFAULT_TP_PERCENT

        curr_price = ticker["price"]
        if chosen_side == "SHORT":
            stop_loss = round(curr_price * (1.0 + sl_pct), 6 if curr_price < 1 else 4)
            take_profit = round(curr_price * (1.0 - tp_pct), 6 if curr_price < 1 else 4)
            liq_price = round(curr_price * (1.0 + (1.0 / leverage) * 0.95), 6 if curr_price < 1 else 4)
        else:
            stop_loss = round(curr_price * (1.0 - sl_pct), 6 if curr_price < 1 else 4)
            take_profit = round(curr_price * (1.0 + tp_pct), 6 if curr_price < 1 else 4)
            liq_price = round(curr_price * (1.0 - (1.0 / leverage) * 0.95), 6 if curr_price < 1 else 4)

        self.portfolio.log_thought(
            "Kelly Risk",
            "INFO",
            f"Quản trị Rủi ro ({selected_coin}): Đòn bẩy {leverage}x | Ký quỹ: ${stake_dollars:.2f} | Cắt lỗ (SL): ${stop_loss:,.4f} (-{sl_pct*100:.1f}%) | Chốt lời (TP): ${take_profit:,.4f} (+{tp_pct*100:.1f}%) | Giá thanh lý: ${liq_price:,.4f}"
        )

        reasoning = (
            f"Tín hiệu Alpha: {chosen_side} {leverage}x trên {selected_coin} (Lợi thế: {edge:+.1%}). "
            f"Ký quỹ: ${stake_dollars:.2f} (Vị thế: ${stake_dollars*leverage:.2f}). "
            f"SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f}"
        )

        analysis_summary = {
            "spotter": f"Khối lượng 24h: {ticker.get('liquidity_formatted', 'Tốt')} | Sổ lệnh L2: {ratio:.2f}x ({depth_sentiment})",
            "researcher": f"Tâm lý tin tức: {'Tích cực' if news_score > 0 else ('Tiêu cực' if news_score < 0 else 'Trung tính')} ({len(articles)} tin)",
            "pricer": f"{trend_desc} | RSI: {quant_res.get('rsi', 50)} | VSA: {quant_res.get('vsa', {}).get('pattern', 'NORMAL')} | Xác suất {chosen_side}: {int(chosen_prob*100)}% (Lợi thế: {edge:+.1%})",
            "kelly": f"Ký quỹ đề xuất ${stake_dollars:.2f} (Đòn bẩy {leverage}x)"
        }

        # If proposal mode is requested (or default), put into the approval queue
        if as_proposal and self.proposal_manager:
            proposal = self.proposal_manager.add_proposal(
                coin=selected_coin,
                side=chosen_side,
                price=ticker["price"],
                leverage=leverage,
                stake_amount=stake_dollars,
                stop_loss=stop_loss,
                take_profit=take_profit,
                liquidation_price=liq_price,
                timeframe=timeframe,
                edge=edge,
                reasoning=reasoning,
                analysis_summary=analysis_summary
            )
            self.portfolio.log_thought(
                "Kelly Risk",
                "SUCCESS",
                f"ĐÃ TẠO ĐỀ XUẤT CHỜ DUYỆT: {chosen_side} {leverage}x ${stake_dollars:.2f} của {selected_coin}/USDT @ {ticker['price_formatted']} (SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f})"
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
            price=ticker["price"],
            stake_amount=stake_dollars,
            reasoning=reasoning,
            asset_type="crypto",
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
            symbol=selected_coin
        )

        if success:
            self.portfolio.log_thought(
                "Executor",
                "TRADE",
                f"KHỚP LỆNH MARGIN THÀNH CÔNG: {chosen_side} {leverage}x ${stake_dollars:.2f} của {selected_coin}/USDT @ {ticker['price_formatted']} (Vị thế: ${stake_dollars*leverage:.2f} | SL: ${stop_loss:,.4f} | TP: ${take_profit:,.4f})"
            )

        return {
            "status": "traded",
            "coin": selected_coin,
            "side": chosen_side,
            "price": ticker["price"],
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
        timeframe: str = "1h",
        max_leverage: Optional[int] = None,
        max_stake: Optional[float] = None,
        custom_sl_pct: Optional[float] = None,
        custom_tp_pct: Optional[float] = None,
        as_proposal: bool = True
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
        stake = min(summary["cash_balance"], round(summary["total_equity"] * 0.03, 2))
        if stake < 5.0:
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
