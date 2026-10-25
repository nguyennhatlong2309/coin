let isAutoRunning = false;
let autoStatusInterval = null;

// ============================================================
// NOTIFICATION SYSTEM & AGENT ANIMATION ENGINE
// ============================================================
const NOTIF_STORAGE_KEY = "quantdesk_notifications_v2";
let notifications = [];
window._notifActions = {};

function initNotificationSystem() {
  loadStoredNotifications();
  updateNotificationBadge();
  renderNotificationList();

  // Override window.alert globally so native browser alert never blocks execution
  window.alert = function(msg) {
    showNotification({
      type: "info",
      title: "Thông Báo Hệ Thống",
      message: String(msg)
    });
  };
}

function loadStoredNotifications() {
  try {
    const raw = localStorage.getItem(NOTIF_STORAGE_KEY);
    if (raw) {
      notifications = JSON.parse(raw);
    }
  } catch (e) {
    notifications = [];
  }
}

function saveStoredNotifications() {
  try {
    localStorage.setItem(NOTIF_STORAGE_KEY, JSON.stringify(notifications.slice(0, 50)));
  } catch (e) {
    console.warn("Cannot save notifications:", e);
  }
}

function updateNotificationBadge() {
  const badge = document.getElementById("notify-badge");
  const drawerCount = document.getElementById("notify-drawer-count-badge");
  const unreadCount = notifications.filter(n => !n.isRead).length;

  if (badge) {
    badge.textContent = unreadCount;
    if (unreadCount === 0) {
      badge.classList.add("zero");
    } else {
      badge.classList.remove("zero");
    }
  }
  if (drawerCount) {
    drawerCount.textContent = `${unreadCount} CHƯA ĐỌC • ${notifications.length} TỔNG CỘNG`;
  }
}

function showNotification({
  type = "info", // "success", "info", "ai", "warning", "error"
  title = "Thông Báo",
  message = "",
  duration = 5500,
  action = null,
  actionLabel = "Bấm để xem chi tiết →"
}) {
  const id = "notif_" + Date.now() + "_" + Math.floor(Math.random() * 1000);
  const notifObj = {
    id,
    type,
    title,
    message,
    time: Date.now(),
    isRead: false,
    hasAction: !!action,
    actionLabel
  };

  if (action && typeof action === "function") {
    window._notifActions[id] = action;
  }

  // Add to drawer storage
  notifications.unshift(notifObj);
  if (notifications.length > 50) notifications.pop();
  saveStoredNotifications();
  updateNotificationBadge();
  renderNotificationList();

  // Spawn floating corner toast
  createToastItem(notifObj, duration, actionLabel);
  return id;
}

function createToastItem(notif, duration, actionLabel) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast-item toast-${notif.type}`;
  toast.id = `toast-${notif.id}`;

  const iconMap = {
    success: "✅",
    info: "ℹ️",
    ai: "🤖",
    warning: "⚠️",
    error: "❌"
  };
  const icon = iconMap[notif.type] || "🔔";

  toast.innerHTML = `
    <div class="toast-header">
      <div class="toast-title-group">
        <span class="toast-icon">${icon}</span>
        <span class="toast-title">${escapeHtml(notif.title)}</span>
      </div>
      <button class="toast-close-btn" title="Đóng" onclick="event.stopPropagation(); dismissToast('${notif.id}')">✕</button>
    </div>
    <div class="toast-message">${escapeHtml(notif.message)}</div>
    <div class="toast-hint">${escapeHtml(actionLabel)}</div>
    <div class="toast-progress" style="animation-duration: ${duration}ms;"></div>
  `;

  // Clicking toast opens notification or executes action
  toast.addEventListener("click", () => {
    if (window._notifActions && window._notifActions[notif.id]) {
      window._notifActions[notif.id]();
    } else {
      openNotificationDrawer();
      highlightNotificationInDrawer(notif.id);
    }
    dismissToast(notif.id);
  });

  container.appendChild(toast);

  toast._dismissTimer = setTimeout(() => {
    dismissToast(notif.id);
  }, duration);
}

function dismissToast(id) {
  const toast = document.getElementById(`toast-${id}`);
  if (!toast) return;
  if (toast._dismissTimer) clearTimeout(toast._dismissTimer);

  toast.classList.add("removing");
  setTimeout(() => {
    if (toast.parentNode) {
      toast.parentNode.removeChild(toast);
    }
  }, 280);
}

function toggleNotificationDrawer() {
  const drawer = document.getElementById("notification-drawer");
  if (!drawer) return;
  if (drawer.classList.contains("open")) {
    closeNotificationDrawer();
  } else {
    openNotificationDrawer();
  }
}

function openNotificationDrawer() {
  const drawer = document.getElementById("notification-drawer");
  const backdrop = document.getElementById("notification-backdrop");
  if (drawer) drawer.classList.add("open");
  if (backdrop) backdrop.classList.add("open");
  renderNotificationList();
}

function closeNotificationDrawer() {
  const drawer = document.getElementById("notification-drawer");
  const backdrop = document.getElementById("notification-backdrop");
  if (drawer) drawer.classList.remove("open");
  if (backdrop) backdrop.classList.remove("open");
}

function markAllNotificationsRead() {
  notifications.forEach(n => n.isRead = true);
  saveStoredNotifications();
  updateNotificationBadge();
  renderNotificationList();
}

function clearAllNotifications() {
  notifications = [];
  saveStoredNotifications();
  updateNotificationBadge();
  renderNotificationList();
}

function renderNotificationList() {
  const list = document.getElementById("notification-list");
  if (!list) return;

  if (!notifications || notifications.length === 0) {
    list.innerHTML = `
      <div class="notify-empty-state">
        <span style="font-size: 2.2rem;">🔕</span>
        <div style="font-weight: 700; margin-top: 10px; color: #fff;">Chưa có thông báo nào</div>
        <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 4px; max-width: 260px;">
          Các sự kiện vào lệnh, khớp TP/SL, và kết quả quét AI sẽ được lưu trữ tự động tại đây.
        </div>
      </div>
    `;
    return;
  }

  const iconMap = {
    success: "✅",
    info: "ℹ️",
    ai: "🤖",
    warning: "⚠️",
    error: "❌"
  };

  list.innerHTML = notifications.map(n => {
    const timeStr = formatNotificationTime(n.time);
    const icon = iconMap[n.type] || "🔔";
    const unreadClass = n.isRead ? "" : "unread";

    return `
      <div class="notify-item type-${n.type} ${unreadClass}" id="notify-item-${n.id}" onclick="handleNotificationClick('${n.id}')">
        <div class="notify-item-header">
          <div class="notify-item-title-wrap">
            <span class="notify-item-icon">${icon}</span>
            <span class="notify-item-title">${escapeHtml(n.title)}</span>
          </div>
          <span class="notify-item-time">${timeStr}</span>
        </div>
        <div class="notify-item-body">${escapeHtml(n.message)}</div>
        ${n.hasAction ? `
          <div class="notify-item-footer">
            <button class="notify-item-action-btn">${escapeHtml(n.actionLabel || "Xem chi tiết →")}</button>
          </div>
        ` : ""}
      </div>
    `;
  }).join("");
}

function handleNotificationClick(id) {
  const item = notifications.find(n => n.id === id);
  if (item) {
    item.isRead = true;
    saveStoredNotifications();
    updateNotificationBadge();
    const el = document.getElementById(`notify-item-${id}`);
    if (el) el.classList.remove("unread");

    if (window._notifActions && window._notifActions[id]) {
      closeNotificationDrawer();
      window._notifActions[id]();
    }
  }
}

function highlightNotificationInDrawer(id) {
  setTimeout(() => {
    const el = document.getElementById(`notify-item-${id}`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      el.style.borderColor = "var(--accent-cyan)";
      el.style.boxShadow = "0 0 16px rgba(0, 240, 255, 0.4)";
      setTimeout(() => {
        el.style.borderColor = "";
        el.style.boxShadow = "";
      }, 2000);
    }
  }, 100);
}

function formatNotificationTime(ts) {
  if (!ts) return "";
  const diffSec = Math.floor((Date.now() - ts) / 1000);
  if (diffSec < 10) return "Vừa xong";
  if (diffSec < 60) return `${diffSec}s trước`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m trước`;
  const diffHours = Math.floor(diffMin / 60);
  if (diffHours < 24) return `${diffHours}h trước`;
  const d = new Date(ts);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}

// ============================================================
// AGENT ANIMATIONS & LIVE STATUS VISUALS
// ============================================================
const AGENT_KEYS = ["spotter", "researcher", "pricer", "kelly"];

function setAgentActive(agentKey, isActive, customStatusText = null) {
  const card = document.getElementById(`agent-card-${agentKey}`);
  const statusEl = document.getElementById(`agent-status-${agentKey}`);
  if (!card) return;

  if (isActive) {
    card.classList.add("agent-active", `active-${agentKey}`);
    if (statusEl) {
      const textNode = statusEl.querySelector(".agent-status-text");
      if (textNode) {
        textNode.textContent = customStatusText || "ĐANG HOẠT ĐỘNG...";
      }
    }
  } else {
    card.classList.remove("agent-active", `active-${agentKey}`);
    if (statusEl) {
      const textNode = statusEl.querySelector(".agent-status-text");
      if (textNode) {
        textNode.textContent = "SẴN SÀNG";
      }
    }
  }
}

function resetAllAgents() {
  AGENT_KEYS.forEach(k => setAgentActive(k, false));
  const panel = document.getElementById("thought-panel");
  if (panel) {
    panel.classList.remove("flash-spotter", "flash-researcher", "flash-pricer", "flash-kelly", "flash-trade");
  }
}

let thoughtFlashTimer = null;
function flashThoughtPanel(agentKey, duration = 2600) {
  const panel = document.getElementById("thought-panel");
  const liveIndicator = document.getElementById("thought-live-indicator");
  if (!panel) return;

  // Clear previous flash states
  panel.classList.remove("flash-spotter", "flash-researcher", "flash-pricer", "flash-kelly", "flash-trade");

  if (!agentKey) return;
  const key = agentKey.toLowerCase();
  let flashClass = "";
  let label = "TRỰC TIẾP";
  let color = "";

  if (key.includes("spotter")) {
    flashClass = "flash-spotter";
    label = "⚡ SPOTTER ĐANG NÓI...";
    color = "var(--accent-cyan)";
  } else if (key.includes("researcher")) {
    flashClass = "flash-researcher";
    label = "🌐 RESEARCHER ĐANG NÓI...";
    color = "var(--accent-blue)";
  } else if (key.includes("pricer")) {
    flashClass = "flash-pricer";
    label = "📊 THE PRICER ĐANG NÓI...";
    color = "var(--accent-purple)";
  } else if (key.includes("kelly")) {
    flashClass = "flash-kelly";
    label = "🛡️ KELLY RISK ĐANG NÓI...";
    color = "var(--accent-gold)";
  } else if (key.includes("executor") || key.includes("trade")) {
    flashClass = "flash-trade";
    label = "🚀 KHỚP LỆNH MOCK...";
    color = "var(--accent-green)";
  }

  if (flashClass) {
    panel.classList.add(flashClass);
    if (liveIndicator) {
      liveIndicator.textContent = label;
      liveIndicator.style.borderColor = color;
      liveIndicator.style.color = color;
      liveIndicator.style.boxShadow = `0 0 12px ${color}`;
    }

    if (thoughtFlashTimer) clearTimeout(thoughtFlashTimer);
    thoughtFlashTimer = setTimeout(() => {
      panel.classList.remove(flashClass);
      if (liveIndicator) {
        liveIndicator.textContent = "TRỰC TIẾP";
        liveIndicator.style.borderColor = "";
        liveIndicator.style.color = "";
        liveIndicator.style.boxShadow = "";
      }
    }, duration);
  }
}

let agentCycleTimer = null;
function playAgentSequence(targetCoin = null) {
  if (agentCycleTimer) clearTimeout(agentCycleTimer);
  resetAllAgents();

  const coinLabel = targetCoin ? targetCoin.toUpperCase() : "THỊ TRƯỜNG";
  const steps = [
    { key: "spotter", text: `ĐANG SĂN KÈO ${coinLabel}...`, duration: 700 },
    { key: "researcher", text: `ĐANG CÀO GOOGLE NEWS...`, duration: 900 },
    { key: "pricer", text: `ĐANG TÍNH STATS (Δp)...`, duration: 900 },
    { key: "kelly", text: `ĐANG QUẢN TRỊ RỦI RO KELLY...`, duration: 1000 }
  ];

  let currentIdx = 0;
  function runStep() {
    if (currentIdx >= steps.length) {
      setTimeout(() => {
        resetAllAgents();
      }, 1500);
      return;
    }

    const step = steps[currentIdx];
    AGENT_KEYS.forEach(k => {
      if (k !== step.key) setAgentActive(k, false);
    });
    setAgentActive(step.key, true, step.text);
    flashThoughtPanel(step.key, step.duration);

    currentIdx++;
    agentCycleTimer = setTimeout(runStep, step.duration);
  }

  runStep();
}

function pulseAgentLight(key, statusText) {
  setAgentActive(key, true, statusText);
  flashThoughtPanel(key, 2600);
  setTimeout(() => {
    setAgentActive(key, false);
  }, 2600);
}

// Chart State
let chartInstance = null;
let candleSeries = null;
let volumeSeries = null;
let currentChartCoin = "BTC";
let currentChartInterval = "1h";

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  initNotificationSystem();
  loadPortfolio();
  loadTradesHistory();
  loadStrategyProfiles();
  loadCryptoWatchlist(true);
  initCoinSearchAutocomplete();
  initChart();
  loadChartData(currentChartCoin, currentChartInterval);
  loadMarkets();
  checkAutoStatus();
  fetchBinanceStatus();
  fetch("/api/discovery/latest").then(r => r.json()).then(renderDiscoveryReport).catch(()=>{});

  // Periodic portfolio poll (every 3 seconds)
  setInterval(() => {
    loadPortfolio();
    checkAutoStatus();
  }, 3000);

  // Periodic crypto watchlist poll (every 5 seconds)
  setInterval(() => {
    loadCryptoWatchlist(false);
  }, 5000);

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
      showNotification({
        type: "success",
        title: "Đã Đóng Vị Thế",
        message: "Vị thế đã được tất toán thành công theo giá thị trường.",
        duration: 5000
      });
    } else {
      showNotification({
        type: "error",
        title: "Không Thể Đóng Vị Thế",
        message: data.message || "Không thể đóng vị thế.",
        duration: 6000
      });
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Đóng Vị Thế",
      message: "Lỗi kết nối: " + err,
      duration: 6000
    });
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

    currentPortfolioCash = data.cash_balance;
    currentPortfolioEquity = data.total_equity;

    equityEl.textContent = `$${data.total_equity.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    cashEl.textContent = `Tiền mặt: $${data.cash_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

    const pnlSign = data.total_pnl >= 0 ? "+" : "";
    pnlEl.textContent = `${pnlSign}$${data.total_pnl.toFixed(2)} (${pnlSign}${data.pnl_percent.toFixed(1)}%)`;
    pnlEl.className = `kpi-value ${data.total_pnl >= 0 ? 'highlight-green' : 'highlight-red'}`;

    realizedEl.textContent = `Đã chốt: $${data.realized_pnl.toFixed(2)} • Tạm tính: $${data.unrealized_pnl.toFixed(2)}`;
    winrateEl.textContent = `${data.win_rate.toFixed(1)}%`;
    tradesEl.textContent = `${data.trades_count} Lệnh • ${data.total_open_count} Vị thế mở`;

    // Trading Memory count badge in Header
    const memoryBadge = document.getElementById("header-memory-count");
    if (memoryBadge && data.trading_memory) {
      memoryBadge.textContent = data.trading_memory.total_reflections || 0;
    }

    // Session Display in Header
    if (data.current_session) {
      updateSessionDisplay(data.current_session);
    }

    // Daily Metrics & Circuit Breaker
    if (data.daily_metrics) {
      updateDailyMetricsUI(data.daily_metrics, data.total_equity);
    }

    // Dedicated Coin Workers Live Grid
    if (data.swarm_workers) {
      updateCoinWorkersUI(data.swarm_workers);
    }

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

    // Terminal Thought Stream & Dynamic Agent Pulse
    const terminal = document.getElementById("thought-terminal");
    if (data.thought_logs && data.thought_logs.length > 0) {
      terminal.innerHTML = data.thought_logs.map(log => {
        let tagClass = "tag-sys";
        const ag = (log.agent || "").toLowerCase();
        if (ag.includes("spotter")) tagClass = "tag-spotter";
        else if (ag.includes("bull")) tagClass = "tag-bull";
        else if (ag.includes("bear")) tagClass = "tag-bear";
        else if (ag.includes("manager")) tagClass = "tag-manager";
        else if (ag.includes("memory")) tagClass = "tag-memory";
        else if (ag.includes("researcher")) tagClass = "tag-researcher";
        else if (ag.includes("pricer")) tagClass = "tag-pricer";
        else if (ag.includes("kelly")) tagClass = "tag-kelly";
        else if (ag.includes("executor") || log.level === "TRADE") tagClass = "tag-trade";
        else if (log.level === "WARN") tagClass = "tag-warn";

        let msgHtml = escapeHtml(log.message);
        if (msgHtml.includes("[SMC Smart Money]")) {
          msgHtml = msgHtml.replace("[SMC Smart Money]", '<span class="badge-smc-log">⚡ KỸ NĂNG 1: SMC CONCEPTS</span>');
        }
        if (msgHtml.includes("[SMC Sniper SL]")) {
          msgHtml = msgHtml.replace("[SMC Sniper SL]", '<span class="badge-smc-sl">🎯 SMC SNIPER SL</span>');
        }
        if (msgHtml.includes("[Tranh Luận Phe Bò]")) {
          msgHtml = msgHtml.replace("[Tranh Luận Phe Bò]", '<span class="badge-bull-log">🐂 PHE BÒ (BULL)</span>');
        }
        if (msgHtml.includes("[Tranh Luận Phe Gấu]")) {
          msgHtml = msgHtml.replace("[Tranh Luận Phe Gấu]", '<span class="badge-bear-log">🐻 PHE GẤU (BEAR)</span>');
        }
        if (msgHtml.includes("[Tổng Hợp Tranh Biện]")) {
          msgHtml = msgHtml.replace("[Tổng Hợp Tranh Biện]", '<span class="badge-manager-log">⚖️ TỔNG HỢP TRANH BIỆN</span>');
        }
        if (msgHtml.includes("[Trí Nhớ AI")) {
          msgHtml = msgHtml.replace(/\[Trí Nhớ AI([^\]]*)\]/, '<span class="badge-memory-log">🧠 TRÍ NHỚ AI$1</span>');
        }
        if (msgHtml.includes("[Quy Tắc Phòng Vệ]")) {
          msgHtml = msgHtml.replace("[Quy Tắc Phòng Vệ]", '<span class="badge-defense-log">🛡️ QUY TẮC PHÒNG VỆ</span>');
        }
        if (msgHtml.includes("[Cảnh Báo Suy Giảm Hiệu Quả - Alpha Decay]")) {
          msgHtml = msgHtml.replace("[Cảnh Báo Suy Giảm Hiệu Quả - Alpha Decay]", '<span class="badge-decay-log">⚡ ALPHA DECAY</span>');
        }
        if (msgHtml.includes("[Phòng Vệ Alpha Decay]")) {
          msgHtml = msgHtml.replace("[Phòng Vệ Alpha Decay]", '<span class="badge-defense-log">⚡ PHÒNG VỆ ALPHA DECAY</span>');
        }

        return `<div class="terminal-line"><span class="log-time">[${log.timestamp}]</span> <span class="log-tag ${tagClass}">[${escapeHtml(log.agent)}]</span> ${msgHtml}</div>`;
      }).join("");

      // Dynamically highlight active agent & flash parent thought panel from latest thought log
      const latest = data.thought_logs[0];
      if (latest && !agentCycleTimer) {
        const ag = (latest.agent || "").toLowerCase();
        if (ag.includes("spotter")) pulseAgentLight("spotter", "Đang săn kèo & lọc coin");
        else if (ag.includes("researcher")) pulseAgentLight("researcher", "Đang đọc tin tức Google");
        else if (ag.includes("pricer")) pulseAgentLight("pricer", "Đang định giá thống kê");
        else if (ag.includes("kelly")) pulseAgentLight("kelly", "Đang quản trị rủi ro Kelly");
        else if (ag.includes("executor") || latest.level === "TRADE") flashThoughtPanel("trade", 2600);
      }
    }

    // Trade History: Auto sync when new trade occurs
    if (data.trades_count !== undefined && data.trades_count !== tradeHistoryState.lastTradesCount) {
      tradeHistoryState.lastTradesCount = data.trades_count;
      if (tradeHistoryState.offset === 0) {
        loadTradesHistory();
      } else {
        const tradesCountBadge = document.getElementById("trades-count-badge");
        if (tradesCountBadge) {
          tradesCountBadge.textContent = `${tradeHistoryState.filtered_count} LỆNH (TỔNG ${data.trades_count})`;
        }
      }
    }
  } catch (err) {
    console.error("Error polling portfolio:", err);
  }
}

// ============================================================
// 2.1 PAGINATED & FILTERED TRADE HISTORY ENGINE
// ============================================================
let tradeHistoryState = {
  limit: 50,
  offset: 0,
  symbol: "ALL",
  filter_type: "all",
  total_count: 0,
  filtered_count: 0,
  lastTradesCount: -1,
  isLoading: false
};

async function loadTradesHistory() {
  if (tradeHistoryState.isLoading) return;
  tradeHistoryState.isLoading = true;

  try {
    const params = new URLSearchParams({
      limit: tradeHistoryState.limit,
      offset: tradeHistoryState.offset,
      symbol: tradeHistoryState.symbol,
      filter_type: tradeHistoryState.filter_type
    });

    const res = await fetch(`/api/portfolio/trades?${params.toString()}`);
    if (!res.ok) throw new Error("Failed to fetch trades");
    const data = await res.json();

    tradeHistoryState.total_count = data.total_count || 0;
    tradeHistoryState.filtered_count = data.filtered_count || 0;

    // Populate symbols dropdown dynamically if needed
    const symSelect = document.getElementById("trade-filter-symbol");
    if (symSelect && data.symbols && data.symbols.length > 0 && symSelect.options.length <= 1) {
      data.symbols.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        opt.textContent = `${s} (${s}/USDT)`;
        symSelect.appendChild(opt);
      });
      if (tradeHistoryState.symbol !== "ALL") {
        symSelect.value = tradeHistoryState.symbol;
      }
    }

    // Update Header Badges with filtered stats
    const tradesCountBadge = document.getElementById("trades-count-badge");
    const tradesPnlBadge = document.getElementById("trades-pnl-summary-badge");
    const tradesWinRateBadge = document.getElementById("trades-win-rate-badge");

    if (tradesCountBadge) {
      if (tradeHistoryState.filtered_count === tradeHistoryState.total_count) {
        tradesCountBadge.textContent = `${data.total_count} LỆNH ĐÃ KHỚP`;
      } else {
        tradesCountBadge.textContent = `LỌC: ${data.filtered_count} / ${data.total_count} LỆNH`;
      }
    }
    if (tradesPnlBadge && data.stats) {
      const pnlVal = data.stats.realized_pnl || 0;
      const isPos = pnlVal >= 0;
      tradesPnlBadge.textContent = `LÃI ĐÃ CHỐT: ${isPos ? '+' : ''}$${pnlVal.toFixed(2)}`;
      tradesPnlBadge.style.color = isPos ? "#10b981" : "#ef4444";
      tradesPnlBadge.style.borderColor = isPos ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)";
      tradesPnlBadge.style.background = isPos ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)";
    }
    if (tradesWinRateBadge && data.stats) {
      const wr = data.stats.win_rate || 0;
      tradesWinRateBadge.textContent = `THẮNG: ${wr}% (${data.stats.win_count}W - ${data.stats.loss_count}L)`;
      tradesWinRateBadge.style.color = wr >= 50 ? "#10b981" : "#f59e0b";
      tradesWinRateBadge.style.borderColor = wr >= 50 ? "rgba(16, 185, 129, 0.4)" : "rgba(245, 158, 11, 0.4)";
      tradesWinRateBadge.style.background = wr >= 50 ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)";
    }

    // Update Pagination Controls
    const paginationInfo = document.getElementById("trades-pagination-info");
    const pageIndicator = document.getElementById("trades-current-page");
    const btnPrev = document.getElementById("btn-trades-prev");
    const btnNext = document.getElementById("btn-trades-next");

    const totalF = data.filtered_count;
    const limit = tradeHistoryState.limit;
    const offset = tradeHistoryState.offset;

    if (limit === 0 || limit >= totalF) {
      if (paginationInfo) paginationInfo.textContent = `Hiển thị toàn bộ ${totalF} lệnh`;
      if (pageIndicator) pageIndicator.textContent = "1 / 1";
      if (btnPrev) btnPrev.disabled = true;
      if (btnNext) btnNext.disabled = true;
    } else {
      const startIdx = totalF > 0 ? offset + 1 : 0;
      const endIdx = Math.min(offset + limit, totalF);
      const curPage = Math.floor(offset / limit) + 1;
      const totalPages = Math.ceil(totalF / limit) || 1;

      if (paginationInfo) paginationInfo.textContent = `Hiển thị ${startIdx} - ${endIdx} / ${totalF} lệnh`;
      if (pageIndicator) pageIndicator.textContent = `${curPage} / ${totalPages}`;
      if (btnPrev) btnPrev.disabled = offset <= 0;
      if (btnNext) btnNext.disabled = offset + limit >= totalF;
    }

    renderTradesTable(data.trades || []);
  } catch (err) {
    console.error("Error loading trades history:", err);
  } finally {
    tradeHistoryState.isLoading = false;
  }
}

function renderTradesTable(trades) {
  const tradesTbody = document.getElementById("trades-tbody");
  if (!tradesTbody) return;

  if (!trades || trades.length === 0) {
    tradesTbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted" style="padding:28px;">Không tìm thấy lệnh nào phù hợp với bộ lọc.</td></tr>`;
    return;
  }

  tradesTbody.innerHTML = trades.map(t => {
    const actionStr = (t.action || "").toUpperCase();
    const isClose = actionStr.startsWith("CLOSE");
    const isOpen = actionStr.startsWith("OPEN");
    const isLong = actionStr.includes("LONG") || actionStr.includes("BUY") || actionStr.includes("YES");
    const lev = t.leverage ? `${t.leverage}x` : "";

    // Action badge rendering
    let actionBadge = "";
    if (isClose) {
      const reason = (t.reason || "").toUpperCase();
      if (reason === "TAKE_PROFIT") {
        actionBadge = `<span class="badge-action-tp">🎯 CHỐT LỜI (TP)</span>`;
      } else if (reason === "STOP_LOSS") {
        actionBadge = `<span class="badge-action-sl">🛑 CẮT LỖ (SL)</span>`;
      } else if (reason === "LIQUIDATION") {
        actionBadge = `<span class="badge-action-liq">⚠️ THANH LÝ</span>`;
      } else {
        const cleanAction = actionStr.replace("CLOSE_", "");
        actionBadge = `<span class="badge-action-close">✋ ĐÓNG ${cleanAction}</span>`;
      }
    } else if (isOpen) {
      if (isLong) {
        actionBadge = `<span class="badge-action-long">🟢 MỞ LONG ${lev}</span>`;
      } else {
        actionBadge = `<span class="badge-action-short">🔴 MỞ SHORT ${lev}</span>`;
      }
    } else {
      actionBadge = `<span class="tag-outcome-yes">${escapeHtml(actionStr)}</span>`;
    }

    // Price formatting
    const priceVal = (t.price !== undefined && t.price !== null) ? Number(t.price) : (t.exit_price || t.entry_price || 0);
    let priceHtml = `<div style="font-family:var(--font-mono); font-weight:600;">${formatPriceNum(priceVal)}</div>`;
    if (isClose && t.entry_price && t.exit_price) {
      priceHtml = `
        <div style="font-family:var(--font-mono); font-weight:700; color:#fff;">Ra: ${formatPriceNum(t.exit_price)}</div>
        <div style="font-size:0.68rem; color:var(--text-dim); font-family:var(--font-mono);">Vào: ${formatPriceNum(t.entry_price)}</div>
      `;
    }

    // Capital / Margin formatting
    const marginVal = Number(t.margin || t.total_amount || 0);
    let marginHtml = `<div style="font-family:var(--font-mono); font-weight:700; color:#fff;">$${marginVal.toFixed(2)}</div>`;
    if (t.leverage && t.leverage > 1) {
      const posSize = marginVal * t.leverage;
      marginHtml += `<div style="font-size:0.68rem; color:var(--accent-cyan); font-family:var(--font-mono); white-space:nowrap;">Vị thế: $${posSize.toFixed(1)}</div>`;
    }

    // PnL Win/Loss formatting
    let pnlHtml = "";
    if (isClose && t.pnl !== undefined) {
      const pnlVal = Number(t.pnl);
      const pnlPct = Number(t.pnl_percent || 0);
      const isWin = pnlVal >= 0;
      const sign = isWin ? "+" : "";
      const pnlClass = isWin ? "pnl-win-cell" : "pnl-loss-cell";
      const statusTag = isWin ? "THẮNG" : "THUA";

      pnlHtml = `
        <div class="${pnlClass}" style="text-align:right;">
          <div class="pnl-amount">${sign}$${Math.abs(pnlVal).toFixed(2)}</div>
          <div style="font-size:0.7rem; font-family:var(--font-mono); font-weight:600;">${sign}${pnlPct.toFixed(1)}%</div>
          <div class="pnl-status-tag">${statusTag}</div>
        </div>
      `;
    } else {
      pnlHtml = `
        <div style="text-align:right;">
          <span class="badge-open-tag">ĐANG MỞ</span>
        </div>
      `;
    }

    const symName = t.symbol || (t.question ? t.question.split(" ")[0].replace("/USDT", "").replace("crypto_", "") : "-");
    const cleanPair = `${symName}/USDT`;
    const reasonText = t.reasoning || (t.reason ? `Đóng lệnh: ${t.reason}` : "-");

    return `
      <tr>
        <td class="text-muted" style="white-space:nowrap; font-family:var(--font-mono); font-size:0.75rem;">${t.timestamp || "-"}</td>
        <td>${actionBadge}</td>
        <td>
          <div style="font-family:var(--font-mono); font-weight:700; color:#fff;">${escapeHtml(cleanPair)}</div>
          ${t.shares ? `<div style="font-size:0.68rem; color:var(--text-dim); font-family:var(--font-mono);">${Number(t.shares).toLocaleString()} units</div>` : ''}
        </td>
        <td>${priceHtml}</td>
        <td>${marginHtml}</td>
        <td>${pnlHtml}</td>
        <td class="text-muted" style="font-size:0.75rem; max-width:280px; line-height:1.4;">${escapeHtml(reasonText)}</td>
      </tr>
    `;
  }).join("");
}

function onTradeFilterChange() {
  const symSelect = document.getElementById("trade-filter-symbol");
  const typeSelect = document.getElementById("trade-filter-type");
  tradeHistoryState.symbol = symSelect ? symSelect.value : "ALL";
  tradeHistoryState.filter_type = typeSelect ? typeSelect.value : "all";
  tradeHistoryState.offset = 0;
  loadTradesHistory();
}

function onTradeLimitChange() {
  const limitSelect = document.getElementById("trade-filter-limit");
  tradeHistoryState.limit = limitSelect ? parseInt(limitSelect.value, 10) : 50;
  tradeHistoryState.offset = 0;
  loadTradesHistory();
}

function changeTradePage(delta) {
  const limit = tradeHistoryState.limit;
  if (limit === 0) return;
  const newOffset = tradeHistoryState.offset + (delta * limit);
  if (newOffset < 0) return;
  if (newOffset >= tradeHistoryState.filtered_count) return;
  tradeHistoryState.offset = newOffset;
  loadTradesHistory();
}

function exportTradesCSV() {
  const params = new URLSearchParams({
    symbol: tradeHistoryState.symbol,
    filter_type: tradeHistoryState.filter_type
  });
  window.location.href = `/api/portfolio/trades/export.csv?${params.toString()}`;
}

window.loadTradesHistory = loadTradesHistory;
window.onTradeFilterChange = onTradeFilterChange;
window.onTradeLimitChange = onTradeLimitChange;
window.changeTradePage = changeTradePage;
window.exportTradesCSV = exportTradesCSV;

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
      countBadge.textContent = `${activeCount}/${data.tickers.length} COIN ĐANG BẬT AI (Tối đa 5)`;
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
              <button class="btn-table-action btn-scan-coin" onclick="openScanModal('${t.coin}')" title="Thiết lập quét & phân tích AI cho ${t.coin}">⚡ Quét</button>
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

// 4. Add & Remove Coins & Autocomplete Search
let searchDebounceTimer = null;
let currentHighlightedIndex = -1;
let currentSearchResults = [];

function initCoinSearchAutocomplete() {
  const input = document.getElementById("new-coin-input");
  const dropdown = document.getElementById("coin-search-dropdown");
  if (!input || !dropdown) return;

  // On typing
  input.addEventListener("input", () => {
    const query = input.value.trim();
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      fetchAndRenderCoinSearchResults(query);
    }, 180);
  });

  // On focus
  input.addEventListener("focus", () => {
    fetchAndRenderCoinSearchResults(input.value.trim());
  });

  // Keyboard navigation
  input.addEventListener("keydown", (e) => {
    if (!dropdown || dropdown.style.display === "none") {
      if (e.key === "Enter") {
        addNewCoin();
      }
      return;
    }

    const items = dropdown.querySelectorAll(".coin-search-item");
    if (e.key === "ArrowDown") {
      e.preventDefault();
      if (items.length > 0) {
        currentHighlightedIndex = (currentHighlightedIndex + 1) % items.length;
        updateHighlightedItem(items);
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (items.length > 0) {
        currentHighlightedIndex = (currentHighlightedIndex - 1 + items.length) % items.length;
        updateHighlightedItem(items);
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (currentHighlightedIndex >= 0 && currentHighlightedIndex < currentSearchResults.length) {
        selectCoinSearchResult(currentSearchResults[currentHighlightedIndex].coin);
      } else {
        addNewCoin();
      }
    } else if (e.key === "Escape") {
      closeCoinSearchDropdown();
    }
  });

  // Click outside to close
  document.addEventListener("click", (e) => {
    if (!input.contains(e.target) && !dropdown.contains(e.target)) {
      closeCoinSearchDropdown();
    }
  });
}

function updateHighlightedItem(items) {
  items.forEach((item, idx) => {
    if (idx === currentHighlightedIndex) {
      item.classList.add("highlighted");
      item.scrollIntoView({ block: "nearest" });
    } else {
      item.classList.remove("highlighted");
    }
  });
}

function closeCoinSearchDropdown() {
  const dropdown = document.getElementById("coin-search-dropdown");
  if (dropdown) {
    dropdown.style.display = "none";
  }
  currentHighlightedIndex = -1;
}

async function fetchAndRenderCoinSearchResults(query) {
  const dropdown = document.getElementById("coin-search-dropdown");
  if (!dropdown) return;

  try {
    const res = await fetch(`/api/crypto/search?q=${encodeURIComponent(query)}&limit=15`);
    const data = await res.json();
    currentSearchResults = data.results || [];

    if (currentSearchResults.length === 0) {
      dropdown.innerHTML = `
        <div class="coin-search-empty">
          <div style="font-size:1.2rem; margin-bottom:4px;">🔍</div>
          <div>Không tìm thấy cặp USDT nào khớp với "<strong>${escapeHtml(query)}</strong>" trên Binance.</div>
        </div>
      `;
      dropdown.style.display = "block";
      currentHighlightedIndex = -1;
      return;
    }

    currentHighlightedIndex = -1;
    const headerTitle = query ? `KẾT QUẢ KHỚP VỚI "${query.toUpperCase()}"` : `🔥 COIN PHỔ BIẾN (TOP THANH KHOẢN BINANCE)`;

    dropdown.innerHTML = `
      <div class="coin-search-header">
        <span>${headerTitle}</span>
        <span>${currentSearchResults.length} cặp</span>
      </div>
      <div class="coin-search-list">
        ${currentSearchResults.map((item, idx) => {
          const isUp = item.change_pct >= 0;
          const changeClass = isUp ? "up" : "down";
          const changeSign = isUp ? "+" : "";
          const inWatchlist = item.in_watchlist;

          return `
            <div class="coin-search-item" onclick="selectCoinSearchResult('${item.coin}')" data-coin="${item.coin}">
              <div class="coin-item-left">
                <div class="coin-symbol-row">
                  <span class="coin-name-txt">${item.coin}</span>
                  <span class="coin-pair-sub">/USDT</span>
                  ${inWatchlist ? `<span class="badge-in-watchlist">✓ Đang theo dõi</span>` : ""}
                </div>
                <div class="coin-vol-sub">24h Vol: ${item.volume_formatted} USDT</div>
              </div>
              <div class="coin-item-right">
                <div class="coin-price-txt">${item.price_formatted}</div>
                <div class="coin-pct-pill ${changeClass}">${changeSign}${item.change_pct}%</div>
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
    dropdown.style.display = "block";

  } catch (err) {
    console.error("Error searching coins:", err);
  }
}

async function selectCoinSearchResult(coin) {
  closeCoinSearchDropdown();
  const input = document.getElementById("new-coin-input");
  if (input) input.value = coin;
  await addNewCoin(coin);
}

async function addNewCoin(coinToSet) {
  const input = document.getElementById("new-coin-input");
  const raw = (coinToSet || (input ? input.value : "")).trim();
  closeCoinSearchDropdown();
  if (!raw) return;

  try {
    const res = await fetch("/api/crypto/watchlist/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin: raw })
    });
    const result = await res.json();
    if (result.success) {
      if (input) input.value = "";
      await loadCryptoWatchlist(true);
      await loadPortfolio();
      showNotification({
        type: "success",
        title: "Đã Thêm Vào Watchlist",
        message: result.message,
        duration: 5000
      });
    } else {
      showNotification({
        type: "warning",
        title: "Thông Báo Watchlist",
        message: result.message,
        duration: 5000
      });
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Kết Nối",
      message: "Lỗi khi thêm coin: " + err,
      duration: 6000
    });
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
      showNotification({
        type: "success",
        title: "Đã Thêm Nhanh Coin",
        message: result.message,
        duration: 5000
      });
    } else {
      showNotification({
        type: "warning",
        title: "Thông Báo Watchlist",
        message: result.message,
        duration: 5000
      });
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Kết Nối",
      message: "Không thể thêm nhanh coin: " + err,
      duration: 6000
    });
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
    const data = await res.json();
    await loadCryptoWatchlist(true);
    showNotification({
      type: data.success ? "info" : "warning",
      title: data.success ? "Đã Xóa Khỏi Watchlist" : "Không Thể Xóa",
      message: data.message || `Đã xóa ${coin} khỏi danh sách theo dõi.`,
      duration: 4000
    });
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Xóa Coin",
      message: "Lỗi kết nối: " + err,
      duration: 6000
    });
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

// ============================================================
// 4.5. ADVERSARIAL MARKET DISCOVERY COMMITTEE (Scout + Gatekeeper)
// ============================================================
async function triggerDiscoveryScan() {
  const btn = document.getElementById("btn-discovery");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.innerHTML = `⏳ Đang thẩm định thị trường...`;
    btn.disabled = true;
  }

  showNotification({
    type: "info",
    title: "🔍 Hội Đồng AI Khởi Động",
    message: "Alpha Scout đang quét Top 100 coin & Gatekeeper chuẩn bị phản biện đối soát...",
    duration: 4000
  });

  try {
    const res = await fetch("/api/discovery/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const data = await res.json();
    renderDiscoveryReport(data);

    if (data.approved_candidate) {
      showNotification({
        type: "success",
        title: "✅ Phê Duyệt Kết Nạp",
        message: `Quan Tòa Phản Biện đã phê duyệt ${data.approved_candidate.coin} (${data.approved_candidate.audit_score}/100đ)!`,
        duration: 5000
      });
      await loadCryptoWatchlist(true);
      await loadPortfolio();
    } else {
      showNotification({
        type: "warning",
        title: "⚖️ Quan Tòa Phản Biện",
        message: "Các coin được đề cử đều bị bác bỏ do rủi ro downtrend/FOMO. Danh mục được bảo vệ an toàn!",
        duration: 5000
      });
    }
  } catch (err) {
    console.error("Error triggering discovery scan:", err);
    showNotification({
      type: "error",
      title: "Lỗi Thẩm Định",
      message: "Không thể kết nối API Hội Đồng AI.",
      duration: 4000
    });
  } finally {
    if (btn) {
      btn.innerHTML = origText;
      btn.disabled = false;
    }
  }
}

function renderDiscoveryReport(data) {
  const container = document.getElementById("discovery-report-card");
  if (!container) return;

  if (!data || !data.audited_candidates || data.audited_candidates.length === 0) {
    container.style.display = "none";
    return;
  }

  container.style.display = "block";
  const approved = data.approved_candidate;
  const action = data.relegation_action;

  let actionHtml = "";
  if (action) {
    actionHtml = `<div style="margin-top:6px; color:#34d399; font-weight:700;">🔄 ${action.message}</div>`;
  }

  container.innerHTML = `
    <div class="discovery-header">
      <div class="discovery-title">
        <span>⚖️ BÁO CÁO HỘI ĐỒNG AI THẨM ĐỊNH THỊ TRƯỜNG</span>
        <span style="font-size:0.68rem; color:var(--text-dim);">[${data.timestamp || ""}] - Giới Hạn: 5 Coin</span>
      </div>
      <button onclick="document.getElementById('discovery-report-card').style.display='none'" style="background:transparent; border:none; color:var(--text-dim); cursor:pointer;">✕ Đóng</button>
    </div>
    ${actionHtml}
    <div class="discovery-candidate-grid">
      ${data.audited_candidates.map(c => {
        const isApp = c.is_approved;
        const boxClass = isApp ? "candidate-box approved" : "candidate-box rejected";
        const scoreClass = isApp ? "score-high" : "score-low";
        const verdictBadge = isApp ? `<span class="cand-score-badge score-high">✓ PHÊ DUYỆT (${c.audit_score}đ)</span>` : `<span class="cand-score-badge score-low">✕ BÁC BỎ (${c.audit_score}đ)</span>`;

        return `
          <div class="${boxClass}">
            <div class="cand-top-row">
              <span class="cand-symbol">${c.coin}/USDT</span>
              ${verdictBadge}
            </div>
            <div style="font-size:0.7rem; color:var(--text-muted); display:flex; justify-content:space-between;">
              <span>Vol 24h: <strong>${c.volume_formatted}</strong></span>
              <span class="${c.change_pct >= 0 ? 'highlight-green' : 'highlight-red'}">24h: ${c.change_pct >= 0 ? '+' : ''}${c.change_pct}%</span>
            </div>
            <div class="cand-reason-list">
              ${c.strengths && c.strengths.length > 0 ? `<div style="color:#34d399;">+ ${c.strengths[0]}</div>` : ''}
              ${c.objections && c.objections.length > 0 ? `<div style="color:#f87171;">- ${c.objections[0]}</div>` : ''}
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
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

// ============================================================
// 7. SCAN SETUP MODAL & AI TRADE PROPOSALS QUEUE
// ============================================================

let currentPendingProposals = [];

async function openScanModal(targetCoin = null) {
  const modal = document.getElementById("scan-modal");
  if (!modal) return;

  const coinSelect = document.getElementById("scan-target-coin");
  const titleEl = document.getElementById("scan-modal-title");

  // Populate target coin options from watchlist
  if (coinSelect) {
    try {
      const res = await fetch("/api/crypto/watchlist");
      const data = await res.json();
      let optionsHtml = `<option value="ALL">🌐 Quét toàn bộ danh sách coin đang theo dõi (AI tự chọn cơ hội tốt nhất)</option>`;
      let hasTarget = false;
      if (data.tickers && data.tickers.length > 0) {
        optionsHtml += data.tickers.map(t => {
          const isSelected = targetCoin && targetCoin.toUpperCase() === t.coin.toUpperCase();
          if (isSelected) hasTarget = true;
          return `<option value="${t.coin}" ${isSelected ? "selected" : ""}>🪙 ${t.coin}/USDT (${t.price_formatted} • 24h: ${t.change_24h}%)</option>`;
        }).join("");
      }
      if (targetCoin && !hasTarget) {
        optionsHtml = `<option value="${targetCoin.toUpperCase()}" selected>🪙 ${targetCoin.toUpperCase()}/USDT (Mục tiêu quét mới)</option>` + optionsHtml;
      }
      coinSelect.innerHTML = optionsHtml;
      if (targetCoin) {
        coinSelect.value = targetCoin.toUpperCase();
      }
    } catch (e) {
      if (targetCoin) {
        coinSelect.innerHTML = `<option value="${targetCoin.toUpperCase()}" selected>🪙 ${targetCoin.toUpperCase()}/USDT</option>` + coinSelect.innerHTML;
        coinSelect.value = targetCoin.toUpperCase();
      }
    }
  }

  if (titleEl) {
    titleEl.textContent = targetCoin 
      ? `⚡ THIẾT LẬP QUÉT & PHÂN TÍCH CHO ${targetCoin.toUpperCase()}/USDT`
      : `⚡ THIẾT LẬP THÔNG SỐ QUÉT & PHÂN TÍCH AI`;
  }

  // Pre-fill stake recommendation (15% for micro accounts ~$1.50, or 3% for large)
  setScanStakePct(currentPortfolioEquity <= 30.0 ? 0.15 : 0.03);

  // Pre-fill defaults for fast scalping: 1m timeframe & 20x leverage
  const tfSelect = document.getElementById("scan-timeframe");
  if (tfSelect && !tfSelect.value) tfSelect.value = "1m";
  const levSelect = document.getElementById("scan-leverage");
  if (levSelect && (!levSelect.value || levSelect.value === "0")) levSelect.value = "20";

  modal.classList.add("open");
}

function closeScanModal() {
  const modal = document.getElementById("scan-modal");
  if (modal) modal.classList.remove("open");
}

function setScanStakePct(pct) {
  const input = document.getElementById("scan-max-stake");
  if (!input) return;
  const base = currentPortfolioCash > 0 ? currentPortfolioCash : currentPortfolioEquity;
  const minAllowed = base <= 30.0 ? 0.5 : 5.0;
  const val = Math.max(minAllowed, Math.round(base * pct * 100) / 100);
  input.value = val.toFixed(2);
}

function selectScanTf(tf, btn) {
  const tfSelect = document.getElementById("scan-timeframe");
  if (tfSelect) tfSelect.value = tf;
  const label = document.getElementById("active-tf-label");
  if (label) label.textContent = `⚡ ${tf.toUpperCase()}`;
  if (btn && btn.parentElement) {
    btn.parentElement.querySelectorAll(".btn-pill").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
  }
}

function onScanTfDropdownChange(val) {
  const label = document.getElementById("active-tf-label");
  if (label) label.textContent = `⚡ ${val.toUpperCase()}`;
  const group = document.querySelector("#scan-modal .quick-pill-group");
  if (group) {
    group.querySelectorAll(".btn-pill").forEach(b => {
      if (b.getAttribute("onclick") && b.getAttribute("onclick").includes(`'${val}'`)) {
        b.classList.add("active");
      } else {
        b.classList.remove("active");
      }
    });
  }
}

function selectScanLev(lev, btn) {
  const levSelect = document.getElementById("scan-leverage");
  if (levSelect) levSelect.value = lev;
  const label = document.getElementById("active-lev-label");
  if (label) label.textContent = lev > 0 ? `🔥 ${lev}X` : "🤖 TỰ ĐỘNG AI";
  if (btn && btn.parentElement) {
    btn.parentElement.querySelectorAll(".btn-pill").forEach(b => b.classList.remove("active-lev"));
    btn.classList.add("active-lev");
  }
}

function onScanLevDropdownChange(val) {
  const lev = parseInt(val) || 0;
  const label = document.getElementById("active-lev-label");
  if (label) label.textContent = lev > 0 ? `🔥 ${lev}X` : "🤖 TỰ ĐỘNG AI";
  const groups = document.querySelectorAll("#scan-modal .quick-pill-group");
  if (groups.length >= 2) {
    groups[1].querySelectorAll(".btn-pill").forEach(b => {
      if (b.getAttribute("onclick") && b.getAttribute("onclick").includes(`(${lev},`)) {
        b.classList.add("active-lev");
      } else {
        b.classList.remove("active-lev");
      }
    });
  }
}

window.selectScanTf = selectScanTf;
window.onScanTfDropdownChange = onScanTfDropdownChange;
window.selectScanLev = selectScanLev;
window.onScanLevDropdownChange = onScanLevDropdownChange;

async function executeScanWithOptions() {
  const btn = document.getElementById("btn-run-scan-submit");
  const origText = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="btn-icon">⏳</span> AI ĐANG QUÉT & THẨM ĐỊNH TÍN HIỆU...`;
  }

  const coinSelect = document.getElementById("scan-target-coin");
  const rawCoin = coinSelect ? coinSelect.value : "ALL";
  const coin = rawCoin === "ALL" ? null : rawCoin;

  const tfEl = document.getElementById("scan-timeframe");
  const timeframe = tfEl ? tfEl.value : "1m";

  const levEl = document.getElementById("scan-leverage");
  const levVal = levEl ? parseInt(levEl.value) : 0;
  const max_leverage = levVal > 0 ? Math.min(25, levVal) : 20;

  const stakeEl = document.getElementById("scan-max-stake");
  const stakeVal = stakeEl ? parseFloat(stakeEl.value) : 0;
  const max_stake = stakeVal > 0 ? stakeVal : null;

  const slEl = document.getElementById("scan-sl-pct");
  const slVal = slEl ? parseFloat(slEl.value) : 0;
  const custom_sl_pct = slVal > 0 ? slVal : null;

  const tpEl = document.getElementById("scan-tp-pct");
  const tpVal = tpEl ? parseFloat(tpEl.value) : 0;
  const custom_tp_pct = tpVal > 0 ? tpVal : null;

  const modeEl = document.querySelector('input[name="scan-exec-mode"]:checked');
  const mode = modeEl ? modeEl.value : "DIRECT_EXECUTE";

  const payload = {
    coin: coin,
    timeframe: timeframe,
    max_leverage: max_leverage,
    max_stake: max_stake,
    custom_sl_pct: custom_sl_pct,
    custom_tp_pct: custom_tp_pct,
    mode: mode
  };

  try {
    playAgentSequence(payload.coin);

    const res = await fetch("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    closeScanModal();

    await loadPortfolio();
    await loadCryptoWatchlist(true);
    await loadProposals();

    if (mode === "PROPOSAL") {
      scrollToProposals();
      if (data.cycle_result && data.cycle_result.status === "hold") {
        showNotification({
          type: "warning",
          title: "AI Hội Đồng: GIỮ TIỀN MẶT (HOLD)",
          message: `Lợi thế thống kê của thị trường hiện tại trên ${data.cycle_result.coin || 'thị trường'} chưa vượt ngưỡng an toàn (>4.0%). AI quyết định GIỮ NGUYÊN TIỀN MẶT để bảo toàn vốn.`,
          duration: 8000
        });
      } else {
        showNotification({
          type: "ai",
          title: "AI Quét Xong & Tạo Đề Xuất Mới",
          message: `Đã đưa phương án giao dịch ${data.cycle_result?.coin || ''} vào Hàng Đợi Chờ Duyệt.`,
          duration: 8000,
          action: scrollToProposals,
          actionLabel: "Xem hàng đợi đề xuất →"
        });
      }
    } else {
      // Direct Execute Mode (Bỏ qua phê duyệt)
      if (data.cycle_result && data.cycle_result.status === "traded") {
        showNotification({
          type: "success",
          title: `⚡ TỰ ĐỘNG KHỚP LỆNH: ${data.cycle_result.side} ${data.cycle_result.coin}/USDT`,
          message: `AI đã tự động mở vị thế ${data.cycle_result.leverage}x tại giá $${data.cycle_result.price} ngay khi phát hiện xung lực biến động!`,
          duration: 8000
        });
      } else if (data.cycle_result && data.cycle_result.status === "hold") {
        showNotification({
          type: "warning",
          title: "AI Hội Đồng: BẢO TOÀN VỐN (HOLD)",
          message: `Đồng ${data.cycle_result.coin || ''} chưa đạt đủ điều kiện bùng nổ biến động (>4.0% Edge). AI tiếp tục theo dõi nén sóng.`,
          duration: 7000
        });
      } else if (data.cycle_result && data.cycle_result.status === "position_already_open") {
        showNotification({
          type: "info",
          title: "Vị Thế Đang Mở",
          message: `Đồng ${data.cycle_result.coin} hiện đang có vị thế mở. AI đang giám sát điểm chốt lời/cắt lỗ.`,
          duration: 6000
        });
      } else {
        showNotification({
          type: "success",
          title: "Đã Quét & Phân Tích",
          message: `Hoàn tất vòng quét định lượng trên ${data.cycle_result?.coin || 'thị trường'}.`,
          duration: 6000
        });
      }
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Quét AI",
      message: "Không thể hoàn thành quét thị trường: " + err,
      duration: 6000
    });
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

// Fallback for header or quick calls
async function triggerManualScan(coin = null) {
  openScanModal(coin);
}

// ============================================================
// 8. TRADE PROPOSALS QUEUE MANAGEMENT
// ============================================================

async function loadProposals() {
  try {
    const res = await fetch("/api/proposals");
    if (!res.ok) return;
    const data = await res.json();
    currentPendingProposals = data.proposals || [];
    renderProposals(currentPendingProposals);

    // Update count badges
    const badge = document.getElementById("proposals-count");
    if (badge) badge.textContent = `${currentPendingProposals.length} ĐỀ XUẤT`;

    const headerBadge = document.getElementById("header-proposals-count");
    if (headerBadge) headerBadge.textContent = currentPendingProposals.length;
  } catch (err) {
    console.error("Error loading proposals:", err);
  }
}

function renderProposals(proposals) {
  const container = document.getElementById("proposals-list-container");
  if (!container) return;

  if (!proposals || proposals.length === 0) {
    container.innerHTML = `
      <div class="text-center text-muted" style="padding: 24px; font-size: 0.85rem;">
        Chưa có đề xuất nào trong danh sách đợi. Hãy bấm <strong>"QUÉT THỊ TRƯỜNG"</strong> để AI phân tích và đưa cơ hội vào đây!
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div class="proposals-list">
      ${proposals.map(p => {
        const isLong = p.side === "LONG";
        const sideClass = isLong ? "prop-side-long" : "prop-side-short";
        const cardSideClass = isLong ? "side-long" : "side-short";
        const sym = p.coin || "COIN";
        const priceStr = formatPriceNum(p.price);
        const slStr = p.stop_loss ? formatPriceNum(p.stop_loss) : "Không SL";
        const tpStr = p.take_profit ? formatPriceNum(p.take_profit) : "Gồng tự do";
        const liqStr = p.liquidation_price ? formatPriceNum(p.liquidation_price) : "-";

        let analysisHtml = "";
        if (p.analysis_summary && Object.keys(p.analysis_summary).length > 0) {
          analysisHtml = `
            <div class="prop-analysis-box">
              <div style="font-weight:700; color:#a5b4fc; margin-bottom:4px; font-size:0.75rem;">🧠 BÁO CÁO PHÂN TÍCH ĐA ĐẶC VỤ AI:</div>
              ${p.analysis_summary.spotter ? `<div>• <strong>Spotter:</strong> ${escapeHtml(p.analysis_summary.spotter)}</div>` : ''}
              ${p.analysis_summary.researcher ? `<div>• <strong>Researcher:</strong> ${escapeHtml(p.analysis_summary.researcher)}</div>` : ''}
              ${p.analysis_summary.pricer ? `<div>• <strong>The Pricer:</strong> ${escapeHtml(p.analysis_summary.pricer)}</div>` : ''}
              ${p.analysis_summary.debate ? `<div style="color:#fbbf24; margin-top:2px;">• <strong>Tranh luận Bull vs Bear:</strong> ${escapeHtml(p.analysis_summary.debate)}</div>` : ''}
              ${p.analysis_summary.smc ? `<div style="color:#e879f9; font-weight:600; margin-top:2px;">• <strong>SMC (Kỹ Năng 1):</strong> ${escapeHtml(p.analysis_summary.smc)}</div>` : ''}
              ${p.analysis_summary.dna ? `<div style="color:#a78bfa; font-weight:600; margin-top:2px;">• <strong>🧬 DNA Tín Hiệu:</strong> ${escapeHtml(p.analysis_summary.dna)}</div>` : ''}
              ${p.analysis_summary.memory ? `<div style="color:#38bdf8; margin-top:2px;">• <strong>Trí nhớ quá khứ:</strong> ${escapeHtml(p.analysis_summary.memory)}</div>` : ''}
              ${p.analysis_summary.kelly ? `<div>• <strong>Kelly Risk:</strong> ${escapeHtml(p.analysis_summary.kelly)}</div>` : ''}
            </div>
          `;
        }

        let smcBadge = "";
        if (p.analysis_summary && p.analysis_summary.smc) {
          const isSweep = p.analysis_summary.smc.includes("Sweep");
          smcBadge = `<span class="badge-smc-tag">${isSweep ? '⚡ SMC SWEEP' : '🎯 SMC FVG'}</span>`;
        }

        let dnaBadge = "";
        const isDecay = (p.analysis_summary && p.analysis_summary.dna && p.analysis_summary.dna.includes("SUY GIẢM")) ||
                        (p.signal_dna && p.signal_dna.status === "ALPHA_DECAY");
        const badgeCls = isDecay ? "badge-decay-tag" : "badge-dna-tag";
        const icon = isDecay ? "⚡" : "🧬";
        if (p.signal_dna && p.signal_dna.display_label) {
          dnaBadge = `<span class="${badgeCls}">${icon} ${escapeHtml(p.signal_dna.display_label)}</span>`;
        } else if (p.analysis_summary && p.analysis_summary.dna) {
          dnaBadge = `<span class="${badgeCls}">${icon} ${escapeHtml(p.analysis_summary.dna.split('|')[0].trim())}</span>`;
        }

        return `
          <div class="proposal-card ${cardSideClass}" id="prop-card-${p.id}">
            <div class="prop-header">
              <div class="prop-title-area">
                <span class="prop-coin-badge">${escapeHtml(sym)}/USDT</span>
                <span class="prop-side-badge ${sideClass}">${p.side} ${p.leverage}x</span>
                <span class="sub-badge" style="font-size:0.65rem;">${p.timeframe ? p.timeframe.toUpperCase() : '1H'}</span>
                ${smcBadge}
                ${dnaBadge}
              </div>
              <div class="prop-time">Tạo lúc: ${p.created_at || '-'}</div>
            </div>

            <div class="prop-grid">
              <div class="prop-metric">
                <span class="prop-metric-lbl">Giá Vào Dự Kiến</span>
                <span class="prop-metric-val highlight-cyan">${priceStr}</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Ký Quỹ / Vị Thế</span>
                <span class="prop-metric-val">$${p.stake_amount.toFixed(2)} ($${p.position_size.toFixed(2)})</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Cắt Lỗ (Hard SL)</span>
                <span class="prop-metric-val highlight-red">${slStr}</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Chốt Lời (Hard TP)</span>
                <span class="prop-metric-val highlight-green">${tpStr}</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Tỷ Lệ Risk:Reward</span>
                <span class="prop-metric-val" style="color:#a855f7;">1 : ${p.risk_reward_ratio || 2.0}</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Lợi Thế Thống Kê (Edge)</span>
                <span class="prop-metric-val" style="color:#38bdf8;">${p.edge_percent || '+0.0%'}</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Giá Thanh Lý</span>
                <span class="prop-metric-val" style="color:#f59e0b;">${liqStr}</span>
              </div>
              <div class="prop-metric">
                <span class="prop-metric-lbl">Trạng Thái</span>
                <span class="prop-metric-val" style="color:#fbbf24;">⏳ CHỜ DUYỆT</span>
              </div>
            </div>

            ${analysisHtml}

            <div class="prop-actions">
              <button class="btn-prop-approve" onclick="approveProposal('${p.id}')">
                ✅ CHẤP NHẬN & VÀO LỆNH NGAY
              </button>
              <button class="btn-prop-tweak" onclick="tweakProposalInPlanner('${p.id}')" title="Mở kế hoạch này trong bộ đàm phán AI để điều chỉnh SL/TP">
                ⚡ ĐIỀU CHỈNH
              </button>
              <button class="btn-prop-reject" onclick="rejectProposal('${p.id}')" title="Từ chối cơ hội này">
                ✕ HỦY BỎ
              </button>
            </div>
          </div>
        `;
      }).join("")}
    </div>
  `;
}

async function approveProposal(proposalId) {
  if (!confirm("Bạn có chắc chắn muốn CHẤP NHẬN đề xuất này và mở vị thế ngay lập tức?")) return;
  try {
    const res = await fetch("/api/proposals/approve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: proposalId })
    });
    const data = await res.json();
    if (data.success) {
      await loadPortfolio();
      await loadProposals();
      // Switch chart to this coin if possible
      const prop = currentPendingProposals.find(p => p.id === proposalId);
      if (prop) changeChartCoin(prop.coin, true);
      showNotification({
        type: "success",
        title: "Đã Phê Duyệt & Khớp Lệnh!",
        message: data.message || "Vị thế mới đã được kích hoạt thành công.",
        duration: 6500
      });
    } else {
      showNotification({
        type: "error",
        title: "Phê Duyệt Thất Bại",
        message: data.message || "Không thể phê duyệt đề xuất.",
        duration: 6000
      });
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Kết Nối",
      message: "Lỗi khi phê duyệt đề xuất: " + err,
      duration: 6000
    });
  }
}

async function rejectProposal(proposalId) {
  try {
    const res = await fetch("/api/proposals/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proposal_id: proposalId })
    });
    const data = await res.json();
    if (data.success) {
      await loadProposals();
      showNotification({
        type: "info",
        title: "Đã Hủy Bỏ Đề Xuất",
        message: "Đề xuất đã được loại bỏ khỏi hàng đợi.",
        duration: 4000
      });
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Hủy Đề Xuất",
      message: "Không thể hủy đề xuất: " + err,
      duration: 5000
    });
  }
}

async function clearAllProposals() {
  if (!confirm("Bạn có chắc muốn xóa tất cả đề xuất trong hàng đợi?")) return;
  try {
    await fetch("/api/proposals/clear", { method: "POST" });
    await loadProposals();
    showNotification({
      type: "info",
      title: "Đã Dọn Hàng Đợi",
      message: "Tất cả đề xuất trong hàng đợi đã được xóa sạch.",
      duration: 4500
    });
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Xóa Hàng Đợi",
      message: "Không thể xóa đề xuất: " + err,
      duration: 5000
    });
  }
}

function tweakProposalInPlanner(proposalId) {
  const prop = currentPendingProposals.find(p => p.id === proposalId);
  if (!prop) return;

  openTradePlannerModal(prop.coin);

  // Set values into planner form
  setTimeout(() => {
    const sideSelect = document.getElementById("plan-side");
    if (sideSelect) sideSelect.value = prop.side;

    const levSelect = document.getElementById("plan-leverage");
    if (levSelect) levSelect.value = prop.leverage;

    const stakeInput = document.getElementById("plan-stake");
    if (stakeInput) stakeInput.value = prop.stake_amount;

    const slInput = document.getElementById("plan-stop-loss");
    if (slInput && prop.stop_loss) slInput.value = prop.stop_loss;

    const tpInput = document.getElementById("plan-take-profit");
    if (tpInput && prop.take_profit) tpInput.value = prop.take_profit;

    recalculatePlannerEstimates();
    submitPlanForAIValidation();
  }, 300);
}

function scrollToProposals() {
  const el = document.getElementById("proposals-panel");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function scrollToTrades() {
  const el = document.getElementById("trades-panel");
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

window.openScanModal = openScanModal;
window.closeScanModal = closeScanModal;
window.setScanStakePct = setScanStakePct;
window.executeScanWithOptions = executeScanWithOptions;
window.approveProposal = approveProposal;
window.rejectProposal = rejectProposal;
window.clearAllProposals = clearAllProposals;
window.tweakProposalInPlanner = tweakProposalInPlanner;
window.scrollToProposals = scrollToProposals;
window.scrollToTrades = scrollToTrades;

let currentAutoMode = "AUTONOMOUS";
let currentAutoTimeframe = "15m";

// 8. Toggle Auto-Scan Mode
async function toggleAutoMode() {
  try {
    const tfSelect = document.getElementById("auto-timeframe-select");
    if (tfSelect) currentAutoTimeframe = tfSelect.value || "1m";
    const res = await fetch("/api/auto/toggle", { 
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ execution_mode: "AUTONOMOUS", timeframe: currentAutoTimeframe })
    });
    const data = await res.json();
    isAutoRunning = data.is_auto_running;
    currentAutoMode = data.execution_mode || "AUTONOMOUS";
    currentAutoTimeframe = data.timeframe || currentAutoTimeframe || "1m";
    if (tfSelect) tfSelect.value = currentAutoTimeframe;
    updateAutoButtonState();
    showNotification({
      type: isAutoRunning ? "success" : "info",
      title: isAutoRunning ? `Tự Động Khớp Lệnh ${currentAutoTimeframe.toUpperCase()}: ĐÃ BẬT` : "Vòng Tự Động: ĐÃ TẮT",
      message: isAutoRunning ? `AI Swarm quét 6 coin trên khung nến ${currentAutoTimeframe.toUpperCase()} (Scalping) và tự động vào lệnh trực tiếp.` : "Đã tạm dừng chế độ giao dịch tự động.",
      duration: 5000
    });
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Chế Độ Tự Động",
      message: "Không thể chuyển trạng thái: " + err,
      duration: 5000
    });
  }
}

async function changeAutoLoopTimeframe(tf) {
  currentAutoTimeframe = tf || "1m";
  const tfSelect = document.getElementById("auto-timeframe-select");
  if (tfSelect) tfSelect.value = currentAutoTimeframe;
  try {
    await fetch("/api/auto/toggle", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ 
        enabled: isAutoRunning, 
        execution_mode: currentAutoMode, 
        timeframe: currentAutoTimeframe 
      })
    });
  } catch (e) {}
  updateAutoButtonState();
  showNotification({
    type: "info",
    title: `Khung Tự Động: ${currentAutoTimeframe.toUpperCase()}`,
    message: `Đã đổi khung nến quét Swarm sang ${currentAutoTimeframe.toUpperCase()} (Phù hợp Scalping lướt sóng nhanh).`,
    duration: 3500
  });
}
window.changeAutoLoopTimeframe = changeAutoLoopTimeframe;

async function checkAutoStatus() {
  try {
    const res = await fetch("/api/auto/status");
    if (res.ok) {
      const data = await res.json();
      isAutoRunning = data.is_auto_running;
      currentAutoMode = data.execution_mode || "AUTONOMOUS";
      currentAutoTimeframe = data.timeframe || "1m";
      const tfSelect = document.getElementById("auto-timeframe-select");
      if (tfSelect && data.timeframe) {
        tfSelect.value = data.timeframe;
      }
      updateAutoButtonState();
    }
  } catch (e) {}
}

function updateAutoButtonState() {
  const dot = document.getElementById("auto-dot");
  const text = document.getElementById("auto-text");
  if (!dot || !text) return;
  if (isAutoRunning) {
    dot.className = "status-dot active";
    text.textContent = `TỰ ĐỘNG: BẬT (${currentAutoTimeframe.toUpperCase()})`;
  } else {
    dot.className = "status-dot";
    text.textContent = "TỰ ĐỘNG: TẮT";
  }
}

// 9. Reset Portfolio
async function resetPortfolio() {
  if (!confirm("Bạn có chắc chắn muốn đặt lại số dư vốn về $10.00?")) return;
  try {
    await fetch("/api/portfolio/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ capital: 10.0 })
    });
    await loadPortfolio();
    showNotification({
      type: "success",
      title: "Đã Đặt Lại Danh Mục",
      message: "Số dư vốn ảo đã được khôi phục về $10.00 tiền mặt ban đầu.",
      duration: 5000
    });
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Đặt Lại Danh Mục",
      message: "Lỗi kết nối: " + err,
      duration: 5000
    });
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
  const rawLev = parseInt(document.getElementById("plan-leverage").value) || 20;
  const leverage = Math.min(25, Math.max(1, rawLev));
  const stake = parseFloat(document.getElementById("plan-stake").value) || 2.0;
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
    playAgentSequence(coin);

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

    if (data.verdict === "APPROVED") {
      showNotification({
        type: "success",
        title: "Hội Đồng AI Đã Phê Duyệt",
        message: data.title || "Kế hoạch đã vượt qua kiểm định rủi ro Kelly.",
        duration: 6000
      });
    } else if (data.verdict === "SUGGEST_ADJUSTMENT") {
      showNotification({
        type: "warning",
        title: "AI Khuyến Nghị Điều Chỉnh",
        message: data.title || "Vui lòng xem thông số tối ưu đề xuất để bảo toàn vốn.",
        duration: 6000
      });
    } else {
      showNotification({
        type: "error",
        title: "Hội Đồng AI Từ Chối Kế Hoạch",
        message: data.title || "Rủi ro vị thế quá cao, không đáp ứng tiêu chuẩn an toàn.",
        duration: 6000
      });
    }

  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Thẩm Định AI",
      message: "Không thể kết nối đến AI: " + err,
      duration: 6000
    });
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
  const rawLev = parseInt(document.getElementById("plan-leverage").value) || 20;
  const leverage = Math.min(25, Math.max(1, rawLev));
  const stake = parseFloat(document.getElementById("plan-stake").value) || 2.0;
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
      showNotification({
        type: "success",
        title: "Đã Khớp Lệnh Kế Hoạch!",
        message: `Đã mở vị thế ${payload.coin} ${payload.side} đòn bẩy x${payload.leverage} với $${payload.stake_amount.toFixed(2)}.`,
        duration: 7000
      });
    } else {
      showNotification({
        type: "error",
        title: "Khớp Lệnh Không Thành Công",
        message: data.message || "Vui lòng kiểm tra lại số dư vốn ký quỹ.",
        duration: 6000
      });
    }
  } catch (err) {
    showNotification({
      type: "error",
      title: "Lỗi Khớp Lệnh",
      message: "Lỗi kết nối khi khớp lệnh: " + err,
      duration: 6000
    });
  } finally {
    if (btnExec) {
      btnExec.disabled = false;
      btnExec.textContent = "🚀 XÁC NHẬN VÀO LỆNH NGAY";
    }
  }
}

// ============================================================
// 🧠 TRADING MEMORY & SELF-REFLECTION MODAL (3-Compartment Architecture)
// ============================================================
let currentMemoryData = null;
let currentMemoryTab = 'coins'; // 'coins', 'strategies', 'patterns'

function switchMemoryTab(tab) {
  currentMemoryTab = tab;
  document.querySelectorAll('.mem-tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tab);
  });
  document.querySelectorAll('.mem-tab-content').forEach(content => {
    content.style.display = (content.dataset.tab === tab) ? 'block' : 'none';
  });
}

async function openMemoryModal() {
  const modal = document.getElementById("memory-modal");
  if (!modal) return;
  modal.classList.add("open");
  modal.classList.add("active");
  await fetchAndRenderMemory();
}

function closeMemoryModal() {
  const modal = document.getElementById("memory-modal");
  if (modal) {
    modal.classList.remove("open");
    modal.classList.remove("active");
  }
}
window.openMemoryModal = openMemoryModal;
window.closeMemoryModal = closeMemoryModal;

async function fetchAndRenderMemory() {
  try {
    const res = await fetch("/api/memory");
    const data = await res.json();
    currentMemoryData = data;
    renderMemoryData(data);
  } catch (e) {
    console.error("Lỗi lấy trí nhớ AI:", e);
  }
}

function renderMemoryData(data) {
  const statsContainer = document.getElementById("memory-stats-grid");
  const listContainer = document.getElementById("memory-list-container");
  if (!statsContainer || !listContainer) return;

  const total = data.total_reflections || 0;
  const wins = data.wins || 0;
  const losses = data.losses || 0;
  const winRate = data.win_rate || 0.0;

  const symbols = data.symbol_matrix || [];
  const strategies = data.strategy_matrix || [];
  const winAmps = data.win_amplifiers || [];
  const decaying = data.alpha_decaying || [];
  const traps = data.loss_traps || [];

  statsContainer.innerHTML = `
    <div style="background: rgba(16, 24, 40, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 10px; text-align: center;">
      <div style="font-size: 0.68rem; color: var(--text-dim);">TỔNG LỆNH ĐÓNG</div>
      <div style="font-size: 1.2rem; font-weight: 800; color: #fff;">${total}</div>
    </div>
    <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 8px; padding: 10px; text-align: center;">
      <div style="font-size: 0.68rem; color: #86efac;">LỆNH THẮNG (WIN)</div>
      <div style="font-size: 1.2rem; font-weight: 800; color: #4ade80;">${wins}</div>
    </div>
    <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 10px; text-align: center;">
      <div style="font-size: 0.68rem; color: #fca5a5;">LỆNH THUA (LOSS)</div>
      <div style="font-size: 1.2rem; font-weight: 800; color: #f87171;">${losses}</div>
    </div>
    <div style="background: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); border-radius: 8px; padding: 10px; text-align: center;">
      <div style="font-size: 0.68rem; color: #d8b4fe;">TỶ LỆ THẮNG</div>
      <div style="font-size: 1.2rem; font-weight: 800; color: #c084fc;">${winRate}%</div>
    </div>
  `;

  // Render 3-Compartment Matrix Container
  const patternsContainer = document.getElementById("memory-patterns-container");
  if (patternsContainer) {
    const renderFormPills = (outcomes) => {
      if (!outcomes || outcomes.length === 0) return '';
      return `
        <div style="display:flex; gap:2px; align-items:center;" title="Phong độ từ mới nhất (trái) đến cũ hơn (phải)">
          <span style="font-size:0.6rem; color:var(--text-dim); margin-right:3px;">Form:</span>
          ${outcomes.map(w => w 
            ? `<span class="form-pill form-pill-w">W</span>` 
            : `<span class="form-pill form-pill-l">L</span>`
          ).join('')}
        </div>
      `;
    };

    patternsContainer.innerHTML = `
      <!-- Tab Bar -->
      <div class="mem-tab-bar">
        <button class="mem-tab-btn ${currentMemoryTab === 'coins' ? 'active' : ''}" data-tab="coins" onclick="switchMemoryTab('coins')">
          <span>🪙</span>
          <span>Ngăn 1: Từng Đồng Coin (${symbols.length})</span>
        </button>
        <button class="mem-tab-btn ${currentMemoryTab === 'strategies' ? 'active' : ''}" data-tab="strategies" onclick="switchMemoryTab('strategies')">
          <span>🎯</span>
          <span>Ngăn 2: Từng Chiến Thuật (${strategies.length})</span>
        </button>
        <button class="mem-tab-btn ${currentMemoryTab === 'patterns' ? 'active' : ''}" data-tab="patterns" onclick="switchMemoryTab('patterns')">
          <span>🧬</span>
          <span>Ngăn 3: Quy Luật & Time-Decay (${winAmps.length + decaying.length + traps.length})</span>
        </button>
      </div>

      <!-- TAB 1: COINS PROFILE MATRIX -->
      <div class="mem-tab-content" data-tab="coins" style="display: ${currentMemoryTab === 'coins' ? 'block' : 'none'};">
        <div style="background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.73rem; color: #bae6fd; line-height: 1.4;">
          🛡️ <strong>Cơ Chế Phân Lập Rủi Ro Độc Lập (Isolated Risk Shield)</strong>: Mỗi đồng coin được gán một ngăn nhớ riêng biệt. Nếu PEPE hay DOGE dính chuỗi thua, bot chỉ giảm vốn và siết đòn bẩy cho riêng coin đó, hoàn toàn <strong>KHÔNG lây lan sang SOL hay BNB</strong>!
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px;">
          ${symbols.map(c => {
            const isDefense = c.status === "DEFENSE_LOCK";
            const isHealthy = c.status === "HEALTHY";
            const cardClass = isDefense ? 'coin-card defense-lock' : (isHealthy ? 'coin-card healthy' : 'coin-card');
            
            let statusBadge = '';
            if (isDefense) {
              statusBadge = `<span style="font-size:0.63rem; font-weight:800; color:#f87171; background:rgba(239,68,68,0.2); padding:2px 6px; border-radius:4px; border:1px solid rgba(239,68,68,0.4);">🛡️ PHÒNG VỆ RIÊNG (${c.recent_loss_streak} SL)</span>`;
            } else if (isHealthy) {
              statusBadge = `<span style="font-size:0.63rem; font-weight:800; color:#4ade80; background:rgba(34,197,94,0.2); padding:2px 6px; border-radius:4px; border:1px solid rgba(34,197,94,0.4);">⭐ PHONG ĐỘ CAO</span>`;
            } else {
              statusBadge = `<span style="font-size:0.63rem; font-weight:700; color:#94a3b8; background:rgba(148,163,184,0.15); padding:2px 6px; border-radius:4px;">⚖️ KIỂM ĐỊNH</span>`;
            }

            let categoryBadge = '';
            if (c.category === 'MEME_HIGH_VOLATILITY') {
              categoryBadge = `<span style="font-size:0.6rem; color:#f472b6; background:rgba(236,72,153,0.15); padding:1px 5px; border-radius:3px;">Meme Biến Động</span>`;
            } else if (c.category === 'MAJOR_CRYPTO') {
              categoryBadge = `<span style="font-size:0.6rem; color:#38bdf8; background:rgba(56,189,248,0.15); padding:1px 5px; border-radius:3px;">Coin Trụ</span>`;
            } else {
              categoryBadge = `<span style="font-size:0.6rem; color:#a78bfa; background:rgba(167,139,250,0.15); padding:1px 5px; border-radius:3px;">Altcoin</span>`;
            }

            return `
              <div class="${cardClass}">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                  <div style="display:flex; align-items:center; gap:6px;">
                    <span style="font-weight:800; font-size:0.95rem; color:#fff;">${escapeHtml(c.symbol)}</span>
                    ${categoryBadge}
                  </div>
                  ${statusBadge}
                </div>

                <div style="margin-bottom:6px;">
                  ${renderFormPills(c.recent_outcomes)}
                </div>

                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.68rem; background:rgba(0,0,0,0.25); padding:6px 8px; border-radius:6px; margin-bottom:6px;">
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">GẦN ĐÂY (DECAYED)</span>
                    <strong style="color:${c.decayed_win_rate >= 50 ? '#4ade80' : '#f87171'}; font-size:0.8rem;">${c.decayed_win_rate}%</strong>
                  </div>
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">LỊCH SỬ</span>
                    <span style="color:#e2e8f0; font-weight:700;">${c.win_rate}% (${c.wins}/${c.total_trades})</span>
                  </div>
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">TỔNG PNL</span>
                    <span style="color:${c.total_pnl_percent >= 0 ? '#4ade80' : '#f87171'}; font-weight:700;">${c.total_pnl_percent >= 0 ? '+' : ''}${c.total_pnl_percent}%</span>
                  </div>
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">CHIẾN THUẬT TỐT NHẤT</span>
                    <span style="color:#38bdf8; font-weight:700; font-size:0.63rem;">${c.best_strategy}</span>
                  </div>
                </div>

                ${c.defense_warning ? `
                  <div class="coin-defense-alert">
                    ${escapeHtml(c.defense_warning)}
                  </div>
                ` : `
                  <div class="coin-isolated-note">
                    <span>🛡️</span>
                    <span>Phân lập độc lập • Không lây lan rủi ro</span>
                  </div>
                `}
              </div>
            `;
          }).join('')}
        </div>
      </div>

      <!-- TAB 2: STRATEGIES MATRIX -->
      <div class="mem-tab-content" data-tab="strategies" style="display: ${currentMemoryTab === 'strategies' ? 'block' : 'none'};">
        <div style="background: rgba(168, 85, 247, 0.08); border: 1px solid rgba(168, 85, 247, 0.25); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.73rem; color: #e9d5ff; line-height: 1.4;">
          🎯 <strong>Hiệu Suất Từng Trường Phái Định Lượng</strong>: Đánh giá độc lập 4 nhóm chiến thuật (SMC Sweep săn râu cá mập, SMC Retest FVG, Momentum Breakout bứt phá xu hướng, và Range Scalp lướt sóng sideway). Tự động cộng thêm hoặc trừ bớt Edge lúc vào lệnh.
        </div>

        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px;">
          ${strategies.map(s => {
            const isEdge = s.status === "PROVEN_EDGE";
            const isUnder = s.status === "UNDERPERFORMING";
            
            let badge = '';
            if (isEdge) {
              badge = `<span style="font-size:0.63rem; font-weight:800; color:#4ade80; background:rgba(34,197,94,0.2); padding:2px 6px; border-radius:4px; border:1px solid rgba(34,197,94,0.4);">🎯 LỢI THẾ VÀNG (+${(s.edge_adjustment*100).toFixed(1)}%)</span>`;
            } else if (isUnder) {
              badge = `<span style="font-size:0.63rem; font-weight:800; color:#f87171; background:rgba(239,68,68,0.2); padding:2px 6px; border-radius:4px; border:1px solid rgba(239,68,68,0.4);">⚠️ BỊ PHẠT (${(s.edge_adjustment*100).toFixed(1)}%)</span>`;
            } else {
              badge = `<span style="font-size:0.63rem; font-weight:700; color:#38bdf8; background:rgba(56,189,248,0.15); padding:2px 6px; border-radius:4px;">⚖️ ĐANG KIỂM ĐỊNH</span>`;
            }

            return `
              <div class="strat-card" style="border-left: 3px solid ${isEdge ? '#4ade80' : (isUnder ? '#f87171' : '#38bdf8')};">
                <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:4px; gap:6px;">
                  <div>
                    <span style="font-weight:800; font-size:0.85rem; color:#fff; display:block;">${escapeHtml(s.strategy_key)}</span>
                    <span style="font-size:0.68rem; color:#94a3b8;">${escapeHtml(s.display_label)}</span>
                  </div>
                  ${badge}
                </div>

                <div style="margin: 6px 0;">
                  ${renderFormPills(s.recent_outcomes)}
                </div>

                <div style="display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:0.68rem; background:rgba(0,0,0,0.25); padding:6px 8px; border-radius:6px;">
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">THẮNG GẦN ĐÂY</span>
                    <strong style="color:${s.decayed_win_rate >= 50 ? '#4ade80' : '#f87171'}; font-size:0.8rem;">${s.decayed_win_rate}%</strong>
                  </div>
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">LỊCH SỬ</span>
                    <span style="color:#e2e8f0; font-weight:700;">${s.win_rate}% (${s.wins}/${s.total_trades})</span>
                  </div>
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">COIN HIỆU QUẢ NHẤT</span>
                    <span style="color:#38bdf8; font-weight:700;">${s.best_coin || 'N/A'}</span>
                  </div>
                  <div>
                    <span style="color:var(--text-dim); display:block; font-size:0.6rem;">PNL TÍCH LŨY</span>
                    <span style="color:${s.total_pnl_percent >= 0 ? '#4ade80' : '#f87171'}; font-weight:700;">${s.total_pnl_percent >= 0 ? '+' : ''}${s.total_pnl_percent}%</span>
                  </div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>

      <!-- TAB 3: PATTERNS & TIME-DECAY MATRIX -->
      <div class="mem-tab-content" data-tab="patterns" style="display: ${currentMemoryTab === 'patterns' ? 'block' : 'none'};">
        <div style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255,255,255,0.08); border-radius: 10px; padding: 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div style="font-weight: 800; font-size: 0.82rem; color: #f8fafc; display: flex; align-items: center; gap: 6px;">
              <span>🧬</span>
              <span>MA TRẬN MẪU HÌNH & CHẾ ĐỘ THỊ TRƯỜNG (TIME-DECAY ALPHA MATRIX)</span>
            </div>
            <span style="font-size: 0.68rem; color: #a5b4fc;">Trọng số thời gian (Time-Decay) • Tự động nhận diện Alpha Decay khi thị trường đổi chu kỳ</span>
          </div>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px;">
            <!-- Win Amplifiers Column -->
            <div style="background: rgba(34, 197, 94, 0.05); border: 1px solid rgba(34, 197, 94, 0.25); border-radius: 8px; padding: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 0.72rem; font-weight: 800; color: #4ade80;">🏆 MẪU HÌNH VÀNG (WIN AMPLIFIERS)</span>
                <span style="font-size: 0.65rem; background: rgba(34, 197, 94, 0.2); color: #4ade80; padding: 1px 6px; border-radius: 4px; font-weight: 700;">${winAmps.length} MẪU</span>
              </div>
              ${winAmps.length === 0 ? `
                <div style="font-size: 0.7rem; color: var(--text-dim); padding: 8px 0;">Đang tích lũy thêm dữ liệu mẫu hình...</div>
              ` : winAmps.map(p => `
                <div style="background: rgba(16, 24, 40, 0.6); border: 1px solid rgba(34, 197, 94, 0.2); border-radius: 6px; padding: 8px; margin-bottom: 6px;">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; gap: 6px;">
                    <span style="font-size: 0.72rem; font-weight: 700; color: #e2e8f0; line-height: 1.3;">${escapeHtml(p.display_label)}</span>
                    <span style="font-size: 0.65rem; font-weight: 800; color: #4ade80; background: rgba(34, 197, 94, 0.15); padding: 1px 5px; border-radius: 3px; white-space: nowrap;">
                      ${p.decayed_win_rate !== undefined ? p.decayed_win_rate : p.win_rate}% THẮNG
                    </span>
                  </div>
                  <div style="margin-bottom: 4px;">
                    ${renderFormPills(p.recent_outcomes)}
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 0.65rem; color: #94a3b8;">
                    <span>Lịch sử: ${p.win_rate}% (${p.wins}/${p.total_trades})</span>
                    <span style="color: #38bdf8; font-weight: 700;">+${(p.edge_boost * 100).toFixed(1)}% EDGE</span>
                  </div>
                </div>
              `).join("")}
            </div>

            <!-- Alpha Decay Column -->
            <div style="background: rgba(245, 158, 11, 0.05); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px; padding: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 0.72rem; font-weight: 800; color: #fbbf24;">⚡ SUY GIẢM HIỆU QUẢ (ALPHA DECAY)</span>
                <span style="font-size: 0.65rem; background: rgba(245, 158, 11, 0.2); color: #fbbf24; padding: 1px 6px; border-radius: 4px; font-weight: 700;">${decaying.length} MẪU</span>
              </div>
              ${decaying.length === 0 ? `
                <div style="font-size: 0.7rem; color: var(--text-dim); padding: 8px 0;">Không có mẫu hình nào bị suy giảm hiệu quả gần đây.</div>
              ` : decaying.map(p => `
                <div style="background: rgba(16, 24, 40, 0.6); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 6px; padding: 8px; margin-bottom: 6px;">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; gap: 6px;">
                    <span style="font-size: 0.72rem; font-weight: 700; color: #e2e8f0; line-height: 1.3;">${escapeHtml(p.display_label)}</span>
                    <span style="font-size: 0.65rem; font-weight: 800; color: #fbbf24; background: rgba(245, 158, 11, 0.15); padding: 1px 5px; border-radius: 3px; white-space: nowrap;">
                      ⚡ SUY GIẢM (${p.recent_loss_streak} SL)
                    </span>
                  </div>
                  <div style="margin-bottom: 4px;">
                    ${renderFormPills(p.recent_outcomes)}
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 0.65rem; color: #94a3b8; margin-bottom: 2px;">
                    <span>Lịch sử: ${p.win_rate}% ➔ Gần đây: <strong style="color:#fbbf24;">${p.decayed_win_rate}%</strong></span>
                    <span style="color: #fbbf24; font-weight: 700;">${(p.edge_boost * 100).toFixed(1)}% EDGE</span>
                  </div>
                  <div style="font-size: 0.62rem; color: #cbd5e1; background: rgba(245, 158, 11, 0.1); border-radius: 4px; padding: 3px 5px; margin-top: 3px;">
                    🛡️ Khống chế đòn bẩy &le; 10x, hạ 25% vốn cược để phòng ngừa đổi chế độ thị trường.
                  </div>
                </div>
              `).join("")}
            </div>

            <!-- Loss Traps Column -->
            <div style="background: rgba(239, 68, 68, 0.05); border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 8px; padding: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 0.72rem; font-weight: 800; color: #f87171;">⚠️ BẪY THUA ĐÃ NHẬN DIỆN (LOSS TRAPS)</span>
                <span style="font-size: 0.65rem; background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 1px 6px; border-radius: 4px; font-weight: 700;">${traps.length} BẪY</span>
              </div>
              ${traps.length === 0 ? `
                <div style="font-size: 0.7rem; color: var(--text-dim); padding: 8px 0;">Chưa ghi nhận bẫy thua lặp lại.</div>
              ` : traps.map(p => `
                <div style="background: rgba(16, 24, 40, 0.6); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; padding: 8px; margin-bottom: 6px;">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px; gap: 6px;">
                    <span style="font-size: 0.72rem; font-weight: 700; color: #e2e8f0; line-height: 1.3;">${escapeHtml(p.display_label)}</span>
                    <span style="font-size: 0.65rem; font-weight: 800; color: #f87171; background: rgba(239, 68, 68, 0.15); padding: 1px 5px; border-radius: 3px; white-space: nowrap;">
                      ${(100 - p.win_rate).toFixed(1)}% THUA
                    </span>
                  </div>
                  <div style="margin-bottom: 4px;">
                    ${renderFormPills(p.recent_outcomes)}
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 0.65rem; color: #94a3b8;">
                    <span>${p.losses} dính SL / ${p.total_trades} lệnh</span>
                    <span style="color: #ef4444; font-weight: 700;">TỰ ĐỘNG CHẶN/HOLD</span>
                  </div>
                </div>
              `).join("")}
            </div>
          </div>
        </div>
      </div>
    `;
  }

  const reflections = data.recent_reflections || [];
  if (reflections.length === 0) {
    listContainer.innerHTML = `
      <div style="text-align: center; padding: 30px; color: var(--text-dim); font-size: 0.85rem;">
        Chưa có bài học phản tỉnh nào. Sau khi hệ thống khớp và chốt/cắt lỗ lệnh đầu tiên, các phân tích nguyên nhân và đúc kết kinh nghiệm của AI sẽ xuất hiện tại đây!
      </div>
    `;
    return;
  }

  listContainer.innerHTML = reflections.map(r => {
    const isWin = r.is_win;
    const borderCol = isWin ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)';
    const bgCol = isWin ? 'rgba(34, 197, 94, 0.04)' : 'rgba(239, 68, 68, 0.04)';
    const pnlCol = isWin ? '#4ade80' : '#f87171';
    const tagBg = isWin ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)';
    const sign = r.pnl >= 0 ? '+' : '';

    return `
      <div style="border: 1px solid ${borderCol}; background: ${bgCol}; border-radius: 8px; padding: 12px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-weight: 800; font-size: 0.85rem; color: #fff;">${escapeHtml(r.symbol)}</span>
            <span style="background: ${tagBg}; color: ${pnlCol}; font-size: 0.65rem; font-weight: 700; padding: 2px 6px; border-radius: 4px;">
              ${r.side} ${r.leverage || 1}x • ${escapeHtml(r.reason)}
            </span>
          </div>
          <div style="font-weight: 800; font-family: var(--font-mono); color: ${pnlCol}; font-size: 0.85rem;">
            ${sign}${r.pnl}$ (${sign}${r.pnl_percent}%)
          </div>
        </div>

        ${r.signal_dna && r.signal_dna.display_label ? `
          <div style="margin-bottom: 6px;">
            <span style="background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.3); color: #d8b4fe; font-size: 0.68rem; font-weight: 700; padding: 2px 8px; border-radius: 4px;">
              🧬 DNA: ${escapeHtml(r.signal_dna.display_label)}
            </span>
          </div>
        ` : ''}

        ${r.root_cause ? `
          <div style="font-size: 0.74rem; color: #fbbf24; margin-bottom: 4px; display: flex; align-items: flex-start; gap: 4px; background: rgba(245, 158, 11, 0.08); padding: 4px 8px; border-radius: 4px; border-left: 2px solid #f59e0b;">
            <span>🔍 <strong>Chuẩn đoán:</strong> ${escapeHtml(r.root_cause)}</span>
          </div>
        ` : ''}

        <div style="font-size: 0.78rem; color: #e2e8f0; margin-bottom: 4px;">
          ${escapeHtml(r.lesson)}
        </div>
        <div style="font-size: 0.72rem; color: #38bdf8; font-weight: 600; display: flex; align-items: center; gap: 4px;">
          <span>💡 Bài học đúc kết:</span>
          <span>${escapeHtml(r.takeaway)}</span>
        </div>
        <div style="font-size: 0.65rem; color: var(--text-dim); margin-top: 4px; text-align: right;">
          ${r.timestamp}
        </div>
      </div>
    `;
  }).join("");
}

async function clearTradingMemory() {
  if (!confirm("Bạn có chắc chắn muốn đặt lại kho Trí Nhớ & Bài Học Tự Phản Tỉnh AI không?")) return;
  try {
    const res = await fetch("/api/memory/clear", { method: "POST" });
    const data = await res.json();
    renderMemoryData(data.memory);
    showNotification({
      type: "info",
      title: "Đã Đặt Lại Trí Nhớ AI",
      message: "Toàn bộ bài học tự phản tỉnh đã được làm mới.",
      duration: 5000
    });
    const memoryBadge = document.getElementById("header-memory-count");
    if (memoryBadge) memoryBadge.textContent = "0";
  } catch (e) {
    showNotification({
      type: "error",
      title: "Lỗi",
      message: "Không thể xóa trí nhớ AI: " + e,
      duration: 5000
    });
  }
}

// ============================================================
// ⚡ BINANCE FUTURES LIVE & TESTNET ADAPTER (BƯỚC 2)
// ============================================================
let currentBinanceStatus = null;

async function openBinanceModal() {
  const modal = document.getElementById("binance-modal");
  if (!modal) return;
  modal.classList.add("open");
  modal.classList.add("active");
  await fetchBinanceStatus();
}

function closeBinanceModal() {
  const modal = document.getElementById("binance-modal");
  if (modal) {
    modal.classList.remove("open");
    modal.classList.remove("active");
  }
}
window.openBinanceModal = openBinanceModal;
window.closeBinanceModal = closeBinanceModal;

function onBinanceModeChange(mode) {
  const apiKeyInput = document.getElementById("binance-api-key");
  const apiSecInput = document.getElementById("binance-api-secret");
  if (mode === "PAPER") {
    if (apiKeyInput) apiKeyInput.placeholder = "Không yêu cầu API Key ở chế độ mô phỏng nội bộ...";
    if (apiSecInput) apiSecInput.placeholder = "Không yêu cầu Secret Key...";
  } else if (mode === "BINANCE_TESTNET") {
    if (apiKeyInput) apiKeyInput.placeholder = "Dán API Key từ https://testnet.binancefuture.com...";
    if (apiSecInput) apiSecInput.placeholder = "Dán Secret Key từ https://testnet.binancefuture.com...";
  } else {
    if (apiKeyInput) apiKeyInput.placeholder = "Dán API Key thực tế từ Binance.com (Chỉ cấp quyền Futures Trading)...";
    if (apiSecInput) apiSecInput.placeholder = "Dán Secret Key thực tế...";
  }
}

async function fetchBinanceStatus() {
  try {
    const res = await fetch("/api/binance/status");
    const data = await res.json();
    currentBinanceStatus = data;
    renderBinanceStatus(data);
  } catch (e) {
    console.error("Lỗi lấy trạng thái Binance:", e);
  }
}

function renderBinanceStatus(data) {
  const conn = data.connection || {};
  const isConfigured = data.is_configured;
  const mode = data.mode || "BINANCE_TESTNET";

  // Update Header Button
  const headerMode = document.getElementById("header-binance-mode");
  const headerIcon = document.getElementById("binance-status-icon");
  const subBadge = document.getElementById("sub-badge-mode");
  const btnConnect = document.getElementById("btn-binance-connect");

  if (mode === "BINANCE_TESTNET") {
    const totalStr = conn.total_equity_usd ? ` • $${Math.round(conn.total_equity_usd).toLocaleString()}` : (conn.wallet_balance ? ` • $${Math.round(conn.wallet_balance).toLocaleString()} USDT` : "");
    if (headerMode) headerMode.textContent = isConfigured ? `TESTNET LIVE${totalStr}` : "BINANCE TESTNET";
    if (headerIcon) headerIcon.textContent = isConfigured ? "🟢" : "🟡";
    if (subBadge) subBadge.textContent = isConfigured ? "SWARM v1.0 • BINANCE TESTNET LIVE" : "SWARM v1.0 • TESTNET CHỜ CẤU HÌNH";
  } else if (mode === "BINANCE_REAL") {
    if (headerMode) headerMode.textContent = "BINANCE REAL";
    if (headerIcon) headerIcon.textContent = isConfigured ? "🔴" : "⚠️";
    if (subBadge) subBadge.textContent = "SWARM v1.0 • TIỀN THẬT (REAL MONEY)";
  } else {
    if (headerMode) headerMode.textContent = "PAPER TRADING";
    if (headerIcon) headerIcon.textContent = "⚪";
    if (subBadge) subBadge.textContent = "SWARM v1.0 • MÔ PHỎNG NỘI BỘ";
  }

  if (btnConnect) {
    if (isConfigured && mode === "BINANCE_TESTNET") {
      btnConnect.style.borderColor = "rgba(34, 197, 94, 0.5)";
      btnConnect.style.color = "#4ade80";
      btnConnect.style.background = "rgba(34, 197, 94, 0.12)";
    } else if (isConfigured && mode === "BINANCE_REAL") {
      btnConnect.style.borderColor = "rgba(239, 68, 68, 0.6)";
      btnConnect.style.color = "#f87171";
      btnConnect.style.background = "rgba(239, 68, 68, 0.12)";
    } else {
      btnConnect.style.borderColor = "rgba(245, 158, 11, 0.5)";
      btnConnect.style.color = "#fbbf24";
      btnConnect.style.background = "rgba(245, 158, 11, 0.1)";
    }
  }

  // Update Modal Banner
  const statusText = document.getElementById("binance-status-text");
  const dot = document.getElementById("binance-dot");
  const latencyVal = document.getElementById("binance-latency-val");
  const balanceVal = document.getElementById("binance-balance-val");
  const totalUsdVal = document.getElementById("binance-total-usd-val");
  const assetsPill = document.getElementById("binance-assets-pill");
  const assetsText = document.getElementById("binance-assets-breakdown-text");

  if (latencyVal) latencyVal.textContent = conn.latency_ms ? `${conn.latency_ms} ms` : "-- ms";
  if (balanceVal) balanceVal.textContent = conn.available_balance !== undefined ? `$${conn.available_balance.toLocaleString()} USDT` : "-- USDT";
  if (totalUsdVal) totalUsdVal.textContent = conn.total_equity_usd !== undefined ? `$${conn.total_equity_usd.toLocaleString()} USD` : (conn.wallet_balance ? `$${conn.wallet_balance.toLocaleString()} USD` : "-- USD");

  if (assetsPill && assetsText) {
    if (conn.assets_breakdown && Object.keys(conn.assets_breakdown).length > 0) {
      assetsPill.style.display = "flex";
      const parts = Object.entries(conn.assets_breakdown).map(([asset, amt]) => {
        const fmtAmt = typeof amt === 'number' && amt < 1 ? amt.toFixed(4) : Math.round(amt).toLocaleString();
        return `<strong style="color:#fbbf24;">${fmtAmt}</strong> ${asset}`;
      });
      assetsText.innerHTML = parts.join(" &bull; ");
    } else {
      assetsPill.style.display = "none";
    }
  }

  if (statusText && dot) {
    if (!conn.success) {
      statusText.textContent = conn.message || "Lỗi kết nối máy chủ Binance";
      statusText.style.color = "#f87171";
      dot.className = "status-dot error";
    } else if (isConfigured) {
      statusText.textContent = `ĐÃ KẾT NỐI • ${mode === 'BINANCE_REAL' ? 'TIỀN THẬT' : 'TESTNET'}`;
      statusText.style.color = "#4ade80";
      dot.className = "status-dot active";
    } else {
      statusText.textContent = `SẴN SÀNG KẾT NỐI (Chưa cài đặt API Key)`;
      statusText.style.color = "#fbbf24";
      dot.className = "status-dot warning";
    }
  }

  // Select matching radio
  const radios = document.querySelectorAll('input[name="binance-mode-select"]');
  radios.forEach(r => {
    if (r.value === mode) r.checked = true;
  });

  const apiKeyInput = document.getElementById("binance-api-key");
  const apiSecInput = document.getElementById("binance-api-secret");
  if (isConfigured) {
    if (apiKeyInput && !apiKeyInput.value) apiKeyInput.placeholder = "•••••••••••••••• (Đã lưu trong .env, nhập để thay đổi)";
    if (apiSecInput && !apiSecInput.value) apiSecInput.placeholder = "•••••••••••••••• (Đã lưu trong .env, nhập để thay đổi)";
  }
}

async function testBinanceConnection() {
  const btn = document.getElementById("btn-binance-test");
  if (btn) btn.textContent = "⏳ Đang ping sàn...";
  try {
    const res = await fetch("/api/binance/test-connection", { method: "POST" });
    const data = await res.json();
    const conn = data.connection || {};
    renderBinanceStatus({
      mode: currentBinanceStatus ? currentBinanceStatus.mode : "BINANCE_TESTNET",
      is_configured: currentBinanceStatus ? currentBinanceStatus.is_configured : false,
      connection: conn
    });
    showNotification({
      type: conn.success ? "success" : "error",
      title: conn.success ? "Kết Nối Binance Thành Công" : "Lỗi Kết Nối",
      message: conn.message || "Đã kiểm tra ping sàn Binance.",
      duration: 5000
    });
  } catch (e) {
    showNotification({
      type: "error",
      title: "Lỗi Mạng",
      message: "Không thể gửi yêu cầu kiểm tra ping: " + e,
      duration: 5000
    });
  } finally {
    if (btn) btn.textContent = "⚡ KIỂM TRA PING & SỐ DƯ";
  }
}

async function saveBinanceConfig() {
  const btn = document.getElementById("btn-binance-save");
  const modeRadio = document.querySelector('input[name="binance-mode-select"]:checked');
  const mode = modeRadio ? modeRadio.value : "BINANCE_TESTNET";
  const apiKey = (document.getElementById("binance-api-key")?.value || "").trim();
  const apiSecret = (document.getElementById("binance-api-secret")?.value || "").trim();

  if (btn) btn.textContent = "⏳ Đang lưu & xác thực...";
  try {
    const res = await fetch("/api/binance/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: mode,
        api_key: apiKey,
        api_secret: apiSecret
      })
    });
    const data = await res.json();
    await fetchBinanceStatus();
    showNotification({
      type: "success",
      title: "Đã Cập Nhật Cấu Hình Sàn",
      message: `Chế độ: ${mode}. ${data.connection?.message || ''}`,
      duration: 6000
    });
    // Clear inputs for security
    if (apiKey) document.getElementById("binance-api-key").value = "";
    if (apiSecret) document.getElementById("binance-api-secret").value = "";
  } catch (e) {
    showNotification({
      type: "error",
      title: "Lỗi Lưu Cấu Hình",
      message: "Không thể lưu thông tin sàn: " + e,
      duration: 5000
    });
  } finally {
    if (btn) btn.textContent = "💾 LƯU CẤU HÌNH & ÁP DỤNG";
  }
}

window.onBinanceModeChange = onBinanceModeChange;
window.testBinanceConnection = testBinanceConnection;
window.saveBinanceConfig = saveBinanceConfig;
window.fetchBinanceStatus = fetchBinanceStatus;

// ============================================================
// 12. MULTI-CAPITAL STRATEGY PROFILES CONTROLLER
// ============================================================

let currentStrategiesList = [];
let currentActiveStrategyId = "MICRO_SNIPER_SMC";

async function loadStrategyProfiles() {
  try {
    const res = await fetch("/api/strategy/list");
    if (!res.ok) return;
    const data = await res.json();
    currentStrategiesList = data.strategies || [];
    currentActiveStrategyId = data.active_id || "MICRO_SNIPER_SMC";

    const selectEl = document.getElementById("strategy-profile-select");
    if (selectEl && currentStrategiesList.length > 0) {
      selectEl.innerHTML = currentStrategiesList.map(s => {
        const isSel = (s.id === currentActiveStrategyId);
        return `<option value="${s.id}" ${isSel ? "selected" : ""} style="background:#0f172a; color:#38bdf8;">${s.badge} (${s.target_capital})</option>`;
      }).join("");
      selectEl.value = currentActiveStrategyId;
    }

    renderStrategyModal(currentStrategiesList, currentActiveStrategyId);
  } catch (e) {
    console.warn("Failed to load strategy profiles:", e);
  }
}

async function changeStrategyProfile(strategyId) {
  if (!strategyId) return;
  try {
    const res = await fetch("/api/strategy/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy_id: strategyId })
    });
    const data = await res.json();
    if (data.success && data.active_strategy) {
      const s = data.active_strategy;
      currentActiveStrategyId = s.id;
      showNotification({
        type: "success",
        title: "Đã Chuyển Đổi Chiến Lược",
        message: `Kích hoạt: ${s.badge} - ${s.name}\nĐòn bẩy: ${s.leverage}x-${s.max_leverage}x | SL: ${(s.sl_percent*100).toFixed(1)}% | TP: ${(s.tp_percent*100).toFixed(1)}%`,
        duration: 6000
      });
      loadStrategyProfiles();
    }
  } catch (e) {
    showNotification({
      type: "error",
      title: "Lỗi Chuyển Đổi Chiến Lược",
      message: String(e),
      duration: 5000
    });
  }
}

function renderStrategyModal(strategies, activeId) {
  const container = document.getElementById("strategy-cards-list");
  if (!container || !strategies) return;

  container.innerHTML = strategies.map(s => {
    const isActive = (s.id === activeId);
    const borderColor = isActive ? "#10b981" : "rgba(255,255,255,0.12)";
    const bg = isActive ? "rgba(16, 185, 129, 0.08)" : "rgba(15, 23, 42, 0.6)";

    const coinsBadges = (s.target_coins || []).map(c => 
      `<span style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); padding: 2px 7px; border-radius: 4px; font-weight: 700; font-size: 0.72rem;">${c}</span>`
    ).join(" ");

    return `
      <div style="background: ${bg}; border: 1px solid ${borderColor}; border-radius: 8px; padding: 16px; position: relative; transition: all 0.2s ease;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 8px;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 1.05rem; font-weight: 800; color: ${isActive ? '#34d399' : '#e2e8f0'};">${escapeHtml(s.name)}</span>
              ${isActive ? '<span style="background: #10b981; color: #022c22; font-weight: 800; font-size: 0.65rem; padding: 2px 8px; border-radius: 10px;">ĐANG HOẠT ĐỘNG</span>' : ''}
            </div>
            <div style="font-size: 0.75rem; color: #94a3b8; margin-top: 3px;">💰 Phù hợp: <strong style="color: #fbbf24;">${escapeHtml(s.target_capital)}</strong> • Danh mục ưu tiên: ${coinsBadges}</div>
          </div>
          <div>
            ${isActive ? `
              <button class="btn btn-secondary" style="border-color: #10b981; color: #34d399; background: rgba(16,185,129,0.15); font-weight: 700; font-size: 0.76rem; cursor: default;">✓ ĐANG CHẠY</button>
            ` : `
              <button class="btn btn-primary" style="background: linear-gradient(135deg, #10b981, #059669); border-color: #10b981; font-weight: 700; font-size: 0.76rem;" onclick="changeStrategyProfile('${s.id}')">⚡ KÍCH HOẠT</button>
            `}
          </div>
        </div>

        <p style="font-size: 0.78rem; color: #cbd5e1; line-height: 1.5; margin: 8px 0 12px 0;">${escapeHtml(s.description)}</p>

        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; background: rgba(0,0,0,0.25); border-radius: 6px; padding: 10px;">
          <div>
            <div style="font-size: 0.64rem; color: var(--text-dim);">ĐÒN BẨY (LEVERAGE)</div>
            <div style="font-weight: 800; font-size: 0.85rem; color: #38bdf8;">${s.leverage}x - ${s.max_leverage}x</div>
          </div>
          <div>
            <div style="font-size: 0.64rem; color: var(--text-dim);">PHÂN BỔ VỐN/LỆNH</div>
            <div style="font-weight: 800; font-size: 0.85rem; color: #fbbf24;">${Math.round(s.stake_percent_range[0]*100)}% - ${Math.round(s.stake_percent_range[1]*100)}%</div>
          </div>
          <div>
            <div style="font-size: 0.64rem; color: var(--text-dim);">CẮT LỖ (SL)</div>
            <div style="font-weight: 800; font-size: 0.85rem; color: #f87171;">-${(s.sl_percent*100).toFixed(1)}%</div>
          </div>
          <div>
            <div style="font-size: 0.64rem; color: var(--text-dim);">CHỐT LỜI (TP)</div>
            <div style="font-weight: 800; font-size: 0.85rem; color: #4ade80;">+${(s.tp_percent*100).toFixed(1)}% (R:R 1:${(s.tp_percent/s.sl_percent).toFixed(1)})</div>
          </div>
        </div>

        <div style="display: flex; gap: 8px; margin-top: 10px; font-size: 0.7rem; color: #94a3b8;">
          <span>${s.multi_timeframe ? '✅ Nến Đa Khung 1H-15M-1M' : '⚪ Đơn Khung'}</span>
          <span>•</span>
          <span>${s.candlestick_patterns ? '✅ Nhận diện Pinbar/Engulfing' : '⚪ Không quét mẫu hình'}</span>
          <span>•</span>
          <span>Phân loại: <strong style="color: #cbd5e1;">${s.strategy_category}</strong></span>
        </div>
      </div>
    `;
  }).join("");
}

function openStrategyModal() {
  const modal = document.getElementById("strategy-modal");
  if (modal) {
    modal.classList.add("active");
    modal.classList.add("open");
    loadStrategyProfiles();
  }
}

function closeStrategyModal() {
  const modal = document.getElementById("strategy-modal");
  if (modal) {
    modal.classList.remove("active");
    modal.classList.remove("open");
  }
}

window.loadStrategyProfiles = loadStrategyProfiles;
window.changeStrategyProfile = changeStrategyProfile;
window.openStrategyModal = openStrategyModal;
window.closeStrategyModal = closeStrategyModal;

// ============================================================
// 12. SESSION STRATEGY ADAPTATION ENGINE (TIME-OF-DAY FILTER)
// ============================================================
function updateSessionDisplay(session) {
  if (!session) return;
  const nameEl = document.getElementById("header-session-name");
  const iconEl = document.getElementById("session-badge-icon");
  const btnEl = document.getElementById("btn-session-info");
  
  if (nameEl) {
    nameEl.textContent = session.badge ? session.badge.replace(/^[^\w\s]+/, '').trim() : (session.name || "PHIÊN GIAO DỊCH");
  }
  
  if (iconEl) {
    const icons = {
      "NEW_YORK_SURGE": "🚀",
      "LATE_US_CLEANUP": "🦅",
      "ASIAN_ACCUMULATION": "🌏",
      "LONDON_JUDAS_TRAP": "⚠️",
      "US_PREMARKET": "⏳",
      "QUIET_HOURS": "🌙"
    };
    iconEl.textContent = icons[session.id] || "🌐";
  }
  
  if (btnEl) {
    if (session.id === "LONDON_JUDAS_TRAP") {
      btnEl.style.borderColor = "rgba(239, 68, 68, 0.6)";
      btnEl.style.color = "#f87171";
      btnEl.style.background = "rgba(239, 68, 68, 0.15)";
      btnEl.title = `⚠️ ${session.name} (${session.time_range}) - Chế độ Siêu Phòng Thủ!`;
    } else if (session.id === "NEW_YORK_SURGE") {
      btnEl.style.borderColor = "rgba(245, 158, 11, 0.6)";
      btnEl.style.color = "#fbbf24";
      btnEl.style.background = "rgba(245, 158, 11, 0.15)";
      btnEl.title = `🚀 ${session.name} (${session.time_range}) - Tấn Công Toàn Lực!`;
    } else if (session.id === "LATE_US_CLEANUP") {
      btnEl.style.borderColor = "rgba(52, 211, 153, 0.6)";
      btnEl.style.color = "#34d399";
      btnEl.style.background = "rgba(52, 211, 153, 0.15)";
      btnEl.title = `🦅 ${session.name} (${session.time_range}) - Bắn Tỉa Chốt Sổ!`;
    } else {
      btnEl.style.borderColor = "rgba(56, 189, 248, 0.4)";
      btnEl.style.color = "#38bdf8";
      btnEl.style.background = "rgba(56, 189, 248, 0.1)";
      btnEl.title = `${session.name} (${session.time_range})`;
    }
  }
}

async function loadSessionInfo() {
  try {
    const res = await fetch("/api/session/all");
    if (!res.ok) return;
    const data = await res.json();
    const curr = data.current;
    const sessions = data.sessions || [];

    // Render current highlight card
    const highlightEl = document.getElementById("session-current-highlight");
    if (highlightEl && curr) {
      const isTrap = curr.id === "LONDON_JUDAS_TRAP";
      const isGold = curr.id === "NEW_YORK_SURGE";
      const borderColor = isTrap ? "rgba(239, 68, 68, 0.6)" : (isGold ? "rgba(245, 158, 11, 0.6)" : "rgba(56, 189, 248, 0.6)");
      const bg = isTrap ? "rgba(239, 68, 68, 0.12)" : (isGold ? "rgba(245, 158, 11, 0.12)" : "rgba(56, 189, 248, 0.12)");

      highlightEl.innerHTML = `
        <div style="background: ${bg}; border: 1.5px solid ${borderColor}; border-radius: 10px; padding: 14px 16px; position: relative;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 1.4rem;">${curr.id === 'LONDON_JUDAS_TRAP' ? '⚠️' : (curr.id === 'NEW_YORK_SURGE' ? '🚀' : '🌐')}</span>
              <div>
                <div style="font-size: 0.95rem; font-weight: 800; color: #f8fafc;">${curr.name}</div>
                <div style="font-size: 0.72rem; color: #94a3b8;">Khung giờ: <strong style="color:#e2e8f0;">${curr.time_range}</strong> • Giờ hiện tại (VN): <strong style="color:#38bdf8;">${curr.current_time_vn}</strong></div>
              </div>
            </div>
            <span style="background: ${isTrap ? '#ef4444' : (isGold ? '#f59e0b' : '#3b82f6')}; color: #fff; font-weight: 800; font-size: 0.7rem; padding: 4px 10px; border-radius: 9999px; letter-spacing: 0.5px;">
              ĐANG HOẠT ĐỘNG
            </span>
          </div>
          <div style="font-size: 0.78rem; color: #cbd5e1; line-height: 1.5; margin-bottom: 10px;">
            ${curr.description}
          </div>
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; background: rgba(0,0,0,0.25); border-radius: 6px; padding: 8px 10px; font-size: 0.72rem;">
            <div><span style="color:#94a3b8;">Đòn bẩy trần:</span> <strong style="color:#f8fafc;">${curr.leverage_cap}x</strong></div>
            <div><span style="color:#94a3b8;">Hệ số cược:</span> <strong style="color:${curr.stake_multiplier < 1 ? '#f87171' : '#34d399'};">${(curr.stake_multiplier*100).toFixed(0)}%</strong></div>
            <div><span style="color:#94a3b8;">Chế độ rủi ro:</span> <strong style="color:${isTrap ? '#f87171' : '#34d399'};">${curr.risk_mode}</strong></div>
            <div><span style="color:#94a3b8;">Lệnh Breakout:</span> <strong style="color:${curr.allow_breakout ? '#34d399' : '#f87171'};">${curr.allow_breakout ? 'Cho phép' : 'CẤM (Tránh bẫy)'}</strong></div>
          </div>
        </div>
      `;
    }

    // Render list of all sessions
    const listEl = document.getElementById("session-cards-list");
    if (listEl) {
      listEl.innerHTML = sessions.map(s => {
        const isActive = curr && s.id === curr.id;
        const activeBorder = isActive ? "border: 1.5px solid #38bdf8; background: rgba(56, 189, 248, 0.08);" : "border: 1px solid rgba(255,255,255,0.08); background: rgba(15, 23, 42, 0.6);";
        return `
          <div style="border-radius: 8px; padding: 12px 14px; ${activeBorder} display: flex; flex-direction: column; gap: 6px;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-weight: 700; font-size: 0.82rem; color: #f1f5f9;">${s.name}</span>
                <span style="font-size: 0.7rem; color: #38bdf8; background: rgba(56, 189, 248, 0.12); padding: 2px 6px; border-radius: 4px;">${s.time_range}</span>
              </div>
              ${isActive ? '<span style="color:#34d399; font-weight:700; font-size:0.7rem;">● Đang diễn ra</span>' : ''}
            </div>
            <div style="font-size: 0.74rem; color: #94a3b8; line-height: 1.4;">${s.description}</div>
            <div style="display: flex; gap: 16px; font-size: 0.7rem; color: #64748b; margin-top: 2px;">
              <span>Đòn bẩy tối đa: <strong style="color:#e2e8f0;">${s.leverage_cap}x</strong></span>
              <span>Vốn cược: <strong style="color:#e2e8f0;">${(s.stake_multiplier*100).toFixed(0)}%</strong></span>
              <span>Lệnh Breakout: <strong style="color:${s.allow_breakout ? '#34d399' : '#f87171'};">${s.allow_breakout ? 'Bắt sóng' : 'Cấm'}</strong></span>
            </div>
          </div>
        `;
      }).join("");
    }
  } catch (err) {
    console.error("Error loading session info:", err);
  }
}

function openSessionModal() {
  const modal = document.getElementById("session-modal");
  if (modal) {
    modal.classList.add("active");
    modal.classList.add("open");
    loadSessionInfo();
  }
}

function closeSessionModal() {
  const modal = document.getElementById("session-modal");
  if (modal) {
    modal.classList.remove("active");
    modal.classList.remove("open");
  }
}

window.openSessionModal = openSessionModal;
window.closeSessionModal = closeSessionModal;
window.loadSessionInfo = loadSessionInfo;
window.updateSessionDisplay = updateSessionDisplay;

// ============================================================
// 13. DEDICATED COIN WORKERS (PARALLEL SWARM UI)
// ============================================================
function updateCoinWorkersUI(swarmData) {
  if (!swarmData) return;
  const countBadge = document.getElementById("workers-count-badge");
  const gridEl = document.getElementById("coin-workers-grid");
  if (!gridEl) return;

  const workers = swarmData.workers || [];
  if (countBadge) {
    const active = swarmData.active_workers || 0;
    countBadge.textContent = `${active} BOT ĐANG CHẠY SONG SONG`;
  }

  if (workers.length === 0) {
    gridEl.innerHTML = `<div style="grid-column: 1 / -1; text-align: center; color: var(--text-dim); font-size: 0.75rem; padding: 12px;">Chưa có bot chuyên trách nào. Hãy thêm coin vào Watchlist để hệ thống tự động phân thân!</div>`;
    return;
  }

  gridEl.innerHTML = workers.map(w => {
    let statusBg = "rgba(56, 189, 248, 0.15)";
    let statusColor = "#38bdf8";
    let statusText = "SĂN MỒI";
    let dotColor = "#38bdf8";

    if (w.status === "IN_POSITION") {
      statusBg = "rgba(245, 158, 11, 0.15)";
      statusColor = "#fbbf24";
      statusText = "GIỮ VỊ THẾ";
      dotColor = "#fbbf24";
    } else if (w.status === "SCANNING_MTF") {
      statusBg = "rgba(168, 85, 247, 0.15)";
      statusColor = "#c084fc";
      statusText = "SOI NẾN 1M";
      dotColor = "#c084fc";
    } else if (w.status === "SIGNAL_TRIGGERED") {
      statusBg = "rgba(34, 197, 94, 0.15)";
      statusColor = "#4ade80";
      statusText = "BÓP CÒ";
      dotColor = "#4ade80";
    } else if (w.status === "PAUSED" || w.is_paused) {
      statusBg = "rgba(148, 163, 184, 0.15)";
      statusColor = "#94a3b8";
      statusText = "TẠM NGHỈ";
      dotColor = "#94a3b8";
    } else if (w.status === "STANDBY") {
      statusBg = "rgba(100, 116, 139, 0.15)";
      statusColor = "#cbd5e1";
      statusText = "STANDBY";
      dotColor = "#64748b";
    }

    return `
      <div class="coin-worker-card" style="background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 6px; position: relative; overflow: hidden; transition: border-color 0.2s ease;">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div style="display: flex; align-items: center; gap: 6px;">
            <span style="font-weight: 800; font-size: 0.85rem; color: #f8fafc;">${w.coin}</span>
            <span style="font-size: 0.65rem; color: var(--text-dim);">/USDT</span>
          </div>
          <span style="font-size: 0.65rem; font-weight: 700; background: ${statusBg}; color: ${statusColor}; padding: 2px 6px; border-radius: 4px; display: flex; align-items: center; gap: 4px;">
            <span style="display: inline-block; width: 5px; height: 5px; border-radius: 50%; background: ${dotColor};"></span>
            ${statusText}
          </span>
        </div>
        <div style="font-size: 0.7rem; color: #94a3b8; line-height: 1.35; min-height: 28px; display: flex; align-items: center;">
          ${w.last_action_desc || 'Sẵn sàng bắt sóng nến'}
        </div>
        <div style="display: flex; justify-content: space-between; font-size: 0.65rem; color: #64748b; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 5px; margin-top: 2px;">
          <span>⚡ Quét: <strong style="color:#cbd5e1;">${w.scan_count}</strong></span>
          <span>${w.last_scan_time_vn || ''}</span>
        </div>
      </div>
    `;
  }).join("");
}

window.updateCoinWorkersUI = updateCoinWorkersUI;

// ============================================================
// 14. DAILY METRICS & CIRCUIT BREAKER MODAL / UI
// ============================================================
let currentDailyMetrics = null;

function updateDailyMetricsUI(daily, totalEquity) {
  if (!daily) return;
  currentDailyMetrics = daily;

  const dailyPnl = daily.daily_pnl || 0.0;
  const dailyRoi = daily.daily_roi_percent || 0.0;
  const startEq = daily.start_equity || 10.0;
  const pnlSign = dailyPnl >= 0 ? "+" : "";

  // 1. KPI Card in Bento Grid
  const kpiDailyPnl = document.getElementById("kpi-daily-pnl");
  const kpiDailySub = document.getElementById("kpi-daily-sub");
  if (kpiDailyPnl) {
    kpiDailyPnl.textContent = `${pnlSign}$${dailyPnl.toFixed(2)} (${pnlSign}${dailyRoi.toFixed(1)}%)`;
    kpiDailyPnl.className = `kpi-value ${dailyPnl >= 0 ? 'highlight-green' : 'highlight-red'}`;
  }

  if (kpiDailySub) {
    let statusSub = "Cầu chì: An toàn";
    if (daily.circuit_breaker_active) {
      statusSub = "🚨 CẦU CHÌ ĐÃ NGẮT!";
    } else if (daily.target_reached) {
      statusSub = "🏆 Đạt mục tiêu (+20%)";
    }
    kpiDailySub.textContent = `Vốn ngày: $${startEq.toFixed(2)} • ${statusSub}`;
  }

  // 2. Header Status Button
  const headerRoiEl = document.getElementById("header-daily-pnl-roi");
  const headerDotEl = document.getElementById("daily-status-dot");
  if (headerRoiEl) {
    headerRoiEl.textContent = `${pnlSign}${dailyRoi.toFixed(1)}%`;
    headerRoiEl.style.color = dailyPnl >= 0 ? "#4ade80" : "#f87171";
  }
  if (headerDotEl) {
    if (daily.circuit_breaker_active) {
      headerDotEl.className = "status-dot";
      headerDotEl.style.background = "#ef4444";
      headerDotEl.style.boxShadow = "0 0 8px #ef4444";
    } else {
      headerDotEl.className = "status-dot active";
      headerDotEl.style.background = "#4ade80";
      headerDotEl.style.boxShadow = "0 0 8px #4ade80";
    }
  }

  // 3. Modal Elements if open
  updateDailyModalContent(daily, totalEquity);
}

function updateDailyModalContent(daily, totalEquity) {
  if (!daily) return;
  const modalDate = document.getElementById("daily-modal-date");
  const modalStartEq = document.getElementById("daily-modal-start-equity");
  const modalRoi = document.getElementById("daily-modal-roi");
  const modalCurrentEq = document.getElementById("daily-modal-current-equity");
  const modalBadge = document.getElementById("daily-modal-badge");
  const targetBadge = document.getElementById("daily-target-status-badge");
  const breakerBadge = document.getElementById("daily-breaker-status-badge");

  const dailyPnl = daily.daily_pnl || 0.0;
  const dailyRoi = daily.daily_roi_percent || 0.0;
  const pnlSign = dailyPnl >= 0 ? "+" : "";

  if (modalDate) modalDate.textContent = daily.trading_day || "Hôm nay";
  if (modalStartEq) modalStartEq.textContent = `$${(daily.start_equity || 10).toFixed(2)}`;
  if (modalRoi) {
    modalRoi.textContent = `${pnlSign}$${dailyPnl.toFixed(2)} (${pnlSign}${dailyRoi.toFixed(1)}%)`;
    modalRoi.style.color = dailyPnl >= 0 ? "#4ade80" : "#f87171";
  }
  if (modalCurrentEq) modalCurrentEq.textContent = `$${(totalEquity || daily.current_equity || 10).toFixed(2)}`;

  if (modalBadge) {
    if (daily.profit_lock_active) {
      modalBadge.textContent = "🔒 ĐÃ KHÓA LÃI NGÀY";
      modalBadge.style.background = "rgba(245, 158, 11, 0.25)";
      modalBadge.style.color = "#fbbf24";
      modalBadge.style.borderColor = "rgba(245, 158, 11, 0.6)";
    } else if (daily.circuit_breaker_active) {
      modalBadge.textContent = "🚨 CẦU CHÌ NGẮT";
      modalBadge.style.background = "rgba(239, 68, 68, 0.2)";
      modalBadge.style.color = "#f87171";
      modalBadge.style.borderColor = "rgba(239, 68, 68, 0.5)";
    } else if (daily.target_reached) {
      modalBadge.textContent = "🏆 ĐẠT MỤC TIÊU";
      modalBadge.style.background = "rgba(245, 158, 11, 0.2)";
      modalBadge.style.color = "#fbbf24";
      modalBadge.style.borderColor = "rgba(245, 158, 11, 0.5)";
    } else {
      modalBadge.textContent = "✓ HOẠT ĐỘNG";
      modalBadge.style.background = "rgba(74, 222, 128, 0.2)";
      modalBadge.style.color = "#4ade80";
      modalBadge.style.borderColor = "rgba(74, 222, 128, 0.4)";
    }
  }

  if (targetBadge) {
    if (daily.profit_lock_active) {
      targetBadge.textContent = "🔒 ĐÃ ĐẠT (+20%) • KHÓA BẢO VỆ VỐN";
      targetBadge.style.background = "rgba(245, 158, 11, 0.25)";
      targetBadge.style.color = "#fbbf24";
    } else if (daily.target_reached) {
      targetBadge.textContent = "✓ ĐÃ ĐẠT (+20%)";
      targetBadge.style.background = "rgba(245, 158, 11, 0.25)";
      targetBadge.style.color = "#fbbf24";
    } else {
      targetBadge.textContent = "ĐANG BÁM SÁT";
      targetBadge.style.background = "rgba(100, 116, 139, 0.2)";
      targetBadge.style.color = "#cbd5e1";
    }
  }

  const unlockWrapper = document.getElementById("btn-unlock-profit-wrapper");
  if (unlockWrapper) {
    unlockWrapper.style.display = daily.profit_lock_active ? "block" : "none";
  }

  if (breakerBadge) {
    if (daily.circuit_breaker_active) {
      breakerBadge.textContent = "🚨 ĐÃ NGẮT (DỪNG TRADE)";
      breakerBadge.style.background = "rgba(239, 68, 68, 0.25)";
      breakerBadge.style.color = "#f87171";
    } else {
      breakerBadge.textContent = "AN TOÀN";
      breakerBadge.style.background = "rgba(16, 185, 129, 0.2)";
      breakerBadge.style.color = "#4ade80";
    }
  }
}

function openDailyMetricsModal() {
  const modal = document.getElementById("daily-modal");
  if (modal) {
    modal.classList.add("active");
    modal.classList.add("open");
    if (currentDailyMetrics) {
      updateDailyModalContent(currentDailyMetrics, currentPortfolioEquity);
    }
  }
}

function closeDailyMetricsModal() {
  const modal = document.getElementById("daily-modal");
  if (modal) {
    modal.classList.remove("active");
    modal.classList.remove("open");
  }
}

async function resetDailyMetricsNow() {
  if (!confirm("Bạn có chắc chắn muốn chốt số liệu và đặt lại mốc vốn bắt đầu ngày mới ngay bây giờ không?")) {
    return;
  }
  try {
    const res = await fetch("/api/daily/reset", { method: "POST" });
    if (res.ok) {
      if (typeof showToast === "function") {
        showToast({
          title: "Reset Mốc Ngày Thành Công",
          message: "Đã đặt lại mốc vốn bắt đầu ngày mới và xóa trạng thái cầu chì.",
          type: "success"
        });
      }
      await loadPortfolio();
      closeDailyMetricsModal();
    }
  } catch (err) {
    console.error("Lỗi reset daily:", err);
  }
}

async function unlockProfitTargetNow() {
  if (!confirm("Bạn có chắc chắn muốn mở khóa giao dịch để bot tiếp tục mở lệnh mới hôm nay không?")) {
    return;
  }
  try {
    const res = await fetch("/api/daily/unlock_profit", { method: "POST" });
    if (res.ok) {
      if (typeof showToast === "function") {
        showToast({
          title: "Đã Mở Khóa Giao Dịch",
          message: "Đã gỡ bỏ khóa bảo vệ thành quả ngày theo lệnh của bạn.",
          type: "info"
        });
      }
      await loadPortfolio();
    }
  } catch (err) {
    console.error("Lỗi mở khóa profit lock:", err);
  }
}

window.openDailyMetricsModal = openDailyMetricsModal;
window.closeDailyMetricsModal = closeDailyMetricsModal;
window.resetDailyMetricsNow = resetDailyMetricsNow;
window.unlockProfitTargetNow = unlockProfitTargetNow;
window.updateDailyMetricsUI = updateDailyMetricsUI;





