import math
from typing import Dict, Any, Optional
from ..config import (
    DEFAULT_LEVERAGE, 
    MAX_LEVERAGE,
    DEFAULT_SL_PERCENT, 
    DEFAULT_TP_PERCENT, 
    MAINTENANCE_MARGIN_BUFFER
)
from .quant_indicators import analyze_quant_structure

class TradePlanValidator:
    def __init__(self, crypto_service, portfolio):
        self.crypto_service = crypto_service
        self.portfolio = portfolio

    def validate_plan(
        self,
        coin: str,
        side: str = "AUTO",
        timeframe: str = "1m",
        leverage: int = DEFAULT_LEVERAGE,
        stake_amount: float = 50.0,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        no_sl_confirmed: bool = False
    ) -> Dict[str, Any]:
        """
        Validates a proposed trade plan with comprehensive Risk Committee checks:
        - Liquidity depth & orderbook pressure
        - Wick sweep risk / Volatility buffer for Stop-Loss
        - Risk-to-Reward (R:R) ratio for Take-Profit
        - Liquidation price safety buffer
        - Leverage vs Timeframe compatibility
        """
        clean_coin = coin.upper().replace("USDT", "").strip()
        ticker = self.crypto_service.fetch_coin_ticker(clean_coin, force_refresh=True)
        if not ticker:
            return {
                "verdict": "REJECTED",
                "title": "Không tìm thấy dữ liệu thị trường",
                "analysis": f"Không thể lấy dữ liệu giá thực tế từ sàn Binance cho cặp {clean_coin}/USDT.",
                "metrics": {},
                "suggested_params": {}
            }

        depth = self.crypto_service.fetch_coin_depth(clean_coin)
        ratio = depth.get("ratio", 1.0)

        # Fetch real candles for Quant Trend & VSA validation (Supports 1m, 3m, 5m scalping up to 1d)
        tf_map = {
            "1M": "1m", "3M": "3m", "5M": "5m", "15M": "15m",
            "1H": "1h", "4H": "4h", "1D": "1d",
            "SCALP": "1m", "DAY": "1h", "SWING": "4h"
        }
        klines_tf = tf_map.get(timeframe.upper(), timeframe.lower() if timeframe.lower() in ["1m", "3m", "5m", "15m", "1h", "4h", "1d"] else "1m")
        klines = self.crypto_service.fetch_klines(clean_coin, interval=klines_tf, limit=60)
        candles = klines.get("candles", []) if isinstance(klines, dict) and "candles" in klines else []

        # Tích hợp Dữ liệu Nến Đa Khung Thời Gian (1H Macro + 15M Cấu trúc + 1M Trigger)
        mtf_data = self.crypto_service.fetch_multi_timeframe_klines(clean_coin)
        quant_res = analyze_quant_structure(candles, orderbook_ratio=ratio, mtf_data=mtf_data, use_patterns=True)
        curr_price = candles[-1]["close"] if (candles and len(candles) > 0 and candles[-1].get("close")) else ticker["price"]

        # Nhận diện Phiên Giao Dịch Thế Giới (Giờ Việt Nam)
        from .session_manager import get_current_session
        curr_session = get_current_session()

        # 1. Determine or validate Direction (Side)
        if side == "AUTO" or not side:
            chosen_side = quant_res["chosen_side"] if quant_res["chosen_side"] != "HOLD" else "LONG"
        else:
            chosen_side = side.upper()

        leverage = max(1, min(MAX_LEVERAGE, leverage))
        margin = max(0.5, stake_amount)
        position_size = margin * leverage

        # 2. Calculate Liquidation Price
        if chosen_side == "SHORT":
            liq_price = round(curr_price * (1.0 + (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), 6 if curr_price < 1 else 4)
        else:
            liq_price = round(curr_price * (1.0 - (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), 6 if curr_price < 1 else 4)

        # 3. Minimum safe distance for Stop-Loss depending on Timeframe
        min_sl_pct_map = {
            "1M": 0.003, # 0.3% minimum distance for 1m ultra-fast scalp
            "3M": 0.004,
            "5M": 0.005, # 0.5% distance for 5m scalp
            "15M": 0.008,
            "1H": 0.015,
            "4H": 0.030,
            "1D": 0.050,
            "SCALP": 0.004,
            "DAY": 0.015,
            "SWING": 0.030
        }
        min_sl_pct = min_sl_pct_map.get(timeframe.upper(), 0.005)
        safe_sl_pct = max(min_sl_pct * 1.5, DEFAULT_SL_PERCENT)

        # Suggested default SL/TP if needed
        if chosen_side == "SHORT":
            suggested_sl = round(curr_price * (1.0 + safe_sl_pct), 6 if curr_price < 1 else 4)
            suggested_tp = round(curr_price * (1.0 - safe_sl_pct * 2.0), 6 if curr_price < 1 else 4)
        else:
            suggested_sl = round(curr_price * (1.0 - safe_sl_pct), 6 if curr_price < 1 else 4)
            suggested_tp = round(curr_price * (1.0 + safe_sl_pct * 2.0), 6 if curr_price < 1 else 4)

        has_sl = (stop_loss is not None and stop_loss > 0)
        has_tp = (take_profit is not None and take_profit > 0)

        # ----------------- RISK EVALUATION CHECKS -----------------
        # Check CB: Cầu Chì An Toàn Ngày (Daily Circuit Breaker)
        summary = self.portfolio.get_summary()
        daily = summary.get("daily_metrics", {})
        if daily.get("circuit_breaker_active", False):
            return {
                "verdict": "REJECTED",
                "title": "🚨 CẦU CHÌ AN TOÀN NGÀY ĐANG NGẮT",
                "analysis": (
                    f"Thua lỗ trong ngày hôm nay đã chạm giới hạn tối đa (-{daily.get('max_drawdown_pct', 8.0)}%). "
                    f"Cầu chì an toàn tự động ngắt mở vị thế mới để bảo toàn vốn tích lũy. "
                    f"Hệ thống sẽ tự động mở lại vào 07:00 sáng mai (giờ Việt Nam / 00:00 UTC)!"
                ),
                "metrics": {
                    "entry_price": curr_price,
                    "liq_price": liq_price,
                    "daily_pnl": daily.get("daily_pnl", 0.0),
                    "daily_roi": daily.get("daily_roi_percent", 0.0)
                },
                "suggested_params": {"stop_loss": suggested_sl, "take_profit": suggested_tp}
            }

        # Check PL: Luật Khóa Lợi Nhuận Bảo Vệ Thành Quả Ngày
        if daily.get("profit_lock_active", False):
            return {
                "verdict": "REJECTED",
                "title": "🔒 LUẬT KHÓA LỢI NHUẬN NGÀY ĐANG BẬT",
                "analysis": (
                    f"Mục tiêu lợi nhuận ngày hôm nay (+{daily.get('target_profit_pct', 20.0)}%) đã hoàn thành xuất sắc! "
                    f"Hệ thống tự động kích hoạt Luật Khóa Lợi Nhuận để bảo vệ 100% tiền lãi vào két và chặn toàn bộ lệnh mở mới đến 07:00 sáng mai."
                ),
                "metrics": {
                    "entry_price": curr_price,
                    "liq_price": liq_price,
                    "daily_pnl": daily.get("daily_pnl", 0.0),
                    "daily_roi": daily.get("daily_roi_percent", 0.0)
                },
                "suggested_params": {"stop_loss": suggested_sl, "take_profit": suggested_tp}
            }

        smc = quant_res.get("smc", {})
        pat = quant_res.get("candlestick_pattern", {})
        mtf = quant_res.get("multi_timeframe", {})

        # Check 0: Counter-Trend Warning (Đánh ngược xu hướng kỹ thuật)
        if chosen_side == "LONG" and quant_res["trend"] in ["BEARISH", "BEARISH_PULLBACK"]:
            # Ngoại lệ hợp lệ: Có tín hiệu SMC Bullish Sweep hoặc nến Pinbar rút chân đáy (Hammer / Tweezer)
            has_pinbar_reversal = pat.get("detected") and pat.get("signal") == "BULLISH" and ("PINBAR" in pat.get("pattern", "") or "TWEEZER" in pat.get("pattern", "") or "ENGULFING" in pat.get("pattern", ""))
            if smc.get("pattern") == "BULLISH_SWEEP" or has_pinbar_reversal:
                # Chấp thuận như một cú Scalp Reversal bắt đáy có bảo hiểm Price Action / SMC
                pass
            else:
                return {
                    "verdict": "SUGGEST_ADJUSTMENT",
                    "title": "CẢNH BÁO RỦI RO: ĐÁNH NGƯỢC XU HƯỚNG GIẢM",
                    "analysis": (
                        f"Bạn đang chọn LONG (đánh lên) trong khi {clean_coin} đang nằm trong "
                        f"XU HƯỚNG GIẢM RÕ RỆT (Giá ${curr_price:,.4f} < EMA20 ${quant_res['ema20']:,.4f} < EMA50 ${quant_res['ema50']:,.4f}). "
                        f"VSA cảnh báo: {quant_res['vsa']['description']}. "
                        f"Bắt đáy ngược xu hướng khi chưa có nến Pin Bar rút râu xác nhận có tỷ lệ thua lỗ cao. Đề xuất chuyển hướng sang SHORT hoặc hạ đòn bẩy xuống mức tối thiểu (1x-2x)."
                    ),
                    "metrics": {
                        "entry_price": curr_price,
                        "liq_price": liq_price,
                        "trend": quant_res["trend_desc"],
                        "rsi": quant_res["rsi"],
                        "vsa": quant_res["vsa"]["pattern"],
                        "smc": smc.get("pattern", "NONE"),
                        "candlestick": pat.get("pattern", "NONE"),
                        "mtf": mtf.get("description", "N/A")
                    },
                    "suggested_params": {
                        "side": "SHORT",
                        "leverage": min(leverage, 2),
                        "stop_loss": suggested_sl,
                        "take_profit": suggested_tp
                    }
                }

        if chosen_side == "SHORT" and quant_res["trend"] in ["BULLISH", "BULLISH_RECOVERY"]:
            # Ngoại lệ hợp lệ: Có tín hiệu SMC Bearish Sweep hoặc nến Pinbar bắn sao (Shooting Star / Tweezer)
            has_pinbar_reversal = pat.get("detected") and pat.get("signal") == "BEARISH" and ("PINBAR" in pat.get("pattern", "") or "TWEEZER" in pat.get("pattern", "") or "ENGULFING" in pat.get("pattern", ""))
            if smc.get("pattern") == "BEARISH_SWEEP" or has_pinbar_reversal:
                pass
            else:
                return {
                    "verdict": "SUGGEST_ADJUSTMENT",
                    "title": "CẢNH BÁO RỦI RO: ĐÁNH NGƯỢC XU HƯỚNG TĂNG",
                    "analysis": (
                        f"Bạn đang chọn SHORT (bán khống) trong khi {clean_coin} đang nằm trong "
                        f"XU HƯỚNG TĂNG RÕ RỆT (Giá ${curr_price:,.4f} > EMA20 ${quant_res['ema20']:,.4f} > EMA50 ${quant_res['ema50']:,.4f}). "
                        f"VSA cảnh báo: {quant_res['vsa']['description']}. "
                        f"Chặn đầu xe lửa trong Uptrend khi chưa có nến Shooting Star rút râu rất dễ bị ép giá thanh lý. Đề xuất đổi sang LONG theo xu hướng chính."
                    ),
                    "metrics": {
                        "entry_price": curr_price,
                        "liq_price": liq_price,
                        "trend": quant_res["trend_desc"],
                        "rsi": quant_res["rsi"],
                        "vsa": quant_res["vsa"]["pattern"],
                        "smc": smc.get("pattern", "NONE"),
                        "candlestick": pat.get("pattern", "NONE"),
                        "mtf": mtf.get("description", "N/A")
                    },
                    "suggested_params": {
                        "side": "LONG",
                        "leverage": min(leverage, 2),
                        "stop_loss": suggested_sl,
                        "take_profit": suggested_tp
                    }
                }

        # Check A: No Stop-Loss provided
        if not has_sl:
            if not no_sl_confirmed:
                return {
                    "verdict": "REJECTED",
                    "title": "BẮT BUỘC CÓ CẮT LỖ HOẶC XÁC NHẬN TẤT TAY",
                    "analysis": (
                        f"Kế hoạch của bạn đang để trống mức Cắt Lỗ (Stop-Loss). "
                        f"Với đòn bẩy {leverage}x, nếu giá đi ngược chạm ${liq_price:,.4f}, bạn sẽ bị THANH LÝ MẤT TRẮNG toàn bộ ${margin:.2f} ký quỹ! "
                        f"Vui lòng đặt một mức Cắt Lỗ an toàn hoặc đánh dấu vào ô xác nhận 'Chấp nhận rủi ro tất tay'."
                    ),
                    "metrics": {
                        "entry_price": curr_price,
                        "liq_price": liq_price,
                        "risk_dollars": margin,
                        "reward_dollars": 0,
                        "rr_ratio": 0.0
                    },
                    "suggested_params": {
                        "side": chosen_side,
                        "leverage": min(3, leverage),
                        "stop_loss": suggested_sl,
                        "take_profit": suggested_tp
                    }
                }

        # Check B: Stop-Loss placed on the wrong side
        if has_sl:
            if chosen_side == "LONG" and stop_loss >= curr_price:
                return {
                    "verdict": "REJECTED",
                    "title": "MỨC CẮT LỖ KHÔNG HỢP LỆ",
                    "analysis": f"Với lệnh LONG (đánh lên), giá Cắt Lỗ (${stop_loss:,.4f}) bắt buộc phải THẤP HƠN giá vào lệnh (${curr_price:,.4f}).",
                    "metrics": {"entry_price": curr_price, "liq_price": liq_price},
                    "suggested_params": {"stop_loss": suggested_sl, "take_profit": suggested_tp}
                }
            if chosen_side == "SHORT" and stop_loss <= curr_price:
                return {
                    "verdict": "REJECTED",
                    "title": "MỨC CẮT LỖ KHÔNG HỢP LỆ",
                    "analysis": f"Với lệnh SHORT (bán khống), giá Cắt Lỗ (${stop_loss:,.4f}) bắt buộc phải CAO HƠN giá vào lệnh (${curr_price:,.4f}).",
                    "metrics": {"entry_price": curr_price, "liq_price": liq_price},
                    "suggested_params": {"stop_loss": suggested_sl, "take_profit": suggested_tp}
                }

            # Check B2: Stop-Loss placed beyond Liquidation Price (Guaranteed liquidation before SL!)
            if chosen_side == "LONG" and stop_loss <= liq_price:
                return {
                    "verdict": "REJECTED",
                    "title": "CẮT LỖ NẰM DƯỚI GIÁ THANH LÝ",
                    "analysis": (
                        f"Với đòn bẩy {leverage}x, vị thế LONG sẽ bị THANH LÝ tại ${liq_price:,.4f}! "
                        f"Mức Cắt Lỗ (${stop_loss:,.4f}) nằm sâu hơn giá thanh lý, khiến tài khoản bị cháy sạch tiền ký quỹ trước khi lệnh cắt lỗ kịp chạm tới. "
                        f"Vui lòng nâng mức Cắt Lỗ lên trên ${liq_price:,.4f} (đề xuất an toàn: ${suggested_sl:,.4f})."
                    ),
                    "metrics": {"entry_price": curr_price, "liq_price": liq_price},
                    "suggested_params": {"stop_loss": suggested_sl, "take_profit": suggested_tp}
                }
            if chosen_side == "SHORT" and stop_loss >= liq_price:
                return {
                    "verdict": "REJECTED",
                    "title": "CẮT LỖ NẰM TRÊN GIÁ THANH LÝ",
                    "analysis": (
                        f"Với đòn bẩy {leverage}x, vị thế SHORT sẽ bị THANH LÝ tại ${liq_price:,.4f}! "
                        f"Mức Cắt Lỗ (${stop_loss:,.4f}) nằm cao hơn giá thanh lý, khiến tài khoản bị cháy sạch tiền ký quỹ trước khi lệnh cắt lỗ kịp chạm tới. "
                        f"Vui lòng hạ mức Cắt Lỗ xuống dưới ${liq_price:,.4f} (đề xuất an toàn: ${suggested_sl:,.4f})."
                    ),
                    "metrics": {"entry_price": curr_price, "liq_price": liq_price},
                    "suggested_params": {"stop_loss": suggested_sl, "take_profit": suggested_tp}
                }

        # Check C: Wick Sweep / Volatility Noise risk (SL too tight)
        if has_sl:
            sl_distance_pct = abs(curr_price - stop_loss) / curr_price
            if sl_distance_pct < min_sl_pct:
                return {
                    "verdict": "SUGGEST_ADJUSTMENT",
                    "title": "CẢNH BÁO: CẮT LỖ QUÁ GẦN (DỄ BỊ QUÉT RÂU NẾN)",
                    "analysis": (
                        f"Điểm Cắt Lỗ (${stop_loss:,.4f}) chỉ cách giá hiện tại {sl_distance_pct*100:.2f}%. "
                        f"Trong khung thời gian {timeframe}, độ giật tự nhiên của sổ lệnh và nến {clean_coin} thường biến động từ {min_sl_pct*100:.1f}% trở lên. "
                        f"Nếu giữ mức này, cá mập chỉ cần 'quét râu' nhẹ là bạn bị đá văng khỏi vị thế trước khi giá kịp chạy đúng xu hướng! "
                        f"Đề xuất nới rộng Cắt Lỗ ra ngoài vùng nhiễu giá (khoảng ${suggested_sl:,.4f})."
                    ),
                    "metrics": {
                        "entry_price": curr_price,
                        "liq_price": liq_price,
                        "sl_distance_pct": round(sl_distance_pct * 100, 2),
                        "safe_min_distance_pct": round(min_sl_pct * 100, 2)
                    },
                    "suggested_params": {
                        "side": chosen_side,
                        "leverage": leverage,
                        "stop_loss": suggested_sl,
                        "take_profit": suggested_tp if has_tp else suggested_tp
                    }
                }

        # Check D: Take-Profit & Risk-to-Reward (R:R) ratio
        rr_ratio = 0.0
        risk_dollars = margin
        reward_dollars = 0.0

        if has_sl:
            loss_per_coin = abs(curr_price - stop_loss)
            shares = position_size / curr_price
            risk_dollars = min(margin, round(loss_per_coin * shares, 2))

        if has_tp:
            if chosen_side == "LONG" and take_profit <= curr_price:
                return {
                    "verdict": "REJECTED",
                    "title": "MỨC CHỐT LỜI KHÔNG HỢP LỆ",
                    "analysis": f"Với lệnh LONG, giá Chốt Lời (${take_profit:,.4f}) phải CAO HƠN giá vào lệnh (${curr_price:,.4f}).",
                    "metrics": {"entry_price": curr_price, "liq_price": liq_price},
                    "suggested_params": {"take_profit": suggested_tp}
                }
            if chosen_side == "SHORT" and take_profit >= curr_price:
                return {
                    "verdict": "REJECTED",
                    "title": "MỨC CHỐT LỜI KHÔNG HỢP LỆ",
                    "analysis": f"Với lệnh SHORT, giá Chốt Lời (${take_profit:,.4f}) phải THẤP HƠN giá vào lệnh (${curr_price:,.4f}).",
                    "metrics": {"entry_price": curr_price, "liq_price": liq_price},
                    "suggested_params": {"take_profit": suggested_tp}
                }

            profit_per_coin = abs(take_profit - curr_price)
            shares = position_size / curr_price
            reward_dollars = round(profit_per_coin * shares, 2)
            rr_ratio = round(reward_dollars / risk_dollars, 2) if risk_dollars > 0 else 0.0

            if rr_ratio < 1.0:
                return {
                    "verdict": "SUGGEST_ADJUSTMENT",
                    "title": "TỶ LỆ LỜI / LỖ (R:R) BẤT LỢI",
                    "analysis": (
                        f"Tỷ lệ R:R hiện tại là 1:{rr_ratio:.2f} (Mạo hiểm ${risk_dollars:.2f} để chỉ kiếm về ${reward_dollars:.2f}). "
                        f"Trong đầu tư định lượng, một kèo có kỳ vọng lời thấp hơn rủi ro là kèo 'âm kỳ vọng' (-EV). "
                        f"Đề xuất nâng mức Chốt Lời lên tối thiểu ${suggested_tp:,.4f} để đạt tỷ lệ R:R chuẩn 1:2.0."
                    ),
                    "metrics": {
                        "entry_price": curr_price,
                        "liq_price": liq_price,
                        "risk_dollars": risk_dollars,
                        "reward_dollars": reward_dollars,
                        "rr_ratio": rr_ratio
                    },
                    "suggested_params": {
                        "side": chosen_side,
                        "leverage": leverage,
                        "stop_loss": stop_loss if has_sl else suggested_sl,
                        "take_profit": suggested_tp
                    }
                }

        # Check E: Leverage vs Timeframe compatibility
        if timeframe.upper() in ["SWING", "4H", "1D"] and leverage > 5:
            return {
                "verdict": "SUGGEST_ADJUSTMENT",
                "title": "ĐÒN BẨY QUÁ CAO CHO KHUNG SWING DÀI HẠN",
                "analysis": (
                    f"Giao dịch dài hạn (Swing 4h-1d) với đòn bẩy {leverage}x rất nguy hiểm do biến động giá qua đêm "
                    f"và chi phí phí duy trì Funding Rate. Đề xuất hạ đòn bẩy xuống 2x hoặc 3x (hoặc chuyển sang khung 1m-5m Scalp nếu muốn đánh đòn bẩy lớn)."
                ),
                "metrics": {
                    "entry_price": curr_price,
                    "liq_price": liq_price,
                    "risk_dollars": risk_dollars,
                    "reward_dollars": reward_dollars,
                    "rr_ratio": rr_ratio
                },
                "suggested_params": {
                    "side": chosen_side,
                    "leverage": 3,
                    "stop_loss": stop_loss if has_sl else suggested_sl,
                    "take_profit": take_profit if has_tp else suggested_tp
                }
            }

        # ----------------- APPROVED PLAN -----------------
        summary_msg = (
            f"Kế hoạch {chosen_side} {leverage}x trên {clean_coin}/USDT đã được Hội đồng Thẩm định AI thông qua! "
            f"Hàng rào Cắt Lỗ (${stop_loss:,.4f} nếu có) nằm ngoài vùng nhiễu động giá, "
            f"Giá Thanh Lý an toàn ở mức ${liq_price:,.4f}"
        )
        if has_tp:
            summary_msg += f", Tỷ lệ R:R tối ưu đạt 1:{rr_ratio:.2f} (Rủi ro: ${risk_dollars:.2f} / Kỳ vọng lời: ${reward_dollars:.2f})."
        if pat.get("detected"):
            summary_msg += f" [Price Action: {pat.get('description')}]."
        if mtf.get("is_confluent"):
            summary_msg += f" [Hợp Lưu Đa Khung: {mtf.get('description')}]."
        if smc.get("detected"):
            summary_msg += f" [SMC Tín hiệu: {smc.get('description')}]."
        summary_msg += f" [{curr_session.get('badge', 'Phiên')}: {curr_session.get('time_range', '')}]."

        return {
            "verdict": "APPROVED",
            "title": "KẾ HOẠCH ĐƯỢC CHẤP THUẬN (APPROVED)",
            "analysis": summary_msg,
            "metrics": {
                "entry_price": curr_price,
                "liq_price": liq_price,
                "risk_dollars": risk_dollars,
                "reward_dollars": reward_dollars,
                "rr_ratio": rr_ratio,
                "orderbook_ratio": round(ratio, 2),
                "momentum_24h": ticker["change_24h"],
                "smc": smc.get("pattern", "NONE"),
                "candlestick": pat.get("pattern", "NONE"),
                "candlestick_desc": pat.get("description", ""),
                "multi_timeframe": mtf.get("description", "Đơn khung"),
                "session": curr_session.get("name", ""),
                "session_badge": curr_session.get("badge", ""),
                "session_risk_mode": curr_session.get("risk_mode", "")
            },
            "suggested_params": {
                "side": chosen_side,
                "leverage": leverage,
                "stop_loss": stop_loss if has_sl else None,
                "take_profit": take_profit if has_tp else None
            }
        }
