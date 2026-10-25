"""
Session Strategy Manager (Cơ Chế Chiến Thuật Thích Ứng Theo Phiên & Khung Giờ)
Phân tích múi giờ Việt Nam (UTC+7) tương ứng với dòng tiền định lượng toàn cầu:
1. 20:00 - 23:30: PHIÊN VÀNG NEW YORK (Wall Street & ETF Flow - Bùng nổ xung lực, đòn bẩy 20x-25x, thắng lớn)
2. 03:00 - 05:30: SÓNG RẠNG SÁNG (Chốt sổ phiên Mỹ - Sóng êm, ít quét râu, win rate thực tế 80%)
3. 08:30 - 12:30: PHIÊN Á TÍCH LŨY (Tokyo/HongKong/Singapore - Đi ngang hộp Range, đánh hồi phục, cấm breakout)
4. 13:30 - 16:30: PHIÊN BẪY QUÉT RÂU LONDON (Judas Swing - Rủi ro cao, siết đòn bẩy 8x, giảm 70% cược, cấm breakout)
5. 17:30 - 20:00: TIỀN PHIÊN MỸ (Pre-market - Chờ tin, giảm 50% cược)
6. Các giờ còn lại: KHUNG GIỜ LẮNG ĐỌNG (Thanh khoản mỏng, bảo vệ vốn)
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional

# Múi giờ Việt Nam (UTC+7)
VN_TZ = timezone(timedelta(hours=7))

SESSION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "NEW_YORK_SURGE": {
        "id": "NEW_YORK_SURGE",
        "name": "Phiên Vàng New York (Bùng Nổ Xung Lực)",
        "badge": "🚀 PHIÊN VÀNG NEW YORK",
        "time_range": "20:00 – 23:30 VN",
        "risk_mode": "AGGRESSIVE",
        "leverage_cap": 25,
        "stake_multiplier": 1.0,
        "min_edge_bonus": 0.0,
        "allow_breakout": True,
        "require_super_confluence": False,
        "description": "Dòng tiền Wall Street & ETF dồi dào (chiếm 65%+ volume toàn cầu). Bắt trend bứt phá dứt khoát, tối đa hóa lợi nhuận với đòn bẩy 20x-25x.",
        "badge_style": "badge-session-gold"
    },
    "LATE_US_CLEANUP": {
        "id": "LATE_US_CLEANUP",
        "name": "Sóng Rạng Sáng (Bắn Tỉa Chốt Sổ Phiên Mỹ)",
        "badge": "🦅 SÓNG RẠNG SÁNG",
        "time_range": "03:00 – 05:30 VN",
        "risk_mode": "SNIPER",
        "leverage_cap": 20,
        "stake_multiplier": 0.75,
        "min_edge_bonus": 0.005,
        "allow_breakout": True,
        "require_super_confluence": False,
        "description": "Dòng tiền tổ chức chốt sổ và đẩy nốt sóng trước khi đóng nến ngày. Nến đi êm, ít bị giật 2 đầu (Win rate thực tế của bot đạt 80%).",
        "badge_style": "badge-session-sniper"
    },
    "ASIAN_ACCUMULATION": {
        "id": "ASIAN_ACCUMULATION",
        "name": "Phiên Á Tích Lũy (Lướt Sóng Hộp Biên Độ)",
        "badge": "🌏 PHIÊN Á TÍCH LŨY",
        "time_range": "08:30 – 12:30 VN",
        "risk_mode": "BALANCED",
        "leverage_cap": 12,
        "stake_multiplier": 0.50,
        "min_edge_bonus": 0.010,
        "allow_breakout": False,
        "require_super_confluence": False,
        "description": "Thị trường châu Á tích lũy đi ngang. Đánh phản ứng hỗ trợ/kháng cự và FVG retest, không fomo theo breakout giả.",
        "badge_style": "badge-session-asian"
    },
    "LONDON_JUDAS_TRAP": {
        "id": "LONDON_JUDAS_TRAP",
        "name": "Phiên Bẫy Quét Râu London (Siêu Phòng Thủ)",
        "badge": "⚠️ BẪY QUÉT RÂU LONDON",
        "time_range": "13:30 – 16:30 VN",
        "risk_mode": "DEFENSIVE_LOCK",
        "leverage_cap": 8,
        "stake_multiplier": 0.30,
        "min_edge_bonus": 0.025,
        "allow_breakout": False,
        "require_super_confluence": True,
        "description": "Market Maker London quét Stop-Loss 2 đầu (Judas Swing). Tự động siết đòn bẩy về 8x, giảm 70% vốn cược, cấm đu Breakout giả.",
        "badge_style": "badge-session-trap"
    },
    "US_PREMARKET": {
        "id": "US_PREMARKET",
        "name": "Tiền Phiên Mỹ (Chờ Dòng Tiền & Cảnh Giác)",
        "badge": "⏳ TIỀN PHIÊN MỸ",
        "time_range": "17:30 – 20:00 VN",
        "risk_mode": "CAUTIOUS",
        "leverage_cap": 15,
        "stake_multiplier": 0.50,
        "min_edge_bonus": 0.010,
        "allow_breakout": False,
        "require_super_confluence": False,
        "description": "Thị trường nén chờ tin tức kinh tế Mỹ và giờ mở cửa New York. Hạn chế vào lệnh sớm trước sóng lớn.",
        "badge_style": "badge-session-cautious"
    },
    "QUIET_HOURS": {
        "id": "QUIET_HOURS",
        "name": "Khung Giờ Lắng Đọng (Thanh Khoản Thấp)",
        "badge": "🌙 KHUNG GIỜ LẮNG ĐỌNG",
        "time_range": "Các giờ chuyển giao",
        "risk_mode": "CONSERVATIVE",
        "leverage_cap": 10,
        "stake_multiplier": 0.40,
        "min_edge_bonus": 0.015,
        "allow_breakout": False,
        "require_super_confluence": False,
        "description": "Thanh khoản toàn cầu ở mức thấp. Bot hạ đòn bẩy, giảm vốn cược để bảo toàn tài khoản chờ các phiên bùng nổ.",
        "badge_style": "badge-session-quiet"
    }
}

def get_vn_now() -> datetime:
    """Trả về thời gian hiện tại chuẩn hóa múi giờ Việt Nam (UTC+7)."""
    return datetime.now(timezone.utc).astimezone(VN_TZ)

def get_current_session(dt: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Xác định chính xác phiên giao dịch định lượng theo giờ Việt Nam.
    """
    if dt is None:
        dt = get_vn_now()
    elif dt.tzinfo is None:
        # Nếu truyền naive datetime từ máy người dùng, giả định là giờ VN
        dt = dt.replace(tzinfo=VN_TZ)
    else:
        dt = dt.astimezone(VN_TZ)

    t = dt.hour + dt.minute / 60.0

    if 20.0 <= t < 23.5:
        session_id = "NEW_YORK_SURGE"
    elif 3.0 <= t < 5.5:
        session_id = "LATE_US_CLEANUP"
    elif 8.5 <= t < 12.5:
        session_id = "ASIAN_ACCUMULATION"
    elif 13.5 <= t < 16.5:
        session_id = "LONDON_JUDAS_TRAP"
    elif 17.5 <= t < 20.0:
        session_id = "US_PREMARKET"
    else:
        session_id = "QUIET_HOURS"

    session = dict(SESSION_DEFINITIONS.get(session_id, SESSION_DEFINITIONS["QUIET_HOURS"]))
    session["current_time_vn"] = dt.strftime("%H:%M:%S")
    session["current_date_vn"] = dt.strftime("%Y-%m-%d")
    return session

def evaluate_session_gate(
    session: Dict[str, Any],
    signal_type: str,
    edge: float,
    has_super_confluence: bool = False,
    has_smc_sweep: bool = False
) -> Tuple[bool, str]:
    """
    Kiểm tra xem lệnh có vượt qua bộ lọc an toàn của phiên hiện tại hay không.
    Trả về (is_allowed, reason).
    """
    badge = session.get("badge", "Phiên")
    name = session.get("name", "Phiên")

    # 1. Kiểm tra cấm Breakout giả trong phiên bẫy (London Judas hoặc Tiền phiên Mỹ)
    if not session.get("allow_breakout", True) and signal_type == "MOMENTUM_BREAKOUT":
        # Ngoại lệ: Nếu có xác nhận bẫy SMC Sweep hoặc Pinbar siêu hợp lưu thì chấp thuận
        if not (has_smc_sweep or has_super_confluence or edge >= 0.08):
            return False, (
                f"[{badge}] Từ chối lệnh Breakout vì 80%+ bứt phá trong {name} là bẫy giật 2 đầu (Judas Swing). "
                f"Chỉ chấp thuận khi có xác nhận bẫy SMC Sweep hoặc Siêu Hợp Lưu nến!"
            )

    # 2. Kiểm tra yêu cầu Siêu Hợp Lưu (Super Confluence) trong phiên bẫy
    if session.get("require_super_confluence", False):
        if not (has_super_confluence or has_smc_sweep or edge >= 0.075):
            return False, (
                f"[{badge}] {name} có rủi ro quét Stop-Loss cực cao. "
                f"Yêu cầu bắt buộc phải có Siêu Hợp Lưu 1H-15M-1M hoặc bẫy SMC Sweep (Lợi thế hiện tại: {edge:+.1%}). Tạm đứng ngoài."
            )

    return True, "Hợp lệ theo bộ lọc phiên"
