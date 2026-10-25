import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)

DATA_DIR = BASE_DIR / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

# Binance Live & Testnet Execution Modes
TRADING_MODE = os.getenv("TRADING_MODE", "BINANCE_TESTNET").upper() # "PAPER", "BINANCE_TESTNET", "BINANCE_REAL"
BINANCE_TESTNET_API_KEY = os.getenv("BINANCE_TESTNET_API_KEY", "")
BINANCE_TESTNET_API_SECRET = os.getenv("BINANCE_TESTNET_API_SECRET", "")
BINANCE_REAL_API_KEY = os.getenv("BINANCE_REAL_API_KEY", "")
BINANCE_REAL_API_SECRET = os.getenv("BINANCE_REAL_API_SECRET", "")

def save_env_config(updates: dict):
    """
    Cập nhật và lưu các biến môi trường vào file .env một cách an toàn.
    """
    current_env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    current_env[k.strip()] = v.strip()

    current_env.update(updates)
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("# Quant Desk Trading Environment\n")
        for k, v in current_env.items():
            f.write(f"{k}={v}\n")
            os.environ[k] = str(v)

# Default Watchlist Coins (Premier High-Liquidity Sniper Portfolio: BTC, ETH, SOL)
DEFAULT_WATCHLIST = ["BTC", "ETH", "SOL"]

# Trading Strategy & Margin Defaults (15M Day-Scalp for $10 Account)
INITIAL_CAPITAL = 10.00
MIN_STAKE = 2.50                 # $2.50 margin per 15m scalp trade
KELLY_FRACTION = 0.50            # Half Kelly for controlled capital growth
MAX_PORTFOLIO_PER_TRADE = 0.50   # Up to 50% of capital ($2.50 - $4.00 on $10 account)
MIN_EDGE_THRESHOLD = 0.040       # 4.0% edge threshold on 15m candles
AUTO_SCAN_INTERVAL_SECONDS = 30  # 30s interval for 15m candle heartbeat

# Margin & Leverage Parameters (Calibrated to 15m Swings)
DEFAULT_LEVERAGE = 10           # 10x margin leverage (Chuẩn mực an toàn cho sóng 15m)
MAX_LEVERAGE = 15               # Maximum allowed leverage capped at 15x
DEFAULT_SL_PERCENT = 0.015      # 1.5% SL theo swing high/low nến 15m (không sợ râu quét)
DEFAULT_TP_PERCENT = 0.030      # 3.0% TP ăn trọn nhịp sóng nến 15m (R:R = 1:2.0, lãi +30% margin)
MAINTENANCE_MARGIN_BUFFER = 0.95 # Liquidation trigger when loss reaches 95% of margin
DEFAULT_TIMEFRAME = "15m"       # Default timeframe: 15-minute Day-Scalp

