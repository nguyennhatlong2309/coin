let isAutoRunning = false;
let autoStatusInterval = null;

// Chart State
let chartInstance = null;
let candleSeries = null;
let volumeSeries = null;
let currentChartCoin = "BTC";
let currentChartInterval = "1h";

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  loadPortfolio();
  loadCryptoWatchlist(true);
  initChart();
  loadChartData(currentChartCoin, currentChartInterval);
  loadMarkets();
  checkAutoStatus();

  // Periodic portfolio poll (every 3 seconds)
  setInterval(() => {
    loadPortfolio();
  }, 3000);

  // Periodic crypto watchlist poll (every 4 seconds)
  setInterval(() => {
    loadCryptoWatchlist(false);
  }, 4000);

  // Periodic active chart refresh (managed dynamically in loadChartData)
  startChartAutoRefresh();

  // Periodic market refresh (every 30 seconds)
  setInterval(() => {
    loadMarkets();
  }, 30000);
});

// ============================================================
// 1. TRADINGVIEW LIGHTWEIGHT CHARTS ENGINE
// ============================================================
function initChart() {
  const container = document.getElementById("tv-chart-container");
  if (!container) return;

  if (typeof LightweightCharts === "undefined") {
    container.innerHTML = `<div class="text-center text-muted" style="padding:40px;">LightweightCharts library not loaded.</div>`;
    return;
  }

  container.innerHTML = "";

  chartInstance = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: 380,
    layout: {
      background: { type: 'solid', color: '#090d16' },
      textColor: '#94a3b8',
      fontSize: 11,
      fontFamily: "'JetBrains Mono', monospace"
    },
    grid: {
      vertLines: { color: 'rgba(255, 255, 255, 0.04)' },
      horzLines: { color: 'rgba(255, 255, 255, 0.04)' }
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: {
        color: '#00f0ff',
        width: 1,
        style: 3,
        labelBackgroundColor: '#00f0ff'
      },
      horzLine: {
        color: '#00f0ff',
        width: 1,
        style: 3,
        labelBackgroundColor: '#00f0ff'
      }
    },
    rightPriceScale: {
      borderColor: 'rgba(255, 255, 255, 0.1)',
      autoScale: true
    },
    timeScale: {
      borderColor: 'rgba(255, 255, 255, 0.1)',
      timeVisible: true,
      secondsVisible: false
    }
  });

  // Candlestick Series
  candleSeries = chartInstance.addCandlestickSeries({
    upColor: '#10b981',
    downColor: '#ef4444',
    borderUpColor: '#10b981',
    borderDownColor: '#ef4444',
    wickUpColor: '#10b981',
    wickDownColor: '#ef4444'
  });

  // Volume Histogram Series
  volumeSeries = chartInstance.addHistogramSeries({
    priceFormat: {
      type: 'volume'
    },
    priceScaleId: '', // Set as overlay
    scaleMargins: {
      top: 0.8,
      bottom: 0
    }
  });

  // Crosshair move listener to update stats banner
  chartInstance.subscribeCrosshairMove(param => {
    if (!param || !param.time || !param.seriesData) return;
    const candle = param.seriesData.get(candleSeries);
    const vol = param.seriesData.get(volumeSeries);
    if (candle) {
      updateStatsBanner(candle.open, candle.high, candle.low, candle.close, vol ? vol.value : 0);
    }
  });

  // Responsive resize
  window.addEventListener("resize", () => {
    if (chartInstance && container) {
      chartInstance.applyOptions({ width: container.clientWidth });
    }
  });
}

async function loadChartData(coin, interval = "1h") {
  currentChartCoin = coin.toUpperCase();
  currentChartInterval = interval;

  const badge = document.getElementById("chart-active-coin-badge");
  if (badge) {
    badge.textContent = `${currentChartCoin} / USDT (${interval.toUpperCase()})`;
  }

  // Update tabs active state
  document.querySelectorAll(".chart-tab").forEach(tab => {
    if (tab.dataset.coin === currentChartCoin) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });

  // Adjust timeScale precision for seconds (1s) vs minutes/hours
  if (chartInstance) {
    chartInstance.applyOptions({
      timeScale: {
        timeVisible: true,
        secondsVisible: (interval === "1s")
      }
    });
  }

  // Adjust refresh frequency
  startChartAutoRefresh();

  try {
    const limit = (interval === "1s") ? 150 : 120;
    const res = await fetch(`/api/crypto/klines/${currentChartCoin}?interval=${currentChartInterval}&limit=${limit}`);
    const data = await res.json();

    if (data.error || !data.candles || data.candles.length === 0) {
      console.warn("Could not load klines:", data.error);
      return;
    }

    if (candleSeries && volumeSeries) {
      candleSeries.setData(data.candles);
      volumeSeries.setData(data.volumes);

      // Fit content nicely
      chartInstance.timeScale().fitContent();

      // Update banner with last candle
      const last = data.candles[data.candles.length - 1];
      const lastVol = data.volumes[data.volumes.length - 1];
      updateStatsBanner(last.open, last.high, last.low, last.close, lastVol ? lastVol.value : 0);
    }
  } catch (err) {
    console.error("Error fetching chart data:", err);
  }
}

let chartRefreshTimer = null;

function startChartAutoRefresh() {
  if (chartRefreshTimer) clearInterval(chartRefreshTimer);

  let delay = 5000;
  if (currentChartInterval === "1s") {
    delay = 1000; // 1 second live tick
  } else if (currentChartInterval === "1m" || currentChartInterval === "3m" || currentChartInterval === "5m") {
    delay = 2000; // 2 seconds tick
  }

  chartRefreshTimer = setInterval(() => {
    refreshActiveChartCandle();
  }, delay);
}

async function refreshActiveChartCandle() {
  if (!candleSeries || !volumeSeries) return;
  try {
    const res = await fetch(`/api/crypto/klines/${currentChartCoin}?interval=${currentChartInterval}&limit=3`);
    const data = await res.json();
    if (data.candles && data.candles.length > 0) {
      for (let i = 0; i < data.candles.length; i++) {
        candleSeries.update(data.candles[i]);
        volumeSeries.update(data.volumes[i]);
      }
      const last = data.candles[data.candles.length - 1];
      const lastVol = data.volumes[data.volumes.length - 1];
      updateStatsBanner(last.open, last.high, last.low, last.close, lastVol ? lastVol.value : 0);
    }
  } catch (e) {}
}


function updateStatsBanner(o, h, l, c, volUsdt) {
  const elO = document.getElementById("stat-open");
  const elH = document.getElementById("stat-high");
  const elL = document.getElementById("stat-low");
  const elC = document.getElementById("stat-close");
  const elV = document.getElementById("stat-vol");

  if (elO) elO.textContent = formatPriceNum(o);
  if (elH) elH.textContent = formatPriceNum(h);
  if (elL) elL.textContent = formatPriceNum(l);
  if (elC) {
    elC.textContent = formatPriceNum(c);
    elC.className = c >= o ? "highlight-green" : "highlight-red";
  }
  if (elV) {
    elV.textContent = volUsdt >= 1e6 ? `$${(volUsdt / 1e6).toFixed(2)}M` : `$${(volUsdt / 1e3).toFixed(1)}K`;
  }
}

function changeTimeframe(tf) {
  currentChartInterval = tf;
  document.querySelectorAll(".btn-tf").forEach(btn => btn.classList.remove("active"));
  const activeBtn = document.getElementById(`tf-${tf}`);
  if (activeBtn) activeBtn.classList.add("active");
  loadChartData(currentChartCoin, tf);
}

function changeChartCoin(coin, scrollToChart = false) {
  loadChartData(coin, currentChartInterval);
  if (scrollToChart) {
    const chartEl = document.querySelector(".chart-panel");
    if (chartEl) {
      chartEl.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }
}

function renderChartCoinTabs(coins) {
  const container = document.getElementById("chart-coin-tabs");
  if (!container || !coins || coins.length === 0) return;

  const topCoins = coins.slice(0, 6);
  container.innerHTML = topCoins.map(coin => {
    const active = coin.toUpperCase() === currentChartCoin ? "active" : "";
    return `<button class="chart-tab ${active}" data-coin="${coin}" onclick="changeChartCoin('${coin}')">${coin}</button>`;
  }).join("");
}

function formatPriceNum(num) {
  if (num === undefined || num === null) return "-";
  if (num >= 1000) return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (num >= 1) return `$${num.toFixed(3)}`;
  if (num >= 0.001) return `$${num.toFixed(6)}`;
  return `$${num.toFixed(8)}`;
}

// ============================================================
// 2. PORTFOLIO & SWARM ENGINE STATS
// ============================================================
async function loadPortfolio() {
  try {
    const res = await fetch("/api/portfolio");
    if (!res.ok) return;
    const data = await res.json();

    // KPIs
    const equityEl = document.getElementById("kpi-equity");
    const cashEl = document.getElementById("kpi-cash");
    const pnlEl = document.getElementById("kpi-pnl");
    const realizedEl = document.getElementById("kpi-realized");
    const winrateEl = document.getElementById("kpi-winrate");
    const tradesEl = document.getElementById("kpi-trades");

    equityEl.textContent = `$${data.total_equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    cashEl.textContent = `Tiền mặt: $${data.cash_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

    const pnlSign = data.total_pnl >= 0 ? "+" : "";
    pnlEl.textContent = `${pnlSign}$${data.total_pnl.toFixed(2)} (${pnlSign}${data.pnl_percent.toFixed(1)}%)`;
    pnlEl.className = `kpi-value ${data.total_pnl >= 0 ? 'highlight-green' : 'highlight-red'}`;

    realizedEl.textContent = `Đã chốt: $${data.realized_pnl.toFixed(2)} • Tạm tính: $${data.unrealized_pnl.toFixed(2)}`;
    winrateEl.textContent = `${data.win_rate.toFixed(1)}%`;
    tradesEl.textContent = `${data.trades_count} Lệnh • ${data.total_open_count} Vị thế mở`;

    // Active Positions Table
    const posTbody = document.getElementById("positions-tbody");
    const posCountBadge = document.getElementById("open-positions-count");
    posCountBadge.textContent = `${data.open_positions.length} ĐANG MỞ`;

    if (data.open_positions.length === 0) {
      posTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Chưa có vị thế nào. Hãy bấm "QUÉT THỊ TRƯỜNG NGAY" để AI vào lệnh!</td></tr>`;
    } else {

      posTbody.innerHTML = data.open_positions.map(pos => {
        const isCrypto = pos.asset_type === "crypto";
        let pnl = 0;
        let pnlPct = 0;

        if (isCrypto && pos.outcome === "SHORT") {
          pnl = (pos.entry_price - pos.current_price) * pos.shares;
          pnlPct = ((pos.entry_price - pos.current_price) / pos.entry_price) * 100;
        } else {
          pnl = (pos.current_price - pos.entry_price) * pos.shares;
          pnlPct = ((pos.current_price - pos.entry_price) / pos.entry_price) * 100;
        }

        const pnlClass = pnl >= 0 ? "highlight-green" : "highlight-red";
        let tagClass = "tag-outcome-yes";
        if (pos.outcome === "NO" || pos.outcome === "SHORT") {
          tagClass = "tag-outcome-no";
        }

        const sharesStr = isCrypto ? (pos.shares < 1 ? pos.shares.toFixed(4) : pos.shares.toFixed(2)) : pos.shares.toFixed(1);
        const entryStr = isCrypto && pos.entry_price >= 1 ? `$${pos.entry_price.toLocaleString('en-US', {minimumFractionDigits: 2})}` : `$${pos.entry_price}`;
        const currentStr = isCrypto && pos.current_price >= 1 ? `$${pos.current_price.toLocaleString('en-US', {minimumFractionDigits: 2})}` : `$${pos.current_price}`;

        return `
          <tr>
            <td>
              <strong>${escapeHtml(pos.question)}</strong>
              ${isCrypto ? '<span class="sub-badge" style="margin-left:6px; font-size:0.65rem">CRYPTO</span>' : '<span class="sub-badge" style="margin-left:6px; font-size:0.65rem">PREDICTION</span>'}
            </td>
            <td><span class="${tagClass}">${pos.outcome}</span></td>
            <td>${sharesStr}</td>
            <td>${entryStr}</td>
            <td>${currentStr}</td>
            <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct.toFixed(1)}%)</td>
          </tr>
        `;
      }).join("");
    }

    // Terminal Thought Stream
    const terminal = document.getElementById("thought-terminal");
    if (data.thought_logs && data.thought_logs.length > 0) {
      terminal.innerHTML = data.thought_logs.map(log => {
        let tagClass = "tag-sys";
        const ag = (log.agent || "").toLowerCase();
        if (ag.includes("spotter")) tagClass = "tag-spotter";
        else if (ag.includes("researcher")) tagClass = "tag-researcher";
        else if (ag.includes("pricer")) tagClass = "tag-pricer";
        else if (ag.includes("kelly")) tagClass = "tag-kelly";
        else if (ag.includes("executor") || log.level === "TRADE") tagClass = "tag-trade";
        else if (log.level === "WARN") tagClass = "tag-warn";

        return `<div class="terminal-line"><span class="log-time">[${log.timestamp}]</span> <span class="log-tag ${tagClass}">[${escapeHtml(log.agent)}]</span> ${escapeHtml(log.message)}</div>`;
      }).join("");
    }

    // Recent Trades History Table
    const tradesTbody = document.getElementById("trades-tbody");
    if (data.recent_trades && data.recent_trades.length > 0) {
      tradesTbody.innerHTML = data.recent_trades.map(t => {
        const isBuy = t.action.includes("BUY") || t.action.includes("LONG") || t.action.includes("YES");
        return `
          <tr>
            <td class="text-muted">${t.timestamp}</td>
            <td><span class="${isBuy ? 'tag-outcome-yes' : 'tag-outcome-no'}">${t.action}</span></td>
            <td>${escapeHtml(t.question)}</td>
            <td>${t.shares}</td>
            <td>$${Number(t.price).toLocaleString()}</td>
            <td>$${t.total_amount.toFixed(2)}</td>
            <td class="text-muted" style="font-size:0.75rem">${escapeHtml(t.reasoning)}</td>
          </tr>
        `;
      }).join("");
    } else {
      tradesTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Chưa có lịch sử giao dịch nào.</td></tr>`;
    }
  } catch (err) {
    console.error("Error polling portfolio:", err);
  }
}

// ============================================================
// 3. CRYPTO WATCHLIST & LIQUIDITY MATRIX
// ============================================================
async function loadCryptoWatchlist(force = false) {
  try {
    const res = await fetch("/api/crypto/watchlist");
    if (!res.ok) return;
    const data = await res.json();

    const tbody = document.getElementById("crypto-watchlist-tbody");
    const countBadge = document.getElementById("watchlist-count-badge");
    if (countBadge) {
      const activeCount = data.tickers.filter(t => t.is_active).length;
      countBadge.textContent = `${activeCount}/${data.tickers.length} COIN ĐANG BẬT AI`;
    }

    // Render coin selector tabs above the chart
    if (data.tickers && data.tickers.length > 0) {
      renderChartCoinTabs(data.tickers.map(t => t.coin));
    }

    if (!data.tickers || data.tickers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-muted">Chưa có coin nào trong danh sách. Hãy dùng ô phía trên để thêm coin (ví dụ: BTC, ETH, SOL)!</td></tr>`;
      return;
    }

    tbody.innerHTML = data.tickers.map(t => {
      const changeClass = t.change_24h >= 0 ? "highlight-green" : "highlight-red";
      const changeSign = t.change_24h >= 0 ? "+" : "";

      return `
        <tr>
          <td>
            <div class="coin-cell">
              <span class="coin-badge">${t.coin}</span>
              <span style="font-size:0.8rem; color:var(--text-muted)">/USDT</span>
            </div>
          </td>
          <td><strong style="font-family:var(--font-mono)">${t.price_formatted}</strong></td>
          <td class="${changeClass}" style="font-family:var(--font-mono)"><strong>${changeSign}${t.change_24h}%</strong></td>
          <td>
            <div style="font-family:var(--font-mono); font-weight:700; color:var(--accent-cyan)">
              ${t.liquidity_formatted}
            </div>
          </td>
          <td><span class="tier-badge ${t.tier_badge}">${t.tier}</span></td>
          <td class="text-muted" style="font-family:var(--font-mono)">${t.spread_bps} bps</td>
          <td>
            <div class="switch-wrapper">
              <input type="checkbox" class="toggle-input" ${t.is_active ? 'checked' : ''} onchange="toggleCoin('${t.coin}')" title="Bật/Tắt quyền quét cho AI Swarm" />
              <span style="font-size:0.7rem; color:var(--text-dim)">${t.is_active ? 'Bật' : 'Tắt'}</span>
            </div>
          </td>
          <td style="text-align:center">
            <div class="row-actions" style="justify-content:center;">
              <button class="btn-table-action btn-scan-coin" onclick="triggerManualScan('${t.coin}')" title="Quét đồng coin này bằng AI Swarm">⚡ Quét</button>
              <button class="btn-table-action" onclick="changeChartCoin('${t.coin}', true)" title="Mở biểu đồ nến">📈 Biểu Đồ</button>
              <button class="btn-table-action" onclick="openDepthModal('${t.coin}')" title="Xem độ sâu sổ lệnh L2">📊 Độ Sâu</button>
              <button class="btn-table-action btn-del-coin" onclick="removeCoin('${t.coin}')" title="Xóa khỏi danh sách">✕</button>
            </div>
          </td>
        </tr>
      `;
    }).join("");

  } catch (err) {
    console.error("Error loading crypto watchlist:", err);
  }
}

// 4. Add & Remove Coins
async function addNewCoin() {
  const input = document.getElementById("new-coin-input");
  const raw = input.value.trim();
  if (!raw) return;

  try {
    const res = await fetch("/api/crypto/watchlist/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin: raw })
    });
    const result = await res.json();
    if (result.success) {
      input.value = "";
      await loadCryptoWatchlist(true);
      await loadPortfolio();
    } else {
      alert("Thông báo: " + result.message);
    }
  } catch (err) {
    alert("Lỗi khi thêm coin: " + err);
  }
}

async function quickAdd(coin) {
  try {
    const res = await fetch("/api/crypto/watchlist/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin: coin })
    });
    const result = await res.json();
    if (result.success) {
      await loadCryptoWatchlist(true);
      await loadPortfolio();
    } else {
      alert(result.message);
    }
  } catch (err) {
    console.error("Error quick adding:", err);
  }
}

async function removeCoin(coin) {
  if (!confirm(`Bạn có chắc muốn xóa ${coin} khỏi danh sách theo dõi?`)) return;
  try {
    const res = await fetch("/api/crypto/watchlist/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin: coin })
    });
    await loadCryptoWatchlist(true);
  } catch (err) {
    console.error("Error removing coin:", err);
  }
}

async function toggleCoin(coin) {
  try {
    await fetch("/api/crypto/watchlist/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin: coin })
    });
    await loadCryptoWatchlist(true);
  } catch (err) {
    console.error("Error toggling coin:", err);
  }
}

// 5. Order Book Depth Modal
async function openDepthModal(coin) {
  const modal = document.getElementById("depth-modal");
  const title = document.getElementById("modal-coin-title");
  const content = document.getElementById("modal-depth-content");

  title.textContent = `📊 Độ Sâu Sổ Lệnh L2 ${coin}/USDT (Binance L2)`;
  content.innerHTML = `<div class="text-center text-muted" style="padding: 25px;">Đang kết nối sổ lệnh L2 Binance cho ${coin}...</div>`;
  modal.classList.add("open");

  try {
    const res = await fetch(`/api/crypto/depth/${coin}`);
    const data = await res.json();
    if (data.error) {
      content.innerHTML = `<div class="highlight-red text-center" style="padding:20px;">Lỗi: ${data.error}</div>`;
      return;
    }

    const bidPct = Math.round((data.total_bid_usd / (data.total_bid_usd + data.total_ask_usd)) * 100);
    const askPct = 100 - bidPct;

    content.innerHTML = `
      <div class="depth-ratio-bar">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
          <span>Bên Mua (Bids): <strong>$${data.total_bid_usd.toLocaleString()}</strong> (${bidPct}%)</span>
          <span class="${data.sentiment_color}"><strong>${data.depth_sentiment}</strong></span>
          <span>Bên Bán (Asks): <strong>$${data.total_ask_usd.toLocaleString()}</strong> (${askPct}%)</span>
        </div>
        <div style="width:100%; height:8px; background:var(--accent-red); border-radius:4px; overflow:hidden; display:flex;">
          <div style="width:${bidPct}%; height:100%; background:var(--accent-green);"></div>
        </div>
        <div style="text-align:center; margin-top:6px; font-size:0.72rem; color:var(--text-dim)">
          Tỷ số Mua/Bán: <strong>${data.bid_ask_ratio}x</strong> (Trên 1.15x thể hiện lực gom mua áp đảo)
        </div>
      </div>

      <div class="depth-grid">
        <div>
          <h4 style="font-size:0.8rem; color:var(--accent-green); margin-bottom:8px;">🟢 TOP LỆNH ĐẶT MUA (BIDS)</h4>
          <table class="depth-subtable">
            <thead>
              <tr><th>Mức Giá ($)</th><th>Số Lượng</th><th>Tổng ($)</th></tr>
            </thead>
            <tbody>
              ${data.top_bids.map(b => `<tr><td style="color:var(--accent-green)">$${b.price.toLocaleString()}</td><td>${b.qty}</td><td>$${b.total.toLocaleString()}</td></tr>`).join('')}
            </tbody>
          </table>
        </div>

        <div>
          <h4 style="font-size:0.8rem; color:var(--accent-red); margin-bottom:8px;">🔴 TOP LỆNH ĐẶT BÁN (ASKS)</h4>
          <table class="depth-subtable">
            <thead>
              <tr><th>Mức Giá ($)</th><th>Số Lượng</th><th>Tổng ($)</th></tr>
            </thead>
            <tbody>
              ${data.top_asks.map(a => `<tr><td style="color:var(--accent-red)">$${a.price.toLocaleString()}</td><td>${a.qty}</td><td>$${a.total.toLocaleString()}</td></tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;

  } catch (err) {
    content.innerHTML = `<div class="highlight-red text-center" style="padding:20px;">Lỗi mạng khi tải sổ lệnh: ${err}</div>`;
  }
}

function closeDepthModal() {
  const modal = document.getElementById("depth-modal");
  modal.classList.remove("open");
}

// 6. Fetch & Render Prediction Markets Feed
async function loadMarkets() {
  const feed = document.getElementById("market-feed");
  try {
    const res = await fetch("/api/markets");
    if (!res.ok) return;
    const markets = await res.json();

    if (!markets || markets.length === 0) {
      feed.innerHTML = `<div class="text-muted text-center">Không có thị trường nào khả dụng.</div>`;
      return;
    }

    feed.innerHTML = markets.map(m => {
      return `
        <div class="market-item">
          <div class="market-info">
            <div class="market-question">${escapeHtml(m.question)}</div>
            <div class="market-meta">
              <span>🏷️ ${escapeHtml(m.category)}</span>
              <span>💰 Vol: $${(m.volume || 0).toLocaleString()}</span>
              <span>🌐 ${escapeHtml(m.source)}</span>
            </div>
          </div>
          <div class="market-odds">
            <span class="odd-pill odd-yes">CÓ ${Math.round(m.probability_yes * 100)}%</span>
            <span class="odd-pill odd-no">KHÔNG ${Math.round(m.probability_no * 100)}%</span>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    feed.innerHTML = `<div class="text-muted text-center">Lỗi khi tải thị trường.</div>`;
  }
}

// 7. Trigger Swarm Scan Manual Run (supports target coin or global)
async function triggerManualScan(coin = null) {
  const btn = document.getElementById("btn-scan");
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="btn-icon">⏳</span> AI ĐANG SUY LUẬN TRÊN ${coin || 'HỆ THỐNG'}...`;

  try {
    const body = coin ? JSON.stringify({ coin: coin }) : null;
    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body
    });
    const data = await res.json();
    await loadPortfolio();
    await loadCryptoWatchlist(true);
  } catch (err) {
    alert("Lỗi khi chạy quét AI: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}

// 8. Toggle Auto-Scan Mode
async function toggleAutoMode() {
  try {
    const res = await fetch("/api/auto/toggle", { method: "POST" });
    const data = await res.json();
    isAutoRunning = data.is_auto_running;
    updateAutoButtonState();
  } catch (err) {
    alert("Lỗi khi bật/tắt chế độ tự động: " + err);
  }
}

async function checkAutoStatus() {
  try {
    const res = await fetch("/api/auto/status");
    if (res.ok) {
      const data = await res.json();
      isAutoRunning = data.is_auto_running;
      updateAutoButtonState();
    }
  } catch (e) {}
}

function updateAutoButtonState() {
  const dot = document.getElementById("auto-dot");
  const text = document.getElementById("auto-text");
  if (isAutoRunning) {
    dot.className = "status-dot active";
    text.textContent = "VÒNG TỰ ĐỘNG: BẬT (30s)";
  } else {
    dot.className = "status-dot";
    text.textContent = "VÒNG TỰ ĐỘNG: TẮT";
  }
}

// 9. Reset Portfolio
async function resetPortfolio() {
  if (!confirm("Bạn có chắc chắn muốn đặt lại số dư vốn ảo về $1,000.00?")) return;
  try {
    await fetch("/api/portfolio/reset", { method: "POST" });
    await loadPortfolio();
  } catch (err) {
    alert("Lỗi khi đặt lại vốn danh mục: " + err);
  }
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

