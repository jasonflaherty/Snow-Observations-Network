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
  const modal = document.getElementById("modal");
  const modalTitle = document.getElementById("modal-title");
  const modalProvider = document.getElementById("modal-provider");
  const modalId = document.getElementById("modal-id");
  const modalObserved = document.getElementById("modal-observed");
  const modalReadings = document.getElementById("modal-readings");
  const modalError = document.getElementById("modal-error");
  const modalApi = document.getElementById("modal-api");

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
  let activeMarker = null;
  let allFeatures = [];

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

  function openModal(props, detail) {
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

    const observed = detail?.timestamp || props.observed_at;
    modalObserved.textContent = `Observed ${fmtTime(observed)}`;

    setReadings([
      ["SWE", fmt(detail?.swe_mm ?? props.swe_mm, "mm")],
      ["Snow depth", fmt(detail?.snow_depth_cm ?? props.snow_depth_cm, "cm")],
      ["Temperature", fmt(detail?.temperature_c ?? props.temperature_c, "°C")],
      ["Precipitation", fmt(detail?.precipitation_mm, "mm")],
      ["Elevation", fmt(props.elevation_m, "m")],
      ["Wind", fmt(detail?.wind_speed_ms, "m/s")],
      ["Humidity", fmt(detail?.humidity, "%")],
    ]);

    const currentUrl = `${API_BASE}/v1/stations/${encodeURIComponent(props.id)}/current`;
    modalApi.href = currentUrl;
  }

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = "";
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
          openModal(props, null);
          modalObserved.textContent = "No observations for this station yet.";
          return;
        }
        throw new Error(`HTTP ${res.status}`);
      }
      const detail = await res.json();
      openModal(props, detail);
    } catch (err) {
      openModal(props, null);
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
    updateStatus();
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
