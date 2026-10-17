let isAutoRunning = false;
let autoStatusInterval = null;

// Initialize Dashboard
document.addEventListener("DOMContentLoaded", () => {
  loadPortfolio();
  loadMarkets();
  checkAutoStatus();

  // Periodic status poll (every 3 seconds)
  setInterval(() => {
    loadPortfolio();
  }, 3000);

  // Periodic market refresh (every 30 seconds)
  setInterval(() => {
    loadMarkets();
  }, 30000);
});

// 1. Fetch & Render Portfolio Metrics, Positions, Logs, Trades
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
    cashEl.textContent = `Cash: $${data.cash_balance.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;

    const pnlSign = data.total_pnl >= 0 ? "+" : "";
    pnlEl.textContent = `${pnlSign}$${data.total_pnl.toFixed(2)} (${pnlSign}${data.pnl_percent.toFixed(1)}%)`;
    pnlEl.className = `kpi-value ${data.total_pnl >= 0 ? 'highlight-green' : 'highlight-red'}`;

    realizedEl.textContent = `Realized: $${data.realized_pnl.toFixed(2)} • Unr: $${data.unrealized_pnl.toFixed(2)}`;
    winrateEl.textContent = `${data.win_rate.toFixed(1)}%`;
    tradesEl.textContent = `${data.trades_count} Trades • ${data.total_open_count} Active Positions`;

    // Active Positions Table
    const posTbody = document.getElementById("positions-tbody");
    const posCountBadge = document.getElementById("open-positions-count");
    posCountBadge.textContent = `${data.open_positions.length} ACTIVE`;

    if (data.open_positions.length === 0) {
      posTbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No open positions. Run a Swarm Scan to take positions!</td></tr>`;
    } else {
      posTbody.innerHTML = data.open_positions.map(pos => {
        const pnl = (pos.shares * pos.current_price) - (pos.shares * pos.entry_price);
        const pnlPct = ((pos.current_price - pos.entry_price) / pos.entry_price) * 100;
        const pnlClass = pnl >= 0 ? "highlight-green" : "highlight-red";
        const tagClass = pos.outcome === "YES" ? "tag-outcome-yes" : "tag-outcome-no";

        return `
          <tr>
            <td><strong>${escapeHtml(pos.question)}</strong></td>
            <td><span class="${tagClass}">${pos.outcome}</span></td>
            <td>${pos.shares.toFixed(1)}</td>
            <td>$${pos.entry_price.toFixed(2)}</td>
            <td>$${pos.current_price.toFixed(2)}</td>
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
        return `
          <tr>
            <td class="text-muted">${t.timestamp}</td>
            <td><span class="${t.action.includes('YES') ? 'tag-outcome-yes' : 'tag-outcome-no'}">${t.action}</span></td>
            <td>${escapeHtml(t.question)}</td>
            <td>${t.shares.toFixed(1)}</td>
            <td>$${t.price.toFixed(2)}</td>
            <td>$${t.total_amount.toFixed(2)}</td>
            <td class="text-muted" style="font-size:0.75rem">${escapeHtml(t.reasoning)}</td>
          </tr>
        `;
      }).join("");
    }
  } catch (err) {
    console.error("Error polling portfolio:", err);
  }
}

// 2. Fetch & Render Live Markets
async function loadMarkets() {
  const feed = document.getElementById("market-feed");
  try {
    const res = await fetch("/api/markets");
    if (!res.ok) return;
    const markets = await res.json();

    if (!markets || markets.length === 0) {
      feed.innerHTML = `<div class="text-muted text-center">No active markets available.</div>`;
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
            <span class="odd-pill odd-yes">YES ${Math.round(m.probability_yes * 100)}%</span>
            <span class="odd-pill odd-no">NO ${Math.round(m.probability_no * 100)}%</span>
          </div>
        </div>
      `;
    }).join("");
  } catch (err) {
    feed.innerHTML = `<div class="text-muted text-center">Error loading markets.</div>`;
  }
}

// 3. Trigger Swarm Scan Manual Run
async function triggerManualScan() {
  const btn = document.getElementById("btn-scan");
  const origText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = `<span class="btn-icon">⏳</span> SWARM REASONING...`;

  try {
    const res = await fetch("/api/scan", { method: "POST" });
    const data = await res.json();
    await loadPortfolio();
  } catch (err) {
    alert("Error executing swarm scan: " + err);
  } finally {
    btn.disabled = false;
    btn.innerHTML = origText;
  }
}

// 4. Toggle Auto-Scan Mode
async function toggleAutoMode() {
  try {
    const res = await fetch("/api/auto/toggle", { method: "POST" });
    const data = await res.json();
    isAutoRunning = data.is_auto_running;
    updateAutoButtonState();
  } catch (err) {
    alert("Error toggling auto mode: " + err);
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
    text.textContent = "AUTO-LOOP: ON (30s)";
  } else {
    dot.className = "status-dot";
    text.textContent = "AUTO-LOOP: OFF";
  }
}

// 5. Reset Portfolio
async function resetPortfolio() {
  if (!confirm("Are you sure you want to reset mock balance back to $1,000.00?")) return;
  try {
    await fetch("/api/portfolio/reset", { method: "POST" });
    await loadPortfolio();
  } catch (err) {
    alert("Error resetting portfolio: " + err);
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
