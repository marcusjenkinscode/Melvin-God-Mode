/**
 * Melvin God Mode — Dashboard JavaScript
 * Initialises Chart.js charts and polls API endpoints to keep stats live.
 */

(function () {
  "use strict";

  /* ── Constants ──────────────────────────────────────────── */
  const POLL_INTERVAL_MS  = 5000;
  const MAX_HISTORY_POINTS = 20;

  /* ── Chart.js defaults ──────────────────────────────────── */
  Chart.defaults.color = "#888888";
  Chart.defaults.borderColor = "#1a1a2e";
  Chart.defaults.font.family = "'JetBrains Mono', 'Courier New', monospace";
  Chart.defaults.font.size   = 11;

  const ACCENT       = "#00ff41";
  const ACCENT_BLUE  = "#00b4d8";
  const ACCENT_WARN  = "#ffaa00";
  const ACCENT_DIM   = "#00b84d";

  /* ── Chart instances ────────────────────────────────────── */
  let cpuChart    = null;
  let memChart    = null;
  let gpuChart    = null;

  /* ── History buffers ────────────────────────────────────── */
  const cpuHistory = [];
  const timeLabels  = [];

  /* ── Helpers ────────────────────────────────────────────── */
  function nowLabel() {
    return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  }

  function pushRing(arr, value, max) {
    arr.push(value);
    if (arr.length > max) arr.shift();
  }

  function getCtx(id) {
    const el = document.getElementById(id);
    return el ? el.getContext("2d") : null;
  }

  function gradientFill(ctx, color) {
    if (!ctx) return color;
    const grad = ctx.createLinearGradient(0, 0, 0, 200);
    grad.addColorStop(0, color + "66");
    grad.addColorStop(1, color + "00");
    return grad;
  }

  /* ── CPU Chart ──────────────────────────────────────────── */
  function initCpuChart() {
    const ctx = getCtx("cpu-chart");
    if (!ctx) return;

    cpuChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: timeLabels,
        datasets: [{
          label: "CPU %",
          data: cpuHistory,
          borderColor: ACCENT,
          backgroundColor: gradientFill(ctx, ACCENT),
          borderWidth: 1.5,
          pointRadius: 0,
          fill: true,
          tension: 0.4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        scales: {
          x: { grid: { color: "#1a1a2e" }, ticks: { maxTicksLimit: 6 } },
          y: { min: 0, max: 100, grid: { color: "#1a1a2e" }, ticks: { callback: (v) => v + "%" } },
        },
        plugins: { legend: { display: false } },
      },
    });
  }

  /* ── Memory Chart ───────────────────────────────────────── */
  function initMemChart() {
    const ctx = getCtx("mem-chart");
    if (!ctx) return;

    memChart = new Chart(ctx, {
      type: "doughnut",
      data: {
        labels: ["Used", "Free"],
        datasets: [{
          data: [0, 100],
          backgroundColor: [ACCENT_BLUE, "#1a1a2e"],
          borderColor: ["#00b4d888", "#1a1a2e"],
          borderWidth: 1,
          hoverOffset: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "72%",
        animation: { duration: 400 },
        plugins: {
          legend: { display: true, position: "bottom" },
          tooltip: {
            callbacks: {
              label: (ctx) => ` ${ctx.label}: ${ctx.parsed.toFixed(1)} GB`,
            },
          },
        },
      },
    });
  }

  /* ── GPU Chart ──────────────────────────────────────────── */
  function initGpuChart() {
    const ctx = getCtx("gpu-chart");
    if (!ctx) return;

    gpuChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: [],
        datasets: [
          {
            label: "GPU Util %",
            data: [],
            backgroundColor: ACCENT + "99",
            borderColor: ACCENT,
            borderWidth: 1,
          },
          {
            label: "VRAM Util %",
            data: [],
            backgroundColor: ACCENT_WARN + "99",
            borderColor: ACCENT_WARN,
            borderWidth: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 300 },
        scales: {
          x: { grid: { color: "#1a1a2e" } },
          y: { min: 0, max: 100, grid: { color: "#1a1a2e" }, ticks: { callback: (v) => v + "%" } },
        },
        plugins: { legend: { display: true, position: "bottom" } },
      },
    });
  }

  /* ── Fetch helpers ──────────────────────────────────────── */
  async function fetchJSON(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) return null;
      return r.json();
    } catch {
      return null;
    }
  }

  /* ── Update system stats ────────────────────────────────── */
  async function updateSystem() {
    const data = await fetchJSON("/api/system");
    if (!data) return;

    // Stat cards
    setInner("cpu-pct",  (data.cpu?.percent ?? 0).toFixed(1) + "%");
    setInner("mem-used", (data.memory?.used_gb ?? 0).toFixed(1) + " GB");
    setInner("mem-pct",  (data.memory?.percent ?? 0).toFixed(1) + "%");
    setInner("disk-pct", (data.disk?.percent ?? 0).toFixed(1) + "%");
    setInner("disk-free",(data.disk?.free_gb ?? 0).toFixed(1) + " GB free");
    setInner("net-sent", (data.network?.bytes_sent_mb ?? 0).toFixed(1) + " MB");
    setInner("net-recv", (data.network?.bytes_recv_mb ?? 0).toFixed(1) + " MB");

    // Progress bars
    setProgress("cpu-bar",  data.cpu?.percent ?? 0);
    setProgress("mem-bar",  data.memory?.percent ?? 0);
    setProgress("disk-bar", data.disk?.percent ?? 0);

    // CPU chart
    pushRing(cpuHistory, data.cpu?.percent ?? 0, MAX_HISTORY_POINTS);
    pushRing(timeLabels,  nowLabel(),             MAX_HISTORY_POINTS);
    if (cpuChart) {
      cpuChart.data.labels   = [...timeLabels];
      cpuChart.data.datasets[0].data = [...cpuHistory];
      cpuChart.update("none");
    }

    // Memory doughnut
    if (memChart) {
      const used = data.memory?.used_gb ?? 0;
      const free = data.memory?.free_gb ?? 0;
      memChart.data.datasets[0].data = [used, free];
      memChart.update();
    }
  }

  /* ── Update GPU stats ───────────────────────────────────── */
  async function updateGpu() {
    const data = await fetchJSON("/api/gpu");
    if (!data) return;

    const gpus = data.gpus || [];

    // No GPU — show placeholder
    const noGpuEl = document.getElementById("no-gpu-msg");
    const gpuTable = document.getElementById("gpu-table-body");

    if (gpus.length === 0) {
      if (noGpuEl) noGpuEl.style.display = "block";
      if (gpuChart) {
        gpuChart.data.labels = ["No GPU detected"];
        gpuChart.data.datasets[0].data = [0];
        gpuChart.data.datasets[1].data = [0];
        gpuChart.update();
      }
      return;
    }
    if (noGpuEl) noGpuEl.style.display = "none";

    // Bar chart
    if (gpuChart) {
      gpuChart.data.labels = gpus.map((g) => g.name || `GPU ${g.index}`);
      gpuChart.data.datasets[0].data = gpus.map((g) => g.gpu_util_pct ?? 0);
      gpuChart.data.datasets[1].data = gpus.map((g) => g.mem_util_pct ?? 0);
      gpuChart.update("none");
    }

    // GPU table
    if (gpuTable) {
      gpuTable.innerHTML = gpus
        .map(
          (g) => `
          <tr>
            <td>${g.index}</td>
            <td>${g.name}</td>
            <td>${(g.gpu_util_pct ?? "–")}%</td>
            <td>${(g.mem_used_mb ?? 0).toFixed(0)} / ${(g.mem_total_mb ?? 0).toFixed(0)} MB</td>
            <td>${g.temp_c != null ? g.temp_c + " °C" : "–"}</td>
            <td>${g.power_w != null ? g.power_w.toFixed(0) + " W" : "–"}</td>
          </tr>`
        )
        .join("");
    }
  }

  /* ── Update agents table ────────────────────────────────── */
  async function updateAgents() {
    const data = await fetchJSON("/api/agents");
    if (!data) return;

    const tbody = document.getElementById("agents-table-body");
    if (!tbody) return;

    const agents = data.agents || [];
    tbody.innerHTML = agents
      .map(
        (a) => `
        <tr>
          <td><span class="text-accent">${a.id}</span></td>
          <td>${a.name}</td>
          <td><span class="badge ${a.status === "idle" ? "badge-grey" : "badge-green"}">${a.status}</span></td>
          <td class="text-dim">–</td>
        </tr>`
      )
      .join("");
  }

  /* ── Update cluster ─────────────────────────────────────── */
  async function updateCluster() {
    const data = await fetchJSON("/api/cluster");
    if (!data) return;

    setInner("cluster-count", data.count ?? 0);

    const tbody = document.getElementById("cluster-table-body");
    if (!tbody) return;

    const nodes = data.nodes || [];
    tbody.innerHTML = nodes
      .map(
        (n) => `
        <tr>
          <td>${n.id}</td>
          <td>${n.host}</td>
          <td><span class="badge ${n.role === "primary" ? "badge-blue" : "badge-grey"}">${n.role}</span></td>
          <td><span class="badge ${n.status === "online" ? "badge-green" : "badge-red"}">${n.status}</span></td>
          <td>${n.cpu_pct != null ? n.cpu_pct.toFixed(1) + "%" : "–"}</td>
          <td>${n.mem_used_gb != null ? n.mem_used_gb.toFixed(1) + " / " + n.mem_total_gb.toFixed(1) + " GB" : "–"}</td>
        </tr>`
      )
      .join("");
  }

  /* ── Log helpers ────────────────────────────────────────── */
  function appendLog(level, message) {
    const logsBody = document.getElementById("logs-body");
    if (!logsBody) return;
    const time = nowLabel();
    const line = document.createElement("div");
    line.className = "log-line";
    line.innerHTML = `<span class="log-time">${time}</span><span class="log-level-${level}">[${level.toUpperCase()}]</span><span>${message}</span>`;
    logsBody.appendChild(line);
    if (logsBody.children.length > 100) logsBody.firstElementChild.remove();
    logsBody.scrollTop = logsBody.scrollHeight;
  }

  /* ── DOM helpers ────────────────────────────────────────── */
  function setInner(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  }

  function setProgress(id, pct) {
    const el = document.getElementById(id);
    if (el) el.style.width = Math.min(100, Math.max(0, pct)) + "%";
  }

  /* ── Main update cycle ──────────────────────────────────── */
  async function updateDashboard() {
    await Promise.allSettled([
      updateSystem(),
      updateGpu(),
      updateAgents(),
      updateCluster(),
    ]);
    appendLog("info", "Dashboard refreshed");
  }

  /* ── Init ───────────────────────────────────────────────── */
  document.addEventListener("DOMContentLoaded", () => {
    initCpuChart();
    initMemChart();
    initGpuChart();
    updateDashboard();
    setInterval(updateDashboard, POLL_INTERVAL_MS);
  });

  // Expose for inline handlers
  window.updateDashboard = updateDashboard;
})();
