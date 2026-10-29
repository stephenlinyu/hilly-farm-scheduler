(function () {
  "use strict";

  const DEFAULT_CENTER = [29.56, 106.55];

  function toLngLat(point) {
    return [Number(point[1]), Number(point[0])];
  }

  function toLatLng(point) {
    if (Array.isArray(point)) return [Number(point[1]), Number(point[0])];
    return [Number(point.getLat()), Number(point.getLng())];
  }

  function validPoint(point) {
    return Array.isArray(point)
      && point.length >= 2
      && Number.isFinite(Number(point[0]))
      && Number.isFinite(Number(point[1]));
  }

  function paddingArray(options = {}) {
    const topLeft = options.paddingTopLeft || options.padding || [60, 60];
    const bottomRight = options.paddingBottomRight || options.padding || [60, 60];
    return [
      Number(topLeft[1] || 0),
      Number(bottomRight[1] || 0),
      Number(topLeft[0] || 0),
      Number(bottomRight[0] || 0),
    ];
  }

  function loadScript(src, marker) {
    if (marker && window[marker]) return Promise.resolve();
    const existing = document.querySelector(`script[data-map-loader="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "true") return Promise.resolve();
      return new Promise((resolve, reject) => {
        existing.addEventListener("load", resolve, { once: true });
        existing.addEventListener("error", () => reject(new Error("地图加载器不可用")), { once: true });
      });
    }

    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      const timeout = window.setTimeout(() => reject(new Error("地图加载器响应超时")), 10000);
      script.src = src;
      script.async = true;
      script.dataset.mapLoader = src;
      script.addEventListener("load", () => {
        window.clearTimeout(timeout);
        script.dataset.loaded = "true";
        resolve();
      }, { once: true });
      script.addEventListener("error", () => {
        window.clearTimeout(timeout);
        reject(new Error("地图加载器不可用"));
      }, { once: true });
      document.head.appendChild(script);
    });
  }

  async function fetchMapConfig() {
    const response = await fetch("/api/map/config", { credentials: "same-origin" });
    if (!response.ok) throw new Error("无法读取地图配置");
    return response.json();
  }

  async function loadAMap(config) {
    window._AMapSecurityConfig = { serviceHost: config.service_host };
    await loadScript("https://webapi.amap.com/loader.js", "AMapLoader");
    return window.AMapLoader.load({
      key: config.key,
      version: config.version || "2.0",
      plugins: ["AMap.Scale", "AMap.ToolBar"],
    }).then((AMap) => {
      AMap.getConfig().appname = "amap-jsapi-skill";
      return AMap;
    });
  }

  class AMapMarkerHandle {
    constructor(owner, marker, point) {
      this.owner = owner;
      this.raw = marker;
      this.point = point;
      this.infoWindow = null;
    }

    bindPopup(html) {
      this.infoWindow = new this.owner.AMap.InfoWindow({
        content: html,
        anchor: "bottom-center",
        offset: new this.owner.AMap.Pixel(0, -22),
        autoMove: true,
        closeWhenClickMap: true,
      });
      this.raw.on("click", () => this.openPopup());
      return this;
    }

    bindTooltip(html) {
      this.raw.on("mouseover", () => this.owner.showTooltip(html, this.raw.getPosition()));
      this.raw.on("mouseout", () => this.owner.hideTooltip());
      return this;
    }

    on(eventName, handler) {
      this.raw.on(eventName, handler);
      return this;
    }

    openPopup() {
      if (this.infoWindow) {
        this.infoWindow.open(this.owner.map, this.raw.getPosition());
      }
      return this;
    }

    setPosition(point) {
      this.point = point;
      this.raw.setPosition(toLngLat(point));
    }

    setRadius(radius) {
      if (this.raw.setRadius) this.raw.setRadius(radius);
    }

    setStyle(style) {
      if (this.raw.setOptions) {
        this.raw.setOptions({
          fillOpacity: style.fillOpacity,
          fillColor: style.fillColor,
          strokeColor: style.color || style.strokeColor,
          strokeOpacity: style.opacity || style.strokeOpacity,
          strokeWeight: style.weight || style.strokeWeight,
        });
      }
    }
  }

  class AMapOverlayGroup {
    constructor(owner, options = {}) {
      this.owner = owner;
      this.visible = options.visible !== false;
      this.overlays = [];
    }

    addOverlay(overlay) {
      this.overlays.push(overlay);
      if (this.visible) this.owner.map.add(overlay);
      return overlay;
    }

    addHtmlMarker(point, options = {}) {
      const size = options.size || [36, 36];
      const anchor = options.anchor || [size[0] / 2, size[1] / 2];
      const marker = new this.owner.AMap.Marker({
        position: toLngLat(point),
        content: options.html || "",
        title: options.title || "",
        offset: new this.owner.AMap.Pixel(-anchor[0], -anchor[1]),
        zIndex: options.zIndex || 100,
        bubble: false,
      });
      this.addOverlay(marker);
      return new AMapMarkerHandle(this.owner, marker, point);
    }

    addCircleMarker(point, options = {}) {
      const marker = new this.owner.AMap.CircleMarker({
        center: toLngLat(point),
        radius: options.radius || 5,
        strokeColor: options.color || options.strokeColor || "#ffffff",
        strokeOpacity: options.opacity ?? options.strokeOpacity ?? 0.9,
        strokeWeight: options.weight || options.strokeWeight || 1.5,
        fillColor: options.fillColor || "#ff6b35",
        fillOpacity: options.fillOpacity ?? 0.75,
        zIndex: options.zIndex || 80,
        cursor: "pointer",
      });
      this.addOverlay(marker);
      return new AMapMarkerHandle(this.owner, marker, point);
    }

    addPolyline(points, options = {}) {
      const dashArray = String(options.dashArray || "")
        .split(/[, ]+/)
        .map(Number)
        .filter(Number.isFinite);
      const line = new this.owner.AMap.Polyline({
        path: points.filter(validPoint).map(toLngLat),
        strokeColor: options.color || options.strokeColor || "#2f9df4",
        strokeOpacity: options.opacity ?? options.strokeOpacity ?? 0.9,
        strokeWeight: options.weight || options.strokeWeight || 4,
        strokeStyle: dashArray.length ? "dashed" : "solid",
        strokeDasharray: dashArray.length ? dashArray : undefined,
        isOutline: Boolean(options.outlineColor),
        outlineColor: options.outlineColor,
        borderWeight: options.borderWeight || 2,
        lineJoin: "round",
        lineCap: "round",
        showDir: Boolean(options.showDir),
        zIndex: options.zIndex || 60,
      });
      this.addOverlay(line);
      return line;
    }

    clear() {
      if (this.overlays.length) this.owner.map.remove(this.overlays);
      this.overlays = [];
    }

    setVisible(visible) {
      if (this.visible === visible) return;
      this.visible = visible;
      if (!this.overlays.length) return;
      if (visible) this.owner.map.add(this.overlays);
      else this.owner.map.remove(this.overlays);
    }

    isVisible() {
      return this.visible;
    }
  }

  class AMapFarmMap {
    constructor(containerId, AMap, options = {}) {
      this.provider = "amap";
      this.AMap = AMap;
      this.normalLayer = AMap.createDefaultLayer({ zooms: [3, 20] });
      this.satelliteLayer = new AMap.TileLayer.Satellite({ zooms: [3, 20] });
      this.roadNetLayer = new AMap.TileLayer.RoadNet({ zooms: [3, 20] });
      this.map = new AMap.Map(containerId, {
        viewMode: "3D",
        zoom: options.zoom || 13,
        center: toLngLat(options.center || DEFAULT_CENTER),
        zooms: [options.minZoom || 4, options.maxZoom || 20],
        pitch: 0,
        rotation: 0,
        animateEnable: true,
        mapStyle: options.mapStyle || "amap://styles/normal",
        features: ["bg", "point", "road", "building"],
        layers: [this.normalLayer],
      });
      this.tooltip = new AMap.InfoWindow({
        isCustom: true,
        anchor: "bottom-center",
        offset: new AMap.Pixel(0, -8),
        closeWhenClickMap: true,
      });
      this.map.addControl(new AMap.Scale());
      if (options.toolBar) this.map.addControl(new AMap.ToolBar({ position: "RT" }));
    }

    createGroup(options) {
      return new AMapOverlayGroup(this, options);
    }

    on(eventName, handler) {
      this.map.on(eventName, handler);
    }

    onLoad(handler) {
      this.map.on("complete", handler);
    }

    onError(handler) {
      this.map.on("error", handler);
    }

    showTooltip(html, position) {
      this.tooltip.setContent(`<div class="amap-hover-tip">${html}</div>`);
      this.tooltip.open(this.map, position);
    }

    hideTooltip() {
      this.tooltip.close();
    }

    setBaseLayer(type) {
      this.map.setLayers(type === "satellite"
        ? [this.satelliteLayer, this.roadNetLayer]
        : [this.normalLayer]);
    }

    setView(point, zoom) {
      this.map.setZoomAndCenter(zoom || this.map.getZoom(), toLngLat(point));
    }

    getZoom() {
      return this.map.getZoom();
    }

    fitBounds(points, options = {}) {
      const validPoints = points.filter(validPoint);
      if (!validPoints.length) return;
      if (validPoints.length === 1) {
        this.setView(validPoints[0], options.maxZoom || 15);
        return;
      }
      const lngs = validPoints.map((point) => Number(point[1]));
      const lats = validPoints.map((point) => Number(point[0]));
      const bounds = new this.AMap.Bounds(
        [Math.min(...lngs), Math.min(...lats)],
        [Math.max(...lngs), Math.max(...lats)],
      );
      const fitted = this.map.getFitZoomAndCenterByBounds(
        bounds,
        paddingArray(options),
        options.maxZoom || 15,
      );
      this.map.setZoomAndCenter(fitted[0], fitted[1]);
    }

    invalidateSize() {
      this.map.resize();
    }

    destroy() {
      this.map.destroy();
    }
  }

  class LeafletMarkerHandle {
    constructor(marker) {
      this.raw = marker;
    }

    bindPopup(html) {
      this.raw.bindPopup(html);
      return this;
    }

    bindTooltip(html, options) {
      this.raw.bindTooltip(html, options);
      return this;
    }

    on(eventName, handler) {
      this.raw.on(eventName, handler);
      return this;
    }

    openPopup() {
      this.raw.openPopup();
      return this;
    }

    setPosition(point) {
      this.raw.setLatLng(point);
    }

    setRadius(radius) {
      if (this.raw.setRadius) this.raw.setRadius(radius);
    }

    setStyle(style) {
      if (this.raw.setStyle) this.raw.setStyle(style);
    }
  }

  class LeafletOverlayGroup {
    constructor(owner, options = {}) {
      this.owner = owner;
      this.visible = options.visible !== false;
      this.layer = options.clustered && window.L.markerClusterGroup
        ? window.L.markerClusterGroup({
            showCoverageOnHover: false,
            spiderfyOnMaxZoom: true,
            maxClusterRadius: 46,
            disableClusteringAtZoom: 15,
            removeOutsideVisibleBounds: true,
            iconCreateFunction(cluster) {
              return window.L.divIcon({
                html: `<div class="cluster-badge">${cluster.getChildCount()}</div>`,
                className: "",
                iconSize: [46, 46],
              });
            },
          })
        : window.L.layerGroup();
      if (this.visible) this.layer.addTo(owner.map);
    }

    addHtmlMarker(point, options = {}) {
      const size = options.size || [36, 36];
      const anchor = options.anchor || [size[0] / 2, size[1] / 2];
      const marker = window.L.marker(point, {
        icon: window.L.divIcon({
          html: options.html || "",
          className: "",
          iconSize: size,
          iconAnchor: anchor,
          popupAnchor: options.popupAnchor || [0, -anchor[1]],
        }),
        title: options.title || "",
      });
      this.layer.addLayer(marker);
      return new LeafletMarkerHandle(marker);
    }

    addCircleMarker(point, options = {}) {
      const marker = window.L.circleMarker(point, options);
      this.layer.addLayer(marker);
      return new LeafletMarkerHandle(marker);
    }

    addPolyline(points, options = {}) {
      const line = window.L.polyline(points, options);
      this.layer.addLayer(line);
      return line;
    }

    clear() {
      this.layer.clearLayers();
    }

    setVisible(visible) {
      if (this.visible === visible) return;
      this.visible = visible;
      if (visible) this.layer.addTo(this.owner.map);
      else this.owner.map.removeLayer(this.layer);
    }

    isVisible() {
      return this.visible;
    }
  }

  class LeafletFarmMap {
    constructor(containerId, options = {}) {
      this.provider = "leaflet";
      this.map = window.L.map(containerId, {
        zoomControl: false,
        minZoom: options.minZoom || 4,
        maxZoom: options.maxZoom || 18,
        preferCanvas: true,
      }).setView(options.center || DEFAULT_CENTER, options.zoom || 13);

      if (options.toolBar) window.L.control.zoom({ position: "topright" }).addTo(this.map);
      this.streetLayer = window.L.tileLayer(
        "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}",
        {
          subdomains: ["1", "2", "3", "4"], minZoom: 3, maxZoom: 18,
          detectRetina: true, keepBuffer: 3, attribution: "&copy; 高德地图",
        },
      );
      this.satelliteLayer = window.L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        { minZoom: 3, maxZoom: 18, detectRetina: true, keepBuffer: 3, attribution: "&copy; Esri" },
      );
      this.labelLayer = window.L.tileLayer(
        "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
        { minZoom: 3, maxZoom: 18, detectRetina: true, keepBuffer: 3, attribution: "&copy; Esri" },
      );
      this.streetLayer.addTo(this.map);
    }

    createGroup(options) {
      return new LeafletOverlayGroup(this, options);
    }

    on(eventName, handler) {
      this.map.on(eventName, handler);
    }

    onLoad(handler) {
      this.streetLayer.on("load", handler);
    }

    onError(handler) {
      [this.streetLayer, this.satelliteLayer, this.labelLayer]
        .forEach((layer) => layer.on("tileerror", handler));
    }

    setBaseLayer(type) {
      [this.streetLayer, this.satelliteLayer, this.labelLayer]
        .forEach((layer) => this.map.removeLayer(layer));
      if (type === "satellite") {
        this.satelliteLayer.addTo(this.map);
        this.labelLayer.addTo(this.map);
      } else {
        this.streetLayer.addTo(this.map);
      }
    }

    setView(point, zoom) {
      this.map.setView(point, zoom || this.map.getZoom());
    }

    getZoom() {
      return this.map.getZoom();
    }

    fitBounds(points, options = {}) {
      if (!points.filter(validPoint).length) return;
      this.map.fitBounds(points, {
        animate: true,
        maxZoom: options.maxZoom || 15,
        paddingTopLeft: options.paddingTopLeft || options.padding || [60, 60],
        paddingBottomRight: options.paddingBottomRight || options.padding || [60, 60],
      });
    }

    invalidateSize() {
      this.map.invalidateSize();
    }

    destroy() {
      this.map.remove();
    }
  }

  async function create(containerId, options = {}) {
    let config = null;
    let fallbackReason = "高德地图尚未配置";
    try {
      config = await fetchMapConfig();
      if (config.configured && config.provider === "amap") {
        const AMap = await loadAMap(config);
        const provider = new AMapFarmMap(containerId, AMap, options);
        provider.fallbackReason = "";
        return provider;
      }
    } catch (error) {
      fallbackReason = error?.message || "高德地图加载失败";
      console.warn("AMap unavailable, using Leaflet fallback:", error);
    }

    const fallback = new LeafletFarmMap(containerId, options);
    fallback.fallbackReason = config?.configured ? fallbackReason : "高德地图尚未配置";
    return fallback;
  }

  window.FarmMapProvider = { create };
})();
