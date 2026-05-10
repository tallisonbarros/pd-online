(function () {
    function parsePayload() {
        const node = document.getElementById("dashboard-payload");
        if (!node) return null;
        try {
            const parsed = JSON.parse(node.textContent || "{}");
            if (typeof parsed === "string") {
                return JSON.parse(parsed || "{}");
            }
            return parsed;
        } catch (error) {
            return null;
        }
    }

    function num(value) {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function ns(name) {
        return document.createElementNS("http://www.w3.org/2000/svg", name);
    }

    function append(el, tag, attrs) {
        const node = ns(tag);
        Object.entries(attrs || {}).forEach(([k, v]) => node.setAttribute(k, String(v)));
        el.appendChild(node);
        return node;
    }

    function getChartSize(svg, fallbackW, fallbackH) {
        const rect = svg.getBoundingClientRect();
        const W = Math.max(320, Math.round(rect.width) || fallbackW);
        const H = Math.max(180, Math.round(rect.height) || fallbackH);
        svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
        return { W, H };
    }

    function buildSmoothPath(points) {
        if (!points.length) return "";
        if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;

        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 0; i < points.length - 1; i += 1) {
            const p0 = points[i - 1] || points[i];
            const p1 = points[i];
            const p2 = points[i + 1];
            const p3 = points[i + 2] || p2;
            const cp1x = p1.x + (p2.x - p0.x) / 6;
            const cp1y = p1.y + (p2.y - p0.y) / 6;
            const cp2x = p2.x - (p3.x - p1.x) / 6;
            const cp2y = p2.y - (p3.y - p1.y) / 6;
            d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`;
        }
        return d;
    }

    function drawSales(svg, labels, values, average) {
        svg.innerHTML = "";
        const { W, H } = getChartSize(svg, 960, 320);
        const pad = {
            top: Math.max(20, Math.round(H * 0.09)),
            right: Math.max(18, Math.round(W * 0.025)),
            bottom: Math.max(34, Math.round(H * 0.14)),
            left: Math.max(38, Math.round(W * 0.055)),
        };
        const cw = W - pad.left - pad.right;
        const ch = H - pad.top - pad.bottom;
        const maxY = Math.max(1, ...values, average);
        const step = values.length > 1 ? cw / (values.length - 1) : cw;

        for (let i = 0; i <= 4; i += 1) {
            const y = pad.top + (ch / 4) * i;
            append(svg, "line", {
                x1: pad.left,
                y1: y,
                x2: W - pad.right,
                y2: y,
                stroke: "rgba(78,52,46,0.12)",
                "stroke-width": 1,
            });
        }

        const points = values.map((value, idx) => ({
            x: pad.left + step * idx,
            y: pad.top + ch - (value / maxY) * ch,
            v: value,
        }));

        const lineD = buildSmoothPath(points);
        if (!lineD) return;

        const last = points[points.length - 1];
        const first = points[0];
        const areaD = `${lineD} L ${last.x} ${pad.top + ch} L ${first.x} ${pad.top + ch} Z`;
        append(svg, "path", {
            d: areaD,
            fill: "rgba(255,106,0,0.11)",
        });

        const avgY = pad.top + ch - (average / maxY) * ch;
        append(svg, "line", {
            x1: pad.left,
            y1: avgY,
            x2: W - pad.right,
            y2: avgY,
            stroke: "rgba(255,106,0,0.58)",
            "stroke-width": 1.35,
            "stroke-dasharray": "5 5",
        });

        append(svg, "path", {
            d: lineD,
            fill: "none",
            stroke: "#ff6a00",
            "stroke-width": 3,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        });

        points.forEach((point) => {
            append(svg, "circle", {
                cx: point.x,
                cy: point.y,
                r: 4,
                fill: "#ff6a00",
                stroke: "#fff",
                "stroke-width": 1.6,
            });
        });

        labels.forEach((label, idx) => {
            const text = append(svg, "text", {
                x: pad.left + step * idx,
                y: H - 12,
                "text-anchor": "middle",
                fill: "#7c675c",
                "font-size": 11,
                "font-family": "Manrope, sans-serif",
            });
            text.textContent = label;
        });
    }

    function drawHourly(svg, labels, values) {
        svg.innerHTML = "";
        const { W, H } = getChartSize(svg, 960, 260);
        const pad = {
            top: Math.max(16, Math.round(H * 0.08)),
            right: Math.max(16, Math.round(W * 0.02)),
            bottom: Math.max(30, Math.round(H * 0.13)),
            left: Math.max(34, Math.round(W * 0.045)),
        };
        const cw = W - pad.left - pad.right;
        const ch = H - pad.top - pad.bottom;
        const maxY = Math.max(1, ...values);
        const step = values.length > 1 ? cw / (values.length - 1) : cw;

        for (let i = 0; i <= 4; i += 1) {
            const y = pad.top + (ch / 4) * i;
            append(svg, "line", {
                x1: pad.left,
                y1: y,
                x2: W - pad.right,
                y2: y,
                stroke: "rgba(78,52,46,0.11)",
                "stroke-width": 1,
            });
        }

        const points = values.map((value, idx) => ({
            x: pad.left + step * idx,
            y: pad.top + ch - (value / maxY) * ch,
            v: value,
        }));
        const lineD = buildSmoothPath(points);
        if (!lineD) return;

        append(svg, "path", {
            d: lineD,
            fill: "none",
            stroke: "#ff6a00",
            "stroke-width": 2.6,
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        });

        labels.forEach((label, idx) => {
            if (idx % 2 !== 0 && idx !== labels.length - 1) return;
            const text = append(svg, "text", {
                x: pad.left + step * idx,
                y: H - 10,
                "text-anchor": "middle",
                fill: "#7c675c",
                "font-size": 10,
                "font-family": "Manrope, sans-serif",
            });
            text.textContent = label;
        });
    }

    function renderCharts() {
        const payload = parsePayload();
        if (!payload) return;

        const labels = Array.isArray(payload.labels) ? payload.labels : [];
        const series = Array.isArray(payload.series) ? payload.series.map(num) : [];
        const average = num(payload.average);
        const hourLabels = Array.isArray(payload.hour_labels) ? payload.hour_labels : [];
        const hourSeries = Array.isArray(payload.hour_series) ? payload.hour_series.map(num) : [];

        const salesSvg = document.getElementById("dash-sales-chart");
        if (salesSvg && labels.length && series.length) {
            drawSales(salesSvg, labels, series, average);
        }

        const hourSvg = document.getElementById("dash-hour-chart");
        if (hourSvg && hourLabels.length && hourSeries.length) {
            drawHourly(hourSvg, hourLabels, hourSeries);
        }
    }

    function initHeatmap() {
        const card = document.querySelector(".ops-heatmap-card");
        const mapNode = document.getElementById("orders-heatmap");
        const emptyNode = document.getElementById("orders-heatmap-empty");
        if (!card || !mapNode) return null;

        const filters = Array.from(card.querySelectorAll(".ops-heatmap-filter-btn"));
        const endpoint = card.dataset.heatmapUrl || "/dashboard/api/order-heatmap/";
        const bairrosEndpoint = "/dashboard/api/bairros-rio-verde/";
        const bairrosPolygonsEndpoint = "/dashboard/api/bairros-polygons/";

        function showEmpty(visible) {
            if (emptyNode) {
                emptyNode.classList.toggle("hidden", !visible);
            }
            mapNode.classList.toggle("is-hidden", visible);
        }

        if (typeof window.maplibregl === "undefined") {
            showEmpty(true);
            return null;
        }

        const cityCenter = [-50.9192, -17.7923];
        const cityZoom = 12.1;
        const cityBounds = [
            [-51.05, -17.95],
            [-50.75, -17.65],
        ];
        const sourceId = "orders-heat";
        const heatLayerId = "orders-heat-layer";
        const pointLayerId = "orders-heat-points";
        const bairroSourceId = "orders-bairros";
        const bairroLayerId = "orders-bairros-layer";
        const bairroPolySourceId = "orders-bairros-polygons";
        const bairroPolyFillLayerId = "orders-bairros-polygons-fill";
        const bairroPolyLineLayerId = "orders-bairros-polygons-line";
        let requestToken = 0;
        const overlayNode = document.createElement("div");
        overlayNode.className = "ops-heatmap-overlay";
        mapNode.appendChild(overlayNode);
        let overlayFeatures = [];
        let bairrosCidade = [];
        let bairroHoverPopup = null;
        let bairrosPolygonFeatures = [];

        const map = new window.maplibregl.Map({
            container: mapNode,
            style: "https://tiles.openfreemap.org/styles/bright",
            center: cityCenter,
            zoom: cityZoom,
            minZoom: 10.5,
            maxZoom: 15.5,
            maxBounds: cityBounds,
            attributionControl: false,
            dragRotate: false,
            touchPitch: false,
            pitchWithRotate: false,
        });

        map.addControl(new window.maplibregl.AttributionControl({
            compact: true,
            customAttribution: "OpenStreetMap",
        }), "bottom-right");

        function setActiveFilter(period) {
            filters.forEach((button) => {
                button.classList.toggle("is-active", button.dataset.period === period);
            });
        }

        function normalizeFeatures(data) {
            if (!Array.isArray(data)) return [];
            const grouped = new Map();

            data.forEach((point) => {
                const isArrayPoint = Array.isArray(point);
                const lat = Number(
                    isArrayPoint
                        ? point[0]
                        : (point?.lat ?? point?.latitude ?? point?.geometry?.coordinates?.[1])
                );
                const lng = Number(
                    isArrayPoint
                        ? point[1]
                        : (point?.lng ?? point?.longitude ?? point?.geometry?.coordinates?.[0])
                );
                const weight = Number(isArrayPoint ? (point[2] || 1) : (point?.weight || 1));
                const bairro = String(isArrayPoint ? "" : (point?.bairro || "")).trim();
                if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
                if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return;
                const key = `${lat.toFixed(6)},${lng.toFixed(6)}`;
                grouped.set(key, {
                    lat,
                    lng,
                    weight: (grouped.get(key)?.weight || 0) + (Number.isFinite(weight) ? weight : 1),
                    bairro: grouped.get(key)?.bairro || bairro,
                });
            });

            return Array.from(grouped.values()).map((point) => ({
                type: "Feature",
                geometry: {
                    type: "Point",
                    coordinates: [point.lng, point.lat],
                },
                properties: {
                    weight: point.weight,
                    bairro: point.bairro || "",
                },
            }));
        }

        function buildBairroFeatures(features) {
            const byBairro = new Map();
            features.forEach((feature) => {
                const bairro = String(feature?.properties?.bairro || "").trim();
                if (!bairro) return;
                const [lng, lat] = feature.geometry.coordinates;
                const weight = Number(feature?.properties?.weight || 1);
                if (!byBairro.has(bairro)) {
                    byBairro.set(bairro, { latSum: 0, lngSum: 0, weightSum: 0, count: 0 });
                }
                const row = byBairro.get(bairro);
                row.latSum += lat;
                row.lngSum += lng;
                row.weightSum += weight;
                row.count += 1;
            });

            return Array.from(byBairro.entries()).map(([bairro, row]) => ({
                type: "Feature",
                geometry: {
                    type: "Point",
                    coordinates: [row.lngSum / row.count, row.latSum / row.count],
                },
                properties: {
                    bairro,
                    weight: row.weightSum,
                },
            }));
        }

        function buildFallbackBairroPolygons() {
            if (!Array.isArray(bairrosCidade) || !bairrosCidade.length) {
                return [];
            }
            const toNum = (v) => Number(v);
            const radius = 0.0038; // ~400m radius in lat degrees (approximation)
            return bairrosCidade
                .map((row) => {
                    const lat = toNum(row.lat);
                    const lng = toNum(row.lng);
                    const bairro = String(row.bairro || "").trim();
                    if (!Number.isFinite(lat) || !Number.isFinite(lng) || !bairro) return null;
                    const ring = [];
                    for (let i = 0; i < 6; i += 1) {
                        const angle = (Math.PI * 2 * i) / 6;
                        const latAdj = lat + (Math.sin(angle) * radius);
                        const lngAdj = lng + (Math.cos(angle) * radius * 1.08);
                        ring.push([lngAdj, latAdj]);
                    }
                    ring.push(ring[0]);
                    return {
                        type: "Feature",
                        geometry: { type: "Polygon", coordinates: [ring] },
                        properties: { bairro },
                    };
                })
                .filter(Boolean);
        }

        function applyBairroPolygonsToMap(features) {
            bairrosPolygonFeatures = Array.isArray(features) ? features : [];
            if (map.isStyleLoaded() && map.getSource(bairroPolySourceId)) {
                map.getSource(bairroPolySourceId).setData({
                    type: "FeatureCollection",
                    features: bairrosPolygonFeatures,
                });
            }
        }

        function isUrbanLabelLayer(layer) {
            const id = String(layer.id || "").toLowerCase();
            const sourceLayer = String(layer["source-layer"] || "").toLowerCase();
            return (
                layer.type === "symbol" &&
                (
                    id === "label_other" ||
                    id === "label_village" ||
                    id === "label_town" ||
                    id === "label_city" ||
                    id === "label_city_capital" ||
                    id === "highway-name-minor" ||
                    id === "highway-name-major"
                ) &&
                (sourceLayer.includes("place") || sourceLayer.includes("transportation_name"))
            );
        }

        function isRoadLayer(layer) {
            const id = String(layer.id || "").toLowerCase();
            const sourceLayer = String(layer["source-layer"] || "").toLowerCase();
            return (
                layer.type === "line" &&
                sourceLayer.includes("transportation") &&
                !id.includes("railway") &&
                !id.includes("ferry") &&
                !id.includes("cablecar") &&
                !id.includes("pier") &&
                !id.includes("path")
            );
        }

        function isFillToHide(layer) {
            const id = String(layer.id || "").toLowerCase();
            const sourceLayer = String(layer["source-layer"] || "").toLowerCase();
            return (
                layer.type === "fill" || layer.type === "fill-extrusion" || layer.type === "hillshade" || layer.type === "raster" ||
                id.includes("poi") || id.includes("park") || id.includes("landcover") || id.includes("landuse") ||
                id.includes("water") || id.includes("natural") || id.includes("building") || id.includes("aeroway") ||
                sourceLayer.includes("poi") || sourceLayer.includes("park") || sourceLayer.includes("landcover") ||
                sourceLayer.includes("landuse") || sourceLayer.includes("water") || sourceLayer.includes("building")
            );
        }

        function applyMinimalStyle() {
            const style = map.getStyle();
            if (!style || !Array.isArray(style.layers)) return;

            style.layers.forEach((layer) => {
                if (!map.getLayer(layer.id)) return;

                if (layer.id === heatLayerId) return;
                if (layer.id === bairroLayerId) return;
                if (layer.id === bairroPolyFillLayerId || layer.id === bairroPolyLineLayerId) return;

                if (layer.type === "background") {
                    map.setPaintProperty(layer.id, "background-color", "#fbfbfa");
                    return;
                }

                if (isFillToHide(layer) || layer.type === "circle") {
                    map.setLayoutProperty(layer.id, "visibility", "none");
                    return;
                }

                if (isRoadLayer(layer)) {
                    const isCasing = layer.id.includes("casing");
                    map.setPaintProperty(layer.id, "line-color", isCasing ? "#d7d1cc" : "#6b655f");
                    map.setPaintProperty(layer.id, "line-opacity", isCasing ? 0.92 : 0.8);
                    if (layer.paint && Object.prototype.hasOwnProperty.call(layer.paint, "line-width")) {
                        map.setPaintProperty(layer.id, "line-width", [
                            "interpolate",
                            ["linear"],
                            ["zoom"],
                            10, isCasing ? 0.8 : 0.45,
                            12, isCasing ? 1.4 : 0.9,
                            14, isCasing ? 2.1 : 1.55,
                        ]);
                    }
                    return;
                }

                if (layer.type === "line") {
                    map.setLayoutProperty(layer.id, "visibility", "none");
                    return;
                }

                if (isUrbanLabelLayer(layer)) {
                    map.setLayoutProperty(layer.id, "visibility", "none");
                    return;
                }

                if (layer.type === "symbol") {
                    map.setLayoutProperty(layer.id, "visibility", "none");
                }
            });
        }

        function ensureHeatmapSourceAndLayer() {
            if (!map.getSource(sourceId)) {
                map.addSource(sourceId, {
                    type: "geojson",
                    data: {
                        type: "FeatureCollection",
                        features: [],
                    },
                });
            }

            if (!map.getLayer(heatLayerId)) {
                map.addLayer({
                    id: heatLayerId,
                    type: "heatmap",
                    source: sourceId,
                    maxzoom: 16,
                    paint: {
                        "heatmap-weight": [
                            "interpolate",
                            ["linear"],
                            ["get", "weight"],
                            0, 0,
                            1, 0.8,
                            2, 0.95,
                            4, 1.4,
                            8, 2,
                        ],
                        "heatmap-intensity": [
                            "interpolate",
                            ["linear"],
                            ["zoom"],
                            10, 1.25,
                            12, 1.45,
                            14, 1.65,
                        ],
                        "heatmap-radius": [
                            "interpolate",
                            ["linear"],
                            ["zoom"],
                            10, 8,
                            12, 10,
                            14, 13,
                        ],
                        "heatmap-opacity": 0.96,
                        "heatmap-color": [
                            "interpolate",
                            ["linear"],
                            ["heatmap-density"],
                            0, "rgba(255,255,255,0)",
                            0.12, "rgba(255,211,175,0.18)",
                            0.28, "rgba(255,162,96,0.36)",
                            0.46, "rgba(245,113,33,0.58)",
                            0.64, "rgba(231,89,13,0.76)",
                            0.82, "rgba(214,71,6,0.9)",
                            1, "rgba(194,54,3,1)",
                        ],
                    },
                });
            }

            if (!map.getLayer(pointLayerId)) {
                map.addLayer({
                    id: pointLayerId,
                    type: "circle",
                    source: sourceId,
                    layout: {
                        visibility: "visible",
                    },
                    paint: {
                        "circle-radius": [
                            "interpolate",
                            ["linear"],
                            ["get", "weight"],
                            1, 24,
                            2, 32,
                            4, 42,
                            8, 54,
                        ],
                        "circle-color": "rgba(236,96,16,0.92)",
                        "circle-stroke-width": 0,
                        "circle-blur": 0.96,
                        "circle-opacity": 0.62,
                    },
                });
            }


            if (!map.getSource(bairroSourceId)) {
                map.addSource(bairroSourceId, {
                    type: "geojson",
                    data: {
                        type: "FeatureCollection",
                        features: [],
                    },
                });
            }

            if (!map.getLayer(bairroLayerId)) {
                map.addLayer({
                    id: bairroLayerId,
                    type: "symbol",
                    source: bairroSourceId,
                    layout: {
                        "text-field": ["get", "bairro"],
                        "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
                        "text-size": [
                            "interpolate",
                            ["linear"],
                            ["zoom"],
                            10, 10,
                            12, 11,
                            14, 12,
                        ],
                        "text-offset": [0, 0],
                        "text-allow-overlap": false,
                        "text-ignore-placement": false,
                    },
                    paint: {
                        "text-color": "rgba(78,52,46,0)",
                        "text-halo-color": "rgba(255,255,255,0)",
                        "text-halo-width": 0,
                    },
                });
            }

            if (!map.getSource(bairroPolySourceId)) {
                map.addSource(bairroPolySourceId, {
                    type: "geojson",
                    data: { type: "FeatureCollection", features: [] },
                });
            }

            if (!map.getLayer(bairroPolyFillLayerId)) {
                map.addLayer({
                    id: bairroPolyFillLayerId,
                    type: "fill",
                    source: bairroPolySourceId,
                    paint: {
                        "fill-color": "rgba(195,159,144,0.16)",
                        "fill-opacity": 0.08,
                    },
                });
            }

            if (!map.getLayer(bairroPolyLineLayerId)) {
                map.addLayer({
                    id: bairroPolyLineLayerId,
                    type: "line",
                    source: bairroPolySourceId,
                    paint: {
                        "line-color": "rgba(95,75,66,0.62)",
                        "line-width": 1.8,
                    },
                });
            }

            // Keep heat effects above polygon layers.
            if (map.getLayer(heatLayerId)) map.moveLayer(heatLayerId);
            if (map.getLayer(pointLayerId)) map.moveLayer(pointLayerId);
        }

        function clearOverlay() {
            overlayNode.innerHTML = "";
        }

        function renderOverlay(features) {
            clearOverlay();
            overlayFeatures = features.slice();
            // Keep overlay empty; heatmap should be rendered only by map layers.
        }

        function refreshOverlayPositions() {
            if (!overlayFeatures.length) return;
            renderOverlay(overlayFeatures);
        }

        function renderHeat(features) {
            if (!features.length) {
                showEmpty(true);
                if (map.getLayer(heatLayerId)) {
                    map.setLayoutProperty(heatLayerId, "visibility", "none");
                }
                if (map.getLayer(pointLayerId)) {
                    map.setLayoutProperty(pointLayerId, "visibility", "none");
                }
                if (map.getLayer(bairroPolyFillLayerId)) {
                    map.setLayoutProperty(bairroPolyFillLayerId, "visibility", "visible");
                }
                if (map.getLayer(bairroPolyLineLayerId)) {
                    map.setLayoutProperty(bairroPolyLineLayerId, "visibility", "visible");
                }
                clearOverlay();
                overlayFeatures = [];
                return;
            }

            showEmpty(false);
            renderOverlay(features);

            if (map.isStyleLoaded() && map.getSource(sourceId)) {
                map.getSource(sourceId).setData({
                    type: "FeatureCollection",
                    features,
                });
            }
            if (map.isStyleLoaded() && map.getSource(bairroSourceId)) {
                const bairroFeatures = bairrosCidade.length
                    ? bairrosCidade.map((row) => ({
                        type: "Feature",
                        geometry: {
                            type: "Point",
                            coordinates: [Number(row.lng), Number(row.lat)],
                        },
                        properties: {
                            bairro: String(row.bairro || "").trim(),
                        },
                    })).filter((feature) => Number.isFinite(feature.geometry.coordinates[0]) && Number.isFinite(feature.geometry.coordinates[1]) && feature.properties.bairro)
                    : buildBairroFeatures(features);
                map.getSource(bairroSourceId).setData({
                    type: "FeatureCollection",
                    features: bairroFeatures,
                });
            }

            if (map.getLayer(heatLayerId)) {
                map.setLayoutProperty(heatLayerId, "visibility", "none");
            }
            if (map.getLayer(pointLayerId)) {
                map.setLayoutProperty(pointLayerId, "visibility", "visible");
            }
            if (map.getLayer(bairroLayerId)) {
                map.setLayoutProperty(bairroLayerId, "visibility", "none");
            }
            if (map.getLayer(bairroPolyFillLayerId)) {
                map.setLayoutProperty(bairroPolyFillLayerId, "visibility", "visible");
            }
            if (map.getLayer(bairroPolyLineLayerId)) {
                map.setLayoutProperty(bairroPolyLineLayerId, "visibility", "visible");
            }
            map.easeTo({
                center: cityCenter,
                zoom: cityZoom,
                duration: 600,
                essential: true,
            });
        }

        async function fetchPoints(period) {
            const currentToken = ++requestToken;
            card.classList.add("is-loading");
            setActiveFilter(period);

            try {
                const response = await fetch(`${endpoint}?period=${encodeURIComponent(period)}`, {
                    headers: { Accept: "application/json" },
                    credentials: "same-origin",
                });
                if (!response.ok) throw new Error("heatmap-fetch-failed");
                const payload = await response.json();
                if (currentToken !== requestToken) return;
                const normalized = normalizeFeatures(payload);
                if (!normalized.length && period !== "all") {
                    fetchPoints("all");
                    return;
                }
                renderHeat(normalized);
            } catch (error) {
                if (currentToken !== requestToken) return;
                if (period !== "all") {
                    fetchPoints("all");
                } else {
                    renderHeat([]);
                }
            } finally {
                if (currentToken === requestToken) {
                    card.classList.remove("is-loading");
                }
            }
        }

        async function fetchBairrosCidade() {
            try {
                const response = await fetch(`${bairrosEndpoint}?refresh=1`, {
                    headers: { Accept: "application/json" },
                    credentials: "same-origin",
                });
                if (!response.ok) throw new Error("bairros-fetch-failed");
                const payload = await response.json();
                bairrosCidade = Array.isArray(payload) ? payload : [];
                if (!bairrosPolygonFeatures.length && bairrosCidade.length) {
                    applyBairroPolygonsToMap(buildFallbackBairroPolygons());
                }
                refreshOverlayPositions();
            } catch (error) {
                bairrosCidade = [];
            }
        }

        async function fetchBairrosPolygons() {
            try {
                const response = await fetch(`${bairrosPolygonsEndpoint}?refresh=1`, {
                    headers: { Accept: "application/json" },
                    credentials: "same-origin",
                });
                if (!response.ok) throw new Error("bairros-polygons-fetch-failed");
                const payload = await response.json();
                const rawFeatures = payload && payload.type === "FeatureCollection" && Array.isArray(payload.features)
                    ? payload.features
                    : [];
                const features = rawFeatures.length >= 5 ? rawFeatures : buildFallbackBairroPolygons();
                applyBairroPolygonsToMap(features);
            } catch (error) {
                applyBairroPolygonsToMap(buildFallbackBairroPolygons());
            }
        }

        filters.forEach((button) => {
            button.addEventListener("click", () => {
                const period = button.dataset.period || "all";
                fetchPoints(period);
            });
        });

        map.once("load", () => {
            applyMinimalStyle();
            ensureHeatmapSourceAndLayer();
            fetchBairrosCidade();
            fetchBairrosPolygons();
            fetchPoints("all");

            map.on("mousemove", bairroPolyFillLayerId, (event) => {
                const feature = event.features && event.features[0];
                const bairro = feature && feature.properties ? String(feature.properties.bairro || "").trim() : "";
                if (!bairro) {
                    if (bairroHoverPopup) bairroHoverPopup.remove();
                    bairroHoverPopup = null;
                    return;
                }
                map.getCanvas().style.cursor = "pointer";
                if (!bairroHoverPopup) {
                    bairroHoverPopup = new window.maplibregl.Popup({
                        closeButton: false,
                        closeOnClick: false,
                        offset: 10,
                    });
                }
                bairroHoverPopup
                    .setLngLat(event.lngLat)
                    .setHTML(`<strong>${bairro}</strong>`)
                    .addTo(map);
            });

            map.on("mouseleave", bairroPolyFillLayerId, () => {
                map.getCanvas().style.cursor = "";
                if (bairroHoverPopup) {
                    bairroHoverPopup.remove();
                    bairroHoverPopup = null;
                }
            });
        });

        map.on("move", refreshOverlayPositions);
        map.on("resize", refreshOverlayPositions);

        return {
            invalidate() {
                map.resize();
                refreshOverlayPositions();
            },
        };
    }

    let heatmapController = null;

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            renderCharts();
            heatmapController = initHeatmap();
        });
    } else {
        renderCharts();
        heatmapController = initHeatmap();
    }

    let resizeTimer = null;
    window.addEventListener("resize", () => {
        if (resizeTimer) window.clearTimeout(resizeTimer);
        resizeTimer = window.setTimeout(() => {
            renderCharts();
            if (heatmapController && typeof heatmapController.invalidate === "function") {
                heatmapController.invalidate();
            }
        }, 120);
    });
})();
