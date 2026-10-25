"""
Dynamic Multi-Worker Coin Swarm (Kiến Trúc Phân Thân Đa Đặc Vụ Chuyên Trách Theo Từng Coin)
Tự động khởi tạo (spawn) 1 con bot chuyên trách cho mỗi đồng coin trong Watchlist.
Mỗi con bot chạy song song 24/7, phản xạ tức thì dưới 100ms khi nến đóng cửa.
Được điều phối vốn tập trung bởi Central Capital Arbiter để tối ưu an toàn vốn.
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

VN_TZ = timezone(timedelta(hours=7))

class DedicatedCoinWorker:
    """
    Đặc Vụ Chuyên Trách 1 Đồng Coin (Dedicated Coin Worker)
    Mỗi đồng coin (SOL, DOGE, SUI, EPIC...) sở hữu 1 worker độc lập:
    - Canh nến 1M, 15M, 1H và Sổ lệnh L2 của riêng nó liên tục.
    - Bắt trọn từng cây nến rút râu Pinbar cá mập (SMC Sweep / FVG Retest).
    - Phản xạ tức thì, không cần xếp hàng đợi xoay tua.
    """
    def __init__(
        self,
        coin: str,
        swarm_engine,
        portfolio,
        proposal_manager,
        crypto_service,
        spawner,
        scan_interval: float = 24.0
    ):
        self.coin = coin.strip().upper().replace("USDT", "")
        self.swarm_engine = swarm_engine
        self.portfolio = portfolio
        self.proposal_manager = proposal_manager
        self.crypto_service = crypto_service
        self.spawner = spawner
        self.scan_interval = scan_interval

        # Trạng thái vòng đời của Worker
        self.is_running = False
        self.is_paused = False
        self.status = "INITIALIZING" # INITIALIZING, ACTIVE_HUNTING, IN_POSITION, COOLDOWN, PAUSED, STOPPED
        self.scan_count = 0
        self.last_scan_time: float = 0.0
        self.last_signal: Optional[Dict[str, Any]] = None
        self.last_action_desc: str = "Khởi tạo thành công"
        self.last_error: Optional[str] = None
        self.created_at: float = time.time()
        self._task: Optional[asyncio.Task] = None

    def start(self):
        """Khởi động worker chạy nền song song."""
        if self.is_running and self._task and not self._task.done():
            return
        self.is_running = True
        self.is_paused = False
        self.status = "ACTIVE_HUNTING"
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    self._task = asyncio.run_coroutine_threadsafe(self._run_loop(), loop)
                else:
                    self._task = loop.create_task(self._run_loop())
            except Exception as e:
                logger.error(f"[CoinWorker:{self.coin}] Could not start task: {e}")
        logger.info(f"[CoinWorker:{self.coin}] Worker started running background hunting loop.")

    def stop(self):
        """Dừng worker và giải phóng task khỏi bộ nhớ RAM."""
        self.is_running = False
        self.status = "STOPPED"
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info(f"[CoinWorker:{self.coin}] Worker stopped.")

    def pause(self):
        """Tạm dừng săn mồi (khi coin bị toggle OFF)."""
        self.is_paused = True
        self.status = "PAUSED"
        self.last_action_desc = "Tạm dừng (User Toggle OFF)"

    def resume(self):
        """Tiếp tục săn mồi."""
        self.is_paused = False
        self.status = "ACTIVE_HUNTING"
        self.last_action_desc = "Tiếp tục săn mồi"

    async def _run_loop(self):
        """Vòng lặp săn mồi chuyên biệt độc lập 24/7."""
        # Thêm độ trễ ban đầu ngẫu nhiên 0.5s - 2.5s để phân tán các worker, không gửi đồng loạt
        await asyncio.sleep(random.uniform(0.5, 2.5))

        while self.is_running:
            try:
                # 1. Kiểm tra cờ Tự Động (Auto Mode) toàn cục
                if not self.spawner.is_auto_running:
                    self.status = "STANDBY"
                    self.last_action_desc = "Chế độ Auto đang Tắt (Standby)"
                    await asyncio.sleep(3.0)
                    continue

                if self.is_paused:
                    self.status = "PAUSED"
                    await asyncio.sleep(3.0)
                    continue

                # 2. Kiểm tra xem đồng coin này đã có vị thế mở (Open Position) chưa
                open_positions = self.portfolio.state.get("open_positions", {})
                existing_pos = next(
                    (p for p in open_positions.values() if p.get("symbol", "").upper() == self.coin),
                    None
                )

                if existing_pos:
                    self.status = "IN_POSITION"
                    side = existing_pos.get("outcome", "LONG")
                    entry = existing_pos.get("entry_price", 0.0)
                    curr = existing_pos.get("current_price", entry)
                    pnl_pct = ((curr - entry)/entry*100) if side == "LONG" else ((entry - curr)/entry*100)
                    self.last_action_desc = f"Đang bảo vệ vị thế {side} ({pnl_pct:+.2f}%)"
                    # Đang có vị thế mở -> Giãn chu kỳ kiểm tra để nhường tài nguyên
                    await asyncio.sleep(6.0)
                    continue

                # 3. Kiểm tra xem coin có đề xuất chờ duyệt (Pending Proposal) không
                pending_proposals = self.proposal_manager.get_pending() if self.proposal_manager else []
                has_pending = any(p.get("coin", "").upper() == self.coin for p in pending_proposals)
                if has_pending and self.spawner.execution_mode != "AUTONOMOUS":
                    self.status = "PENDING_APPROVAL"
                    self.last_action_desc = "Đang có đề xuất chờ duyệt"
                    await asyncio.sleep(5.0)
                    continue

                # 4. Kích hoạt Chu kỳ Săn mồi & Bắn tỉa độc lập của Worker
                self.status = "SCANNING_MTF"
                self.scan_count += 1
                self.last_scan_time = time.time()

                as_prop = (self.spawner.execution_mode != "AUTONOMOUS")
                timeframe = self.spawner.timeframe or "1m"

                # Chạy phân tích trực tiếp cho riêng đồng coin này qua Swarm Engine trong Threadpool
                # Đảm bảo KHÔNG chặn Event Loop của FastAPI, giúp tải trang web luôn tức thì (<10ms)!
                cycle_result = await asyncio.to_thread(
                    self.swarm_engine.run_crypto_cycle,
                    target_coin=self.coin,
                    timeframe=timeframe,
                    as_proposal=as_prop
                )

                status_code = cycle_result.get("status", "unknown")
                if status_code in ["traded", "proposed"]:
                    self.status = "SIGNAL_TRIGGERED"
                    self.last_signal = cycle_result
                    side = cycle_result.get("side", "")
                    edge = cycle_result.get("edge", 0.0)
                    self.last_action_desc = f"Đã bóp cò: {side} (Lợi thế {edge:+.1%})"
                elif status_code == "hold":
                    self.status = "ACTIVE_HUNTING"
                    reason = cycle_result.get("reason", "Chưa đạt biên độ bóp cò")
                    # Rút gọn lý do để hiển thị đẹp
                    short_reason = reason[:55] + "..." if len(reason) > 55 else reason
                    self.last_action_desc = short_reason
                elif status_code == "all_coins_occupied":
                    self.status = "CAPITAL_OCCUPIED"
                    self.last_action_desc = "Hạn mức danh mục đã đầy"
                else:
                    self.status = "ACTIVE_HUNTING"
                    self.last_action_desc = f"Quét xong ({status_code})"

                self.last_error = None

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.last_error = str(e)
                self.last_action_desc = f"Lỗi vòng quét: {str(e)[:40]}"
                logger.warning(f"[CoinWorker:{self.coin}] Exception in hunting loop: {e}")
                await asyncio.sleep(4.0)

            # Jitter ngẫu nhiên để các worker chạy lệch pha nhịp nhàng
            jitter = random.uniform(-1.5, 2.5)
            sleep_duration = max(18.0, self.scan_interval + jitter)
            await asyncio.sleep(sleep_duration)

    def get_info(self) -> Dict[str, Any]:
        """Trả về thông tin chi tiết của worker cho API & Giao diện."""
        vn_time = datetime.fromtimestamp(self.last_scan_time, tz=VN_TZ).strftime("%H:%M:%S") if self.last_scan_time > 0 else "Chưa quét"
        uptime_s = int(time.time() - self.created_at) if self.created_at > 0 else 0

        return {
            "coin": self.coin,
            "status": self.status,
            "is_running": self.is_running,
            "is_paused": self.is_paused,
            "scan_count": self.scan_count,
            "last_scan_time": self.last_scan_time,
            "last_scan_time_vn": vn_time,
            "last_action_desc": self.last_action_desc,
            "last_error": self.last_error,
            "uptime_seconds": uptime_s
        }


class CoinSwarmSpawner:
    """
    Bộ Phân Thân & Quản Trị Đặc Vụ Đa Coin (Coin Swarm Spawner & Governor)
    - Tự động sinh (spawn) 1 worker khi người dùng thêm coin vào Watchlist.
    - Tự động thu hồi (terminate) worker khi người dùng xóa coin.
    - Điều phối vốn tập trung qua Central Capital Arbiter.
    """
    def __init__(
        self,
        swarm_engine,
        portfolio,
        proposal_manager,
        crypto_service
    ):
        self.swarm_engine = swarm_engine
        self.portfolio = portfolio
        self.proposal_manager = proposal_manager
        self.crypto_service = crypto_service

        self.workers: Dict[str, DedicatedCoinWorker] = {}
        self.is_auto_running = False
        self.execution_mode = "AUTONOMOUS"
        self.timeframe = "1m"
        self.max_concurrent_positions = 4

    def update_auto_settings(self, is_running: bool, mode: str, timeframe: str):
        """Cập nhật trạng thái điều hành của toàn bộ swarm."""
        self.is_auto_running = is_running
        self.execution_mode = mode
        self.timeframe = timeframe

    def spawn_worker(self, raw_coin: str) -> DedicatedCoinWorker:
        """Tự động phân thân ra 1 con bot chuyên trách cho đồng coin này."""
        clean = raw_coin.strip().upper().replace("USDT", "")
        if not clean:
            return None

        if clean in self.workers:
            worker = self.workers[clean]
            if not worker.is_running:
                worker.start()
            return worker

        worker = DedicatedCoinWorker(
            coin=clean,
            swarm_engine=self.swarm_engine,
            portfolio=self.portfolio,
            proposal_manager=self.proposal_manager,
            crypto_service=self.crypto_service,
            spawner=self,
            scan_interval=10.0
        )
        self.workers[clean] = worker
        worker.start()

        self.portfolio.log_thought(
            "Spawner",
            "SUCCESS",
            f"[Tự Động Phân Thân] Đã sinh thành công 1 con bot chuyên trách cho {clean}/USDT (Worker ID: worker_{clean} | Canh nến 1M độc lập 24/7)."
        )
        return worker

    def terminate_worker(self, raw_coin: str):
        """Thu hồi và giải phóng worker khỏi bộ nhớ RAM."""
        clean = raw_coin.strip().upper().replace("USDT", "")
        if clean in self.workers:
            worker = self.workers.pop(clean)
            worker.stop()
            self.portfolio.log_thought(
                "Spawner",
                "INFO",
                f"[Thu Hồi Worker] Đã hủy và giải phóng con bot chuyên trách {clean}/USDT khỏi bộ nhớ."
            )

    def toggle_worker(self, raw_coin: str, is_active: bool):
        """Tạm dừng hoặc tiếp tục worker."""
        clean = raw_coin.strip().upper().replace("USDT", "")
        if clean in self.workers:
            if is_active:
                self.workers[clean].resume()
            else:
                self.workers[clean].pause()

    def sync_with_watchlist(self):
        """Đồng bộ toàn bộ danh sách worker theo Watchlist thực tế."""
        current_watchlist = [c.strip().upper().replace("USDT", "") for c in self.crypto_service.watchlist]
        active_status = self.crypto_service.active_status

        # 1. Spawn worker cho các coin mới có trong watchlist
        for coin in current_watchlist:
            if coin not in self.workers:
                worker = self.spawn_worker(coin)
                is_active = active_status.get(coin, True)
                if not is_active and worker:
                    worker.pause()
            else:
                # Đã có worker, kiểm tra trạng thái pause/resume
                is_active = active_status.get(coin, True)
                if is_active and self.workers[coin].is_paused:
                    self.workers[coin].resume()
                elif not is_active and not self.workers[coin].is_paused:
                    self.workers[coin].pause()

        # 2. Xóa các worker của những coin không còn nằm trong watchlist
        existing_coins = list(self.workers.keys())
        for coin in existing_coins:
            if coin not in current_watchlist:
                self.terminate_worker(coin)

    def start_all(self):
        """Bật toàn bộ workers săn mồi."""
        self.is_auto_running = True
        self.sync_with_watchlist()
        for worker in self.workers.values():
            if not worker.is_running:
                worker.start()

    def stop_all(self):
        """Dừng toàn bộ workers."""
        self.is_auto_running = False
        for worker in self.workers.values():
            worker.stop()

    def get_summary(self) -> Dict[str, Any]:
        """Tổng hợp tình trạng toàn bộ đàn bot đa coin."""
        workers_list = [w.get_info() for w in self.workers.values()]
        active_count = sum(1 for w in workers_list if w["is_running"] and not w["is_paused"])
        hunting_count = sum(1 for w in workers_list if w["status"] in ["ACTIVE_HUNTING", "SCANNING_MTF"])
        in_pos_count = sum(1 for w in workers_list if w["status"] == "IN_POSITION")

        return {
            "total_workers": len(self.workers),
            "active_workers": active_count,
            "hunting_workers": hunting_count,
            "in_position_workers": in_pos_count,
            "is_auto_running": self.is_auto_running,
            "execution_mode": self.execution_mode,
            "timeframe": self.timeframe,
            "workers": workers_list
        }
