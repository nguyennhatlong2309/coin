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
from .core.plan_validator import TradePlanValidator
from .core.proposals import ProposalManager
from .config import BASE_DIR, AUTO_SCAN_INTERVAL_SECONDS

app = FastAPI(title="Quant Desk - Multi-Agent Mock Trading System")

portfolio = PortfolioManager()
crypto_service = CryptoService()
proposal_manager = ProposalManager()
swarm = SwarmEngine(portfolio, crypto_service=crypto_service, proposal_manager=proposal_manager)
plan_validator = TradePlanValidator(crypto_service, portfolio)

# Background auto-scan flag
is_auto_running = False

class CoinRequest(BaseModel):
    coin: str

class ScanRequest(BaseModel):
    coin: Optional[str] = None
    timeframe: str = "1h"
    max_leverage: Optional[int] = None
    max_stake: Optional[float] = None
    custom_sl_pct: Optional[float] = None
    custom_tp_pct: Optional[float] = None
    mode: str = "PROPOSAL" # "PROPOSAL" or "DIRECT_EXECUTE"

class ProposalActionRequest(BaseModel):
    proposal_id: str

class ClosePositionRequest(BaseModel):
    position_id: str

class PlanValidationRequest(BaseModel):
    coin: str
    side: str = "AUTO"
    timeframe: str = "SCALP"
    leverage: int = 3
    stake_amount: float = 50.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    no_sl_confirmed: bool = False

class ExecutePlannedTradeRequest(BaseModel):
    coin: str
    side: str
    leverage: int = 3
    stake_amount: float = 50.0
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reasoning: Optional[str] = "Lệnh đã qua thẩm định Hội đồng Rủi ro AI"

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

@app.post("/api/portfolio/close")
def close_position_api(req: ClosePositionRequest):
    pos = portfolio.state["open_positions"].get(req.position_id)
    if not pos:
        return {"success": False, "message": "Vị thế không tồn tại hoặc đã được đóng."}
    
    clean_sym = pos.get("symbol") or pos["market_id"].replace("crypto_", "").replace("USDT", "")
    ticker = crypto_service.fetch_coin_ticker(clean_sym)
    current_p = ticker["price"] if ticker else pos["current_price"]
    success = portfolio.close_position(req.position_id, current_p, reason="MANUAL")
    return {"success": success, "portfolio": portfolio.get_summary()}

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
    timeframe = req.timeframe if req else "1h"
    max_leverage = req.max_leverage if req else None
    max_stake = req.max_stake if req else None
    custom_sl_pct = req.custom_sl_pct if req else None
    custom_tp_pct = req.custom_tp_pct if req else None
    as_proposal = (req.mode == "PROPOSAL") if req else True

    markets = fetch_prediction_markets(limit=20)
    result = swarm.run_cycle(
        markets=markets,
        target_coin=target_coin,
        timeframe=timeframe,
        max_leverage=max_leverage,
        max_stake=max_stake,
        custom_sl_pct=custom_sl_pct,
        custom_tp_pct=custom_tp_pct,
        as_proposal=as_proposal
    )
    return {
        "cycle_result": result,
        "portfolio": portfolio.get_summary(),
        "proposals": proposal_manager.get_pending()
    }

# ----------------- PROPOSALS APPROVAL QUEUE ENDPOINTS -----------------

@app.get("/api/proposals")
def get_pending_proposals():
    return {
        "proposals": proposal_manager.get_pending(),
        "total_count": len(proposal_manager.get_pending())
    }

@app.post("/api/proposals/approve")
def approve_proposal(req: ProposalActionRequest):
    prop = proposal_manager.get(req.proposal_id)
    if not prop:
        return {"success": False, "message": "Không tìm thấy đề xuất này."}
    if prop.get("status") != "PENDING":
        return {"success": False, "message": "Đề xuất này đã được xử lý trước đó."}

    coin = prop["coin"]
    ticker = crypto_service.fetch_coin_ticker(coin)
    exec_price = ticker["price"] if ticker else prop["price"]

    success = portfolio.execute_trade(
        market_id=f"crypto_{coin}USDT",
        question=f"{coin}/USDT ({prop['side']})",
        outcome=prop["side"],
        price=exec_price,
        stake_amount=prop["stake_amount"],
        reasoning=f"Duyệt đề xuất AI: {prop['reasoning']}",
        asset_type="crypto",
        leverage=prop["leverage"],
        stop_loss=prop["stop_loss"],
        take_profit=prop["take_profit"],
        symbol=coin
    )

    if success:
        proposal_manager.update_status(req.proposal_id, "APPROVED")
        portfolio.log_thought(
            "User",
            "SUCCESS",
            f"ĐÃ PHÊ DUYỆT ĐỀ XUẤT: {prop['side']} {prop['leverage']}x {coin}/USDT @ ${exec_price:,.4f}"
        )
        return {
            "success": True,
            "message": f"Khớp lệnh thành công cho {coin}!",
            "portfolio": portfolio.get_summary(),
            "proposals": proposal_manager.get_pending()
        }
    else:
        return {"success": False, "message": "Không thể khớp lệnh (Vui lòng kiểm tra lại số dư tiền mặt)."}

@app.post("/api/proposals/reject")
def reject_proposal(req: ProposalActionRequest):
    prop = proposal_manager.get(req.proposal_id)
    if not prop:
        return {"success": False, "message": "Không tìm thấy đề xuất."}
    proposal_manager.update_status(req.proposal_id, "REJECTED")
    portfolio.log_thought("User", "INFO", f"Đã từ chối đề xuất {prop['side']} {prop['coin']}.")
    return {"success": True, "proposals": proposal_manager.get_pending()}

@app.post("/api/proposals/clear")
def clear_proposals():
    proposal_manager.clear_all()
    portfolio.log_thought("System", "INFO", "Đã xóa sạch hàng đợi đề xuất giao dịch.")
    return {"success": True, "proposals": []}

@app.post("/api/ai/validate-plan")
def validate_trade_plan(req: PlanValidationRequest):
    return plan_validator.validate_plan(
        coin=req.coin,
        side=req.side,
        timeframe=req.timeframe,
        leverage=req.leverage,
        stake_amount=req.stake_amount,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        no_sl_confirmed=req.no_sl_confirmed
    )

@app.post("/api/ai/execute-planned-trade")
def execute_planned_trade(req: ExecutePlannedTradeRequest):
    clean_coin = req.coin.upper().replace("USDT", "").strip()
    ticker = crypto_service.fetch_coin_ticker(clean_coin)
    exec_price = req.price if req.price > 0 else (ticker["price"] if ticker else 0.0)

    if exec_price <= 0:
        return {"success": False, "message": "Không thể lấy giá vào lệnh hợp lệ."}

    success = portfolio.execute_trade(
        market_id=f"crypto_{clean_coin}USDT",
        question=f"{clean_coin}/USDT ({req.side})",
        outcome=req.side,
        price=exec_price,
        stake_amount=req.stake_amount,
        reasoning=req.reasoning or "Lệnh thủ công đã qua Hội đồng Rủi ro AI thẩm định",
        asset_type="crypto",
        leverage=req.leverage,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit,
        symbol=clean_coin
    )

    if success:
        sl_text = f"${req.stop_loss:,.4f}" if req.stop_loss else "TẤT TAY (KHÔNG SL)"
        tp_text = f"${req.take_profit:,.4f}" if req.take_profit else "GỒNG LÃI TỰ DO"
        portfolio.log_thought(
            "Executor",
            "TRADE",
            f"VÀO LỆNH THEO KẾ HOẠCH: {req.side} {req.leverage}x ${req.stake_amount:.2f} của {clean_coin}/USDT @ ${exec_price:,.4f} | SL: {sl_text} | TP: {tp_text}"
        )

    return {
        "success": success,
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
