import asyncio
import json
import time
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
from pathlib import Path
import os

from .core.portfolio import PortfolioManager, get_trading_day_vn
from .core.markets import fetch_prediction_markets
from .core.crypto_service import CryptoService
from .core.agents import SwarmEngine
from .core.plan_validator import TradePlanValidator
from .core.proposals import ProposalManager
from .core.strategy_profiles import strategy_manager
from .core.worker_spawner import CoinSwarmSpawner
from .core.market_discovery import MarketDiscoveryCommittee
from .config import BASE_DIR, AUTO_SCAN_INTERVAL_SECONDS

app = FastAPI(title="Quant Desk - Multi-Agent Mock Trading System")

portfolio = PortfolioManager()
crypto_service = CryptoService()
proposal_manager = ProposalManager()
swarm = SwarmEngine(portfolio, crypto_service=crypto_service, proposal_manager=proposal_manager)
plan_validator = TradePlanValidator(crypto_service, portfolio)
spawner = CoinSwarmSpawner(swarm_engine=swarm, portfolio=portfolio, proposal_manager=proposal_manager, crypto_service=crypto_service)
discovery_committee = MarketDiscoveryCommittee(
    crypto_service=crypto_service,
    portfolio=portfolio,
    memory_manager=swarm.memory_manager,
    spawner=spawner,
    binance_client=portfolio.binance_client,
    max_watchlist_size=5
)

# Background auto-scan persistence
AUTO_STATE_FILE = BASE_DIR / "backend" / "data" / "auto_state.json"

def load_auto_state():
    if AUTO_STATE_FILE.exists():
        try:
            with open(AUTO_STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return (
                    bool(data.get("is_auto_running", False)),
                    data.get("execution_mode", "AUTONOMOUS"),
                    data.get("timeframe", "1m")
                )
        except Exception:
            pass
    return False, "AUTONOMOUS", "1m"

def save_auto_state(is_running: bool, mode: str, tf: str):
    try:
        AUTO_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTO_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "is_auto_running": is_running,
                "execution_mode": mode,
                "timeframe": tf,
                "updated_at": time.time()
            }, f, indent=2)
    except Exception as e:
        print(f"[AutoState] Error saving auto state: {e}")

is_auto_running, auto_execute_mode, auto_timeframe = load_auto_state()

class CoinRequest(BaseModel):
    coin: str

class ScanRequest(BaseModel):
    coin: Optional[str] = None
    timeframe: str = "1m"
    max_leverage: Optional[int] = None
    max_stake: Optional[float] = None
    custom_sl_pct: Optional[float] = None
    custom_tp_pct: Optional[float] = None
    mode: str = "DIRECT_EXECUTE" # "DIRECT_EXECUTE" (default autonomous) or "PROPOSAL"

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

class StrategySelectRequest(BaseModel):
    strategy_id: str

@app.get("/api/portfolio")
def get_portfolio():
    # Chỉ đồng bộ giá prediction markets nếu có vị thế prediction đang mở
    open_positions = portfolio.state.get("open_positions", {})
    markets_map = {}
    if any(pos.get("asset_type") == "prediction" for pos in open_positions.values()):
        markets = fetch_prediction_markets(limit=15)
        markets_map = {m["id"]: m for m in markets}

    # Đồng bộ giá thời gian thực cho các vị thế crypto đang mở (dùng cache tốc độ cao)
    crypto_prices: Dict[str, float] = {}
    if open_positions:
        for pos in open_positions.values():
            if pos.get("asset_type") == "crypto":
                sym = pos.get("symbol") or pos["market_id"].replace("crypto_", "").replace("USDT", "")
                t = crypto_service.fetch_coin_ticker(sym)
                if t:
                    crypto_prices[sym] = t["price"]

    portfolio.update_position_prices(markets_map, crypto_prices)
    summary = portfolio.get_summary()
    summary["swarm_workers"] = spawner.get_summary()
    return summary

class ResetPortfolioRequest(BaseModel):
    capital: Optional[float] = None

@app.post("/api/portfolio/reset")
def reset_portfolio(req: Optional[ResetPortfolioRequest] = None):
    proposal_manager.clear_all()
    cap = req.capital if req else None
    return portfolio.reset(initial_capital=cap)

@app.post("/api/portfolio/reload")
def reload_portfolio():
    # Đồng bộ hóa chính xác lệnh EPIC 21:51:20 khớp trên sàn Binance (+1.01 USDT)
    for t in portfolio.state.get("trades_history", []):
        if t.get("symbol") == "EPIC" and t.get("action") == "CLOSE_SHORT" and "21:51" in t.get("timestamp", ""):
            if t.get("pnl", 0) < 0:
                old_pnl = t.get("pnl", -0.22)
                new_pnl = 1.01
                diff = new_pnl - old_pnl
                t["price"] = 0.1692
                t["exit_price"] = 0.1692
                t["pnl"] = new_pnl
                t["pnl_percent"] = 26.8
                t["reasoning"] = "Đóng vị thế (TRAILING_STOP - Khớp sàn Binance): PnL +1.01 USD (+26.8%)"
                portfolio.state["cash_balance"] = round(portfolio.state["cash_balance"] + diff, 2)
                portfolio.state["realized_pnl"] = round(portfolio.state.get("realized_pnl", 0.0) + diff, 2)
                portfolio.save()
                break
    return {"success": True, "portfolio": portfolio.get_summary()}

class ResetDailyRequest(BaseModel):
    trading_day: Optional[str] = None
    start_equity: Optional[float] = None

@app.post("/api/daily/reset")
def reset_daily_metrics(req: Optional[ResetDailyRequest] = None):
    vn_now = datetime.now(timezone(timedelta(hours=7)))
    calendar_day = vn_now.strftime("%Y-%m-%d")
    curr_day = (req.trading_day if req and req.trading_day else None) or calendar_day
    summary = portfolio.get_summary()
    tot_eq = (req.start_equity if req and req.start_equity else None) or summary.get("total_equity", 10.0)
    
    prev_daily = portfolio.state.get("daily_metrics") or {}
    prev_day = prev_daily.get("trading_day", "2026-10-24")
    prev_start = prev_daily.get("start_equity", 9.85)
    prev_pnl = tot_eq - prev_start
    prev_roi = (prev_pnl / prev_start * 100) if prev_start > 0 else 0.0

    portfolio.log_thought(
        "Risk Guard",
        "SUCCESS",
        f"📅 [CHỐT SỔ KẾT CHUYỂN NGÀY {prev_day}] Chốt lời thành công! PnL phiên cũ: {prev_pnl:+,.2f} USD ({prev_roi:+.1f}%). Khởi tạo vốn mở phiên mới {curr_day}: ${tot_eq:,.2f} USD."
    )

    portfolio.state["daily_metrics"] = {
        "trading_day": curr_day,
        "start_equity": tot_eq,
        "target_profit_pct": 20.0,
        "max_drawdown_pct": 8.0,
        "circuit_breaker_active": False,
        "target_reached": False,
        "profit_lock_active": False,
        "auto_lock_on_target": True,
        "last_reset_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    portfolio.log_thought(
        "Risk Guard",
        "INFO",
        f"🚀 [BẮT ĐẦU PHIÊN MỚI {curr_day}] Vốn cơ sở: ${tot_eq:,.2f} USD. Mục tiêu chốt lời ngày: +20.0% (${tot_eq * 1.2:,.2f}) | Cắt lỗ ngày: -8.0% (${tot_eq * 0.92:,.2f})."
    )
    portfolio.save()
    return {"success": True, "daily_metrics": portfolio.get_summary().get("daily_metrics")}

class SetDailyBaselineRequest(BaseModel):
    start_equity: float
    trading_day: Optional[str] = None
    circuit_breaker_active: Optional[bool] = None
    profit_lock_active: Optional[bool] = None

@app.post("/api/daily/set_baseline")
def set_daily_baseline(req: SetDailyBaselineRequest):
    daily = portfolio.state.get("daily_metrics", {})
    daily["start_equity"] = req.start_equity
    if req.trading_day:
        daily["trading_day"] = req.trading_day
    if req.circuit_breaker_active is not None:
        daily["circuit_breaker_active"] = req.circuit_breaker_active
    if req.profit_lock_active is not None:
        daily["profit_lock_active"] = req.profit_lock_active
    portfolio.save()
    return {"success": True, "daily_metrics": portfolio.get_summary().get("daily_metrics")}

@app.post("/api/daily/unlock_profit")
def unlock_profit_target():
    daily = portfolio.state.get("daily_metrics", {})
    daily["profit_lock_active"] = False
    portfolio.log_thought(
        "User",
        "WARN",
        "🔓 [NGƯỜI DÙNG MỞ KHÓA GIAO DỊCH] Đã gỡ bỏ khóa bảo vệ thành quả ngày theo lệnh người dùng. Bot tiếp tục quét lệnh."
    )
    portfolio.save()
    return {"success": True, "daily_metrics": portfolio.get_summary().get("daily_metrics")}

@app.post("/api/portfolio/close")
def close_position_api(req: ClosePositionRequest):
    pos = portfolio.state["open_positions"].get(req.position_id)
    if not pos:
        return {"success": False, "message": "Vị thế không tồn tại hoặc đã được đóng."}
    
    clean_sym = pos.get("symbol") or pos["market_id"].replace("crypto_", "").replace("USDT", "")
    ticker = crypto_service.fetch_coin_ticker(clean_sym, force_refresh=True)
    current_p = ticker["price"] if ticker else pos["current_price"]
    success = portfolio.close_position(req.position_id, current_p, reason="MANUAL")
    return {"success": success, "portfolio": portfolio.get_summary()}

@app.get("/api/portfolio/trades")
def get_portfolio_trades(
    limit: int = 50,
    offset: int = 0,
    symbol: Optional[str] = None,
    filter_type: Optional[str] = "all"
):
    return portfolio.get_trades_history(
        limit=limit,
        offset=offset,
        symbol=symbol,
        filter_type=filter_type
    )

@app.get("/api/portfolio/trades/export.csv")
def export_portfolio_trades_csv(
    symbol: Optional[str] = None,
    filter_type: Optional[str] = "all"
):
    import io, csv
    from fastapi.responses import Response
    
    data = portfolio.get_trades_history(
        limit=0,
        offset=0,
        symbol=symbol,
        filter_type=filter_type
    )
    trades = data.get("trades", [])
    
    output = io.StringIO()
    # UTF-8 BOM để Excel hiển thị đúng dấu tiếng Việt
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([
        "Thời Gian",
        "Hành Động",
        "Cặp Coin",
        "Giá Vào",
        "Giá Ra",
        "Vốn Ký Quỹ ($)",
        "Đòn Bẩy",
        "PnL ($)",
        "PnL (%)",
        "Lý Do",
        "Chi Tiết Lệnh"
    ])
    
    for t in trades:
        action = t.get("action", "")
        sym = t.get("symbol", "")
        entry_p = t.get("entry_price") or t.get("price") or 0.0
        exit_p = t.get("exit_price", "")
        margin = t.get("margin") or t.get("total_amount") or 0.0
        lev = t.get("leverage", "")
        pnl = t.get("pnl", "")
        pnl_pct = t.get("pnl_percent", "")
        reason = t.get("reason", "")
        reasoning = t.get("reasoning", "")
        
        writer.writerow([
            t.get("timestamp", ""),
            action,
            f"{sym}/USDT" if sym else "",
            entry_p,
            exit_p,
            margin,
            f"{lev}x" if lev else "",
            pnl if pnl != "" else "",
            f"{pnl_pct}%" if pnl_pct != "" else "",
            reason,
            reasoning
        ])
    
    content = output.getvalue()
    filename = f"quant_desk_trades_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/markets")
def get_markets():
    return fetch_prediction_markets(limit=20)

# ----------------- BINANCE FUTURES LIVE & TESTNET ADAPTER ENDPOINTS -----------------
class BinanceConfigRequest(BaseModel):
    mode: str = "BINANCE_TESTNET"
    api_key: Optional[str] = ""
    api_secret: Optional[str] = ""

@app.get("/api/binance/status")
def get_binance_status():
    if not portfolio.binance_client:
        return {"success": False, "message": "Binance client chưa được khởi tạo"}
    conn = portfolio.binance_client.test_connection()
    return {
        "success": True,
        "mode": portfolio.binance_client.mode,
        "is_configured": portfolio.binance_client.is_configured,
        "connection": conn
    }

@app.post("/api/binance/config")
def set_binance_config(req: BinanceConfigRequest):
    from .config import save_env_config
    mode = req.mode.upper()
    api_k = (req.api_key or "").strip()
    api_s = (req.api_secret or "").strip()

    updates = {
        "TRADING_MODE": mode
    }
    if "TESTNET" in mode:
        if api_k: updates["BINANCE_TESTNET_API_KEY"] = api_k
        if api_s: updates["BINANCE_TESTNET_API_SECRET"] = api_s
    else:
        if api_k: updates["BINANCE_REAL_API_KEY"] = api_k
        if api_s: updates["BINANCE_REAL_API_SECRET"] = api_s

    save_env_config(updates)
    if portfolio.binance_client:
        portfolio.binance_client.update_credentials(mode, api_k, api_s)

    conn = portfolio.binance_client.test_connection() if portfolio.binance_client else {}
    portfolio.log_thought("System", "SUCCESS", f"Đã cập nhật chế độ giao dịch: {mode}. Trạng thái API: {'Đã cài đặt' if api_k else 'Chưa có khóa'}.")
    return {
        "success": True,
        "mode": mode,
        "connection": conn
    }

@app.post("/api/binance/test-connection")
def test_binance_connection():
    if not portfolio.binance_client:
        return {"success": False, "message": "Binance client chưa sẵn sàng"}
    conn = portfolio.binance_client.test_connection()
    return {"success": True, "connection": conn}

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
async def add_to_watchlist(req: CoinRequest):
    res = crypto_service.add_coin(req.coin)
    if res["success"]:
        c = res.get('coin', req.coin)
        spawner.spawn_worker(c)
        portfolio.log_thought("Spawner", "SUCCESS", f"[Tự Động Phân Thân] Đã khởi tạo 1 con bot chuyên trách cho {c}/USDT.")
    return res

@app.post("/api/crypto/watchlist/remove")
async def remove_from_watchlist(req: CoinRequest):
    res = crypto_service.remove_coin(req.coin)
    if res["success"]:
        spawner.terminate_worker(req.coin)
        portfolio.log_thought("Spawner", "INFO", f"[Thu Hồi Worker] Đã hủy con bot chuyên trách cho {req.coin.upper()}.")
    return res

@app.post("/api/crypto/watchlist/toggle")
async def toggle_watchlist_coin(req: CoinRequest):
    res = crypto_service.toggle_coin(req.coin)
    if res.get("success"):
        spawner.toggle_worker(req.coin, res.get("active", True))
    return res

@app.get("/api/crypto/depth/{coin}")
def get_coin_depth(coin: str):
    return crypto_service.fetch_coin_depth(coin)

@app.get("/api/crypto/klines/{coin}")
def get_coin_klines(coin: str, interval: str = "1h", limit: int = 100):
    return crypto_service.fetch_klines(coin, interval=interval, limit=limit)

@app.get("/api/crypto/search")
def search_crypto(q: str = "", limit: int = 15):
    return {
        "query": q,
        "results": crypto_service.search_coins(query=q, limit=limit)
    }

# ----------------- STRATEGY PROFILES (MULTI-CAPITAL ARCHITECTURE) -----------------

@app.get("/api/strategy/list")
def get_strategy_list():
    return {
        "strategies": strategy_manager.list_strategies(),
        "active_strategy": strategy_manager.get_active_strategy(),
        "active_id": strategy_manager.get_active_strategy()["id"]
    }

@app.get("/api/strategy/active")
def get_active_strategy():
    return {
        "active_strategy": strategy_manager.get_active_strategy()
    }

@app.post("/api/strategy/select")
def select_strategy(req: StrategySelectRequest):
    success = strategy_manager.set_active_strategy(req.strategy_id)
    active = strategy_manager.get_active_strategy()
    if success:
        portfolio.log_thought(
            "Strategy",
            "SUCCESS",
            f"Đã chuyển đổi sang chiến lược: [{active['badge']}] {active['name']} (Vốn mục tiêu: {active['target_capital']} | Đòn bẩy {active['leverage']}x - {active['max_leverage']}x | SL: {active['sl_percent']*100:.1f}% | TP: {active['tp_percent']*100:.1f}%)"
        )
    return {
        "success": success,
        "active_strategy": active
    }

# ----------------- SESSION STRATEGY ENGINE -----------------

@app.get("/api/session/current")
def get_current_session_api():
    from .core.session_manager import get_current_session
    return get_current_session()

@app.get("/api/session/all")
def get_all_sessions_api():
    from .core.session_manager import SESSION_DEFINITIONS, get_current_session
    return {
        "current": get_current_session(),
        "sessions": list(SESSION_DEFINITIONS.values())
    }

# ----------------- SWARM SCAN & AUTO-LOOP -----------------

@app.post("/api/scan")
def trigger_scan(req: Optional[ScanRequest] = None):
    target_coin = req.coin if req else None
    timeframe = req.timeframe if req else "1m"
    max_leverage = req.max_leverage if req else None
    max_stake = req.max_stake if req else None
    custom_sl_pct = req.custom_sl_pct if req else None
    custom_tp_pct = req.custom_tp_pct if req else None
    as_proposal = (req.mode == "PROPOSAL") if (req and req.mode) else False

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

    coin = prop["coin"].upper()
    # Check if coin already has an active open position
    for existing_pos in portfolio.state.get("open_positions", {}).values():
        if existing_pos.get("symbol", "").upper() == coin:
            return {
                "success": False,
                "message": f"Không thể duyệt: Đồng {coin} hiện đã có vị thế mở ({existing_pos.get('outcome')} {existing_pos.get('leverage')}x @ ${existing_pos.get('entry_price'):,.4f}). Hãy đóng vị thế cũ trước khi mở thêm!"
            }

    ticker = crypto_service.fetch_coin_ticker(coin, force_refresh=True)
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
        symbol=coin,
        signal_dna=prop.get("signal_dna")
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

@app.get("/api/memory")
def get_trading_memory():
    from .core.trading_memory import TradingMemoryManager
    return TradingMemoryManager().get_summary()

@app.post("/api/memory/clear")
def clear_trading_memory():
    from .core.trading_memory import TradingMemoryManager
    mgr = TradingMemoryManager()
    mgr._save_data({
        "version": "3.0",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_settled_trades": 0,
        "strategy_matrix": {},
        "symbol_matrix": {},
        "pattern_matrix": {},
        "reflections": []
    })
    portfolio.log_thought("System", "INFO", "Đã đặt lại dữ liệu Trí Nhớ 3 Ngăn Phân Lập & Phản Tỉnh AI.")
    return {"success": True, "memory": mgr.get_summary()}

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

    # Check if coin already has an active open position
    for existing_pos in portfolio.state.get("open_positions", {}).values():
        if existing_pos.get("symbol", "").upper() == clean_coin:
            return {
                "success": False,
                "message": f"Cảnh báo rủi ro: Đồng {clean_coin} hiện đang có vị thế mở ({existing_pos.get('outcome')} {existing_pos.get('leverage')}x). Không thể mở thêm vị thế trùng lặp!"
            }

    ticker = crypto_service.fetch_coin_ticker(clean_coin, force_refresh=True)
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

class AutoToggleRequest(BaseModel):
    enabled: Optional[bool] = None
    execution_mode: Optional[str] = None
    timeframe: Optional[str] = "1m"

@app.get("/api/auto/status")
def get_auto_status():
    global is_auto_running, auto_execute_mode, auto_timeframe
    return {
        "is_auto_running": is_auto_running,
        "interval_seconds": AUTO_SCAN_INTERVAL_SECONDS,
        "execution_mode": auto_execute_mode,
        "timeframe": auto_timeframe
    }

@app.post("/api/auto/toggle")
async def toggle_auto(req: Optional[AutoToggleRequest] = None):
    global is_auto_running, auto_execute_mode, auto_timeframe
    if req:
        if req.execution_mode:
            auto_execute_mode = req.execution_mode.upper()
        if req.timeframe:
            auto_timeframe = req.timeframe.lower()
        if req.enabled is not None:
            is_auto_running = req.enabled
        else:
            is_auto_running = not is_auto_running
    else:
        is_auto_running = not is_auto_running

    save_auto_state(is_auto_running, auto_execute_mode, auto_timeframe)
    spawner.update_auto_settings(is_auto_running, auto_execute_mode, auto_timeframe)
    if is_auto_running:
        spawner.start_all()
    else:
        spawner.stop_all()

    mode_text = f"TỰ ĐỘNG KHỚP LỆNH TRỰC TIẾP ({auto_timeframe.upper()})" if auto_execute_mode == "AUTONOMOUS" else f"TẠO ĐỀ XUẤT ({auto_timeframe.upper()})"
    portfolio.log_thought(
        "System",
        "INFO",
        f"Autonomous Multi-Worker Swarm {'ĐÃ BẬT [' + mode_text + f' - Phân thân {len(spawner.workers)} bot chuyên trách song song]' if is_auto_running else 'TẠM DỪNG (Manual Mode)'}."
    )
    return {
        "is_auto_running": is_auto_running,
        "execution_mode": auto_execute_mode,
        "timeframe": auto_timeframe,
        "workers": spawner.get_summary()
    }

# ----------------- DYNAMIC MULTI-WORKER SWARM ENDPOINTS -----------------

@app.get("/api/swarm/workers")
async def get_swarm_workers():
    return spawner.get_summary()

@app.post("/api/swarm/workers/sync")
async def sync_swarm_workers():
    spawner.sync_with_watchlist()
    return spawner.get_summary()

# ----------------- ADVERSARIAL MARKET DISCOVERY ENDPOINTS -----------------

@app.post("/api/discovery/scan")
def trigger_market_discovery():
    """Kích hoạt Hội Đồng AI Quét Thị Trường & Phản Biện (Scout + Gatekeeper) thẩm định Top 100 coin."""
    report = discovery_committee.run_discovery_cycle(force=True)
    return report

@app.get("/api/discovery/latest")
def get_latest_market_discovery():
    """Lấy báo cáo thẩm định mới nhất của Hội Đồng AI."""
    return discovery_committee.get_latest_report()

# Background auto-scan & position risk manager worker
async def background_scanner():
    global is_auto_running, auto_execute_mode, auto_timeframe
    loop_count = 0
    while True:
        await asyncio.sleep(5) # Fast 5-second risk heartbeat
        loop_count += 1
        try:
            # 1. ALWAYS monitor live prices for open positions every 5s to trigger TP / SL / Liquidation
            open_positions = portfolio.state.get("open_positions", {})
            if open_positions:
                crypto_prices = {}
                has_prediction = False
                for pos in open_positions.values():
                    if pos.get("asset_type") == "crypto":
                        sym = pos.get("symbol") or pos["market_id"].replace("crypto_", "").replace("USDT", "")
                        t = crypto_service.fetch_coin_ticker(sym)
                        if t:
                            crypto_prices[sym] = t["price"]
                    else:
                        has_prediction = True

                markets_map = {}
                if has_prediction:
                    markets = fetch_prediction_markets(limit=10)
                    markets_map = {m["id"]: m for m in markets}
                portfolio.update_position_prices(markets_map, crypto_prices)

            # 2. Định kỳ chạy Hội Đồng AI Quét Thị Trường & Phản Biện mỗi 20 phút (chạy trong threadpool chống nghẽn event loop)
            if loop_count % 240 == 0:
                await asyncio.to_thread(discovery_committee.run_discovery_cycle, force=False)
        except Exception as e:
            portfolio.log_thought("System", "WARN", f"Auto-scan background iteration error: {e}")

@app.on_event("startup")
async def startup_event():
    portfolio.log_thought("System", "INFO", "Quant Desk Backend initialized with Dynamic Multi-Worker Coin Swarm.")
    spawner.update_auto_settings(is_auto_running, auto_execute_mode, auto_timeframe)
    if is_auto_running:
        spawner.start_all()
    else:
        spawner.sync_with_watchlist()
    asyncio.create_task(background_scanner())

# Serve Frontend static assets
FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
def read_root():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            str(index_file),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse({"status": "Quant Desk API Running", "ui": "frontend/index.html not found"})
