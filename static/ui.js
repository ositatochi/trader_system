(() => {
  const toastRegion = document.getElementById("toasts");
  const notificationButton = document.getElementById("notifications-toggle");
  const seenKey = "trader-seen-alerts";

  window.toast = (message, type = "info") => {
    if (!toastRegion) return;
    const item = document.createElement("div");
    item.className = `toast toast-${type}`;
    item.textContent = message;
    toastRegion.append(item);
    window.setTimeout(() => {
      item.classList.add("toast-exit");
      window.setTimeout(() => item.remove(), 250);
    }, 4000);
  };

  const getSeen = () => {
    try { return new Set(JSON.parse(localStorage.getItem(seenKey) || "[]")); }
    catch (_) { return new Set(); }
  };

  notificationButton?.addEventListener("click", async () => {
    if (!("Notification" in window)) {
      window.toast("Browser notifications are not supported here.", "error");
      return;
    }
    try {
      if (localStorage.getItem("trader-notifications-asked") === "1" || Notification.permission !== "default") {
        window.toast(Notification.permission === "granted" ? "Browser notifications are enabled." : "Notification permission was already decided in browser settings.");
        return;
      }
    } catch (_) {}
    try {
      const permission = await Notification.requestPermission();
      localStorage.setItem("trader-notifications-asked", "1");
      window.toast(permission === "granted" ? "Browser notifications enabled." : "Browser notifications were not enabled.", permission === "granted" ? "success" : "info");
    } catch (_) {
      window.toast("Could not request notification permission.", "error");
    }
  });

  const refreshDashboard = async () => {
    if (document.visibilityState !== "visible") return;
    try {
      const response = await fetch("/api/signals/latest", { headers: { Accept: "application/json" } });
      if (!response.ok) return;
      const signals = await response.json();
      for (const [type, containerId] of [["stock", "stock-signals"], ["crypto", "crypto-signals"]]) {
        const container = document.getElementById(containerId);
        if (!container) continue;
        container.replaceChildren();
        const matching = signals.filter((signal) => signal.asset_type === type);
        if (!matching.length) {
          const empty = document.createElement("p");
          empty.className = "muted";
          empty.textContent = "No signals yet. Click Refresh.";
          container.append(empty);
        }
        for (const signal of matching) {
          container.append(renderSignal(signal));
        }
      }
      await checkAlerts();
    } catch (_) {
      window.toast("Signal refresh failed.", "error");
    }
  };

  const renderSignal = (signal) => {
    const card = document.createElement("div");
    card.className = "card";
    const heading = document.createElement("div");
    heading.className = "row header-row stack-on-mobile";
    const symbol = document.createElement("strong");
    symbol.textContent = signal.symbol;
    const exchange = document.createElement("span");
    exchange.className = `badge badge-${signal.asset_type}`;
    exchange.textContent = signal.exchange;
    const direction = document.createElement("span");
    direction.className = `signal-${signal.signal}`;
    direction.textContent = signal.signal.toUpperCase();
    heading.append(symbol, exchange, direction);
    const prices = document.createElement("div");
    prices.textContent = `Entry: ${signal.currency} ${Number(signal.entry_price).toFixed(2)} | SL: ${signal.currency} ${Number(signal.stop_loss).toFixed(2)} | TP: ${signal.currency} ${Number(signal.take_profit).toFixed(2)}`;
    const reason = document.createElement("div");
    reason.className = "muted small";
    reason.textContent = signal.reason || "";
    const timestamp = document.createElement("div");
    timestamp.className = "muted micro";
    timestamp.textContent = signal.timestamp;
    card.append(heading, prices, reason, timestamp);
    return card;
  };

  const checkAlerts = async () => {
    if (!("Notification" in window) || Notification.permission !== "granted") return;
    const response = await fetch("/api/alerts/new", { headers: { Accept: "application/json" } });
    if (!response.ok) return;
    const seen = getSeen();
    const ids = [...seen];
    for (const alert of await response.json()) {
      const key = String(alert.id);
      if (seen.has(key)) continue;
      new Notification(`${alert.signal.toUpperCase()} ${alert.symbol}`, { body: alert.reason || "New trading signal" });
      window.toast(`New ${alert.signal.toUpperCase()} signal for ${alert.symbol}.`, "success");
      ids.push(key);
    }
    try { localStorage.setItem(seenKey, JSON.stringify(ids.slice(-100))); } catch (_) {}
  };

  if (document.getElementById("stock-signals") || document.getElementById("crypto-signals")) {
    refreshDashboard();
    window.setInterval(refreshDashboard, 60000);
  }
})();