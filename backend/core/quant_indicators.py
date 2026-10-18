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

def analyze_quant_structure(
    candles: List[Dict[str, float]],
    orderbook_ratio: float = 1.0,
    news_sentiment: float = 0.0
) -> Dict[str, Any]:
    """
    Combines Trend (EMA20/50), Momentum (RSI14), and Volume Spread Analysis (VSA)
    into a 100% deterministic quantitative evaluation:
    - Strictly forbids counter-trend trading.
    - Identifies Chop/Sideways zones and enforces capital preservation (HOLD).
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

    else: # SIDEWAYS
        # Market in chop zone, suppress drift
        drift = 0.0

    # 3. Orderbook depth minor support (damped to ±0.02 max, cannot flip trend)
    depth_adj = min(0.02, max(-0.02, (orderbook_ratio - 1.0) * 0.05))
    drift += depth_adj

    # 4. News sentiment minor support (damped to ±0.02 max)
    news_adj = min(0.02, max(-0.02, news_sentiment * 0.01))
    drift += news_adj

    # 5. STRICT TREND CONSTRAINTS (Never trade against the primary trend)
    if trend in ["BULLISH", "BULLISH_RECOVERY"]:
        # In uptrend, direction CANNOT be SHORT
        p_long = min(0.85, max(0.50, round(0.50 + max(0.0, drift), 3)))
    elif trend in ["BEARISH", "BEARISH_PULLBACK"]:
        # In downtrend, direction CANNOT be LONG
        p_long = max(0.15, min(0.50, round(0.50 + min(0.0, drift), 3)))
    else:
        # Sideways/Chop: zero directional bias
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

    summary_text = (
        f"{trend_desc} | EMA20: ${val_ema20:,.2f} | EMA50: ${val_ema50:,.2f} | "
        f"RSI(14): {rsi} | VSA: {vsa['description']}"
    )

    return {
        "status": "OK",
        "curr_price": curr_price,
        "ema20": val_ema20,
        "ema50": val_ema50,
        "rsi": rsi,
        "vsa": vsa,
        "trend": trend,
        "trend_desc": trend_desc,
        "p_long": p_long,
        "p_short": p_short,
        "chosen_side": chosen_side,
        "chosen_prob": chosen_prob,
        "edge": edge,
        "summary": summary_text
    }
