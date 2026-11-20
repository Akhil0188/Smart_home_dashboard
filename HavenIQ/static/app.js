
/* HavenIQ dashboard front-end. Talks only to the Flask API: /api/data, /api/history, /api/recent, /api/devices */
(() => {
  "use strict";
  const CFG = window.HAVENIQ || { refreshMs: 3000, historyPoints: 60 };
  const $ = (id) => document.getElementById(id);
  const charts = {};
  let ageBase = null;

  /* ---------- helpers ---------- */
  const num = (v) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? null : Number(v));
  const fmt = (v, d = 1) => (num(v) === null ? "--" : num(v).toFixed(d));
  const clampPct = (p) => Math.max(0, Math.min(100, p));
  const timeOnly = (ts) => (ts ? String(ts).split(/[ T]/)[1] || ts : "--");
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function agoText(sec) {
    if (sec === null || sec === undefined) return "unknown";
    if (sec < 5) return "just now";
    if (sec < 60) return `${Math.round(sec)} s ago`;
    if (sec < 3600) return `${Math.floor(sec / 60)} min ago`;
    return `${Math.floor(sec / 3600)} h ${Math.floor((sec % 3600) / 60)} min ago`;
  }

  async function getJSON(url) {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 8000);
    try {
      const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
      let body = null;
      try { body = await res.json(); } catch (_) {}
      return { ok: res.ok, httpStatus: res.status, body };
    } finally { clearTimeout(timer); }
  }

  function setPill(el, tone, text) {
    el.dataset.tone = tone;
    el.querySelector("span").textContent = text;
  }

  /* ---------- clock ---------- */
  function tickClock() {
    $("clock").textContent = new Date().toLocaleString(undefined, {
      weekday: "short", day: "2-digit", month: "short", year: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    });
    if (ageBase) {
      const sec = ageBase.seconds + (Date.now() - ageBase.at) / 1000;
      $("sysDataNote").textContent = `${agoText(sec)}`;
    }
  }

  /* ---------- sensor cards ---------- */
  function card(key, value, digits, label, tone, pct) {
    $("v-" + key).textContent = fmt(value, digits);
    $("st-" + key).textContent = label;
    $("card-" + key).dataset.tone = tone;
    $("b-" + key).style.width = clampPct(pct) + "%";
  }

  function renderLatest(r, energyMax) {
    if (!r) {
      ["temp", "hum", "light", "power", "energy"].forEach((k) => card(k, null, 0, "No data", "muted", 0));
      $("v-door").textContent = "--"; $("st-door").textContent = "No data";
      $("card-door").dataset.tone = "muted"; $("b-door").style.width = "0%";
      return;
    }
    const t = num(r.temperature), h = num(r.humidity), l = num(r.light), p = num(r.power), e = num(r.energy);
    card("temp", t, 1,
      t === null ? "No data" : t < 18 ? "Cool" : t <= 27 ? "Comfortable" : t <= 32 ? "Warm" : "Hot",
      t === null ? "muted" : t < 18 ? "info" : t <= 27 ? "good" : t <= 32 ? "warn" : "bad", ((t ?? 0) / 50) * 100);
    card("hum", h, 1,
      h === null ? "No data" : h < 30 ? "Dry" : h <= 60 ? "Comfortable" : h <= 75 ? "Humid" : "Very humid",
      h === null ? "muted" : h < 30 ? "warn" : h <= 60 ? "good" : h <= 75 ? "warn" : "bad", h ?? 0);
    card("light", l, 0,
      l === null ? "No data" : l < 50 ? "Dark" : l < 200 ? "Dim" : l < 600 ? "Normal" : "Bright",
      l === null ? "muted" : l < 200 ? "info" : "good", ((l ?? 0) / 1000) * 100);
    card("power", p, 1,
      p === null ? "No data" : p < 200 ? "Low load" : p < 600 ? "Normal load" : "High load",
      p === null ? "muted" : p < 200 ? "good" : p < 600 ? "info" : "warn", ((p ?? 0) / 1000) * 100);
    card("energy", e, 2, e === null ? "No data" : "Cumulative", e === null ? "muted" : "info",
      energyMax > 0 ? ((e ?? 0) / energyMax) * 100 : 0);
    const open = !!r.door_open;
    $("v-door").textContent = r.door_label;
    $("st-door").textContent = open ? "Attention" : "Secure";
    $("card-door").dataset.tone = open ? "warn" : "good";
    $("b-door").style.width = open ? "100%" : "8%";
  }

  /* ---------- system status ---------- */
  function renderStatus(s) {
    if (!s) {
      setPill($("mqttPill"), "muted", "MQTT: unknown");
      ["sysBackend", "sysMqtt", "sysDb", "sysData"].forEach((id) => setPill($(id), "bad", "Unavailable"));
      return;
    }
    const m = s.mqtt, d = s.database, x = s.data;
    const mqttTone = m.state === "connected" ? "good" : m.state === "disabled" ? "muted" : "bad";
    const mqttText = m.state === "connected" ? "MQTT Connected" : m.state === "disabled" ? "MQTT Disabled" : "MQTT Disconnected";
    setPill($("mqttPill"), mqttTone, mqttText);
    setPill($("sysMqtt"), mqttTone, m.state[0].toUpperCase() + m.state.slice(1));
    $("sysMqttNote").textContent = m.state === "connected"
      ? `${m.host}:${m.port} · topic ${m.topic}` + (m.last_message_age_seconds !== null ? ` · last message ${agoText(m.last_message_age_seconds)}` : " · no message seen yet")
      : (m.error || `${m.host}:${m.port}`);

    setPill($("sysBackend"), "good", "Running");
    const up = s.backend.uptime_seconds;
    $("sysBackendNote").textContent = `Uptime ${up < 60 ? up + " s" : Math.floor(up / 60) + " min"}`;

    setPill($("sysDb"), d.state === "ok" ? "good" : "bad", d.state === "ok" ? "Connected" : "Problem");
    $("sysDbNote").textContent = d.state === "ok" ? `${d.file} · ${d.rows} readings stored` : d.message;

    const map = { live: ["good", "Live"], stale: ["warn", "Stale"], empty: ["warn", "No data"], unavailable: ["bad", "Unavailable"] };
    const [tone, text] = map[x.state] || ["muted", "--"];
    setPill($("sysData"), tone, text);
    if (x.last_update) {
      ageBase = { seconds: x.age_seconds ?? 0, at: Date.now() };
    } else {
      ageBase = null;
      $("sysDataNote").textContent = x.state === "empty" ? "Waiting for the first reading" : "";
    }
    if (x.state === "stale") {
      showBanner(`No new sensor reading for ${agoText(x.age_seconds)}. Is the simulator / database writer running?`, true);
    } else if (x.state === "empty") {
      showBanner("The database has no sensor readings yet. Start your simulator and database writer.", true);
    }
  }

  function showBanner(msg, warn) {
    const b = $("banner");
    b.textContent = msg; b.hidden = false; b.classList.toggle("warn", !!warn);
  }
  const hideBanner = () => { $("banner").hidden = true; };

  /* ---------- charts ---------- */
  function baseOptions(yTitle) {
    return {
      responsive: true, maintainAspectRatio: false, animation: { duration: 350 },
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { padding: 10, cornerRadius: 8 } },
      elements: { point: { radius: 0, hoverRadius: 4 }, line: { tension: 0.35, borderWidth: 2 } },
      scales: {
        x: { title: { display: true, text: "Time" }, ticks: { maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } },
        y: { title: { display: true, text: yTitle }, grid: { color: "rgba(140,151,178,.12)" } },
      },
    };
  }
  const ds = (label, color, extra = {}) => ({ label, data: [], borderColor: color, backgroundColor: color + "22", fill: true, ...extra });

  function buildCharts() {
    if (typeof Chart === "undefined") {
      document.querySelectorAll(".chart-empty").forEach((e) => {
        e.hidden = false; e.textContent = "Chart.js could not be loaded (internet is needed for the CDN script).";
      });
      return false;
    }
    Chart.defaults.color = "#8c97b2";
    Chart.defaults.font.family = 'Inter, "Segoe UI", system-ui, sans-serif';
    const th = baseOptions("Temperature (°C)");
    th.scales.y1 = { position: "right", title: { display: true, text: "Humidity (%)" }, grid: { drawOnChartArea: false } };
    charts.th = new Chart($("chTH"), { type: "line", options: th, data: { labels: [], datasets: [
      ds("Temperature (°C)", "#f87171", { fill: false, yAxisID: "y" }), ds("Humidity (%)", "#38bdf8", { fill: false, yAxisID: "y1" })] } });
    charts.light = new Chart($("chLight"), { type: "line", options: baseOptions("Light (lux)"), data: { labels: [], datasets: [ds("Light (lux)", "#fbbf24")] } });
    charts.power = new Chart($("chPower"), { type: "line", options: baseOptions("Power (W)"), data: { labels: [], datasets: [ds("Power (W)", "#fb923c")] } });
    charts.energy = new Chart($("chEnergy"), { type: "line", options: baseOptions("Energy (kWh)"), data: { labels: [], datasets: [ds("Energy (kWh)", "#34d399")] } });
    return true;
  }

  function renderCharts(rows) {
    document.querySelectorAll(".chart-empty").forEach((e) => {
      e.textContent = "No readings yet";
      e.style.display = rows.length > 0 ? "none" : "";
    });

    $("histNote").textContent = rows.length ? `last ${rows.length} readings` : "";
    if (!charts.th) return;
    const labels = rows.map((r) => timeOnly(r.timestamp));
    const set = (chart, ...series) => {
      chart.data.labels = labels;
      series.forEach((s, i) => (chart.data.datasets[i].data = rows.map((r) => num(r[s]))));
      chart.update("none");
    };
    set(charts.th, "temperature", "humidity");
    set(charts.light, "light");
    set(charts.power, "power");
    set(charts.energy, "energy");
  }

  /* ---------- door monitor ---------- */
  function renderDoor(latest, rows) {
    const panel = $("doorPanel");
    if (!latest) {
      panel.dataset.tone = "muted"; $("doorBig").textContent = "--";
      $("doorUpdated").textContent = "--"; $("doorChanged").textContent = "--";
      $("doorEvents").innerHTML = '<li class="muted-text">No door data yet</li>';
      return;
    }
    panel.dataset.tone = latest.door_open ? "warn" : "good";
    $("doorBig").textContent = latest.door_label;
    $("doorUpdated").textContent = latest.timestamp;
    const events = [];
    let prev = null;
    rows.forEach((r) => { if (r.door_open !== prev) { events.push({ t: r.timestamp, open: r.door_open }); prev = r.door_open; } });
    $("doorChanged").textContent = events.length > 1 ? events[events.length - 1].t : "No change in loaded window";
    const items = events.slice(-6).reverse().map((e, i, arr) => {
      const first = events.length <= 6 && e === events[0];
      return `<li><span><span class="badge ${e.open ? "open" : "closed"}">${e.open ? "Open" : "Closed"}</span>${first ? ' <span class="muted-text">(first reading in window)</span>' : ""}</span><span class="muted-text">${esc(e.t)}</span></li>`;
    });
    $("doorEvents").innerHTML = items.join("") || '<li class="muted-text">No door data yet</li>';
  }

  /* ---------- recent table ---------- */
  function renderRecent(rows, errorMsg) {
    const body = $("recentBody");
    if (errorMsg) { body.innerHTML = `<tr><td colspan="7" class="empty">${esc(errorMsg)}</td></tr>`; return; }
    if (!rows.length) { body.innerHTML = '<tr><td colspan="7" class="empty">No sensor readings yet. Start your simulator and database writer.</td></tr>'; return; }
    body.innerHTML = rows.map((r) => `<tr>
      <td>${esc(r.timestamp)}</td><td>${fmt(r.temperature, 1)} °C</td><td>${fmt(r.humidity, 1)} %</td>
      <td>${fmt(r.light, 0)} lux</td><td><span class="badge ${r.door_open ? "open" : "closed"}">${esc(r.door_label)}</span></td>
      <td>${fmt(r.power, 1)} W</td><td>${fmt(r.energy, 2)} kWh</td></tr>`).join("");
  }

  /* ---------- device control (Light / Fan / AC) ---------- */
  const DEV_KEYS = ["light", "fan", "ac"];
  const DEV_NAME = { light: "Light", fan: "Fan", ac: "AC" };
  const devUI = {};
  DEV_KEYS.forEach((k) => {
    const card = document.querySelector(`.device[data-device="${k}"]`);
    devUI[k] = { card, msg: card.querySelector(".dev-msg"), label: card.querySelector(".dev-status b"),
                 btns: card.querySelectorAll(".seg-btn"), sending: false, fail: null };
  });
  let lastDev = null, devBusy = false, fastTimer = null;

  function devMessage(k, d) {
    const ui = devUI[k], p = d.pending && d.pending[k];
    if (ui.sending) return ["Sending…", "busy"];
    if (p && !p.timed_out) return [`Waiting for device… (requested ${p.requested})`, "busy"];
    if (ui.fail && Date.now() < ui.fail.until) return [ui.fail.text, "bad"];
    if (p && p.timed_out) return [`No confirmation from the device for ${p.requested}. Is the ESP32 / simulator running?`, "warn"];
    if (!d.connected) return ["Last known state. Commands cannot be sent right now.", "warn"];
    if (!d.status_received) return ["Waiting for the first status from the device…", ""];
    if (d.status_stale) return [`No recent update from the device (last ${agoText(d.status_age_seconds)}). It may be offline.`, "warn"];
    return [`Reported ${agoText(d.status_age_seconds)}`, ""];
  }

  function renderDevices(d, unreachable) {
    lastDev = d;
    const banner = $("devBanner");
    if (unreachable || !d) {
      setPill($("devLink"), "bad", "Device Control: Unavailable");
      banner.hidden = false; banner.textContent = "Cannot reach the HavenIQ backend, so device commands cannot be sent.";
      DEV_KEYS.forEach((k) => {
        devUI[k].btns.forEach((b) => { b.disabled = true; });
        devUI[k].msg.textContent = "Backend not reachable"; devUI[k].msg.className = "dev-msg warn";
      });
      return;
    }
    setPill($("devLink"), d.connected ? "good" : "bad", d.connected ? "Device Control: Connected" : "Device Control: Disconnected");
    if (!d.connected) {
      banner.hidden = false; banner.textContent = `Device commands cannot be sent: ${d.error || "MQTT is not connected"}`;
    } else if (d.error) {
      banner.hidden = false; banner.classList.add("warn"); banner.textContent = d.error;
    } else { banner.hidden = true; banner.classList.remove("warn"); }
    $("devNote").textContent = d.command_topic ? `commands → ${d.command_topic} · status ← ${d.status_topic}` : "";

    DEV_KEYS.forEach((k) => {
      const ui = devUI[k], state = (d.devices && d.devices[k]) || "UNKNOWN";
      const p = d.pending && d.pending[k];
      const busy = ui.sending || (p && !p.timed_out);
      ui.card.dataset.state = state;
      ui.label.textContent = state;
      ui.btns.forEach((b) => {
        b.classList.toggle("active", b.dataset.cmd === state);
        b.setAttribute("aria-pressed", String(b.dataset.cmd === state));
        b.disabled = !d.connected || !!busy;
      });
      const [text, tone] = devMessage(k, d);
      ui.msg.textContent = text; ui.msg.className = "dev-msg" + (tone ? " " + tone : "");
    });
  }

  async function refreshDevices() {
    if (devBusy) return;
    devBusy = true;
    try {
      const r = await getJSON("/api/devices");
      if (r.body && r.ok) renderDevices(r.body, false); else renderDevices(null, true);
    } catch (_) { renderDevices(null, true); }
    finally { devBusy = false; }
  }

  function startFastPoll() {
    clearInterval(fastTimer);
    const until = Date.now() + 20000;
    fastTimer = setInterval(async () => {
      await refreshDevices();
      const waiting = lastDev && lastDev.pending && Object.values(lastDev.pending).some((p) => !p.timed_out);
      if (!waiting || Date.now() > until) clearInterval(fastTimer);
    }, 700);
  }

  async function sendCommand(k, cmd) {
    const ui = devUI[k];
    if (ui.sending) return;
    ui.sending = true; ui.fail = null;
    if (lastDev) renderDevices(lastDev, false);
    try {
      const res = await fetch(`/api/devices/${k}`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: cmd }) });
      let body = null; try { body = await res.json(); } catch (_) {}
      if (!res.ok || !body || !body.ok) {
        ui.fail = { text: "Command failed: " + ((body && body.error) || `HTTP ${res.status}`), until: Date.now() + 10000 };
      }
    } catch (_) {
      ui.fail = { text: "Command failed: the backend could not be reached", until: Date.now() + 10000 };
    } finally { ui.sending = false; }
    await refreshDevices();
    startFastPoll();
  }

  DEV_KEYS.forEach((k) => devUI[k].btns.forEach((b) => b.addEventListener("click", () => sendCommand(k, b.dataset.cmd))));

  /* ---------- refresh loop ---------- */
  async function refresh() {
    const ind = $("refreshInd");
    ind.classList.add("spin");
    const [dataR, histR, recR, devR] = await Promise.allSettled([
      getJSON("/api/data"),
      getJSON(`/api/history?limit=${CFG.historyPoints}`),
      getJSON("/api/recent?limit=15"),
      getJSON("/api/devices"),
    ]);
    const val = (r) => (r.status === "fulfilled" ? r.value : null);
    const data = val(dataR), hist = val(histR), rec = val(recR), dev = val(devR);
    if (dev && dev.ok && dev.body) renderDevices(dev.body, false); else renderDevices(null, true);

    hideBanner();
    if (!data || !data.body) {
      renderStatus(null); renderLatest(null, 0);
      showBanner("Cannot reach the HavenIQ backend. Make sure app.py is still running.");
      renderRecent([], "Backend not reachable");
      $("refreshText").textContent = "Offline";
      ind.classList.remove("spin");
      return;
    }
    renderStatus(data.body.status);
    if (!data.ok) showBanner(data.body.error || "Sensor data could not be loaded.");

    const rows = hist && hist.ok && hist.body ? hist.body.readings : [];
    const energyMax = Math.max(0, ...rows.map((r) => num(r.energy) || 0));
    renderLatest(data.body.latest, energyMax);
    renderCharts(rows);
    renderDoor(data.body.latest, rows);
    if (rec && rec.ok && rec.body) renderRecent(rec.body.readings);
    else renderRecent([], (rec && rec.body && rec.body.error) || "Recent readings could not be loaded.");

    $("refreshText").textContent = "Updated " + new Date().toLocaleTimeString();
    ind.classList.remove("spin");
  }

  async function loop() {
    try { await refresh(); } catch (err) { console.error(err); showBanner("Dashboard error: " + err.message); }
    setTimeout(loop, CFG.refreshMs);
  }

  /* ---------- sidebar (mobile) + active link ---------- */
  const sidebar = $("sidebar"), scrim = $("scrim");
  const toggle = (open) => { sidebar.classList.toggle("open", open); scrim.classList.toggle("show", open); };
  $("menuBtn").addEventListener("click", () => toggle(!sidebar.classList.contains("open")));
  scrim.addEventListener("click", () => toggle(false));
  document.querySelectorAll(".sidebar nav a").forEach((a) => a.addEventListener("click", () => {
    document.querySelectorAll(".sidebar nav a").forEach((x) => x.classList.remove("active"));
    a.classList.add("active"); toggle(false);
  }));

  buildCharts();
  tickClock(); setInterval(tickClock, 1000);
  loop();
})();
