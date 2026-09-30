(() => {
  const root = document.querySelector(".chart-stack[data-asset-id]");
  if (!root || typeof Chart === "undefined") return;

  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  const fg = color("--fg");
  const muted = color("--muted");
  const accent = color("--accent");
  const buy = color("--buy");
  const sell = color("--sell");
  const border = color("--border");

  fetch(`/api/asset/${root.dataset.assetId}/series`)
    .then((response) => {
      if (!response.ok) throw new Error(`Series request failed (${response.status})`);
      return response.json();
    })
    .then((series) => {
      const labels = series.timestamps;
      const common = {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: "index" },
        plugins: { legend: { labels: { color: fg } } },
        scales: {
          x: { ticks: { color: muted, maxTicksLimit: 8 }, grid: { color: border } },
          y: { ticks: { color: muted }, grid: { color: border } },
        },
      };

      new Chart(document.getElementById("price-chart"), {
        type: "line",
        data: {
          labels,
          datasets: [
            { label: "Close", data: series.close, borderColor: fg, pointRadius: 0, tension: 0.15 },
            { label: "EMA 20", data: series.ema20, borderColor: accent, pointRadius: 0, spanGaps: true },
            { label: "EMA 50", data: series.ema50, borderColor: buy, pointRadius: 0, spanGaps: true },
          ],
        },
        options: common,
      });

      if (series.rsi14.some((value) => value !== null)) {
        new Chart(document.getElementById("rsi-chart"), {
          type: "line",
          data: {
            labels,
            datasets: [
              { label: "RSI 14", data: series.rsi14, borderColor: accent, pointRadius: 0, spanGaps: true },
              { label: "70", data: labels.map(() => 70), borderColor: sell, borderDash: [5, 5], pointRadius: 0 },
              { label: "30", data: labels.map(() => 30), borderColor: buy, borderDash: [5, 5], pointRadius: 0 },
            ],
          },
          options: { ...common, scales: { ...common.scales, y: { ...common.scales.y, min: 0, max: 100 } } },
        });
      } else {
        document.getElementById("rsi-chart").closest(".chart-panel").hidden = true;
      }

      new Chart(document.getElementById("volume-chart"), {
        type: "bar",
        data: { labels, datasets: [{ label: "Volume", data: series.volume, backgroundColor: `${accent}99` }] },
        options: common,
      });
    })
    .catch((error) => {
      root.insertAdjacentHTML("beforeend", `<p class="muted">Charts unavailable: ${error.message}</p>`);
    });
})();