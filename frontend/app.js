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
      // Configure dynamic price precision & minMove based on coin price scale
      const last = data.candles[data.candles.length - 1];
      const samplePrice = last ? last.close : 1.0;
      const priceFormatConfig = getPriceFormatOptions(samplePrice);
      candleSeries.applyOptions({
        priceFormat: priceFormatConfig
      });

      candleSeries.setData(data.candles);
      volumeSeries.setData(data.volumes);

      // Fit content nicely
      chartInstance.timeScale().fitContent();

      // Update banner with last candle
      const lastVol = data.volumes[data.volumes.length - 1];
      updateStatsBanner(last.open, last.high, last.low, last.close, lastVol ? lastVol.value : 0);

      // Render TP / SL / Entry / Liq price lines for active position
      updateChartPositionLines();
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

let activeChartPriceLines = [];
let currentOpenPositions = [];

function updateChartPositionLines() {
  if (!candleSeries) return;

  // Clear existing lines safely
  activeChartPriceLines.forEach(line => {
    try { candleSeries.removePriceLine(line); } catch (e) {}
  });
  activeChartPriceLines = [];

  if (!currentOpenPositions || currentOpenPositions.length === 0) return;

  // Find latest position matching currentChartCoin
  const matchingPos = currentOpenPositions.slice().reverse().find(p => {
    const sym = (p.symbol || p.question || "").toUpperCase();
    return sym.includes(currentChartCoin.toUpperCase());
  });

  if (!matchingPos) return;

  // Draw Entry line (Blue dashed)
  if (matchingPos.entry_price) {
    const entryLine = candleSeries.createPriceLine({
      price: matchingPos.entry_price,
      color: '#3b82f6',
      lineWidth: 2,
      lineStyle: 2, // Dashed
      axisLabelVisible: true,
      title: `VÀO (${matchingPos.outcome} ${matchingPos.leverage || 1}x)`
    });
    activeChartPriceLines.push(entryLine);
  }

  // Draw Take-Profit line (Green solid)
  if (matchingPos.take_profit) {
    const tpLine = candleSeries.createPriceLine({
      price: matchingPos.take_profit,
      color: '#10b981',
      lineWidth: 2,
      lineStyle: 0, // Solid
      axisLabelVisible: true,
      title: `TP: ${formatPriceNum(matchingPos.take_profit)}`
    });
    activeChartPriceLines.push(tpLine);
  }

  // Draw Stop-Loss line (Red solid)
  if (matchingPos.stop_loss) {
    const slLine = candleSeries.createPriceLine({
      price: matchingPos.stop_loss,
      color: '#ef4444',
      lineWidth: 2,
      lineStyle: 0, // Solid
      axisLabelVisible: true,
      title: `SL: ${formatPriceNum(matchingPos.stop_loss)}`
    });
    activeChartPriceLines.push(slLine);
  }

  // Draw Liquidation line (Amber dotted)
  if (matchingPos.liquidation_price) {
    const liqLine = candleSeries.createPriceLine({
      price: matchingPos.liquidation_price,
      color: '#f59e0b',
      lineWidth: 1,
      lineStyle: 3, // Dotted
      axisLabelVisible: true,
      title: `THANH LÝ: ${formatPriceNum(matchingPos.liquidation_price)}`
    });
    activeChartPriceLines.push(liqLine);
  }
}

window.closePosition = async function(positionId) {
  if (!confirm("Bạn có chắc chắn muốn đóng vị thế này ngay lập tức theo giá thị trường?")) return;
  try {
    const res = await fetch("/api/portfolio/close", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ position_id: positionId })
    });
    const data = await res.json();
    if (data.success) {
      loadPortfolio();
    } else {
      alert(data.message || "Không thể đóng vị thế.");
    }
  } catch (err) {
    console.error("Error closing position:", err);
  }
};

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

function getPriceFormatOptions(price) {
  if (price === undefined || price === null || price <= 0) {
    return { type: 'price', precision: 2, minMove: 0.01 };
  }

  let precision = 2;
  let minMove = 0.01;

  if (price >= 1000) {
    precision = 2;
    minMove = 0.01;
  } else if (price >= 10) {
    precision = 3;
    minMove = 0.001;
  } else if (price >= 1) {
    precision = 4;
    minMove = 0.0001;
  } else if (price >= 0.01) {
    precision = 5;
    minMove = 0.00001;
  } else if (price >= 0.0001) {
    // e.g. PIXEL ($0.00538) -> 6 decimals, step 0.000001
    precision = 6;
    minMove = 0.000001;
  } else if (price >= 0.000001) {
    // e.g. PEPE ($0.00000391) -> 8 decimals, step 0.00000001
    precision = 8;
    minMove = 0.00000001;
  } else {
    precision = 10;
    minMove = 0.0000000001;
  }

  return {
    type: 'price',
    precision: precision,
    minMove: minMove
  };
}

function formatPriceNum(num) {
  if (num === undefined || num === null || isNaN(num)) return "-";
  if (num >= 1000) return `$${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  if (num >= 10) return `$${num.toFixed(3)}`;
  if (num >= 1) return `$${num.toFixed(4)}`;
  if (num >= 0.01) return `$${num.toFixed(5)}`;
  if (num >= 0.0001) return `$${num.toFixed(6)}`;
  if (num >= 0.000001) return `$${num.toFixed(8)}`;
  return `$${num.toFixed(10)}`;
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

    currentOpenPositions = data.open_positions || [];
    updateChartPositionLines();

    if (data.open_positions.length === 0) {
      posTbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted">Chưa có vị thế nào. Hãy bấm "QUÉT THỊ TRƯỜNG NGAY" để AI vào lệnh Margin!</td></tr>`;
    } else {

      posTbody.innerHTML = data.open_positions.map(pos => {
        const isCrypto = pos.asset_type === "crypto";
        const outcome = pos.outcome || "LONG";
        const lev = pos.leverage || 1;
        const margin = pos.margin || pos.cost_basis || (pos.shares * pos.entry_price);

        let pnl = 0;
        let pnlPct = 0;

        if (outcome === "SHORT" || outcome === "NO") {
          pnl = (pos.entry_price - pos.current_price) * pos.shares;
        } else {
          pnl = (pos.current_price - pos.entry_price) * pos.shares;
        }
        pnlPct = margin > 0 ? (pnl / margin) * 100 : 0;

        const pnlClass = pnl >= 0 ? "highlight-green" : "highlight-red";
        let tagClass = "tag-outcome-yes";
        if (outcome === "NO" || outcome === "SHORT") {
          tagClass = "tag-outcome-no";
        }

        const sym = pos.symbol || pos.question.split("/")[0].replace("crypto_", "");
        const sharesStr = isCrypto ? (pos.shares < 1 ? pos.shares.toFixed(4) : pos.shares.toFixed(2)) : pos.shares.toFixed(1);
        const entryStr = isCrypto ? formatPriceNum(pos.entry_price) : `$${pos.entry_price.toFixed(2)}`;
        const currentStr = isCrypto ? formatPriceNum(pos.current_price) : `$${pos.current_price.toFixed(2)}`;
        const slStr = pos.stop_loss ? formatPriceNum(pos.stop_loss) : "-";
        const tpStr = pos.take_profit ? formatPriceNum(pos.take_profit) : "-";
        const liqStr = pos.liquidation_price ? formatPriceNum(pos.liquidation_price) : "-";

        return `
          <tr>
            <td>
              <strong>${escapeHtml(sym)}/USDT</strong>
              ${isCrypto ? '<span class="sub-badge" style="margin-left:4px; font-size:0.62rem">MARGIN</span>' : '<span class="sub-badge" style="margin-left:4px; font-size:0.62rem">PRED</span>'}
            </td>
            <td><span class="${tagClass}">${outcome} ${lev}x</span></td>
            <td>${sharesStr}</td>
            <td>${entryStr}</td>
            <td>${currentStr}</td>
            <td><span class="highlight-red" style="font-size:0.8rem; font-weight:600">${slStr}</span></td>
            <td><span class="highlight-green" style="font-size:0.8rem; font-weight:600">${tpStr}</span></td>
            <td><span style="color:#f59e0b; font-size:0.8rem; font-weight:600">${liqStr}</span></td>
            <td class="${pnlClass}">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)} (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)</td>
            <td>
              <button class="btn btn-outline" style="padding:2px 8px; font-size:0.75rem; border-color:#ef4444; color:#ef4444" onclick="closePosition('${pos.id}')">Đóng</button>
            </td>
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
            <td>${formatPriceNum(t.price)}</td>
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

// ============================================================
// 10. AI TRADE PLANNER & RISK COMMITTEE NEGOTIATION
// ============================================================

let currentPlannerValidationResult = null;
let lastSuggestedParams = null;

async function openTradePlannerModal(preselectCoin = null) {
  const modal = document.getElementById("planner-modal");
  if (!modal) return;

  const targetCoin = (preselectCoin || currentChartCoin || "BTC").toUpperCase();

  // Populate coin selector from watchlist
  const coinSelect = document.getElementById("plan-coin");
  if (coinSelect) {
    try {
      const res = await fetch("/api/crypto/watchlist");
      const data = await res.json();
      if (data.tickers && data.tickers.length > 0) {
        coinSelect.innerHTML = data.tickers.map(t => {
          const selected = t.coin.toUpperCase() === targetCoin ? "selected" : "";
          return `<option value="${t.coin}" ${selected}>${t.coin}/USDT - $${formatPriceNum(t.price)}</option>`;
        }).join("");
      }
    } catch (e) {}
  }

  // Reset results display
  resetPlannerAiDisplay();

  // Show modal
  modal.style.display = "flex";

  // Sync live price & defaults
  await syncPlannerWithLivePrice();
}

function closeTradePlannerModal() {
  const modal = document.getElementById("planner-modal");
  if (modal) modal.style.display = "none";
}

function resetPlannerAiDisplay() {
  currentPlannerValidationResult = null;
  lastSuggestedParams = null;

  const badge = document.getElementById("ai-verdict-badge");
  const sub = document.getElementById("ai-verdict-sub");
  const rationale = document.getElementById("ai-rationale-box");
  const metrics = document.getElementById("ai-metrics-panel");
  const suggestionBox = document.getElementById("ai-suggestion-box");
  const btnExec = document.getElementById("btn-execute-approved");

  if (badge) badge.style.display = "none";
  if (sub) sub.textContent = "Chờ kế hoạch từ bạn...";
  if (rationale) {
    rationale.innerHTML = `
      Nhập các điều kiện kế hoạch ở bên trái và bấm <strong>"Gửi AI Thẩm Định Kế Hoạch"</strong>.<br/>
      Hội đồng Rủi ro AI sẽ phân tích:
      <ul style="margin: 8px 0 0 16px; padding: 0; line-height: 1.6;">
        <li>Bẫy quét râu nến (Wick sweep) của cá mập</li>
        <li>Tỷ lệ Lời/Lỗ (Risk:Reward) có lợi thế thống kê không</li>
        <li>Khoảng cách an toàn tới Giá Thanh Lý</li>
        <li>Độ sâu sổ lệnh L2 và áp lực mua/bán thực tế</li>
      </ul>
    `;
  }
  if (metrics) metrics.style.display = "none";
  if (suggestionBox) suggestionBox.style.display = "none";
  if (btnExec) btnExec.style.display = "none";
}

async function syncPlannerWithLivePrice() {
  const coinSelect = document.getElementById("plan-coin");
  const priceInput = document.getElementById("plan-price");
  if (!coinSelect || !priceInput) return;

  const coin = coinSelect.value || "BTC";
  try {
    const res = await fetch(`/api/crypto/klines/${coin}?interval=1m&limit=1`);
    const data = await res.json();
    if (data.candles && data.candles.length > 0) {
      const lastPrice = data.candles[data.candles.length - 1].close;
      priceInput.value = lastPrice;

      // Auto set default SL (-2%) and TP (+4%) if empty
      const slInput = document.getElementById("plan-stop-loss");
      const tpInput = document.getElementById("plan-take-profit");
      const side = document.getElementById("plan-side").value || "LONG";

      if (slInput && !slInput.value) {
        slInput.value = (side === "SHORT" ? lastPrice * 1.02 : lastPrice * 0.98).toFixed(lastPrice < 1 ? 6 : 4);
      }
      if (tpInput && !tpInput.value) {
        tpInput.value = (side === "SHORT" ? lastPrice * 0.96 : lastPrice * 1.04).toFixed(lastPrice < 1 ? 6 : 4);
      }

      onStopLossChanged();
      recalculatePlannerEstimates();
    }
  } catch (e) {
    console.error("Error syncing planner price:", e);
  }
}

function onPlannerCoinChanged() {
  syncPlannerWithLivePrice();
}

function onStopLossChanged() {
  const slInput = document.getElementById("plan-stop-loss");
  const warningBox = document.getElementById("box-no-sl-warning");
  const chkNoSl = document.getElementById("chk-no-sl");

  if (!slInput || !warningBox) return;

  const val = parseFloat(slInput.value);
  if (isNaN(val) || val <= 0) {
    warningBox.style.display = "flex";
  } else {
    warningBox.style.display = "none";
    if (chkNoSl) chkNoSl.checked = false;
  }
  recalculatePlannerEstimates();
}

function onNoSlChecked() {
  recalculatePlannerEstimates();
}

function applyQuickSL(pct) {
  const priceInput = document.getElementById("plan-price");
  const slInput = document.getElementById("plan-stop-loss");
  const side = document.getElementById("plan-side").value || "LONG";
  if (!priceInput || !slInput) return;

  const p = parseFloat(priceInput.value);
  if (isNaN(p) || p <= 0) return;

  if (side === "SHORT") {
    slInput.value = (p * (1.0 + pct)).toFixed(p < 1 ? 6 : 4);
  } else {
    slInput.value = (p * (1.0 - pct)).toFixed(p < 1 ? 6 : 4);
  }
  onStopLossChanged();
}

function applyQuickTP(pct) {
  const priceInput = document.getElementById("plan-price");
  const tpInput = document.getElementById("plan-take-profit");
  const side = document.getElementById("plan-side").value || "LONG";
  if (!priceInput || !tpInput) return;

  const p = parseFloat(priceInput.value);
  if (isNaN(p) || p <= 0) return;

  if (side === "SHORT") {
    tpInput.value = (p * (1.0 - pct)).toFixed(p < 1 ? 6 : 4);
  } else {
    tpInput.value = (p * (1.0 + pct)).toFixed(p < 1 ? 6 : 4);
  }
  recalculatePlannerEstimates();
}

function recalculatePlannerEstimates() {
  const priceInput = document.getElementById("plan-price");
  const slInput = document.getElementById("plan-stop-loss");
  const tpInput = document.getElementById("plan-take-profit");
  const slCalc = document.getElementById("plan-sl-calc");
  const tpCalc = document.getElementById("plan-tp-calc");

  const p = parseFloat(priceInput ? priceInput.value : 0);
  const sl = parseFloat(slInput ? slInput.value : 0);
  const tp = parseFloat(tpInput ? tpInput.value : 0);

  if (slCalc) {
    if (!isNaN(p) && p > 0 && !isNaN(sl) && sl > 0) {
      const diffPct = ((sl - p) / p) * 100;
      slCalc.textContent = `${diffPct >= 0 ? '+' : ''}${diffPct.toFixed(2)}% so với giá vào`;
    } else {
      slCalc.textContent = "Chưa đặt (Tất tay)";
    }
  }

  if (tpCalc) {
    if (!isNaN(p) && p > 0 && !isNaN(tp) && tp > 0) {
      const diffPct = ((tp - p) / p) * 100;
      tpCalc.textContent = `${diffPct >= 0 ? '+' : ''}${diffPct.toFixed(2)}% so với giá vào`;
    } else {
      tpCalc.textContent = "Gồng lãi tự do";
    }
  }
}

async function submitPlanForAIValidation() {
  const coin = document.getElementById("plan-coin").value;
  const side = document.getElementById("plan-side").value;
  const timeframe = document.getElementById("plan-timeframe").value;
  const leverage = parseInt(document.getElementById("plan-leverage").value) || 3;
  const stake = parseFloat(document.getElementById("plan-stake").value) || 50.0;
  const price = parseFloat(document.getElementById("plan-price").value) || 0.0;
  const slVal = parseFloat(document.getElementById("plan-stop-loss").value);
  const tpVal = parseFloat(document.getElementById("plan-take-profit").value);
  const chkNoSl = document.getElementById("chk-no-sl");
  const noSlConfirmed = chkNoSl ? chkNoSl.checked : false;

  const btnSubmit = document.getElementById("btn-submit-plan");
  if (btnSubmit) {
    btnSubmit.disabled = true;
    btnSubmit.innerHTML = `⏳ ĐANG THẨM ĐỊNH RỦI RO...`;
  }

  try {
    const payload = {
      coin: coin,
      side: side,
      timeframe: timeframe,
      leverage: leverage,
      stake_amount: stake,
      stop_loss: !isNaN(slVal) && slVal > 0 ? slVal : null,
      take_profit: !isNaN(tpVal) && tpVal > 0 ? tpVal : null,
      no_sl_confirmed: noSlConfirmed
    };

    const res = await fetch("/api/ai/validate-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    currentPlannerValidationResult = data;
    renderAiValidationVerdict(data);

  } catch (err) {
    alert("Lỗi khi gửi thẩm định AI: " + err);
  } finally {
    if (btnSubmit) {
      btnSubmit.disabled = false;
      btnSubmit.innerHTML = `🧠 GỬI AI THẨM ĐỊNH KẾ HOẠCH`;
    }
  }
}

function renderAiValidationVerdict(res) {
  const badge = document.getElementById("ai-verdict-badge");
  const sub = document.getElementById("ai-verdict-sub");
  const rationale = document.getElementById("ai-rationale-box");
  const metrics = document.getElementById("ai-metrics-panel");
  const suggestionBox = document.getElementById("ai-suggestion-box");
  const btnExec = document.getElementById("btn-execute-approved");

  if (!badge || !rationale) return;

  badge.style.display = "inline-block";
  badge.className = `badge-verdict badge-verdict-${res.verdict.toLowerCase().includes('approved') ? 'approved' : (res.verdict === 'SUGGEST_ADJUSTMENT' ? 'suggest' : 'rejected')}`;
  badge.textContent = res.verdict === 'APPROVED' ? 'ĐÃ DUYỆT (APPROVED)' : (res.verdict === 'SUGGEST_ADJUSTMENT' ? 'CẦN ĐIỀU CHỈNH' : 'TỪ CHỐI (REJECTED)');

  if (sub) sub.textContent = res.title || "";

  rationale.innerHTML = `<strong>Đánh giá của Hội Đồng AI:</strong><br/>${escapeHtml(res.analysis)}`;

  // Metrics
  if (metrics) {
    metrics.style.display = "grid";
    const m = res.metrics || {};
    const valRR = document.getElementById("val-rr");
    const valLiq = document.getElementById("val-liq");
    const valRisk = document.getElementById("val-risk");
    const valReward = document.getElementById("val-reward");

    if (valRR) valRR.textContent = m.rr_ratio > 0 ? `1 : ${m.rr_ratio.toFixed(2)}` : "Không xác định";
    if (valLiq) valLiq.textContent = m.liq_price ? `$${formatPriceNum(m.liq_price)}` : "-";
    if (valRisk) valRisk.textContent = m.risk_dollars !== undefined ? `$${m.risk_dollars.toFixed(2)}` : "-";
    if (valReward) valReward.textContent = m.reward_dollars !== undefined && m.reward_dollars > 0 ? `+$${m.reward_dollars.toFixed(2)}` : "Mở (Gồng lãi)";
  }

  // Suggestion comparison
  if (res.verdict === "SUGGEST_ADJUSTMENT" && res.suggested_params && suggestionBox) {
    suggestionBox.style.display = "block";
    lastSuggestedParams = res.suggested_params;

    const tbody = document.getElementById("comparison-tbody");
    if (tbody) {
      const userLev = document.getElementById("plan-leverage").value;
      const userSl = document.getElementById("plan-stop-loss").value || "Tất tay";
      const userTp = document.getElementById("plan-take-profit").value || "Gồng lãi";

      tbody.innerHTML = `
        <tr>
          <td>Đòn bẩy:</td>
          <td>${userLev}x</td>
          <td style="color:#f59e0b; font-weight:700">${res.suggested_params.leverage}x</td>
        </tr>
        <tr>
          <td>Cắt lỗ (SL):</td>
          <td>${userSl !== "Tất tay" ? '$' + formatPriceNum(parseFloat(userSl)) : 'Tất tay'}</td>
          <td style="color:#10b981; font-weight:700">${res.suggested_params.stop_loss ? '$' + formatPriceNum(res.suggested_params.stop_loss) : '-'}</td>
        </tr>
        <tr>
          <td>Chốt lời (TP):</td>
          <td>${userTp !== "Gồng lãi" ? '$' + formatPriceNum(parseFloat(userTp)) : 'Gồng lãi'}</td>
          <td style="color:#10b981; font-weight:700">${res.suggested_params.take_profit ? '$' + formatPriceNum(res.suggested_params.take_profit) : '-'}</td>
        </tr>
      `;
    }
  } else if (suggestionBox) {
    suggestionBox.style.display = "none";
  }

  // Action button
  if (btnExec) {
    if (res.verdict === "APPROVED") {
      btnExec.style.display = "block";
      btnExec.textContent = `🚀 XÁC NHẬN VÀO LỆNH NGAY`;
    } else {
      btnExec.style.display = "none";
    }
  }
}

function applyAiSuggestedParams() {
  if (!lastSuggestedParams) return;

  if (lastSuggestedParams.side) {
    const sideEl = document.getElementById("plan-side");
    if (sideEl) sideEl.value = lastSuggestedParams.side;
  }
  if (lastSuggestedParams.leverage) {
    const levEl = document.getElementById("plan-leverage");
    if (levEl) levEl.value = lastSuggestedParams.leverage;
  }
  if (lastSuggestedParams.stop_loss) {
    const slEl = document.getElementById("plan-stop-loss");
    if (slEl) slEl.value = lastSuggestedParams.stop_loss;
    onStopLossChanged();
  }
  if (lastSuggestedParams.take_profit) {
    const tpEl = document.getElementById("plan-take-profit");
    if (tpEl) tpEl.value = lastSuggestedParams.take_profit;
  }

  recalculatePlannerEstimates();

  // Re-submit for AI approval automatically
  submitPlanForAIValidation();
}

async function executeApprovedPlan() {
  const coin = document.getElementById("plan-coin").value;
  const side = document.getElementById("plan-side").value;
  const leverage = parseInt(document.getElementById("plan-leverage").value) || 3;
  const stake = parseFloat(document.getElementById("plan-stake").value) || 50.0;
  const price = parseFloat(document.getElementById("plan-price").value) || 0.0;
  const slVal = parseFloat(document.getElementById("plan-stop-loss").value);
  const tpVal = parseFloat(document.getElementById("plan-take-profit").value);

  const payload = {
    coin: coin,
    side: side === "AUTO" ? (currentPlannerValidationResult?.suggested_params?.side || "LONG") : side,
    leverage: leverage,
    stake_amount: stake,
    price: price,
    stop_loss: !isNaN(slVal) && slVal > 0 ? slVal : null,
    take_profit: !isNaN(tpVal) && tpVal > 0 ? tpVal : null,
    reasoning: `Lệnh đã qua Hội đồng Rủi ro AI thẩm định (Verdict: APPROVED)`
  };

  const btnExec = document.getElementById("btn-execute-approved");
  if (btnExec) {
    btnExec.disabled = true;
    btnExec.textContent = "⏳ ĐANG KHỚP LỆNH...";
  }

  try {
    const res = await fetch("/api/ai/execute-planned-trade", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.success) {
      closeTradePlannerModal();
      await loadPortfolio();
      // Switch chart to this coin to see the lines!
      changeChartCoin(coin, true);
    } else {
      alert("Khớp lệnh không thành công: " + (data.message || "Vui lòng kiểm tra lại số dư"));
    }
  } catch (err) {
    alert("Lỗi khi khớp lệnh: " + err);
  } finally {
    if (btnExec) {
      btnExec.disabled = false;
      btnExec.textContent = "🚀 XÁC NHẬN VÀO LỆNH NGAY";
    }
  }
}

