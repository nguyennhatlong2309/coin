import math
import random
from typing import Dict, Any, List, Optional
from .news_fetcher import search_google_news
from .portfolio import PortfolioManager
from ..config import KELLY_FRACTION, MAX_PORTFOLIO_PER_TRADE, MIN_EDGE_THRESHOLD

class SwarmEngine:
    def __init__(self, portfolio: PortfolioManager, crypto_service=None):
        self.portfolio = portfolio
        self.crypto_service = crypto_service

    def run_crypto_cycle(self, target_coin: Optional[str] = None) -> Dict[str, Any]:
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

        if target_coin and target_coin.upper() in [c.upper() for c in watchlist]:
            selected_coin = target_coin.upper()
        else:
            selected_coin = random.choice(active_coins)

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
            f"Locked target: {selected_coin}/USDT | Price: {ticker['price_formatted']} | 24h Liq: {ticker['liquidity_formatted']} ({ticker['tier']}) | Order Book: {depth_sentiment} (Ratio {ratio})"
        )

        # 2. RESEARCHER AGENT
        articles = search_google_news(f"{selected_coin} crypto market", max_results=3)
        if articles:
            headlines_summary = " | ".join([f"[{a['source']}] {a['title'][:55]}..." for a in articles[:2]])
        else:
            headlines_summary = f"No breaking news alerts for {selected_coin} in last 12h."

        self.portfolio.log_thought(
            "Researcher",
            "INFO",
            f"Ingested {len(articles)} fresh reports for {selected_coin}: {headlines_summary}"
        )

        # 3. THE PRICER AGENT
        pos_words = {"surge", "record", "rally", "gain", "breakout", "bull", "accumulate", "etf", "approve", "high", "growth", "pump", "support"}
        neg_words = {"drop", "crash", "plunge", "decline", "fall", "dump", "bear", "selloff", "reject", "sec", "ban", "risk", "liquidate"}

        news_score = 0
        for art in articles:
            text = (art.get("title", "") + " " + art.get("snippet", "")).lower()
            news_score += sum(1 for w in pos_words if w in text)
            news_score -= sum(1 for w in neg_words if w in text)

        # Orderbook signal: ratio > 1 means more bids (buying pressure)
        depth_score = (ratio - 1.0) * 0.12 # e.g. ratio 1.25 -> +0.03

        # Momentum signal: 24h change reversion / trend following
        change_24h = ticker["change_24h"]
        momentum_score = min(0.04, max(-0.04, change_24h * 0.005))

        # Total signal drift from 50% baseline
        total_drift = (news_score * 0.02) + depth_score + momentum_score + random.gauss(0, 0.015)
        
        # Fair probability of upward movement (LONG) vs downward (SHORT)
        p_long = min(0.85, max(0.15, round(0.50 + total_drift, 3)))
        p_short = round(1.0 - p_long, 3)

        if p_long >= 0.50:
            chosen_side = "LONG"
            chosen_prob = p_long
            edge = round(p_long - 0.50, 3)
        else:
            chosen_side = "SHORT"
            chosen_prob = p_short
            edge = round(p_short - 0.50, 3)

        self.portfolio.log_thought(
            "The Pricer",
            "INFO",
            f"Multivariate Valuation ({selected_coin}): Signal bias={chosen_side} (P_model={int(chosen_prob*100)}% | Edge={edge:+.1%}). OrderBook={ratio:.2f}x, 24hMom={change_24h:+.1f}%"
        )

        # 4. KELLY RISK AGENT
        summary = self.portfolio.get_summary()
        total_equity = summary["total_equity"]
        cash = summary["cash_balance"]

        if edge < MIN_EDGE_THRESHOLD:
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"Statistical Edge ({edge:+.1%}) below execution threshold ({MIN_EDGE_THRESHOLD:.1%}) on {selected_coin}. Holding capital."
            )
            return {
                "status": "hold",
                "coin": selected_coin,
                "side": chosen_side,
                "edge": edge
            }

        # Kelly: f* = (b*p - q)/b, for 1:1 payout assumption b=1 => f* = 2p - 1
        kelly_fractional = max(0.0, (2 * chosen_prob - 1) * KELLY_FRACTION)
        final_stake_fraction = min(MAX_PORTFOLIO_PER_TRADE, kelly_fractional)

        if final_stake_fraction < 0.015:
            final_stake_fraction = 0.02 # Minimum 2% position

        stake_dollars = round(total_equity * final_stake_fraction, 2)
        stake_dollars = min(stake_dollars, cash)

        if stake_dollars < 5.0 or cash < 5.0:
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"Computed stake ${stake_dollars:.2f} insufficient or cash reserves low. Holding."
            )
            return {"status": "insufficient_capital"}

        reasoning = (
            f"Alpha Signal: {chosen_side} on {selected_coin} (Edge: {edge:+.1%}). "
            f"Liquidity: {ticker['liquidity_formatted']}, Depth Ratio: {ratio:.2f}x. "
            f"Quarter-Kelly allocation: ${stake_dollars:.2f} ({stake_dollars/total_equity:.1%} equity)."
        )

        success = self.portfolio.execute_trade(
            market_id=f"crypto_{ticker['symbol']}",
            question=f"{selected_coin}/USDT ({chosen_side})",
            outcome=chosen_side,
            price=ticker["price"],
            stake_amount=stake_dollars,
            reasoning=reasoning,
            asset_type="crypto"
        )

        if success:
            self.portfolio.log_thought(
                "Executor",
                "TRADE",
                f"EXECUTED MOCK FILL: {chosen_side} ${stake_dollars:.2f} of {selected_coin}/USDT @ {ticker['price_formatted']} (24h Vol: {ticker['liquidity_formatted']})"
            )

        return {
            "status": "traded",
            "coin": selected_coin,
            "side": chosen_side,
            "price": ticker["price"],
            "stake": stake_dollars,
            "edge": edge
        }

    def run_cycle(self, markets: Optional[List[Dict[str, Any]]] = None, target_coin: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes 1 cycle. If target_coin or active crypto watchlist is available, runs crypto cycle.
        Otherwise falls back to prediction markets.
        """
        if target_coin or (self.crypto_service and self.crypto_service.watchlist):
            return self.run_crypto_cycle(target_coin)

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
