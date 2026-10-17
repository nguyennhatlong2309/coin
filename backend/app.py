import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path
import os

from .core.portfolio import PortfolioManager
from .core.markets import fetch_prediction_markets
from .core.crypto_service import CryptoService
from .core.agents import SwarmEngine
from .config import BASE_DIR, AUTO_SCAN_INTERVAL_SECONDS

app = FastAPI(title="Quant Desk - Multi-Agent Mock Trading System")

portfolio = PortfolioManager()
crypto_service = CryptoService()
swarm = SwarmEngine(portfolio, crypto_service=crypto_service)

# Background auto-scan flag
is_auto_running = False

class CoinRequest(BaseModel):
    coin: str

class ScanRequest(BaseModel):
    coin: Optional[str] = None

@app.get("/api/portfolio")
def get_portfolio():
    # Sync current prices for prediction markets
    markets = fetch_prediction_markets(limit=25)
    markets_map = {m["id"]: m for m in markets}

    # Sync live prices for any open crypto positions
    crypto_prices: Dict[str, float] = {}
    for pos in portfolio.state["open_positions"].values():
        if pos.get("asset_type") == "crypto":
            sym = pos["market_id"].replace("crypto_", "")
            t = crypto_service.fetch_coin_ticker(sym)
            if t:
                crypto_prices[sym] = t["price"]

    portfolio.update_position_prices(markets_map, crypto_prices)
    return portfolio.get_summary()

@app.post("/api/portfolio/reset")
def reset_portfolio():
    return portfolio.reset()

@app.get("/api/markets")
def get_markets():
    return fetch_prediction_markets(limit=20)

# ----------------- CRYPTO WATCHLIST & LIQUIDITY ENDPOINTS -----------------

@app.get("/api/crypto/watchlist")
def get_crypto_watchlist():
    tickers = crypto_service.fetch_all_watchlist()
    return {
        "coins": crypto_service.watchlist,
        "tickers": tickers,
        "total_count": len(crypto_service.watchlist)
    }

@app.post("/api/crypto/watchlist/add")
def add_to_watchlist(req: CoinRequest):
    res = crypto_service.add_coin(req.coin)
    if res["success"]:
        portfolio.log_thought("Spotter", "SUCCESS", f"Added {res.get('coin')}/USDT to active trading watchlist.")
    return res

@app.post("/api/crypto/watchlist/remove")
def remove_from_watchlist(req: CoinRequest):
    res = crypto_service.remove_coin(req.coin)
    if res["success"]:
        portfolio.log_thought("Spotter", "INFO", f"Removed {req.coin.upper()} from watchlist.")
    return res

@app.post("/api/crypto/watchlist/toggle")
def toggle_watchlist_coin(req: CoinRequest):
    return crypto_service.toggle_coin(req.coin)

@app.get("/api/crypto/depth/{coin}")
def get_coin_depth(coin: str):
    return crypto_service.fetch_coin_depth(coin)

@app.get("/api/crypto/klines/{coin}")
def get_coin_klines(coin: str, interval: str = "1h", limit: int = 100):
    return crypto_service.fetch_klines(coin, interval=interval, limit=limit)

# ----------------- SWARM SCAN & AUTO-LOOP -----------------

@app.post("/api/scan")
def trigger_scan(req: Optional[ScanRequest] = None):
    target_coin = req.coin if req else None
    markets = fetch_prediction_markets(limit=20)
    result = swarm.run_cycle(markets=markets, target_coin=target_coin)
    return {
        "cycle_result": result,
        "portfolio": portfolio.get_summary()
    }

@app.get("/api/auto/status")
def get_auto_status():
    global is_auto_running
    return {"is_auto_running": is_auto_running, "interval_seconds": AUTO_SCAN_INTERVAL_SECONDS}

@app.post("/api/auto/toggle")
def toggle_auto(background_tasks: BackgroundTasks):
    global is_auto_running
    is_auto_running = not is_auto_running
    portfolio.log_thought(
        "System",
        "INFO",
        f"Autonomous Swarm Loop {'ENABLED (Scanning active coins & markets every 30s)' if is_auto_running else 'PAUSED (Manual Mode)'}."
    )
    return {"is_auto_running": is_auto_running}

# Background auto-scan worker
async def background_scanner():
    global is_auto_running
    while True:
        await asyncio.sleep(AUTO_SCAN_INTERVAL_SECONDS)
        if is_auto_running:
            try:
                markets = fetch_prediction_markets(limit=20)
                swarm.run_cycle(markets=markets)
            except Exception as e:
                portfolio.log_thought("System", "WARN", f"Auto-scan background iteration error: {e}")

@app.on_event("startup")
async def startup_event():
    portfolio.log_thought("System", "INFO", "Quant Desk Backend initialized with Crypto Watchlist & Liquidity Engine.")
    asyncio.create_task(background_scanner())

# Serve Frontend static assets
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def read_root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse({"status": "Quant Desk API Running", "ui": "frontend/index.html not found"})
