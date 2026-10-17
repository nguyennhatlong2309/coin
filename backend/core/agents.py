import math
import random
from typing import Dict, Any, List
from .news_fetcher import search_google_news
from .portfolio import PortfolioManager
from ..config import KELLY_FRACTION, MAX_PORTFOLIO_PER_TRADE, MIN_EDGE_THRESHOLD

class SwarmEngine:
    def __init__(self, portfolio: PortfolioManager):
        self.portfolio = portfolio

    def run_cycle(self, markets: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes 1 full cycle of the 4-Agent Swarm:
        1. Spotter Agent: Filters and selects top tradeable market
        2. Researcher Agent: Queries live Google News RSS
        3. The Pricer Agent: Calculates Gaussian probability distribution and statistical edge
        4. Kelly Risk Agent: Computes optimal bet size and triggers mock execution
        """
        if not markets:
            self.portfolio.log_thought("Spotter", "WARN", "No active prediction markets available to inspect.")
            return {"status": "no_markets"}

        # 1. SPOTTER AGENT
        # Filter markets that are active, liquid, and not trivial extremes (e.g., between 0.12 and 0.88)
        viable_markets = [
            m for m in markets
            if 0.12 <= m["probability_yes"] <= 0.88 and m["volume"] > 50
        ]
        if not viable_markets:
            viable_markets = markets

        # Pick a target market (prioritize high volume or rotation)
        target = random.choice(viable_markets)
        m_id = target["id"]
        question = target["question"]
        p_market_yes = target["probability_yes"]
        p_market_no = target["probability_no"]

        self.portfolio.log_thought(
            "Spotter",
            "INFO",
            f"Locked target: '{question}' (Market Odds: YES {int(p_market_yes*100)}% | NO {int(p_market_no*100)}% | Vol: ${target['volume']:,.0f})"
        )

        # 2. RESEARCHER AGENT
        articles = search_google_news(question, max_results=3)
        headlines_summary = " | ".join([f"[{a['source']}] {a['title'][:60]}..." for a in articles[:2]])
        self.portfolio.log_thought(
            "Researcher",
            "INFO",
            f"Ingested {len(articles)} fresh news reports: {headlines_summary}"
        )

        # 3. THE PRICER AGENT
        # Analyze news keywords to simulate evidence weighting (positive vs negative sentiment)
        pos_words = {"surge", "record", "approve", "gain", "win", "high", "cut", "support", "rally", "growth", "yes", "boost"}
        neg_words = {"delay", "reject", "drop", "decline", "fall", "lose", "ban", "risk", "halt", "fail", "no", "crash"}

        pos_score = 0
        neg_score = 0
        for art in articles:
            text = (art["title"] + " " + art["snippet"]).lower()
            pos_score += sum(1 for w in pos_words if w in text)
            neg_score += sum(1 for w in neg_words if w in text)

        # Gaussian drift model: Prior probability adjusted by incoming signal
        drift = (pos_score - neg_score) * 0.035
        # Add slight natural Bayesian noise
        drift += random.gauss(0, 0.02)
        
        # Clamp estimated true probability
        p_fair_yes = min(0.92, max(0.08, round(p_market_yes + drift, 3)))
        p_fair_no = round(1.0 - p_fair_yes, 3)

        edge_yes = round(p_fair_yes - p_market_yes, 3)
        edge_no = round(p_fair_no - p_market_no, 3)

        self.portfolio.log_thought(
            "The Pricer",
            "INFO",
            f"Gaussian Density Evaluation: Fair Value YES = {int(p_fair_yes*100)}% vs Market {int(p_market_yes*100)}% (Edge: {edge_yes:+.1%})"
        )

        # 4. KELLY RISK AGENT
        summary = self.portfolio.get_summary()
        total_equity = summary["total_equity"]
        cash = summary["cash_balance"]

        # Determine target side with highest edge
        chosen_side = None
        chosen_market_price = 0.0
        chosen_fair_prob = 0.0
        active_edge = 0.0

        if edge_yes >= MIN_EDGE_THRESHOLD:
            chosen_side = "YES"
            chosen_market_price = p_market_yes
            chosen_fair_prob = p_fair_yes
            active_edge = edge_yes
        elif edge_no >= MIN_EDGE_THRESHOLD:
            chosen_side = "NO"
            chosen_market_price = p_market_no
            chosen_fair_prob = p_fair_no
            active_edge = edge_no

        if not chosen_side:
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"Edge ({max(edge_yes, edge_no):+.1%}) below execution threshold ({MIN_EDGE_THRESHOLD:.1%}). No trade triggered."
            )
            return {
                "status": "hold",
                "market": target,
                "p_fair_yes": p_fair_yes,
                "edge": max(edge_yes, edge_no)
            }

        # Kelly Criterion: f* = (b*p - q) / b
        # where b is net odds: b = (1 - market_price) / market_price
        b = (1.0 - chosen_market_price) / chosen_market_price if chosen_market_price > 0 else 1.0
        p = chosen_fair_prob
        q = 1.0 - p
        kelly_full = (b * p - q) / b if b > 0 else 0.0

        # Fractional Kelly (Quarter Kelly) for risk aversion
        kelly_stake_fraction = max(0.0, kelly_full * KELLY_FRACTION)
        
        # Cap stake at MAX_PORTFOLIO_PER_TRADE (e.g. 5%)
        final_stake_fraction = min(MAX_PORTFOLIO_PER_TRADE, kelly_stake_fraction)
        
        if final_stake_fraction < 0.01:
            final_stake_fraction = 0.015 # Minimum allocation 1.5%

        stake_dollars = round(total_equity * final_stake_fraction, 2)
        stake_dollars = min(stake_dollars, cash)

        if stake_dollars < 5.0 or cash < 5.0:
            self.portfolio.log_thought(
                "Kelly Risk",
                "WARN",
                f"Calculated stake ${stake_dollars:.2f} insufficient or cash reserves low. Holding."
            )
            return {"status": "insufficient_capital"}

        reasoning = (
            f"Statistical Edge: {active_edge:+.1%} on {chosen_side}. "
            f"Evaluated P_fair={int(chosen_fair_prob*100)}% vs Market={int(chosen_market_price*100)}%. "
            f"Kelly Quarter allocation: ${stake_dollars:.2f} ({(stake_dollars/total_equity):.1%} of equity)."
        )

        # EXECUTE TRADE
        success = self.portfolio.execute_trade(
            market_id=m_id,
            question=question,
            outcome=chosen_side,
            price=chosen_market_price,
            stake_amount=stake_dollars,
            reasoning=reasoning
        )

        if success:
            self.portfolio.log_thought(
                "Executor",
                "TRADE",
                f"EXECUTED MOCK FILL: Buy ${stake_dollars:.2f} of [{chosen_side}] @ ${chosen_market_price:.2f} on '{question[:45]}...'"
            )

        return {
            "status": "traded",
            "market": target,
            "side": chosen_side,
            "price": chosen_market_price,
            "stake": stake_dollars,
            "edge": active_edge
        }
