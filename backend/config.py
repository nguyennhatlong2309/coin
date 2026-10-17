import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

# Default Watchlist Coins
DEFAULT_WATCHLIST = ["BTC", "ETH", "SOL", "BNB", "DOGE", "SUI"]

# Trading Strategy & Margin Defaults
INITIAL_CAPITAL = 1000.00
KELLY_FRACTION = 0.25          # Quarter Kelly for defensive risk management
MAX_PORTFOLIO_PER_TRADE = 0.05  # Max 5% of total capital on a single bet
MIN_EDGE_THRESHOLD = 0.04       # Minimum 4% probability discrepancy to trigger trade
AUTO_SCAN_INTERVAL_SECONDS = 30 # Interval for automatic background scan

# Margin & Leverage Parameters
DEFAULT_LEVERAGE = 3           # Default 3x margin leverage
MAX_LEVERAGE = 10              # Maximum allowed leverage
DEFAULT_SL_PERCENT = 0.02      # 2.0% Stop-Loss from entry price
DEFAULT_TP_PERCENT = 0.04      # 4.0% Take-Profit from entry price (Risk:Reward = 1:2)
MAINTENANCE_MARGIN_BUFFER = 0.95 # Liquidation trigger when loss reaches 95% of margin

