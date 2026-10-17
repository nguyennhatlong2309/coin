import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import os

from .core.portfolio import PortfolioManager
from .core.markets import fetch_prediction_markets
from .core.agents import SwarmEngine
from .config import BASE_DIR, AUTO_SCAN_INTERVAL_SECONDS

app = FastAPI(title="Quant Desk - Multi-Agent Mock Trading System")

portfolio = PortfolioManager()
swarm = SwarmEngine(portfolio)

# Background auto-scan flag
is_auto_running = False

@app.get("/api/portfolio")
def get_portfolio():
    # Sync current prices
    markets = fetch_prediction_markets(limit=25)
    markets_map = {m["id"]: m for m in markets}
    portfolio.update_position_prices(markets_map)
    return portfolio.get_summary()

@app.post("/api/portfolio/reset")
def reset_portfolio():
    return portfolio.reset()

@app.get("/api/markets")
def get_markets():
    return fetch_prediction_markets(limit=20)

@app.post("/api/scan")
def trigger_scan():
    markets = fetch_prediction_markets(limit=25)
    result = swarm.run_cycle(markets)
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
        f"Autonomous Swarm Loop {'ENABLED (Active every 30s)' if is_auto_running else 'PAUSED (Manual Mode)'}."
    )
    return {"is_auto_running": is_auto_running}

# Background auto-scan worker
async def background_scanner():
    global is_auto_running
    while True:
        await asyncio.sleep(AUTO_SCAN_INTERVAL_SECONDS)
        if is_auto_running:
            try:
                markets = fetch_prediction_markets(limit=25)
                swarm.run_cycle(markets)
            except Exception as e:
                portfolio.log_thought("System", "WARN", f"Auto-scan background iteration error: {e}")

@app.on_event("startup")
async def startup_event():
    portfolio.log_thought("System", "INFO", "Quant Desk Backend initialized. Ready for simulation.")
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
