import math
from typing import List, Dict, Any, Optional

def calculate_ema(prices: List[float], period: int) -> List[float]:
    """Calculates Exponential Moving Average (EMA) for a series of prices."""
    if len(prices) < period:
        return [prices[-1]] * len(prices) if prices else []
    
    multiplier = 2.0 / (period + 1)
    ema = [sum(prices[:period]) / period]
    
    for price in prices[period:]:
        new_val = (price - ema[-1]) * multiplier + ema[-1]
        ema.append(new_val)
        
    # Pad beginning so length matches original prices
    padding = [ema[0]] * (period - 1)
    return padding + ema

def calculate_rsi(closes: List[float], period: int = 14) -> float:
    """Calculates Relative Strength Index (RSI) for closing prices."""
    if len(closes) <= period:
        return 50.0
    
    gains = []
    losses = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(diff))
            
    if len(gains) < period:
        return 50.0
        
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 1)

def analyze_vsa_candle(candles: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Performs Volume Spread Analysis (VSA) on the most recent candles:
    - Stopping Volume (Climax absorption at bottom)
    - Absorption Trap (High volume stall at top)
    - Volume Breakout (High volume strong expansion)
    - No Supply (Pullback with dry volume)
    - No Demand (Rally with dry volume)
    """
    if len(candles) < 20:
        return {"pattern": "INSUFFICIENT_DATA", "vol_ratio": 1.0, "description": "Dữ liệu nến chưa đủ 20 phiên"}
    
    recent_volumes = [c.get("volume", c.get("value", 0.0)) for c in candles[-20:]]
    avg_vol_20 = sum(recent_volumes) / len(recent_volumes) if recent_volumes else 1.0
    
    last = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else last
    
    c_open = last["open"]
    c_close = last["close"]
    c_high = last["high"]
    c_low = last["low"]
    c_vol = last.get("volume", last.get("value", 0.0))
    
    vol_ratio = round(c_vol / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0
    candle_range = max(1e-6, c_high - c_low)
    body = abs(c_close - c_open)
    body_pct = body / candle_range
    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low
    is_bull = c_close >= c_open

    # 1. Stopping Volume (Gom hàng đảo chiều đáy)
    if not is_bull and vol_ratio >= 1.8 and (lower_wick / candle_range) >= 0.40:
        return {
            "pattern": "STOPPING_VOLUME",
            "vol_ratio": vol_ratio,
            "signal": "BULLISH_REVERSAL",
            "description": f"Stopping Volume: Cá mập hấp thụ lực bán xả ở đáy (Volume {vol_ratio}x, Rút râu dưới {int(lower_wick/candle_range*100)}%)"
        }

    # 2. Absorption Trap (Bẫy thanh khoản cá mập tại đỉnh)
    if is_bull and vol_ratio >= 1.8 and ((upper_wick / candle_range) >= 0.40 or body_pct < 0.25):
        return {
            "pattern": "ABSORPTION_TRAP",
            "vol_ratio": vol_ratio,
            "signal": "BEARISH_REVERSAL",
            "description": f"Absorption Trap: Bẫy thanh khoản mua đỉnh (Volume {vol_ratio}x nhưng nến bị ép râu trên {int(upper_wick/candle_range*100)}%)"
        }

    # 3. Volume Breakout (Bứt phá xung lực dòng tiền lớn)
    if vol_ratio >= 1.4 and body_pct >= 0.60:
        side = "BULLISH_EXPANSION" if is_bull else "BEARISH_EXPANSION"
        side_desc = "Tăng" if is_bull else "Giảm"
        return {
            "pattern": "VOLUME_BREAKOUT",
            "vol_ratio": vol_ratio,
            "signal": side,
            "description": f"Volume Breakout: Nến {side_desc} xung lực mạnh có tổ chức bảo trợ (Vol {vol_ratio}x, Thân nến {int(body_pct*100)}%)"
        }

    # 4. No Supply (Nến cạn cung kiểm định đáy)
    if not is_bull and vol_ratio <= 0.65 and body_pct <= 0.40:
        return {
            "pattern": "NO_SUPPLY",
            "vol_ratio": vol_ratio,
            "signal": "BULLISH_CONTINUATION",
            "description": f"No Supply: Cạn kiệt lực bán khi retest hỗ trợ (Volume siêu thấp {vol_ratio}x)"
        }

    # 5. No Demand (Nến cạn cầu kiểm định đỉnh)
    if is_bull and vol_ratio <= 0.65 and body_pct <= 0.40:
        return {
            "pattern": "NO_DEMAND",
            "vol_ratio": vol_ratio,
            "signal": "BEARISH_CONTINUATION",
            "description": f"No Demand: Cạn kiệt lực mua giá cao tại cản (Volume suy kiệt {vol_ratio}x)"
        }

    return {
        "pattern": "NORMAL",
        "vol_ratio": vol_ratio,
        "signal": "NEUTRAL",
        "description": f"Volume bình thường ({vol_ratio}x trung bình)"
    }

def analyze_smc_structure(candles: List[Dict[str, float]], lookback: int = 35) -> Dict[str, Any]:
    """
    Skill 1: Smart Money Concepts (SMC) Engine for 1m-5m Scalping.
    Detects institutional footprint:
    1. Liquidity Sweeps (Stop Hunts / Bẫy săn thanh khoản đỉnh đáy):
       - Bullish Sweep: Giá quét râu thủng swing low trước đó, kích hoạt stop-loss của retail,
         sau đó rút chân đóng nến mạnh mẽ quay lại phía trên đáy cũ với râu dưới >= 35%.
       - Bearish Sweep: Giá quét râu vượt swing high trước đó, bẫy retail FOMO mua breakout,
         sau đó rút râu đóng nến ép xả quay lại dưới đỉnh cũ với râu trên >= 35%.
    2. Fair Value Gaps (FVG / Vùng mất cân bằng giá 3 nến):
       - Bullish FVG: Nến 1 High < Nến 3 Low (Displacement tăng mạnh mẽ).
       - Bearish FVG: Nến 1 Low > Nến 3 High (Displacement giảm mạnh mẽ).
       - Phát hiện giá hồi quy (Retest) và giữ vững trong vùng FVG.
    3. Cung cấp mức Stop-Loss chuẩn xác (ideal_sl) nằm sát ngay ngoài râu nến quét thanh khoản.
    """
    if len(candles) < 15:
        return {
            "detected": False,
            "pattern": "NONE",
            "signal": "NEUTRAL",
            "description": "Chưa đủ dữ liệu nến cho SMC",
            "ideal_sl": None,
            "score": 0.0,
            "sweep_level": None,
            "fvg_zone": None
        }

    sub_candles = candles[-lookback:] if len(candles) > lookback else candles
    n = len(sub_candles)
    
    # 1. Tìm các đỉnh/đáy Fractal cục bộ (Swing Highs / Swing Lows)
    swing_highs = []
    swing_lows = []

    for i in range(2, n - 2):
        h = sub_candles[i]["high"]
        l = sub_candles[i]["low"]
        # Fractal High
        if h > sub_candles[i-1]["high"] and h > sub_candles[i-2]["high"] and h >= sub_candles[i+1]["high"] and h >= sub_candles[i+2]["high"]:
            swing_highs.append((i, h))
        # Fractal Low
        if l < sub_candles[i-1]["low"] and l < sub_candles[i-2]["low"] and l <= sub_candles[i+1]["low"] and l <= sub_candles[i+2]["low"]:
            swing_lows.append((i, l))

    last = sub_candles[-1]
    prev = sub_candles[-2] if n >= 2 else last
    curr_price = last["close"]
    candle_range = max(1e-6, last["high"] - last["low"])
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_wick = last["high"] - max(last["open"], last["close"])
    lower_wick_ratio = lower_wick / candle_range
    upper_wick_ratio = upper_wick / candle_range

    # 2. Phát hiện Bullish Liquidity Sweep (Bẫy Gấu / Quét đáy rũ hàng)
    if swing_lows:
        recent_lows = [price for idx, price in swing_lows if idx < n - 1]
        if recent_lows:
            min_recent_low = min(recent_lows[-4:])
            
            sweep_curr = (last["low"] < min_recent_low) and (last["close"] >= min_recent_low * 0.9995) and (lower_wick_ratio >= 0.35)
            
            prev_range = max(1e-6, prev["high"] - prev["low"])
            prev_lower_wick_ratio = (min(prev["open"], prev["close"]) - prev["low"]) / prev_range
            sweep_prev = (prev["low"] < min_recent_low) and (prev["close"] >= min_recent_low * 0.9995) and (prev_lower_wick_ratio >= 0.35) and (last["close"] >= prev["close"])

            if sweep_curr or sweep_prev:
                sweep_low_point = min(last["low"], prev["low"] if sweep_prev else last["low"])
                ideal_sl = round(sweep_low_point * 0.9985, 6 if curr_price < 1 else 4)
                w_ratio = lower_wick_ratio if sweep_curr else prev_lower_wick_ratio
                return {
                    "detected": True,
                    "pattern": "BULLISH_SWEEP",
                    "signal": "BULLISH",
                    "description": f"SMC Liquidity Sweep: Quét sạch Stop-Loss dưới đáy ${min_recent_low:,.4f} -> Rút chân cực mạnh (Râu dưới {int(w_ratio*100)}%), tạo Bẫy Gấu (Bear Trap)",
                    "ideal_sl": ideal_sl,
                    "score": 0.07,
                    "sweep_level": min_recent_low,
                    "fvg_zone": None
                }

    # 3. Phát hiện Bearish Liquidity Sweep (Bẫy Bò / Quét đỉnh lừa mua)
    if swing_highs:
        recent_highs = [price for idx, price in swing_highs if idx < n - 1]
        if recent_highs:
            max_recent_high = max(recent_highs[-4:])
            
            sweep_curr = (last["high"] > max_recent_high) and (last["close"] <= max_recent_high * 1.0005) and (upper_wick_ratio >= 0.35)
            
            prev_range = max(1e-6, prev["high"] - prev["low"])
            prev_upper_wick_ratio = (prev["high"] - max(prev["open"], prev["close"])) / prev_range
            sweep_prev = (prev["high"] > max_recent_high) and (prev["close"] <= max_recent_high * 1.0005) and (prev_upper_wick_ratio >= 0.35) and (last["close"] <= prev["close"])

            if sweep_curr or sweep_prev:
                sweep_high_point = max(last["high"], prev["high"] if sweep_prev else last["high"])
                ideal_sl = round(sweep_high_point * 1.0015, 6 if curr_price < 1 else 4)
                w_ratio = upper_wick_ratio if sweep_curr else prev_upper_wick_ratio
                return {
                    "detected": True,
                    "pattern": "BEARISH_SWEEP",
                    "signal": "BEARISH",
                    "description": f"SMC Liquidity Sweep: Quét đỉnh thanh khoản ${max_recent_high:,.4f} -> Ép xả rút râu trên {int(w_ratio*100)}%, tạo Bẫy Bò (Bull Trap)",
                    "ideal_sl": ideal_sl,
                    "score": -0.07,
                    "sweep_level": max_recent_high,
                    "fvg_zone": None
                }

    # 4. Phát hiện Fair Value Gap (FVG) Retest trong 10 nến gần nhất
    for j in range(n - 2, max(2, n - 10), -1):
        c1 = sub_candles[j - 2]
        c2 = sub_candles[j - 1]
        c3 = sub_candles[j]
        
        # Bullish FVG: c1.high < c3.low
        if c1["high"] < c3["low"] and (c2["close"] > c2["open"]):
            fvg_low = c1["high"]
            fvg_high = c3["low"]
            gap_size = (fvg_high - fvg_low) / curr_price
            
            if gap_size >= 0.0015:
                if last["low"] <= fvg_high and last["close"] >= fvg_low:
                    ideal_sl = round(fvg_low * 0.998, 6 if curr_price < 1 else 4)
                    return {
                        "detected": True,
                        "pattern": "BULLISH_FVG_RETEST",
                        "signal": "BULLISH",
                        "description": f"SMC Fair Value Gap: Giá retest vùng FVG tăng [${fvg_low:,.4f} - ${fvg_high:,.4f}] và giữ vững hỗ trợ",
                        "ideal_sl": ideal_sl,
                        "score": 0.05,
                        "sweep_level": None,
                        "fvg_zone": [fvg_low, fvg_high]
                    }

        # Bearish FVG: c1.low > c3.high
        if c1["low"] > c3["high"] and (c2["close"] < c2["open"]):
            fvg_low = c3["high"]
            fvg_high = c1["low"]
            gap_size = (fvg_high - fvg_low) / curr_price

            if gap_size >= 0.0015:
                if last["high"] >= fvg_low and last["close"] <= fvg_high:
                    ideal_sl = round(fvg_high * 1.002, 6 if curr_price < 1 else 4)
                    return {
                        "detected": True,
                        "pattern": "BEARISH_FVG_RETEST",
                        "signal": "BEARISH",
                        "description": f"SMC Fair Value Gap: Giá hồi test vùng FVG giảm [${fvg_low:,.4f} - ${fvg_high:,.4f}] và bị kháng cự từ chối",
                        "ideal_sl": ideal_sl,
                        "score": -0.05,
                        "sweep_level": None,
                        "fvg_zone": [fvg_low, fvg_high]
                    }

    return {
        "detected": False,
        "pattern": "NONE",
        "signal": "NEUTRAL",
        "description": "Cấu trúc SMC bình thường, chưa có bẫy quét thanh khoản lớn",
        "ideal_sl": None,
        "score": 0.0,
        "sweep_level": None,
        "fvg_zone": None
    }

def detect_volatility_dynamics(
    candles: List[Dict[str, float]],
    orderbook_ratio: float = 1.0
) -> Dict[str, Any]:
    """
    Skill: Volatility & Pre-Breakout Squeeze Detection Engine
    1. Volatility Expansion (Bùng nổ biến động tức thì):
       - Volume Spike (Khối lượng tăng vọt gấp 1.5x - 3.0x trung bình)
       - Candle Range Expansion (Biên độ nến giật mạnh so với ATR)
    2. Volatility Squeeze Prediction (Dự đoán biến động sắp nổ ra):
       - Bollinger Bands Squeeze (Dải Bollinger co thắt nén lò xo)
       - EMA Convergence (Các đường trung bình hội tụ chuẩn bị bung sóng)
    3. Volatility Surge Index (VSI 0-100): Điểm số lượng hóa xung lực biến động.
    """
    if len(candles) < 20:
        return {
            "state": "NORMAL_VOLATILITY",
            "vsi_score": 50.0,
            "bandwidth_pct": 2.0,
            "is_squeeze": False,
            "volume_ratio": 1.0,
            "range_ratio": 1.0,
            "anticipated_direction": "NEUTRAL",
            "description": "Chưa đủ dữ liệu nến đo lường biến động"
        }

    closes = [c["close"] for c in candles]
    volumes = [c.get("volume", c.get("value", 0.0)) for c in candles]
    
    last = candles[-1]
    curr_price = last["close"]
    candle_range = max(1e-6, last["high"] - last["low"])
    
    # 1. Volume Surge Ratio
    avg_vol_20 = sum(volumes[-20:]) / 20.0 if len(volumes) >= 20 else 1.0
    vol_ratio = round(last.get("volume", 0.0) / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0

    # 2. Average True Range (ATR 14) & Range Expansion Ratio
    trs = []
    for i in range(1, len(candles)):
        c_h = candles[i]["high"]
        c_l = candles[i]["low"]
        p_c = candles[i-1]["close"]
        tr = max(c_h - c_l, abs(c_h - p_c), abs(c_l - p_c))
        trs.append(tr)
    
    atr14 = sum(trs[-14:]) / 14.0 if len(trs) >= 14 else candle_range
    range_ratio = round(candle_range / atr14, 2) if atr14 > 0 else 1.0

    # 3. Bollinger Bands Bandwidth (Squeeze Detection)
    recent_closes = closes[-20:]
    sma20 = sum(recent_closes) / 20.0
    variance = sum((x - sma20) ** 2 for x in recent_closes) / 20.0
    std_dev = math.sqrt(variance)
    upper_band = sma20 + 2 * std_dev
    lower_band = sma20 - 2 * std_dev
    bandwidth_pct = round(((upper_band - lower_band) / sma20) * 100, 2) if sma20 > 0 else 2.0

    # Ngưỡng Squeeze: Bandwidth co thắt cực hẹp <= 1.25%
    is_squeeze = bandwidth_pct <= 1.25

    # 4. Dự đoán hướng bung sóng (Anticipated Direction)
    ema20 = calculate_ema(closes, 20)[-1]
    ema50 = calculate_ema(closes, 50)[-1]
    
    if curr_price > ema20 and ema20 >= ema50 and orderbook_ratio >= 1.05:
        anticipated_dir = "LONG"
    elif curr_price < ema20 and ema20 <= ema50 and orderbook_ratio <= 0.95:
        anticipated_dir = "SHORT"
    elif orderbook_ratio >= 1.25:
        anticipated_dir = "LONG"
    elif orderbook_ratio <= 0.80:
        anticipated_dir = "SHORT"
    else:
        anticipated_dir = "NEUTRAL"

    # 5. Volatility Surge Index (VSI: 0 - 100)
    base_score = 40.0
    # Thưởng theo volume spike
    if vol_ratio >= 2.5:
        base_score += 25.0
    elif vol_ratio >= 1.5:
        base_score += 15.0
    elif vol_ratio <= 0.6:
        base_score -= 10.0

    # Thưởng theo độ giãn nở nến (Range expansion)
    if range_ratio >= 2.0:
        base_score += 25.0
    elif range_ratio >= 1.4:
        base_score += 15.0

    # Thưởng nếu phát hiện Squeeze (Nén lò xo chuẩn bị bung)
    if is_squeeze:
        base_score += 20.0

    # Thưởng nếu sổ lệnh mất cân bằng lớn (Whale orderbook pressure)
    if orderbook_ratio >= 1.30 or orderbook_ratio <= 0.70:
        base_score += 10.0

    vsi_score = min(100.0, max(10.0, round(base_score, 1)))

    # Phân loại trạng thái biến động
    if vol_ratio >= 1.8 or range_ratio >= 1.8:
        state = "ACTIVE_SURGE"
        desc = f"BÙNG NỔ BIẾN ĐỘNG (Volume {vol_ratio}x, Nến giãn nở {range_ratio}x so với ATR)"
    elif is_squeeze:
        state = "PREDICTED_BREAKOUT"
        desc = f"NÉN LÒ XO BIẾN ĐỘNG (Bollinger Squeeze hẹp {bandwidth_pct}%) -> Dự đoán sắp bung sóng {anticipated_dir}!"
    elif vsi_score >= 60.0:
        state = "MODERATE_EXPANSION"
        desc = f"Biến động đang gia tăng (VSI {vsi_score:.0f}/100, Vol {vol_ratio}x)"
    else:
        state = "LOW_VOLATILITY"
        desc = f"Biến động thấp, thị trường tích lũy chậm (VSI {vsi_score:.0f}/100)"

    return {
        "state": state,
        "vsi_score": vsi_score,
        "bandwidth_pct": bandwidth_pct,
        "is_squeeze": is_squeeze,
        "volume_ratio": vol_ratio,
        "range_ratio": range_ratio,
        "anticipated_direction": anticipated_dir,
        "description": desc
    }

def detect_candlestick_patterns(candles: List[Dict[str, float]]) -> Dict[str, Any]:
    """
    Phát hiện các mẫu hình nến Price Action kinh điển (Pin Bar, Engulfing, Inside Bar, Marubozu, Tweezer).
    Đặc biệt tối ưu cho chiến lược Bắn Tỉa Cá Mập (Micro Sniper $10):
    - Đánh giá cả nến hiện tại (candles[-1]) lẫn nến vừa đóng (candles[-2]).
    - Cung cấp mức Stop-Loss chuẩn xác (ideal_sl) nằm sát ngay ngoài râu nến quét thanh khoản.
    """
    if not candles or len(candles) < 2:
        return {"detected": False, "pattern": "NONE", "signal": "NEUTRAL", "confidence": 0.0, "ideal_sl": None, "description": "Không đủ nến để nhận diện mẫu hình"}

    curr = candles[-1]
    prev = candles[-2]
    curr_price = curr["close"]
    prec = 6 if curr_price < 1.0 else (4 if curr_price < 100.0 else 2)

    c_open, c_close, c_high, c_low = curr["open"], curr["close"], curr["high"], curr["low"]
    p_open, p_close, p_high, p_low = prev["open"], prev["close"], prev["high"], prev["low"]

    c_range = max(1e-8, c_high - c_low)
    c_body = abs(c_close - c_open)
    p_range = max(1e-8, p_high - p_low)
    p_body = abs(p_close - p_open)

    c_upper_wick = c_high - max(c_open, c_close)
    c_lower_wick = min(c_open, c_close) - c_low
    p_upper_wick = p_high - max(p_open, p_close)
    p_lower_wick = min(p_open, p_close) - p_low

    is_c_bull = c_close >= c_open
    is_p_bull = p_close >= p_open

    # 1. CONFIRMED BULLISH PINBAR (Nến trước rút râu dài >= 50% + Nến hiện tại xanh xác nhận đẩy giá)
    if (p_lower_wick / p_range >= 0.50) and (p_body / p_range <= 0.35) and (p_upper_wick / p_range <= 0.22) and (c_close >= p_close) and is_c_bull:
        sl_point = round(min(c_low, p_low) * 0.9985, prec)
        return {
            "detected": True,
            "pattern": "CONFIRMED_BULLISH_PINBAR",
            "signal": "BULLISH",
            "confidence": 0.94,
            "ideal_sl": sl_point,
            "description": f"Bullish Pin Bar Đã Xác Nhận: Nến trước rút râu dưới {int(p_lower_wick/p_range*100)}% + Nến hiện tại xanh xác nhận đảo chiều tăng (SL râu: ${sl_point:,.4f})"
        }

    # 2. ACTIVE BULLISH PINBAR (Nến hiện tại đang rút râu búa Hammer/Dragonfly >= 55%)
    if (c_lower_wick / c_range >= 0.55) and (c_body / c_range <= 0.35) and (c_upper_wick / c_range <= 0.20):
        sl_point = round(c_low * 0.9985, prec)
        return {
            "detected": True,
            "pattern": "BULLISH_PINBAR",
            "signal": "BULLISH",
            "confidence": 0.88,
            "ideal_sl": sl_point,
            "description": f"Bullish Pin Bar: Rút chân râu dưới {int(c_lower_wick/c_range*100)}%, quét sạch SL đáy phe mua giành lại quyền kiểm soát (SL râu: ${sl_point:,.4f})"
        }

    # 3. CONFIRMED BEARISH PINBAR (Nến trước rút râu trên dài >= 50% + Nến hiện tại đỏ đạp giá)
    if (p_upper_wick / p_range >= 0.50) and (p_body / p_range <= 0.35) and (p_lower_wick / p_range <= 0.22) and (c_close <= p_close) and (not is_c_bull):
        sl_point = round(max(c_high, p_high) * 1.0015, prec)
        return {
            "detected": True,
            "pattern": "CONFIRMED_BEARISH_PINBAR",
            "signal": "BEARISH",
            "confidence": 0.94,
            "ideal_sl": sl_point,
            "description": f"Bearish Pin Bar Đã Xác Nhận: Nến trước bắn râu trên {int(p_upper_wick/p_range*100)}% + Nến hiện tại đỏ đạp giá xác nhận phe gấu xả hàng (SL râu: ${sl_point:,.4f})"
        }

    # 4. ACTIVE BEARISH PINBAR (Nến hiện tại đang bắn sao Shooting Star >= 55%)
    if (c_upper_wick / c_range >= 0.55) and (c_body / c_range <= 0.35) and (c_lower_wick / c_range <= 0.20):
        sl_point = round(c_high * 1.0015, prec)
        return {
            "detected": True,
            "pattern": "BEARISH_PINBAR",
            "signal": "BEARISH",
            "confidence": 0.88,
            "ideal_sl": sl_point,
            "description": f"Bearish Pin Bar: Rút râu trên {int(c_upper_wick/c_range*100)}%, bẫy mua đỉnh bị từ chối mạnh mẽ (SL râu: ${sl_point:,.4f})"
        }

    # 5. TWEEZER BOTTOM (Đáy nhíp đôi - 2 nến liên tiếp test cùng mức đáy và đều rút râu dưới >= 35%)
    if (abs(c_low - p_low) / max(1e-8, c_low) <= 0.0010) and (c_lower_wick / c_range >= 0.35) and (p_lower_wick / p_range >= 0.35):
        sl_point = round(min(c_low, p_low) * 0.9985, prec)
        return {
            "detected": True,
            "pattern": "TWEEZER_BOTTOM",
            "signal": "BULLISH",
            "confidence": 0.90,
            "ideal_sl": sl_point,
            "description": f"Tweezer Bottom (Đáy nhíp đôi): Hai nến liên tiếp kiểm tra hỗ trợ đáy ${min(c_low, p_low):,.4f} và đều rút chân vững chắc"
        }

    # 6. TWEEZER TOP (Đỉnh nhíp đôi - 2 nến liên tiếp test cùng mức đỉnh và đều rút râu trên >= 35%)
    if (abs(c_high - p_high) / max(1e-8, c_high) <= 0.0010) and (c_upper_wick / c_range >= 0.35) and (p_upper_wick / p_range >= 0.35):
        sl_point = round(max(c_high, p_high) * 1.0015, prec)
        return {
            "detected": True,
            "pattern": "TWEEZER_TOP",
            "signal": "BEARISH",
            "confidence": 0.90,
            "ideal_sl": sl_point,
            "description": f"Tweezer Top (Đỉnh nhíp đôi): Hai nến liên tiếp kiểm tra kháng cự đỉnh ${max(c_high, p_high):,.4f} và đều bị ép bán dội ngược"
        }

    # 7. BULLISH ENGULFING (Nhấn chìm tăng)
    if (not is_p_bull) and is_c_bull and (c_close >= p_open) and (c_open <= p_close) and (c_body >= p_body * 1.05):
        sl_point = round(min(c_low, p_low) * 0.9985, prec)
        return {
            "detected": True,
            "pattern": "BULLISH_ENGULFING",
            "signal": "BULLISH",
            "confidence": 0.84,
            "ideal_sl": sl_point,
            "description": f"Bullish Engulfing: Thân nến xanh nuốt trọn nến đỏ trước đó (+{int(c_body/max(1e-8, p_body)*100)}% độ dài thân, SL: ${sl_point:,.4f})"
        }

    # 8. BEARISH ENGULFING (Nhấn chìm giảm)
    if is_p_bull and (not is_c_bull) and (c_close <= p_open) and (c_open >= p_close) and (c_body >= p_body * 1.05):
        sl_point = round(max(c_high, p_high) * 1.0015, prec)
        return {
            "detected": True,
            "pattern": "BEARISH_ENGULFING",
            "signal": "BEARISH",
            "confidence": 0.84,
            "ideal_sl": sl_point,
            "description": f"Bearish Engulfing: Thân nến đỏ xả mạnh nuốt trọn nến xanh trước đó (SL: ${sl_point:,.4f})"
        }

    # 9. BULLISH MARUBOZU (Đẩy thẳng không râu)
    if is_c_bull and (c_body / c_range >= 0.82) and (c_range >= p_range * 1.15):
        sl_point = round(c_low * 0.9985, prec)
        return {
            "detected": True,
            "pattern": "BULLISH_MARUBOZU",
            "signal": "BULLISH",
            "confidence": 0.78,
            "ideal_sl": sl_point,
            "description": f"Bullish Marubozu: Nến mua đẩy cực mạnh chiếm 82%+ biên độ không râu (SL: ${sl_point:,.4f})"
        }

    # 10. BEARISH MARUBOZU (Xả thẳng không râu)
    if (not is_c_bull) and (c_body / c_range >= 0.82) and (c_range >= p_range * 1.15):
        sl_point = round(c_high * 1.0015, prec)
        return {
            "detected": True,
            "pattern": "BEARISH_MARUBOZU",
            "signal": "BEARISH",
            "confidence": 0.78,
            "ideal_sl": sl_point,
            "description": f"Bearish Marubozu: Nến xả dứt khoát chiếm 82%+ biên độ không râu (SL: ${sl_point:,.4f})"
        }

    # 11. INSIDE BAR (Tích lũy nén lò xo)
    if (c_high <= p_high) and (c_low >= p_low):
        return {
            "detected": True,
            "pattern": "INSIDE_BAR",
            "signal": "NEUTRAL",
            "confidence": 0.65,
            "ideal_sl": None,
            "description": "Inside Bar: Biên độ nến nằm hoàn toàn trong nến mẹ, nén lò xo chuẩn bị bung sóng"
        }

    return {"detected": False, "pattern": "STANDARD_CANDLE", "signal": "NEUTRAL", "confidence": 0.50, "ideal_sl": None, "description": "Nến cơ bản"}

def analyze_multi_timeframe_confluence(
    klines_1m: List[Dict[str, float]],
    klines_15m: List[Dict[str, float]],
    klines_1h: List[Dict[str, float]]
) -> Dict[str, Any]:
    """
    Phân tích Hợp Lưu Đa Khung Thời Gian (Multi-Timeframe Confluence - MTF):
    - Khung 1H: Đại Xu Hướng Vĩ Mô (Macro Trend: EMA20 vs EMA50, RSI 1H, Biên độ 24h).
    - Khung 15M: Cấu Trúc & Vùng Cản Hỗ Trợ/Kháng Cự Then Chốt (Key Support & Resistance Levels).
    - Khung 1M: Bắt Điểm Vào Lệnh Bóp Cò (Trigger Entry) kết hợp Nến Price Action (Pinbar/Engulfing/Tweezer).
    """
    res = {
        "is_confluent": False,
        "is_super_confluence": False,
        "macro_1h_trend": "SIDEWAYS",
        "struct_15m_trend": "SIDEWAYS",
        "support_15m": None,
        "resistance_15m": None,
        "at_15m_support": False,
        "at_15m_resistance": False,
        "confluence_score": 0.0,
        "confluence_direction": "NEUTRAL",
        "description": "Thiếu dữ liệu đa khung thời gian"
    }

    if not klines_1h or len(klines_1h) < 15:
        return res

    # 1. Macro 1H Trend
    c1h = [c["close"] for c in klines_1h]
    curr_1h = c1h[-1]
    ema20_1h = calculate_ema(c1h, 20)[-1]
    ema50_1h = calculate_ema(c1h, 50)[-1] if len(c1h) >= 50 else ema20_1h
    rsi_1h = calculate_rsi(c1h, 14)

    if curr_1h > ema20_1h and ema20_1h >= ema50_1h:
        macro_trend = "BULLISH"
    elif curr_1h < ema20_1h and ema20_1h <= ema50_1h:
        macro_trend = "BEARISH"
    elif curr_1h > ema20_1h and ema20_1h < ema50_1h:
        macro_trend = "BULLISH_RECOVERY"
    elif curr_1h < ema20_1h and ema20_1h > ema50_1h:
        macro_trend = "BEARISH_PULLBACK"
    else:
        macro_trend = "SIDEWAYS"

    res["macro_1h_trend"] = macro_trend
    res["rsi_1h"] = rsi_1h

    # 2. Structure 15M Trend & Key S/R Levels
    curr_price = klines_1m[-1]["close"] if klines_1m else curr_1h
    at_supp = False
    at_res = False
    support_15m = None
    resistance_15m = None

    if klines_15m and len(klines_15m) >= 12:
        c15m = [c["close"] for c in klines_15m]
        curr_15m = c15m[-1]
        ema20_15m = calculate_ema(c15m, 20)[-1]
        if curr_15m > ema20_15m:
            struct_trend = "BULLISH"
        elif curr_15m < ema20_15m:
            struct_trend = "BEARISH"
        else:
            struct_trend = "SIDEWAYS"

        lows_15m = [c["low"] for c in klines_15m[-15:]]
        highs_15m = [c["high"] for c in klines_15m[-15:]]
        support_15m = min(lows_15m)
        resistance_15m = max(highs_15m)

        # Check proximity to 15m Key Levels (within 0.35%)
        if curr_price <= support_15m * 1.0035:
            at_supp = True
        if curr_price >= resistance_15m * 0.9965:
            at_res = True
    else:
        struct_trend = macro_trend

    res["struct_15m_trend"] = struct_trend
    res["support_15m"] = support_15m
    res["resistance_15m"] = resistance_15m
    res["at_15m_support"] = at_supp
    res["at_15m_resistance"] = at_res

    # 3. Trigger 1M Pattern Confirmation
    pattern_1m = detect_candlestick_patterns(klines_1m) if klines_1m else {"detected": False, "signal": "NEUTRAL"}
    res["pattern_1m"] = pattern_1m

    # 4. Super Confluence Detection (Institutional Sniper Alignment)
    # Kịch bản Vàng 1: Nến Pinbar/Hammer 1M xuất hiện ngay tại vùng Hỗ Trợ 15M hoặc đồng pha 1H
    if pattern_1m.get("detected") and pattern_1m["signal"] == "BULLISH" and (at_supp or macro_trend in ["BULLISH", "BULLISH_RECOVERY"]):
        res["is_confluent"] = True
        res["is_super_confluence"] = True
        res["confluence_direction"] = "LONG"
        res["confluence_score"] = 0.85
        supp_text = f"tại Vùng Hỗ Trợ 15M (${support_15m:,.4f})" if at_supp else f"đồng pha Đại Xu Hướng 1H ({macro_trend})"
        res["description"] = f"🎯 SIÊU HỢP LƯU TĂNG: {pattern_1m['pattern']} {supp_text} -> Tín hiệu Bắn Tỉa LONG xác suất cực cao!"
        return res

    # Kịch bản Vàng 2: Nến Pinbar/Shooting Star 1M xuất hiện ngay tại vùng Kháng Cự 15M hoặc đồng pha 1H
    if pattern_1m.get("detected") and pattern_1m["signal"] == "BEARISH" and (at_res or macro_trend in ["BEARISH", "BEARISH_PULLBACK"]):
        res["is_confluent"] = True
        res["is_super_confluence"] = True
        res["confluence_direction"] = "SHORT"
        res["confluence_score"] = -0.85
        res_text = f"tại Vùng Kháng Cự 15M (${resistance_15m:,.4f})" if at_res else f"đồng pha Đại Xu Hướng 1H ({macro_trend})"
        res["description"] = f"🎯 SIÊU HỢP LƯU GIẢM: {pattern_1m['pattern']} {res_text} -> Tín hiệu Bắn Tỉa SHORT xác suất cực cao!"
        return res

    # 5. Standard MTF Confluence Scoring
    confluence_score = 0.0
    if macro_trend in ["BULLISH", "BULLISH_RECOVERY"]:
        confluence_score += 0.45 if macro_trend == "BULLISH" else 0.25
    elif macro_trend in ["BEARISH", "BEARISH_PULLBACK"]:
        confluence_score -= 0.45 if macro_trend == "BEARISH" else 0.25

    if struct_trend == "BULLISH":
        confluence_score += 0.30
    elif struct_trend == "BEARISH":
        confluence_score -= 0.30

    if pattern_1m.get("detected"):
        conf = pattern_1m.get("confidence", 0.80)
        if pattern_1m["signal"] == "BULLISH":
            confluence_score += 0.25 * conf
        elif pattern_1m["signal"] == "BEARISH":
            confluence_score -= 0.25 * conf

    res["confluence_score"] = round(confluence_score, 2)

    if confluence_score >= 0.45:
        res["confluence_direction"] = "LONG"
        res["is_confluent"] = True
        res["description"] = f"HỢP LƯU TĂNG ĐA KHUNG (1H: {macro_trend} | 15M: {struct_trend} | 1M: {pattern_1m.get('pattern', 'SẴN SÀNG')})"
    elif confluence_score <= -0.45:
        res["confluence_direction"] = "SHORT"
        res["is_confluent"] = True
        res["description"] = f"HỢP LƯU GIẢM ĐA KHUNG (1H: {macro_trend} | 15M: {struct_trend} | 1M: {pattern_1m.get('pattern', 'SẴN SÀNG')})"
    else:
        res["confluence_direction"] = "NEUTRAL"
        res["is_confluent"] = False
        res["description"] = f"Xung đột đa khung (1H: {macro_trend} vs 15M: {struct_trend}) -> Chờ nến xác nhận"

    return res

def analyze_quant_structure(
    candles: List[Dict[str, float]],
    orderbook_ratio: float = 1.0,
    news_sentiment: float = 0.0,
    mtf_data: Optional[Dict[str, Any]] = None,
    use_patterns: bool = True
) -> Dict[str, Any]:
    """
    Combines Trend (EMA20/50), Momentum (RSI14), Volume Spread Analysis (VSA),
    Smart Money Concepts (SMC Liquidity Sweeps & FVGs), Candlestick Price Action,
    and Multi-Timeframe Confluence (1H / 15M / 1M) into a deterministic quantitative evaluation.
    """
    if len(candles) < 20:
        return {
            "status": "INSUFFICIENT_DATA",
            "p_long": 0.50,
            "chosen_side": "HOLD",
            "edge": 0.0,
            "trend": "UNKNOWN",
            "summary": "Không đủ nến để phân tích định lượng"
        }

    closes = [c["close"] for c in candles]
    curr_price = closes[-1]
    
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    
    val_ema20 = ema20[-1]
    val_ema50 = ema50[-1]
    rsi = calculate_rsi(closes, 14)
    vsa = analyze_vsa_candle(candles)
    smc = analyze_smc_structure(candles)
    vol_dyn = detect_volatility_dynamics(candles, orderbook_ratio)

    # 0. Candlestick Pattern detection & Multi-Timeframe Confluence
    candle_pat = detect_candlestick_patterns(candles) if use_patterns else {
        "detected": False, "pattern": "NONE", "signal": "NEUTRAL", "confidence": 0.0, "description": "Tắt nhận diện nến"
    }

    if mtf_data:
        mtf_res = analyze_multi_timeframe_confluence(
            klines_1m=candles,
            klines_15m=mtf_data.get("klines_15m", []),
            klines_1h=mtf_data.get("klines_1h", [])
        )
    else:
        mtf_res = {
            "is_confluent": False,
            "macro_1h_trend": "UNKNOWN",
            "struct_15m_trend": "UNKNOWN",
            "confluence_score": 0.0,
            "confluence_direction": "NEUTRAL",
            "description": "Đơn khung thời gian"
        }

    # 1. Trend Direction Classification
    dist_ema20 = (curr_price - val_ema20) / val_ema20
    dist_ema50 = (curr_price - val_ema50) / val_ema50

    if curr_price > val_ema20 and val_ema20 >= val_ema50:
        trend = "BULLISH"
        trend_desc = "Xu Hướng TĂNG Rõ Rệt (Giá > EMA20 > EMA50)"
    elif curr_price < val_ema20 and val_ema20 <= val_ema50:
        trend = "BEARISH"
        trend_desc = "Xu Hướng GIẢM Rõ Rệt (Giá < EMA20 < EMA50)"
    elif curr_price > val_ema20 and val_ema20 < val_ema50:
        trend = "BULLISH_RECOVERY"
        trend_desc = "Phục Hồi Sớm (Giá vượt EMA20 đang hướng lên EMA50)"
    elif curr_price < val_ema20 and val_ema20 > val_ema50:
        trend = "BEARISH_PULLBACK"
        trend_desc = "Điều Chỉnh Sớm (Giá thủng EMA20 đang test EMA50)"
    else:
        trend = "SIDEWAYS"
        trend_desc = "Thị Trường Đi Ngang (Kẹp giữa các đường EMA)"

    # 2. Deterministic Edge Calculation
    drift = 0.0

    if trend in ["BULLISH", "BULLISH_RECOVERY"]:
        # Baseline edge for upward trend
        drift += 0.07 if trend == "BULLISH" else 0.04
        
        # RSI momentum bonus / penalty
        if 48 <= rsi <= 68:
            drift += 0.03 # Healthy trend room
        elif rsi > 72:
            drift -= 0.06 # Overbought warning: penalize Long to prevent buying top!
        elif rsi < 40:
            drift -= 0.02

        # VSA confirmation
        if vsa["pattern"] == "VOLUME_BREAKOUT" and vsa["signal"] == "BULLISH_EXPANSION":
            drift += 0.04
        elif vsa["pattern"] == "NO_SUPPLY":
            drift += 0.03 # Dry supply pullback
        elif vsa["pattern"] == "ABSORPTION_TRAP":
            drift -= 0.07 # Whale trap warning

        # SMC Confluence: Liquidity Sweeps & FVGs
        if smc["detected"]:
            if smc["signal"] == "BULLISH":
                drift += smc["score"] # Add 0.05 - 0.07 for bullish sweep / FVG retest
            elif smc["signal"] == "BEARISH":
                drift += smc["score"] # Negative score alerts institutional top sweep!

    elif trend in ["BEARISH", "BEARISH_PULLBACK"]:
        # Baseline edge for downward trend (negative drift implies SHORT)
        drift -= 0.07 if trend == "BEARISH" else 0.04
        
        # RSI momentum bonus / penalty
        if 32 <= rsi <= 52:
            drift -= 0.03 # Healthy bearish momentum
        elif rsi < 28:
            drift += 0.06 # Oversold warning: penalize Short to prevent shorting bottom!
        elif rsi > 60:
            drift += 0.02

        # VSA confirmation
        if vsa["pattern"] == "VOLUME_BREAKOUT" and vsa["signal"] == "BEARISH_EXPANSION":
            drift -= 0.04
        elif vsa["pattern"] == "NO_DEMAND":
            drift -= 0.03 # Dry demand rally
        elif vsa["pattern"] == "STOPPING_VOLUME":
            drift += 0.07 # Whale absorption bottom

        # SMC Confluence: Liquidity Sweeps & FVGs
        if smc["detected"]:
            if smc["signal"] == "BEARISH":
                drift += smc["score"] # Negative score (-0.05 to -0.07) reinforces SHORT
            elif smc["signal"] == "BULLISH":
                drift += smc["score"] # Positive score alerts bottom sweep trap!

    else: # SIDEWAYS / CHOP ZONE
        # Trong thị trường đi ngang, các pha Quét Thanh Khoản (SMC Liquidity Sweep)
        # ở biên trên và biên dưới là cơ hội Scalping tỷ lệ R:R cao nhất!
        if smc["detected"]:
            if smc["pattern"] == "BULLISH_SWEEP":
                drift = 0.08 # Quét đáy biên dưới -> Long Scalp
            elif smc["pattern"] == "BEARISH_SWEEP":
                drift = -0.08 # Quét đỉnh biên trên -> Short Scalp
            elif smc["pattern"] == "BULLISH_FVG_RETEST":
                drift = 0.05
            elif smc["pattern"] == "BEARISH_FVG_RETEST":
                drift = -0.05
        else:
            drift = 0.0

    # 3. Orderbook depth minor support (damped to ±0.02 max, cannot flip trend)
    depth_adj = min(0.02, max(-0.02, (orderbook_ratio - 1.0) * 0.05))
    drift += depth_adj

    # 4. News sentiment minor support (damped to ±0.02 max)
    news_adj = min(0.02, max(-0.02, news_sentiment * 0.01))
    drift += news_adj

    # 4.5. Volatility Expansion & Squeeze Anticipation Drift
    if vol_dyn.get("state") == "ACTIVE_SURGE":
        # Bùng nổ biến động củng cố xu hướng hoặc bứt phá
        if trend in ["BULLISH", "BULLISH_RECOVERY"]:
            drift += 0.035
        elif trend in ["BEARISH", "BEARISH_PULLBACK"]:
            drift -= 0.035
    elif vol_dyn.get("state") == "PREDICTED_BREAKOUT":
        # Nén Bollinger Squeeze: Dự đoán hướng bung sóng
        if vol_dyn.get("anticipated_direction") == "LONG":
            drift += 0.03
        elif vol_dyn.get("anticipated_direction") == "SHORT":
            drift -= 0.03

    # 4.6 Candlestick Pattern Drift Integration (Price Action Trigger)
    if candle_pat.get("detected"):
        conf = candle_pat.get("confidence", 0.80)
        if candle_pat["signal"] == "BULLISH":
            drift += 0.045 * conf
        elif candle_pat["signal"] == "BEARISH":
            drift -= 0.045 * conf

    # 4.7 Multi-Timeframe Confluence Integration (1H Macro + 15M Structure)
    if mtf_res.get("is_confluent"):
        if mtf_res["confluence_direction"] == "LONG":
            drift += 0.05
        elif mtf_res["confluence_direction"] == "SHORT":
            drift -= 0.05

    # 4.8 Anti-Counter-Trend Safety (Tối quan trọng cho tài khoản $10 đòn bẩy cao)
    # Nếu khung 1H đại xu hướng đang giảm mạnh, cấm hoặc phạt cực nặng lệnh Long nếu không có Pinbar quét đáy SMC
    if mtf_res.get("macro_1h_trend") == "BEARISH" and drift > 0:
        if not (smc.get("detected") and smc.get("pattern") == "BULLISH_SWEEP"):
            drift -= 0.065
    # Nếu khung 1H đại xu hướng đang tăng mạnh, cấm hoặc phạt cực nặng lệnh Short nếu không có Pinbar quét đỉnh SMC
    elif mtf_res.get("macro_1h_trend") == "BULLISH" and drift < 0:
        if not (smc.get("detected") and smc.get("pattern") == "BEARISH_SWEEP"):
            drift += 0.065

    # 5. STRICT TREND CONSTRAINTS & SMC EXPLOITATION
    if smc.get("detected") and smc.get("pattern") in ["BULLISH_SWEEP", "BEARISH_SWEEP"]:
        # Các pha Quét Thanh Khoản (Institutional Stop Hunt) là ngoại lệ Scalping đảo chiều tối thượng:
        # Cá mập quét sạch Stop-loss của retail rồi rút chân đóng nến cực mạnh, cho điểm vào lệnh tỷ lệ R:R cao nhất.
        if smc["pattern"] == "BULLISH_SWEEP":
            p_long = min(0.75, max(0.58, round(0.50 + max(0.08, drift), 3)))
        else: # BEARISH_SWEEP
            p_long = max(0.25, min(0.42, round(0.50 + min(-0.08, drift), 3)))
    elif mtf_res.get("is_super_confluence"):
        # Siêu Hợp Lưu: Nến Pinbar 1M rút râu chuẩn xác tại cản 15M và thuận xu hướng 1H
        if mtf_res["confluence_direction"] == "LONG":
            p_long = min(0.75, max(0.62, round(0.50 + max(0.09, drift), 3)))
        else:
            p_long = max(0.25, min(0.38, round(0.50 + min(-0.09, drift), 3)))
    elif trend in ["BULLISH", "BULLISH_RECOVERY"]:
        # In uptrend, direction CANNOT be SHORT
        p_long = min(0.85, max(0.50, round(0.50 + max(0.0, drift), 3)))
    elif trend in ["BEARISH", "BEARISH_PULLBACK"]:
        # In downtrend, direction CANNOT be LONG
        p_long = max(0.15, min(0.50, round(0.50 + min(0.0, drift), 3)))
    else:
        # Sideways: Cho phép kích hoạt lệnh Scalp khi có bẫy FVG hoặc độ lệch định lượng đủ lớn
        if abs(drift) >= 0.05:
            p_long = min(0.70, max(0.30, round(0.50 + drift, 3)))
        else:
            p_long = 0.50

    p_short = round(1.0 - p_long, 3)

    if p_long > 0.50:
        chosen_side = "LONG"
        chosen_prob = p_long
        edge = round(p_long - 0.50, 3)
    elif p_short > 0.50:
        chosen_side = "SHORT"
        chosen_prob = p_short
        edge = round(p_short - 0.50, 3)
    else:
        chosen_side = "HOLD"
        chosen_prob = 0.50
        edge = 0.0

    smc_desc = f" | SMC: {smc['pattern']} ({smc['description']})" if smc.get("detected") else ""
    vol_desc = f" | {vol_dyn['description']}" if vol_dyn.get("state") != "NORMAL_VOLATILITY" else ""
    pat_desc = f" | Nến: {candle_pat['pattern']} ({candle_pat['description']})" if candle_pat.get("detected") else ""
    mtf_desc = f" | MTF: {mtf_res['description']}" if mtf_res.get("is_confluent") else ""
    summary_text = (
        f"{trend_desc} | EMA20: ${val_ema20:,.2f} | EMA50: ${val_ema50:,.2f} | "
        f"RSI(14): {rsi} | VSA: {vsa['description']}{smc_desc}{vol_desc}{pat_desc}{mtf_desc}"
    )

    return {
        "status": "OK",
        "curr_price": curr_price,
        "ema20": val_ema20,
        "ema50": val_ema50,
        "rsi": rsi,
        "vsa": vsa,
        "smc": smc,
        "volatility": vol_dyn,
        "candlestick_pattern": candle_pat,
        "multi_timeframe": mtf_res,
        "ideal_sl": candle_pat.get("ideal_sl") or smc.get("ideal_sl"),
        "trend": trend,
        "trend_desc": trend_desc,
        "p_long": p_long,
        "p_short": p_short,
        "chosen_side": chosen_side,
        "chosen_prob": chosen_prob,
        "edge": edge,
        "summary": summary_text
    }
