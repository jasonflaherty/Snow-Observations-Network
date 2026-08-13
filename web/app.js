(() => {
  const DEFAULT_API = "https://api.psithurismlabs.com";
  const params = new URLSearchParams(window.location.search);
  const API_BASE = (params.get("api") || DEFAULT_API).replace(/\/$/, "");

  /**
   * Layer keys = NRCS network codes (SNTL/SCAN/MSTL) or provider ids (BCASWS/JMA).
   * Unknown layers appear after these, off by default.
   */
  const LAYER_META = {
    SNTL: { label: "SNOTEL", defaultOn: true, swatch: "sntl" },
    BCASWS: { label: "BC ASWS", defaultOn: true, swatch: "bcasws" },
    SCAN: { label: "SCAN", defaultOn: false, swatch: "scan" },
    MSTL: { label: "SNOTEL (MSTL)", defaultOn: false, swatch: "mstl" },
    JMA: { label: "JMA", defaultOn: false, swatch: "jma" },
  };

  const statusEl = document.getElementById("status");
  const filterList = document.getElementById("filter-list");
  const searchInput = document.getElementById("search-input");
  const searchResults = document.getElementById("search-results");
  const unitMetricBtn = document.getElementById("unit-metric");
  const unitUsBtn = document.getElementById("unit-us");
  const unitHint = document.getElementById("unit-hint");
  const modal = document.getElementById("modal");
  const modalTitle = document.getElementById("modal-title");
  const modalProvider = document.getElementById("modal-provider");
  const modalId = document.getElementById("modal-id");
  const modalObserved = document.getElementById("modal-observed");
  const modalReadings = document.getElementById("modal-readings");
  const modalError = document.getElementById("modal-error");
  const modalMeaning = document.getElementById("modal-meaning");
  const modalApi = document.getElementById("modal-api");
  const historyStatus = document.getElementById("history-status");
  const historyCanvas = document.getElementById("history-chart");
  const history72hBtn = document.getElementById("history-72h");
  const history7dBtn = document.getElementById("history-7d");

  const UNITS_KEY = "son-display-units";
  function loadUnitSystem() {
    const saved = localStorage.getItem(UNITS_KEY);
    if (saved === "us" || saved === "metric") return saved;
    // migrate older temp-only preference
    if (localStorage.getItem("son-temp-unit") === "F") return "us";
    return "metric";
  }
  let unitSystem = loadUnitSystem();
  /** @type {{
   *   props: object,
   *   detail: object | null,
   *   chartRange: '72h' | '7d',
   *   seriesByRange: Record<string, Array<object> | null>,
   *   chartRequestId: number,
   * } | null} */
  let modalState = null;
  let chartRequestSeq = 0;

  const map = L.map("map", {
    zoomControl: false,
    attributionControl: true,
  }).setView([48.5, -115], 5);

  L.control.zoom({ position: "bottomright" }).addTo(map);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 18,
  }).addTo(map);

  /** @type {Record<string, L.LayerGroup>} */
  const layersByKey = {};
  /** @type {Record<string, boolean>} */
  const enabled = {};
  /** @type {Record<string, number>} */
  const counts = {};
  /** @type {Array<{props: object, key: string, lat: number, lon: number, marker: L.Marker}>} */
  let stationIndex = [];
  let activeMarker = null;
  let allFeatures = [];
  let searchActiveIndex = -1;

  function networkFromExternal(externalId) {
    if (!externalId) return null;
    const parts = String(externalId).split(":");
    return parts.length >= 3 ? parts[parts.length - 1].toUpperCase() : null;
  }

  function layerKey(props) {
    const provider = String(props.provider || "OTHER").toUpperCase();
    if (provider === "NRCS") {
      const net = String(props.network || networkFromExternal(props.external_id) || "NRCS").toUpperCase();
      return net;
    }
    return provider;
  }

  function layerLabel(key) {
    return LAYER_META[key]?.label || key;
  }

  function defaultEnabled(key) {
    return Boolean(LAYER_META[key]?.defaultOn);
  }

  function markerClass(key) {
    const swatch = LAYER_META[key]?.swatch || "other";
    return `son-marker son-marker--${swatch}`;
  }

  function swatchClass(key) {
    const swatch = LAYER_META[key]?.swatch || "other";
    return `filter-swatch filter-swatch--${swatch}`;
  }

  function markerIcon(key, active) {
    const cls = [markerClass(key), active ? "is-active" : ""].filter(Boolean).join(" ");
    return L.divIcon({
      className: "",
      html: `<div class="${cls}"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });
  }

  function fmt(value, unit) {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    const n = typeof value === "number" ? value : Number(value);
    if (Number.isNaN(n)) return String(value);
    const text = Math.abs(n) >= 100 ? n.toFixed(0) : n.toFixed(1);
    return unit ? `${text} ${unit}` : text;
  }

  function cToF(celsius) {
    return (celsius * 9) / 5 + 32;
  }

  function mmToIn(mm) {
    return mm / 25.4;
  }

  function cmToIn(cm) {
    return cm / 2.54;
  }

  function mToFt(m) {
    return m / 0.3048;
  }

  function msToMph(ms) {
    return ms * 2.23693629;
  }

  function fmtTemp(celsius) {
    if (celsius === null || celsius === undefined || Number.isNaN(Number(celsius))) {
      return "—";
    }
    const c = Number(celsius);
    if (unitSystem === "us") return fmt(cToF(c), "°F");
    return fmt(c, "°C");
  }

  function fmtMm(mm) {
    if (mm === null || mm === undefined || Number.isNaN(Number(mm))) return "—";
    const v = Number(mm);
    if (unitSystem === "us") return fmt(mmToIn(v), "in");
    return fmt(v, "mm");
  }

  function fmtCm(cm) {
    if (cm === null || cm === undefined || Number.isNaN(Number(cm))) return "—";
    const v = Number(cm);
    if (unitSystem === "us") return fmt(cmToIn(v), "in");
    return fmt(v, "cm");
  }

  function fmtElev(m) {
    if (m === null || m === undefined || Number.isNaN(Number(m))) return "—";
    const v = Number(m);
    if (unitSystem === "us") return fmt(mToFt(v), "ft");
    return fmt(v, "m");
  }

  function fmtWind(ms) {
    if (ms === null || ms === undefined || Number.isNaN(Number(ms))) return "—";
    const v = Number(ms);
    if (unitSystem === "us") return fmt(msToMph(v), "mph");
    return fmt(v, "m/s");
  }

  function syncUnitButtons() {
    const isMetric = unitSystem === "metric";
    unitMetricBtn.classList.toggle("is-active", isMetric);
    unitUsBtn.classList.toggle("is-active", !isMetric);
    unitMetricBtn.setAttribute("aria-pressed", String(isMetric));
    unitUsBtn.setAttribute("aria-pressed", String(!isMetric));
    unitHint.textContent = isMetric ? "°C · mm · cm · m · m/s" : "°F · in · ft · mph";
  }

  function setUnitSystem(system) {
    unitSystem = system === "us" ? "us" : "metric";
    localStorage.setItem(UNITS_KEY, unitSystem);
    syncUnitButtons();
    if (modalState && !modal.hidden) {
      openModal(modalState.props, modalState.detail, { keepChart: true });
    }
  }

  function fmtTime(iso) {
    if (!iso) return "No observation yet";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toISOString().replace(".000", "").replace("T", " ").replace("Z", " UTC");
  }

  function setReadings(rows) {
    modalReadings.innerHTML = "";
    for (const [label, value] of rows) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      modalReadings.append(dt, dd);
    }
  }

  function fieldMeaning(key) {
    if (key === "JMA") {
      return "JMA: precipitation is the last 1 hour (not a year total). Snowfall is last 1 hour. No SWE. Temperature is air temp.";
    }
    if (key === "BCASWS") {
      return "BC ASWS: precipitation is seasonal / water-year accumulation, not hourly rainfall. SWE and snow depth are pillow readings.";
    }
    if (key === "SNTL" || key === "SCAN" || key === "MSTL") {
      return "NRCS: precipitation (PREC) is water-year accumulation (typically from Oct 1), not this hour’s rain. SWE is pillow snow water equivalent.";
    }
    return "Field meanings vary by provider — see the Field legend for details.";
  }

  function syncHistoryButtons(range) {
    const is72 = range === "72h";
    history72hBtn.classList.toggle("is-active", is72);
    history7dBtn.classList.toggle("is-active", !is72);
    history72hBtn.setAttribute("aria-pressed", String(is72));
    history7dBtn.setAttribute("aria-pressed", String(!is72));
  }

  function clearHistoryChart() {
    const ctx = historyCanvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const cssW = historyCanvas.clientWidth || 640;
    const cssH = historyCanvas.clientHeight || 184;
    historyCanvas.width = Math.round(cssW * dpr);
    historyCanvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssW, cssH);
  }

  function displayTemp(celsius) {
    if (celsius === null || celsius === undefined || Number.isNaN(Number(celsius))) {
      return null;
    }
    const c = Number(celsius);
    return unitSystem === "us" ? cToF(c) : c;
  }

  function displaySnow(cm) {
    if (cm === null || cm === undefined || Number.isNaN(Number(cm))) return null;
    const v = Number(cm);
    return unitSystem === "us" ? cmToIn(v) : v;
  }

  function niceTicks(min, max, count) {
    if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
    if (min === max) {
      const pad = Math.abs(min) > 1 ? Math.abs(min) * 0.1 : 1;
      min -= pad;
      max += pad;
    }
    const span = max - min;
    const step = span / Math.max(count - 1, 1);
    const mag = 10 ** Math.floor(Math.log10(step || 1));
    const norm = step / mag;
    let niceStep;
    if (norm < 1.5) niceStep = 1 * mag;
    else if (norm < 3) niceStep = 2 * mag;
    else if (norm < 7) niceStep = 5 * mag;
    else niceStep = 10 * mag;
    const niceMin = Math.floor(min / niceStep) * niceStep;
    const niceMax = Math.ceil(max / niceStep) * niceStep;
    const ticks = [];
    for (let v = niceMin; v <= niceMax + niceStep * 0.5; v += niceStep) {
      ticks.push(Number(v.toFixed(6)));
    }
    return ticks.length ? ticks : [niceMin, niceMax];
  }

  function drawHistoryChart(series) {
    clearHistoryChart();
    const ctx = historyCanvas.getContext("2d");
    if (!ctx) return;

    const cssW = historyCanvas.clientWidth || 640;
    const cssH = historyCanvas.clientHeight || 184;
    const pad = { top: 14, right: 44, bottom: 28, left: 40 };
    const plotW = cssW - pad.left - pad.right;
    const plotH = cssH - pad.top - pad.bottom;

    const points = (series || [])
      .map((row) => {
        const t = new Date(row.timestamp).getTime();
        return {
          t,
          temp: displayTemp(row.temperature_c),
          snow: displaySnow(row.snow_depth_cm),
        };
      })
      .filter((p) => Number.isFinite(p.t))
      .sort((a, b) => a.t - b.t);

    const hasTemp = points.some((p) => p.temp !== null);
    const hasSnow = points.some((p) => p.snow !== null);
    if (!points.length || (!hasTemp && !hasSnow)) {
      ctx.fillStyle = "#3a4a44";
      ctx.font = "500 12px IBM Plex Sans, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("No temperature or snow depth in this window", cssW / 2, cssH / 2);
      return;
    }

    const tMin = points[0].t;
    const tMax = points[points.length - 1].t || tMin + 1;
    const temps = points.map((p) => p.temp).filter((v) => v !== null);
    const snows = points.map((p) => p.snow).filter((v) => v !== null);
    const tempTicks = niceTicks(
      temps.length ? Math.min(...temps) : 0,
      temps.length ? Math.max(...temps) : 1,
      4
    );
    const snowTicks = niceTicks(
      snows.length ? Math.min(...snows) : 0,
      snows.length ? Math.max(...snows) : 1,
      4
    );
    const tempMin = tempTicks[0];
    const tempMax = tempTicks[tempTicks.length - 1];
    const snowMin = snowTicks[0];
    const snowMax = snowTicks[snowTicks.length - 1];

    const xOf = (t) => pad.left + ((t - tMin) / (tMax - tMin || 1)) * plotW;
    const yTemp = (v) => pad.top + (1 - (v - tempMin) / (tempMax - tempMin || 1)) * plotH;
    const ySnow = (v) => pad.top + (1 - (v - snowMin) / (snowMax - snowMin || 1)) * plotH;

    ctx.strokeStyle = "rgba(20, 32, 28, 0.08)";
    ctx.lineWidth = 1;
    for (const tick of tempTicks) {
      const y = yTemp(tick);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + plotW, y);
      ctx.stroke();
    }

    ctx.fillStyle = "#3a4a44";
    ctx.font = "500 10px IBM Plex Sans, system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    const tempUnit = unitSystem === "us" ? "°F" : "°C";
    for (const tick of tempTicks) {
      ctx.fillStyle = "#c45d2c";
      ctx.fillText(tick.toFixed(Math.abs(tick) >= 10 ? 0 : 1), pad.left - 6, yTemp(tick));
    }
    ctx.fillStyle = "#00a8c4";
    ctx.textAlign = "left";
    const snowUnit = unitSystem === "us" ? "in" : "cm";
    for (const tick of snowTicks) {
      ctx.fillText(`${tick.toFixed(Math.abs(tick) >= 10 ? 0 : 1)}`, pad.left + plotW + 6, ySnow(tick));
    }

    // axis unit captions
    ctx.fillStyle = "#c45d2c";
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(tempUnit, 4, 11);
    ctx.fillStyle = "#00a8c4";
    ctx.textAlign = "right";
    ctx.fillText(snowUnit, cssW - 4, 11);

    function strokeSeries(key, color, yOf) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      ctx.beginPath();
      let started = false;
      for (const p of points) {
        const v = p[key];
        if (v === null) {
          started = false;
          continue;
        }
        const x = xOf(p.t);
        const y = yOf(v);
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }

    if (hasSnow) strokeSeries("snow", "#00a8c4", ySnow);
    if (hasTemp) strokeSeries("temp", "#c45d2c", yTemp);

    // time labels
    ctx.fillStyle = "#3a4a44";
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    const labelCount = Math.min(4, points.length);
    for (let i = 0; i < labelCount; i++) {
      const idx =
        labelCount === 1
          ? 0
          : Math.round((i * (points.length - 1)) / (labelCount - 1));
      const p = points[idx];
      const d = new Date(p.t);
      const label =
        modalState?.chartRange === "7d"
          ? d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
          : d.toLocaleString(undefined, {
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });
      ctx.fillText(label, xOf(p.t), pad.top + plotH + 8);
    }
  }

  async function fetchHistorySeries(stationId, range) {
    const end = new Date();
    const start =
      range === "7d"
        ? new Date(end.getTime() - 7 * 24 * 3600 * 1000)
        : new Date(end.getTime() - 72 * 3600 * 1000);
    const resolution = range === "7d" ? "daily" : "hourly";
    const limit = range === "7d" ? 14 : 100;
    const url =
      `${API_BASE}/v1/stations/${encodeURIComponent(stationId)}/observations` +
      `?resolution=${resolution}` +
      `&start=${encodeURIComponent(start.toISOString())}` +
      `&end=${encodeURIComponent(end.toISOString())}` +
      `&limit=${limit}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  function historyCaption(range, series) {
    const n = series?.length || 0;
    if (range === "7d") {
      return n
        ? `${n} daily reading${n === 1 ? "" : "s"} · last 7 days`
        : "No daily history yet for this station";
    }
    return n
      ? `${n} hourly reading${n === 1 ? "" : "s"} · last 72 hours`
      : "No hourly history yet for this station";
  }

  async function loadHistoryForModal(forceReload) {
    if (!modalState?.props?.id) return;
    const range = modalState.chartRange || "72h";
    syncHistoryButtons(range);

    if (!forceReload && modalState.seriesByRange[range]) {
      historyStatus.textContent = historyCaption(range, modalState.seriesByRange[range]);
      drawHistoryChart(modalState.seriesByRange[range]);
      return;
    }

    const requestId = ++chartRequestSeq;
    modalState.chartRequestId = requestId;
    historyStatus.textContent =
      range === "7d" ? "Loading 7-day daily history…" : "Loading 72-hour history…";
    clearHistoryChart();

    try {
      const series = await fetchHistorySeries(modalState.props.id, range);
      if (!modalState || modalState.chartRequestId !== requestId) return;
      modalState.seriesByRange[range] = series;
      historyStatus.textContent = historyCaption(range, series);
      drawHistoryChart(series);
    } catch (err) {
      if (!modalState || modalState.chartRequestId !== requestId) return;
      historyStatus.textContent = `Could not load history (${err.message})`;
      clearHistoryChart();
    }
  }

  function setChartRange(range) {
    if (!modalState) return;
    modalState.chartRange = range === "7d" ? "7d" : "72h";
    loadHistoryForModal(false);
  }

  function openModal(props, detail, opts = {}) {
    const keepChart = Boolean(opts.keepChart && modalState && modalState.props?.id === props.id);
    const prevRange = keepChart ? modalState.chartRange : "72h";
    const prevSeries = keepChart ? modalState.seriesByRange : { "72h": null, "7d": null };

    modalState = {
      props,
      detail,
      chartRange: prevRange || "72h",
      seriesByRange: prevSeries || { "72h": null, "7d": null },
      chartRequestId: keepChart ? modalState.chartRequestId : 0,
    };
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    const key = layerKey(props);
    modalProvider.textContent = layerLabel(key);
    modalTitle.textContent = props.name || props.id || "Station";
    modalId.textContent = props.external_id
      ? `${props.id} · ${props.external_id}`
      : props.id || "";
    modalError.hidden = true;
    modalError.textContent = "";
    modalMeaning.textContent = fieldMeaning(key);

    const observed = detail?.timestamp || props.observed_at;
    modalObserved.textContent = `Observed ${fmtTime(observed)}`;

    setReadings([
      ["SWE", fmtMm(detail?.swe_mm ?? props.swe_mm)],
      ["Snow depth", fmtCm(detail?.snow_depth_cm ?? props.snow_depth_cm)],
      ["Snowfall", fmtCm(detail?.snowfall_cm)],
      ["Temperature", fmtTemp(detail?.temperature_c ?? props.temperature_c)],
      ["Precipitation", fmtMm(detail?.precipitation_mm)],
      ["Elevation", fmtElev(props.elevation_m)],
      ["Wind", fmtWind(detail?.wind_speed_ms)],
      ["Humidity", fmt(detail?.humidity, "%")],
    ]);

    const currentUrl = `${API_BASE}/v1/stations/${encodeURIComponent(props.id)}/current`;
    modalApi.href = currentUrl;

    syncHistoryButtons(modalState.chartRange);
    // redraw after layout so canvas has size
    requestAnimationFrame(() => {
      if (!modalState) return;
      if (keepChart) {
        const series = modalState.seriesByRange[modalState.chartRange];
        if (series) {
          historyStatus.textContent = historyCaption(modalState.chartRange, series);
          drawHistoryChart(series);
        }
        return;
      }
      loadHistoryForModal(true);
    });
  }

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = "";
    modalState = null;
    clearHistoryChart();
    historyStatus.textContent = "";
    if (activeMarker) {
      const p = activeMarker.__sonProps;
      activeMarker.setIcon(markerIcon(layerKey(p), false));
      activeMarker = null;
    }
  }

  modal.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", closeModal);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  async function onMarkerClick(marker, props) {
    if (activeMarker && activeMarker !== marker) {
      activeMarker.setIcon(markerIcon(layerKey(activeMarker.__sonProps), false));
    }
    activeMarker = marker;
    marker.setIcon(markerIcon(layerKey(props), true));

    openModal(props, null);
    modalObserved.textContent = "Loading latest reading…";

    try {
      const res = await fetch(
        `${API_BASE}/v1/stations/${encodeURIComponent(props.id)}/current`
      );
      if (!res.ok) {
        if (res.status === 404) {
          openModal(props, null, { keepChart: true });
          modalObserved.textContent = "No observations for this station yet.";
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const detail = await res.json();
      openModal(props, detail, { keepChart: true });
    } catch (err) {
      openModal(props, null, { keepChart: true });
      modalError.hidden = false;
      modalError.textContent = `Could not load current reading (${err.message}). Showing map snapshot.`;
    }
  }

  function visibleCount() {
    return Object.keys(enabled).reduce(
      (sum, key) => sum + (enabled[key] ? counts[key] || 0 : 0),
      0
    );
  }

  function updateStatus() {
    const total = allFeatures.length;
    const shown = visibleCount();
    statusEl.textContent = `${shown.toLocaleString()} shown · ${total.toLocaleString()} total`;
  }

  function fitVisible() {
    const bounds = [];
    for (const [key, group] of Object.entries(layersByKey)) {
      if (!enabled[key]) continue;
      group.eachLayer((m) => {
        const ll = m.getLatLng && m.getLatLng();
        if (ll) bounds.push(ll);
      });
    }
    if (bounds.length) {
      map.fitBounds(bounds, { padding: [48, 48], maxZoom: 8 });
    }
  }

  function setLayerVisible(key, on) {
    enabled[key] = on;
    const group = layersByKey[key];
    if (!group) return;
    if (on) {
      if (!map.hasLayer(group)) map.addLayer(group);
    } else {
      if (map.hasLayer(group)) map.removeLayer(group);
      if (activeMarker && layerKey(activeMarker.__sonProps) === key) {
        closeModal();
      }
    }
    const checkbox = document.getElementById(`filter-${key}`);
    if (checkbox && checkbox.checked !== on) checkbox.checked = on;
    updateStatus();
  }

  function hideSearchResults() {
    searchResults.hidden = true;
    searchResults.innerHTML = "";
    searchActiveIndex = -1;
  }

  function searchHaystack(props) {
    const id = String(props.id || "");
    const code = id.includes("-") ? id.split("-").pop() : id;
    return [
      props.name,
      props.id,
      props.external_id,
      code,
      props.provider,
      props.network,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
  }

  function rankMatch(query, props) {
    const q = query.toLowerCase().trim();
    if (!q) return 0;
    const name = String(props.name || "").toLowerCase();
    const id = String(props.id || "").toLowerCase();
    const ext = String(props.external_id || "").toLowerCase();
    const code = id.includes("-") ? id.split("-").pop() : id;
    if (id === q || ext === q || code === q) return 100;
    if (id.startsWith(q) || code.startsWith(q)) return 90;
    if (name.startsWith(q)) return 80;
    if (id.includes(q) || ext.includes(q) || code.includes(q)) return 70;
    if (name.includes(q)) return 60;
    if (searchHaystack(props).includes(q)) return 40;
    return 0;
  }

  function findStations(query) {
    const q = query.trim();
    if (q.length < 2) return [];
    return stationIndex
      .map((entry) => ({ entry, score: rankMatch(q, entry.props) }))
      .filter((row) => row.score > 0)
      .sort((a, b) => b.score - a.score || String(a.entry.props.name).localeCompare(String(b.entry.props.name)))
      .slice(0, 12)
      .map((row) => row.entry);
  }

  function renderSearchResults(matches) {
    searchResults.innerHTML = "";
    searchActiveIndex = -1;
    if (!searchInput.value.trim()) {
      hideSearchResults();
      return;
    }
    if (!matches.length) {
      const empty = document.createElement("li");
      empty.className = "search__empty";
      empty.textContent = "No stations found";
      searchResults.append(empty);
      searchResults.hidden = false;
      return;
    }
    matches.forEach((entry, index) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "search__option";
      btn.dataset.index = String(index);
      const name = document.createElement("span");
      name.className = "search__option-name";
      name.textContent = entry.props.name || entry.props.id;
      const id = document.createElement("span");
      id.className = "search__option-id";
      id.textContent = `${layerLabel(entry.key)} · ${entry.props.id}`;
      btn.append(name, id);
      btn.addEventListener("click", () => selectStation(entry));
      li.append(btn);
      searchResults.append(li);
    });
    searchResults.hidden = false;
  }

  function highlightSearchOption(index) {
    const options = [...searchResults.querySelectorAll(".search__option")];
    options.forEach((el, i) => el.classList.toggle("is-active", i === index));
    searchActiveIndex = index;
    if (index >= 0 && options[index]) {
      options[index].scrollIntoView({ block: "nearest" });
    }
  }

  function selectStation(entry) {
    hideSearchResults();
    searchInput.value = entry.props.name || entry.props.id || "";
    if (!enabled[entry.key]) {
      setLayerVisible(entry.key, true);
    }
    if (window.matchMedia("(max-width: 900px)").matches) {
      setMenuOpen(false);
    }
    map.setView([entry.lat, entry.lon], Math.max(map.getZoom(), 10), { animate: true });
    onMarkerClick(entry.marker, entry.props);
  }

  function orderedKeys(keys) {
    const known = Object.keys(LAYER_META);
    const rest = keys.filter((k) => !known.includes(k)).sort();
    return [...known.filter((k) => keys.includes(k)), ...rest];
  }

  function buildFilterUI(keys) {
    filterList.innerHTML = "";
    for (const key of orderedKeys(keys)) {
      const id = `filter-${key}`;
      const label = document.createElement("label");
      label.className = "filter-row";
      label.htmlFor = id;

      const input = document.createElement("input");
      input.type = "checkbox";
      input.id = id;
      input.checked = enabled[key];
      input.addEventListener("change", () => {
        setLayerVisible(key, input.checked);
        fitVisible();
      });

      const swatch = document.createElement("span");
      swatch.className = swatchClass(key);
      swatch.setAttribute("aria-hidden", "true");

      const text = document.createElement("span");
      text.textContent = layerLabel(key);

      const count = document.createElement("span");
      count.className = "filter-count";
      count.textContent = String(counts[key] || 0);

      label.append(input, swatch, text, count);
      filterList.append(label);
    }
  }

  function renderMarkers(features) {
    for (const group of Object.values(layersByKey)) {
      group.clearLayers();
      if (map.hasLayer(group)) map.removeLayer(group);
    }
    Object.keys(layersByKey).forEach((k) => delete layersByKey[k]);
    Object.keys(counts).forEach((k) => delete counts[k]);
    stationIndex = [];

    for (const f of features) {
      const coords = f.geometry && f.geometry.coordinates;
      const props = f.properties || {};
      if (!coords || coords.length < 2) continue;
      const [lon, lat] = coords;
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) continue;

      const key = layerKey(props);
      if (!layersByKey[key]) {
        layersByKey[key] = L.layerGroup();
        counts[key] = 0;
        if (enabled[key] === undefined) {
          enabled[key] = defaultEnabled(key);
        }
      }
      counts[key] += 1;

      const marker = L.marker([lat, lon], {
        icon: markerIcon(key, false),
        title: props.name || props.id,
      });
      marker.__sonProps = props;
      marker.on("click", () => onMarkerClick(marker, props));
      marker.addTo(layersByKey[key]);
      stationIndex.push({ props, key, lat, lon, marker });
    }

    const keys = Object.keys(layersByKey);
    buildFilterUI(keys);

    for (const key of keys) {
      if (enabled[key]) {
        map.addLayer(layersByKey[key]);
      }
    }

    updateStatus();
    fitVisible();
  }

  searchInput.addEventListener("input", () => {
    renderSearchResults(findStations(searchInput.value));
  });

  searchInput.addEventListener("keydown", (e) => {
    const options = [...searchResults.querySelectorAll(".search__option")];
    if (e.key === "ArrowDown" && options.length) {
      e.preventDefault();
      highlightSearchOption(Math.min(searchActiveIndex + 1, options.length - 1));
    } else if (e.key === "ArrowUp" && options.length) {
      e.preventDefault();
      highlightSearchOption(Math.max(searchActiveIndex - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (searchActiveIndex >= 0 && options[searchActiveIndex]) {
        options[searchActiveIndex].click();
        return;
      }
      const matches = findStations(searchInput.value);
      if (matches.length) selectStation(matches[0]);
    } else if (e.key === "Escape") {
      hideSearchResults();
      searchInput.blur();
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search")) hideSearchResults();
  });

  unitMetricBtn.addEventListener("click", () => setUnitSystem("metric"));
  unitUsBtn.addEventListener("click", () => setUnitSystem("us"));
  syncUnitButtons();

  history72hBtn.addEventListener("click", () => setChartRange("72h"));
  history7dBtn.addEventListener("click", () => setChartRange("7d"));
  window.addEventListener("resize", () => {
    if (!modalState || modal.hidden) return;
    const series = modalState.seriesByRange[modalState.chartRange];
    if (series) drawHistoryChart(series);
  });

  const menuToggle = document.getElementById("menu-toggle");
  const menuClose = document.getElementById("menu-close");
  const menuPanel = document.getElementById("menu-panel");
  const menuBackdrop = document.getElementById("menu-backdrop");

  function setMenuOpen(open) {
    menuPanel.classList.toggle("is-open", open);
    menuBackdrop.hidden = !open;
    menuToggle.setAttribute("aria-expanded", String(open));
    menuToggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
    document.body.classList.toggle("menu-open", open);
  }

  menuToggle.addEventListener("click", () => {
    setMenuOpen(!menuPanel.classList.contains("is-open"));
  });
  menuClose.addEventListener("click", () => setMenuOpen(false));
  menuBackdrop.addEventListener("click", () => setMenuOpen(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menuPanel.classList.contains("is-open")) {
      setMenuOpen(false);
    }
  });
  window.addEventListener("resize", () => {
    if (window.matchMedia("(min-width: 901px)").matches) {
      setMenuOpen(false);
    }
  });

  async function loadStations() {
    statusEl.textContent = "Loading stations…";
    try {
      const res = await fetch(`${API_BASE}/v1/map/stations`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const geo = await res.json();
      allFeatures = geo.features || [];
      renderMarkers(allFeatures);
    } catch (err) {
      statusEl.textContent = `Failed to load map (${err.message}). Is the API up and CORS deployed?`;
      console.error(err);
    }
  }

  loadStations();
})();
