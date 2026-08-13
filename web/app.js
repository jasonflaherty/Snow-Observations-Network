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
  const unitCBtn = document.getElementById("unit-c");
  const unitFBtn = document.getElementById("unit-f");
  const modal = document.getElementById("modal");
  const modalTitle = document.getElementById("modal-title");
  const modalProvider = document.getElementById("modal-provider");
  const modalId = document.getElementById("modal-id");
  const modalObserved = document.getElementById("modal-observed");
  const modalReadings = document.getElementById("modal-readings");
  const modalError = document.getElementById("modal-error");
  const modalApi = document.getElementById("modal-api");

  const TEMP_KEY = "son-temp-unit";
  let tempUnit = localStorage.getItem(TEMP_KEY) === "F" ? "F" : "C";
  /** @type {{ props: object, detail: object | null } | null} */
  let modalState = null;

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

  function fmtTemp(celsius) {
    if (celsius === null || celsius === undefined || Number.isNaN(Number(celsius))) {
      return "—";
    }
    const c = Number(celsius);
    if (tempUnit === "F") return fmt(cToF(c), "°F");
    return fmt(c, "°C");
  }

  function syncUnitButtons() {
    const isC = tempUnit === "C";
    unitCBtn.classList.toggle("is-active", isC);
    unitFBtn.classList.toggle("is-active", !isC);
    unitCBtn.setAttribute("aria-pressed", String(isC));
    unitFBtn.setAttribute("aria-pressed", String(!isC));
  }

  function setTempUnit(unit) {
    tempUnit = unit === "F" ? "F" : "C";
    localStorage.setItem(TEMP_KEY, tempUnit);
    syncUnitButtons();
    if (modalState && !modal.hidden) {
      openModal(modalState.props, modalState.detail);
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

  function openModal(props, detail) {
    modalState = { props, detail };
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
      ["Temperature", fmtTemp(detail?.temperature_c ?? props.temperature_c)],
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
    modalState = null;
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

  unitCBtn.addEventListener("click", () => setTempUnit("C"));
  unitFBtn.addEventListener("click", () => setTempUnit("F"));
  syncUnitButtons();

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
