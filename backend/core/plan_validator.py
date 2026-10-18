import math
from typing import Dict, Any, Optional
from ..config import (
    DEFAULT_LEVERAGE, 
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
        timeframe: str = "SCALP",
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
        ticker = self.crypto_service.fetch_coin_ticker(clean_coin)
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
        curr_price = ticker["price"]

        # Fetch real candles for Quant Trend & VSA validation
        tf_map = {"SCALP": "15m", "DAY": "1h", "SWING": "4h"}
        klines_tf = tf_map.get(timeframe.upper(), "1h")
        klines = self.crypto_service.fetch_klines(clean_coin, interval=klines_tf, limit=60)
        candles = klines.get("candles", []) if isinstance(klines, dict) and "candles" in klines else []
        quant_res = analyze_quant_structure(candles, orderbook_ratio=ratio)

        # 1. Determine or validate Direction (Side)
        if side == "AUTO" or not side:
            chosen_side = quant_res["chosen_side"] if quant_res["chosen_side"] != "HOLD" else "LONG"
        else:
            chosen_side = side.upper()

        leverage = max(1, min(10, leverage))
        margin = max(5.0, stake_amount)
        position_size = margin * leverage

        # 2. Calculate Liquidation Price
        if chosen_side == "SHORT":
            liq_price = round(curr_price * (1.0 + (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), 6 if curr_price < 1 else 4)
        else:
            liq_price = round(curr_price * (1.0 - (1.0 / leverage) * MAINTENANCE_MARGIN_BUFFER), 6 if curr_price < 1 else 4)

        # 3. Minimum safe distance for Stop-Loss depending on Timeframe
        min_sl_pct_map = {
            "SCALP": 0.008, # 0.8% minimum distance to avoid wick sweeps on 1m-5m
            "DAY": 0.015,   # 1.5% distance for 15m-1h
            "SWING": 0.030  # 3.0% distance for 4h-1d
        }
        min_sl_pct = min_sl_pct_map.get(timeframe.upper(), 0.012)
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

        # Check 0: Counter-Trend Warning (Đánh ngược xu hướng kỹ thuật)
        if chosen_side == "LONG" and quant_res["trend"] in ["BEARISH", "BEARISH_PULLBACK"]:
            return {
                "verdict": "SUGGEST_ADJUSTMENT",
                "title": "CẢNH BÁO RỦI RO: ĐÁNH NGƯỢC XU HƯỚNG GIẢM",
                "analysis": (
                    f"Bạn đang chọn LONG (đánh lên) trong khi {clean_coin} đang nằm trong "
                    f"XU HƯỚNG GIẢM RÕ RỆT (Giá ${curr_price:,.4f} < EMA20 ${quant_res['ema20']:,.4f} < EMA50 ${quant_res['ema50']:,.4f}). "
                    f"VSA cảnh báo: {quant_res['vsa']['description']}. "
                    f"Bắt đáy ngược xu hướng có tỷ lệ thua lỗ cao. Đề xuất chuyển hướng sang SHORT hoặc hạ đòn bẩy xuống mức tối thiểu (1x-2x)."
                ),
                "metrics": {
                    "entry_price": curr_price,
                    "liq_price": liq_price,
                    "trend": quant_res["trend_desc"],
                    "rsi": quant_res["rsi"],
                    "vsa": quant_res["vsa"]["pattern"]
                },
                "suggested_params": {
                    "side": "SHORT",
                    "leverage": min(leverage, 2),
                    "stop_loss": suggested_sl,
                    "take_profit": suggested_tp
                }
            }

        if chosen_side == "SHORT" and quant_res["trend"] in ["BULLISH", "BULLISH_RECOVERY"]:
            return {
                "verdict": "SUGGEST_ADJUSTMENT",
                "title": "CẢNH BÁO RỦI RO: ĐÁNH NGƯỢC XU HƯỚNG TĂNG",
                "analysis": (
                    f"Bạn đang chọn SHORT (bán khống) trong khi {clean_coin} đang nằm trong "
                    f"XU HƯỚNG TĂNG RÕ RỆT (Giá ${curr_price:,.4f} > EMA20 ${quant_res['ema20']:,.4f} > EMA50 ${quant_res['ema50']:,.4f}). "
                    f"VSA cảnh báo: {quant_res['vsa']['description']}. "
                    f"Chặn đầu xe lửa trong Uptrend rất dễ bị ép giá thanh lý. Đề xuất đổi sang LONG theo xu hướng chính."
                ),
                "metrics": {
                    "entry_price": curr_price,
                    "liq_price": liq_price,
                    "trend": quant_res["trend_desc"],
                    "rsi": quant_res["rsi"],
                    "vsa": quant_res["vsa"]["pattern"]
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
        if timeframe.upper() == "SWING" and leverage > 3:
            return {
                "verdict": "SUGGEST_ADJUSTMENT",
                "title": "ĐÒN BẨY QUÁ CAO CHO KHUNG SWING DÀI HẠN",
                "analysis": (
                    f"Giao dịch dài hạn (Swing 4h-1d) với đòn bẩy {leverage}x rất nguy hiểm do biến động giá qua đêm "
                    f"và chi phí phí duy trì Funding Rate. Đề xuất hạ đòn bẩy xuống 2x hoặc 3x."
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
                "momentum_24h": ticker["change_24h"]
            },
            "suggested_params": {
                "side": chosen_side,
                "leverage": leverage,
                "stop_loss": stop_loss if has_sl else None,
                "take_profit": take_profit if has_tp else None
            }
        }
