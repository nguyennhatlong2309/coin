"""
Market Discovery Committee (Hội Đồng AI Quét & Thẩm Định Thị Trường Tự Động)
Kiến trúc 2 Đặc Vụ Đối Nghịch (Adversarial Multi-Agent Discovery):
1. Alpha Scout (Thợ Săn Cơ Hội):
   - Quét Top 100 coin thanh khoản lớn trên Binance Futures (Volume >= $30M USDT).
   - Nhận diện các đồng coin có dòng tiền mạnh, nén lò xo chuẩn bị bung sóng (RVOL cao, SMC sạch).
2. Gatekeeper / Devil's Advocate (Quan Tòa Phản Biện Khắt Khe):
   - Đóng vai người khó tính nhất, vạch lá tìm sâu để từ chối các ứng viên tiềm ẩn rủi ro:
     * Soi bẫy FOMO đu đỉnh (24h pump > 15%, RSI > 72).
     * Soi trượt giá (Spread > 0.04%), thanh khoản mỏng.
     * Đối soát Trí Nhớ Quá Khứ (Memory Engine): Tránh các coin có dớp thua lỗ.
   - Thang điểm ngặt nghèo (Chỉ duyệt khi đạt >= 75/100 điểm).
3. Cơ chế Giới Hạn Cứng 5 Coin & Quy Tắc 1 Vào - 1 Ra (Promotion & Relegation):
   - Tối đa 5 coin trong Watchlist để tránh xé nhỏ dòng vốn.
   - 2 Coin Trụ Bất Khả Xâm Phạm: BTC & ETH luôn được bảo vệ.
   - Khi có coin mới xuất sắc, tự động thay thế đồng coin yếu nhất (không có lệnh mở).
"""

import time
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

class MarketDiscoveryCommittee:
    def __init__(
        self,
        crypto_service,
        portfolio,
        memory_manager,
        spawner=None,
        binance_client=None,
        max_watchlist_size: int = 5
    ):
        self.crypto_service = crypto_service
        self.portfolio = portfolio
        self.memory_manager = memory_manager
        self.spawner = spawner
        self.binance_client = binance_client
        self.max_watchlist_size = max_watchlist_size

        # 2 Coin Trụ Bất Khả Xâm Phạm (Anchor Core) - Không bao giờ tự động gỡ bỏ
        self.anchor_coins = {"BTC", "ETH"}
        
        # Danh sách đen vĩnh viễn (Meme rác / coin từng gây rủi ro cao / stablecoins)
        self.blacklist = {
            "EPIC", "PEPE", "SHIB", "FLOKI", "BOME", "MEME", "NEIRO",
            "USD1", "USDC", "FDUSD", "TUSD", "BUSD", "EUR", "DAI", "USDP", "AEUR", 
            "USDE", "PYUSD", "USTC", "EURI", "WBTC", "WETH", "USDD", "GUSD"
        }

        self.last_scan_time: float = 0.0
        self.latest_report: Optional[Dict[str, Any]] = None
        self._valid_futures_cache: Optional[set] = None
        self._valid_futures_cache_time: float = 0.0

    def get_valid_futures_symbols(self) -> set:
        """Lấy danh sách các cặp coin THỰC SỰ được hỗ trợ Futures Hợp Đồng Vĩnh Viễn trên Binance."""
        now = time.time()
        if self._valid_futures_cache and (now - self._valid_futures_cache_time < 3600.0):
            return self._valid_futures_cache

        try:
            url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
            resp = self.crypto_service.client.get(url, timeout=4.0)
            if resp.status_code == 200:
                data = resp.json()
                symbols = {
                    s["baseAsset"].upper()
                    for s in data.get("symbols", [])
                    if s.get("quoteAsset") == "USDT" 
                    and s.get("status") == "TRADING" 
                    and s.get("contractType") == "PERPETUAL"
                }
                self._valid_futures_cache = symbols
                self._valid_futures_cache_time = now
                return symbols
        except Exception as e:
            logger.warning(f"Error fetching futures exchangeInfo: {e}")

        # Fallback danh sách coin trụ Futures phổ biến nhất
        fallback = {
            "BTC", "ETH", "SOL", "DOGE", "BNB", "XRP", "ADA", "AVAX", "LINK", "NEAR",
            "SUI", "APT", "TIA", "ARB", "OP", "INJ", "DOT", "MATIC", "LTC", "BCH",
            "UNI", "ATOM", "FIL", "ETC", "XLM", "ICP", "KAS", "FET", "RENDER", "TAO",
            "AAVE", "MKR", "CRV", "STX", "RUNE", "GALA", "SAND", "MANA", "FLOW"
        }
        return fallback

    def run_discovery_cycle(self, force: bool = False, auto_modify: bool = False) -> Dict[str, Any]:
        """
        Thực hiện một chu kỳ Quét Thị Trường & Tranh Biện Đối Nghịch hoàn chỉnh.
        auto_modify: Chỉ tự động thay đổi Watchlist khi được người dùng cấp phép rõ ràng (mặc định False để bảo toàn danh mục chuẩn).
        """
        now = time.time()
        # Giới hạn tần suất: Tối thiểu 10 phút giữa các lần quét tự động (trừ khi force=True)
        if not force and (now - self.last_scan_time < 600.0) and self.latest_report:
            return self.latest_report

        self.last_scan_time = now
        timestamp_str = datetime.now().strftime("%H:%M:%S")

        self.portfolio.log_thought(
            "Scout",
            "INFO",
            f"🔍 [Hội Đồng AI Quét Thị Trường] Bắt đầu rà soát toàn bộ thị trường Binance Futures (Lọc thanh khoản >= $30M, Giới hạn danh mục: {self.max_watchlist_size} coin)..."
        )

        # ---------------------------------------------------------------------
        # BƯỚC 1: ALPHA SCOUT - SÀNG LỌC TOÀN BỘ VŨ TRỤ BINANCE
        # ---------------------------------------------------------------------
        all_tickers = self.crypto_service.get_all_usdt_tickers(force_refresh=True)
        if not all_tickers:
            msg = "Không thể lấy dữ liệu thị trường từ sàn Binance."
            self.portfolio.log_thought("Scout", "WARN", msg)
            return {"status": "error", "message": msg}

        current_watchlist = set(c.upper() for c in self.crypto_service.watchlist)
        valid_futures = self.get_valid_futures_symbols()
        candidates_scored = []

        for item in all_tickers:
            coin = item["coin"].upper()
            vol = item.get("quote_volume", 0.0)
            chg = item.get("change_pct", 0.0)
            price = item.get("price", 0.0)

            # 1.1 Loại trừ coin đã có trong Watchlist, nằm trong blacklist, hoặc không phải Futures Perpetual
            if coin in current_watchlist or coin in self.blacklist or coin not in valid_futures:
                continue

            # 1.2 Điều kiện lọc thanh khoản tối thiểu $30,000,000 USDT (Coin thanh khoản lớn, chống thao túng)
            if vol < 30_000_000:
                continue

            # 1.3 Điều kiện biên độ giá 24h: từ -6.0% đến +14.0%
            # (Tránh xa các coin đang rơi tự do < -6% hoặc các coin đã bơm kiệt sức > +14%)
            if chg < -6.0 or chg > 14.0:
                continue

            # 1.4 Kiểm tra Cooldown từ Trí nhớ AI
            is_cooling, rem_sec, _ = self.memory_manager.is_coin_in_cooldown(coin)
            if is_cooling:
                continue

            # 1.5 Tính điểm tiềm năng của Scout (Scout Potential Score: 0 - 100)
            score = 50.0 # Mức cơ sở

            # Điểm thanh khoản: $30M -> $150M+
            if vol >= 150_000_000:
                score += 25.0
            elif vol >= 80_000_000:
                score += 18.0
            elif vol >= 50_000_000:
                score += 12.0
            else:
                score += 5.0

            # Điểm nhịp đà: Ưu tiên tăng trưởng nhẹ nhàng +1.5% đến +7.0% (sóng bền, không FOMO)
            if 1.5 <= chg <= 7.0:
                score += 15.0
            elif -2.0 <= chg < 1.5:
                score += 8.0 # Tích lũy đẹp
            else:
                score -= 5.0

            candidates_scored.append({
                "coin": coin,
                "symbol": item["symbol"],
                "price": price,
                "change_pct": chg,
                "quote_volume": vol,
                "volume_formatted": item.get("volume_formatted", f"${vol/1e6:.1f}M"),
                "scout_score": round(score, 1)
            })

        candidates_scored.sort(key=lambda x: x["scout_score"], reverse=True)
        top_candidates = candidates_scored[:4]

        if not top_candidates:
            msg = "Thị trường hiện tại không có coin nào đạt chuẩn thanh khoản ($30M+) và biên độ an toàn để bổ sung."
            self.portfolio.log_thought("Scout", "INFO", msg)
            report = {
                "status": "no_candidates",
                "timestamp": timestamp_str,
                "message": msg,
                "scout_count": 0,
                "audited_candidates": []
            }
            self.latest_report = report
            return report

        self.portfolio.log_thought(
            "Scout",
            "SUCCESS",
            f"🎯 [Alpha Scout Đề Cử] Đã tìm ra Top {len(top_candidates)} ứng viên tiềm năng: " +
            ", ".join([f"{c['coin']} (Vol: {c['volume_formatted']}, 24h: {c['change_pct']:+,.1f}%, Điểm: {c['scout_score']})" for c in top_candidates]) +
            ". Chuyển giao sang Quan Tòa Phản Biện thẩm định khắt khe..."
        )

        # ---------------------------------------------------------------------
        # BƯỚC 2: GATEKEEPER / DEVIL'S ADVOCATE - PHẢN BIỆN & VẠCH LÁ TÌM SÂU
        # ---------------------------------------------------------------------
        audited_results = []
        approved_candidate = None

        for cand in top_candidates:
            coin = cand["coin"]
            audit_score = 80.0 # Khởi điểm thẩm định
            objections = []
            strengths = []

            # 2.1 Thu thập dữ liệu nến 15M và 1H để soi cấu trúc kỹ thuật
            klines = self.crypto_service.fetch_multi_timeframe_klines(coin)
            c1h = [c["close"] for c in klines.get("klines_1h", [])]
            c15m = [c["close"] for c in klines.get("klines_15m", [])]

            # Kiểm tra Spread thực tế
            ticker = self.crypto_service.fetch_coin_ticker(coin)
            spread_bps = ticker.get("spread_bps", 5.0) if ticker else 5.0

            # --- VẠCH LÁ TÌM SÂU ---
            # Soi 1: Trượt giá & Spread
            if spread_bps > 4.0:
                audit_score -= 20.0
                objections.append(f"Chênh lệch Spread lớn ({spread_bps:.1f} bps), nguy cơ trượt giá khi khớp")
            else:
                strengths.append(f"Spread siêu hẹp ({spread_bps:.1f} bps)")

            # Soi 2: Bẫy Đu Đỉnh / Quá Mua RSI
            if len(c1h) >= 15:
                from .quant_indicators import calculate_rsi, calculate_ema
                rsi_1h = calculate_rsi(c1h, 14)
                if rsi_1h > 72.0:
                    audit_score -= 35.0
                    objections.append(f"RSI 1H quá mua ({rsi_1h:.1f}), rủi ro đu đỉnh râu nến xả hàng")
                elif rsi_1h < 30.0:
                    audit_score -= 15.0
                    objections.append(f"RSI 1H quá bán ({rsi_1h:.1f}), xu hướng giảm đang đè nặng")
                else:
                    strengths.append(f"RSI 1H lành mạnh ({rsi_1h:.1f})")

                # Soi 3: Xu hướng Macro 1H (EMA20 vs EMA50)
                ema20_1h = calculate_ema(c1h, 20)[-1]
                ema50_1h = calculate_ema(c1h, 50)[-1] if len(c1h) >= 50 else ema20_1h
                curr_p = c1h[-1]
                if curr_p > ema20_1h and ema20_1h >= ema50_1h:
                    audit_score += 15.0
                    strengths.append("Xu hướng 1H là UPTREND vững chắc (Giá > EMA20 > EMA50)")
                elif curr_p < ema20_1h and ema20_1h <= ema50_1h:
                    audit_score -= 25.0
                    objections.append("Khung 1H đang là DOWNTREND (Giá < EMA20 < EMA50)")

                # Soi 4: Giãn cản quá đà
                if curr_p > ema20_1h * 1.04:
                    audit_score -= 20.0
                    objections.append("Giá đang giãn hơn 4% so với đường EMA20 1H, dễ có nhịp chỉnh rũ hàng")

            # Soi 5: Lịch sử Trí Nhớ AI
            track = self.memory_manager.get_symbol_track_record(coin)
            if track.get("loss_streak", 0) >= 1:
                audit_score -= 25.0
                objections.append(f"Quá khứ từng dính chuỗi thua {track.get('loss_streak')} lệnh")
            elif track.get("total", 0) >= 2 and track.get("win_rate", 0) >= 60.0:
                audit_score += 10.0
                strengths.append(f"Lịch sử giao dịch uy tín (Tỷ lệ thắng {track.get('win_rate')}%)")

            audit_score = max(0.0, min(100.0, audit_score))
            is_approved = (audit_score >= 75.0)

            cand_audit = {
                "coin": coin,
                "price": cand["price"],
                "change_pct": cand["change_pct"],
                "quote_volume": cand["quote_volume"],
                "volume_formatted": cand["volume_formatted"],
                "scout_score": cand["scout_score"],
                "audit_score": round(audit_score, 1),
                "is_approved": is_approved,
                "strengths": strengths,
                "objections": objections,
                "verdict": "PHÊ DUYỆT" if is_approved else "BÁC BỎ"
            }
            audited_results.append(cand_audit)

            # Chọn ứng viên xuất sắc nhất vượt qua bài kiểm tra thẩm định
            if is_approved and (approved_candidate is None or audit_score > approved_candidate["audit_score"]):
                approved_candidate = cand_audit

        # ---------------------------------------------------------------------
        # BƯỚC 3: QUY TẮC GIỚI HẠN CỨNG 5 COIN & CƠ CHẾ 1 VÀO - 1 RA
        # ---------------------------------------------------------------------
        relegation_action = None

        if approved_candidate:
            app_coin = approved_candidate["coin"]
            current_coins = list(self.crypto_service.watchlist)

            self.portfolio.log_thought(
                "Gatekeeper",
                "SUCCESS",
                f"⚖️ [Quan Tòa Phản Biện] PHÊ DUYỆT {app_coin} (Đạt {approved_candidate['audit_score']}/100 điểm)! Điểm mạnh: {'; '.join(approved_candidate['strengths'][:2])}."
            )

            if not auto_modify:
                relegation_action = {
                    "action": "RECOMMENDED_ONLY",
                    "promoted_coin": app_coin,
                    "demoted_coin": None,
                    "message": f"Hội Đồng AI đề xuất {app_coin} (Đạt {approved_candidate['audit_score']}đ). Watchlist được bảo toàn cố định theo cấu hình Sniper an toàn."
                }
                self.portfolio.log_thought(
                    "Gatekeeper",
                    "INFO",
                    f"💡 [ĐỀ XUẤT ỨNG VIÊN] {app_coin} đạt chuẩn ({approved_candidate['audit_score']}đ). Watchlist được bảo toàn cố định theo chỉ đạo của người dùng."
                )
            # Trường hợp A: Watchlist chưa đầy (< 5 coin) và có auto_modify=True
            elif len(current_coins) < self.max_watchlist_size:
                res = self.crypto_service.add_coin(app_coin)
                if res.get("success"):
                    if self.spawner:
                        self.spawner.sync_with_watchlist()
                    relegation_action = {
                        "action": "PROMOTED_NEW",
                        "promoted_coin": app_coin,
                        "demoted_coin": None,
                        "message": f"Đã kết nạp {app_coin} vào Watchlist ({len(current_coins)+1}/{self.max_watchlist_size} coin)."
                    }
                    self.portfolio.log_thought(
                        "Risk Guard",
                        "SUCCESS",
                        f"🎉 [KẾT NẠP COIN MỚI] Đã thêm {app_coin} vào danh sách theo dõi. Watchlist hiện tại: {len(current_coins)+1}/{self.max_watchlist_size} coin."
                    )

            # Trường hợp B: Watchlist đã đạt kịch trần (>= 5 coin) và có auto_modify=True
            else:
                open_positions = self.portfolio.state.get("open_positions", {})
                occupied_coins = {
                    pos.get("symbol", "").upper()
                    for pos in open_positions.values()
                    if pos.get("symbol")
                }

                # Tìm các coin có thể bị loại (Không phải coin trụ và Không có lệnh mở)
                replaceable_coins = [
                    c for c in current_coins
                    if c.upper() not in self.anchor_coins and c.upper() not in occupied_coins
                ]

                if not replaceable_coins:
                    self.portfolio.log_thought(
                        "Risk Guard",
                        "INFO",
                        f"Tất cả {len(current_coins)} coin trong Watchlist đều là Coin Trụ hoặc đang có vị thế mở. Tạm hoãn kết nạp {app_coin} để bảo vệ an toàn danh mục."
                    )
                    relegation_action = {
                        "action": "HELD",
                        "promoted_coin": app_coin,
                        "demoted_coin": None,
                        "message": "Danh mục đã đầy 5 coin và tất cả đều đang có vị thế mở."
                    }
                else:
                    # Chấm điểm để tìm coin yếu nhất cần loại bỏ:
                    # Ưu tiên loại coin có: chuỗi thua, hoặc đang trong Cooldown, hoặc winrate thấp nhất
                    weakest_coin = None
                    lowest_score = 999.0

                    for rc in replaceable_coins:
                        rc_track = self.memory_manager.get_symbol_track_record(rc)
                        is_cool, _, _ = self.memory_manager.is_coin_in_cooldown(rc)
                        c_score = rc_track.get("win_rate", 50.0)
                        if is_cool:
                            c_score -= 40.0 # Bị phạt nặng nếu đang nghỉ Cooldown
                        if rc_track.get("loss_streak", 0) >= 1:
                            c_score -= 20.0 * rc_track.get("loss_streak", 1)
                        if c_score < lowest_score:
                            lowest_score = c_score
                            weakest_coin = rc

                    if weakest_coin:
                        # Thực hiện Hoán Đổi: Bỏ weakest_coin, thêm app_coin
                        self.crypto_service.remove_coin(weakest_coin)
                        self.crypto_service.add_coin(app_coin)
                        if self.spawner:
                            self.spawner.sync_with_watchlist()

                        relegation_action = {
                            "action": "SWAPPED",
                            "promoted_coin": app_coin,
                            "demoted_coin": weakest_coin,
                            "message": f"Thăng hạng {app_coin} ({approved_candidate['audit_score']}đ) | Hạ bệ {weakest_coin} để giữ chuẩn 5 coin."
                        }
                        self.portfolio.log_thought(
                            "Risk Guard",
                            "SUCCESS",
                            f"🔄 [CƠ CHẾ 1 VÀO - 1 RA] Thăng hạng {app_coin} (Điểm {approved_candidate['audit_score']}/100) | "
                            f"Hạ bệ {weakest_coin} (Không có vị thế, hiệu suất thấp) để bảo toàn tuyệt đối giới hạn {self.max_watchlist_size} coin!"
                        )
        else:
            self.portfolio.log_thought(
                "Gatekeeper",
                "INFO",
                f"⚖️ [Quan Tòa Phản Biện] Cả {len(top_candidates)} ứng viên đề cử đều KHÔNG vượt qua ngưỡng thẩm định an toàn (>= 75 điểm). Giữ nguyên danh mục hiện tại."
            )

        report = {
            "status": "success",
            "timestamp": timestamp_str,
            "max_watchlist_size": self.max_watchlist_size,
            "current_watchlist": list(self.crypto_service.watchlist),
            "approved_candidate": approved_candidate,
            "relegation_action": relegation_action,
            "audited_candidates": audited_results
        }
        self.latest_report = report
        return report

    def get_latest_report(self) -> Dict[str, Any]:
        """Trả về kết quả lần họp hội đồng gần nhất."""
        if self.latest_report:
            return self.latest_report
        return {
            "status": "idle",
            "message": "Chưa có phiên quét thẩm định nào được thực hiện.",
            "current_watchlist": list(self.crypto_service.watchlist),
            "max_watchlist_size": self.max_watchlist_size
        }
