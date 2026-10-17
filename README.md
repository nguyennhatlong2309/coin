# 🎯 QUANT DESK: Multi-Agent Mock Trading Swarm

Hệ thống giao dịch định lượng giả lập (Paper Trading) sử dụng mô hình **Bầy đàn AI (Swarm Agents)** để quét thị trường dự đoán (Polymarket & Manifold), tự động tìm kiếm tin tức thời gian thực qua Google News RSS, tính toán xác suất lệch giá (Statistical Edge) và quản trị vốn bằng công thức Kelly.

---

## ⚡ Các thành phần trong Swarm Grid

1. **Spotter Agent (Trinh sát):**
   * Quét liên tục các thị trường nhị phân (Binary Markets) có thanh khoản từ Polymarket và Manifold.
   * Lọc các kèo có xác suất từ `12%` đến `88%` để tìm cơ hội vào lệnh tốt nhất.

2. **Researcher Agent (Nghiên cứu thông tin):**
   * Tự động crawl tin tức nóng nhất từ **Google News RSS** theo thời gian thực (Reuters, Bloomberg, AP News, CNBC...).
   * Trích xuất các dữ kiện và xu hướng cảm xúc (positive/negative sentiment signals).

3. **The Pricer Agent (Định giá xác suất):**
   * Dùng mô hình xác suất Gaussian & Bayesian drift để tính toán xác suất thực $P_{fair}$.
   * Tính toán biên độ lệch giá so với sàn: $\text{Edge} = P_{fair} - P_{market}$.

4. **Kelly Risk Agent (Quản trị vốn):**
   * Áp dụng công thức **Quarter-Kelly** ($1/4$ Kelly) để tối ưu hóa tăng trưởng vốn mà không gây rủi ro cháy tài khoản.
   * Khống chế trần rủi ro tối đa `5%` tổng tài sản cho mỗi lệnh đặt cược.

5. **Mock Portfolio Ledger (Sổ cái giao dịch ảo):**
   * Cấp vốn ban đầu `$1,000.00 USD` tiền ảo.
   * Lưu trữ danh mục vị thế đang mở (Open Positions), lịch sử giao dịch và dòng suy nghĩ (Thought Stream) vào `backend/data/portfolio.json`.

---

## 🚀 Hướng dẫn khởi chạy

Chỉ cần chạy lệnh sau từ thư mục dự án:

```bash
python run.py
```

Trình duyệt sẽ tự động mở giao diện tại: **`http://127.0.0.1:8000`**

### Các thao tác trên Dashboard:
* **[⚡ RUN SWARM SCAN NOW]:** Bấm để kích hoạt 1 chu kỳ quét, nghiên cứu và ra quyết định ngay lập tức.
* **[🔴 AUTO-LOOP: OFF/ON]:** Bật chế độ tự động chạy ngầm mỗi 30 giây.
* **[🔄 RESET ($1,000)]:** Đặt lại ví tiền mock về $1,000 ban đầu để thử nghiệm lại từ đầu.

---

## 📁 Cấu trúc thư mục

```text
quant-desk/
├── backend/
│   ├── app.py                # FastAPI server & API endpoints
│   ├── config.py             # Cấu hình vốn, Kelly fraction, scan interval
│   ├── core/
│   │   ├── markets.py        # Client Polymarket + Manifold Markets
│   │   ├── news_fetcher.py   # Bộ cào Google News RSS thời gian thực
│   │   ├── agents.py         # 4 Agents: Spotter, Researcher, Pricer, Kelly Risk
│   │   └── portfolio.py      # Quản lý số dư mock, vị thế mở & PnL
│   └── data/
│       └── portfolio.json    # File lưu trữ dữ liệu danh mục cục bộ
├── frontend/
│   ├── index.html            # Giao diện Cyberpunk Quant Terminal
│   ├── style.css             # Glassmorphism, neon tickers, responsive grid
│   └── app.js                # Xử lý cập nhật thời gian thực, bảng lệnh
├── run.py                    # Script 1-click khởi chạy
├── requirements.txt          # Các thư viện phụ thuộc siêu nhẹ
└── README.md                 # Tài liệu dự án
```
