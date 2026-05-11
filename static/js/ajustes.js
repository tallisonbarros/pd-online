(function () {
    const config = window.PRATO_CONFIG || {};
    const reverseGeocodeUrl = String(config.reverseGeocodeUrl || "/api/address/reverse-geocode/").trim();
    const googleMapsApiKey = String(config.googleMapsApiKey || "").trim();
    const googleMapsLanguage = String(config.googleMapsLanguage || "pt-BR").trim() || "pt-BR";
    const googleMapsRegion = String(config.googleMapsRegion || "BR").trim() || "BR";
    const defaultCenter = { lat: -17.7923, lng: -50.9192 };

    let googleMapsLoadPromise = null;
    let googleMapsLoadedKey = "";
    let leafletAssetsPromise = null;

    function hasGoogleMapsProvider() {
        return Boolean(googleMapsApiKey);
    }

    function loadGoogleMapsRuntime(apiKey = googleMapsApiKey, language = googleMapsLanguage, region = googleMapsRegion, forceReload = false) {
        if (!apiKey) return Promise.reject(new Error("Google Maps não configurado."));

        if (!forceReload && window.google?.maps?.importLibrary && googleMapsLoadedKey === apiKey) {
            return Promise.resolve(window.google.maps);
        }
        if (!forceReload && googleMapsLoadPromise && googleMapsLoadedKey === apiKey) {
            return googleMapsLoadPromise;
        }

        if (forceReload) {
            const existingScript = document.querySelector("script[data-google-maps-js]");
            if (existingScript) existingScript.remove();
            googleMapsLoadPromise = null;
            googleMapsLoadedKey = "";
            if (window.google) {
                try {
                    delete window.google;
                } catch (error) {
                    window.google = undefined;
                }
            }
        }

        googleMapsLoadedKey = apiKey;
        googleMapsLoadPromise = new Promise((resolve, reject) => {
            const callbackName = `__pratoGoogleMapsReady${Date.now()}`;
            window[callbackName] = () => {
                resolve(window.google.maps);
                try {
                    delete window[callbackName];
                } catch (error) {
                    window[callbackName] = undefined;
                }
            };

            const existingScript = document.querySelector("script[data-google-maps-js]");
            if (existingScript) {
                existingScript.addEventListener("load", () => resolve(window.google.maps), { once: true });
                existingScript.addEventListener("error", () => reject(new Error("Falha ao carregar Google Maps.")), { once: true });
                return;
            }

            const params = new URLSearchParams({
                key: apiKey,
                loading: "async",
                callback: callbackName,
                language,
                region,
                v: "weekly",
            });
            const script = document.createElement("script");
            script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
            script.async = true;
            script.defer = true;
            script.setAttribute("data-google-maps-js", "true");
            script.onerror = () => reject(new Error("Falha ao carregar Google Maps."));
            document.body.appendChild(script);
        });

        return googleMapsLoadPromise;
    }

    function loadLeafletAssets() {
        if (window.L) return Promise.resolve(window.L);
        if (leafletAssetsPromise) return leafletAssetsPromise;

        leafletAssetsPromise = new Promise((resolve, reject) => {
            if (!document.querySelector("link[data-leaflet-css]")) {
                const css = document.createElement("link");
                css.rel = "stylesheet";
                css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
                css.setAttribute("data-leaflet-css", "true");
                document.head.appendChild(css);
            }

            const existingScript = document.querySelector("script[data-leaflet-js]");
            if (existingScript) {
                existingScript.addEventListener("load", () => resolve(window.L), { once: true });
                existingScript.addEventListener("error", () => reject(new Error("Falha ao carregar o mapa.")), { once: true });
                return;
            }

            const script = document.createElement("script");
            script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
            script.async = true;
            script.setAttribute("data-leaflet-js", "true");
            script.onload = () => resolve(window.L);
            script.onerror = () => reject(new Error("Falha ao carregar o mapa."));
            document.body.appendChild(script);
        });

        return leafletAssetsPromise;
    }

    async function reverseGeocode(lat, lng) {
        if (!reverseGeocodeUrl) return null;
        try {
            const response = await fetch(`${reverseGeocodeUrl}?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`, {
                method: "GET",
                headers: { Accept: "application/json" },
            });
            if (!response.ok) return null;
            const payload = await response.json();
            if (!payload?.ok) return null;
            return payload;
        } catch (error) {
            return null;
        }
    }

    function normalizeLabel(data) {
        return String(data?.label || data?.street || "Ponto confirmado no mapa").trim();
    }

    function normalizeSubtitle(data) {
        return [data?.district, data?.city || "Rio Verde", data?.state || "GO"].filter(Boolean).join(", ") || "Rio Verde, GO";
    }

    function initPinResolver(cfg) {
        const mapRoot = document.getElementById(cfg.mapId);
        const feedback = document.getElementById(cfg.feedbackId);
        const streetDisplay = document.getElementById(cfg.streetId);
        const districtDisplay = document.getElementById(cfg.districtId);
        const confirmButton = document.getElementById(cfg.confirmButtonId);
        const useLocationButton = document.getElementById(cfg.useLocationButtonId);
        const addressField = document.getElementById(cfg.addressFieldId);
        const latField = document.getElementById(cfg.latFieldId);
        const lngField = document.getElementById(cfg.lngFieldId);
        const labelField = cfg.labelFieldId ? document.getElementById(cfg.labelFieldId) : null;
        const typeField = cfg.typeFieldId ? document.getElementById(cfg.typeFieldId) : null;
        const precisionField = cfg.precisionFieldId ? document.getElementById(cfg.precisionFieldId) : null;
        const shouldSaveOnConfirm = confirmButton.dataset.saveOnConfirm === "true";

        if (!mapRoot || !feedback || !streetDisplay || !districtDisplay || !confirmButton || !useLocationButton || !addressField || !latField || !lngField) {
            return;
        }

        let mapInstance = null;
        let isProgrammaticMove = false;
        let previewData = null;
        let confirmedCenter = null;

        function setFeedback(message, warning = false) {
            feedback.textContent = message;
            feedback.classList.toggle("is-warning", Boolean(warning));
        }

        function writeHidden(data) {
            addressField.value = normalizeLabel(data);
            latField.value = Number(data.lat).toFixed(7);
            lngField.value = Number(data.lng).toFixed(7);
            if (labelField) labelField.value = normalizeLabel(data);
            if (typeField) typeField.value = String(data.type || "manual").trim();
            if (precisionField) precisionField.value = String(data.precision || "manual").trim();
        }

        function clearHidden() {
            addressField.value = "";
            latField.value = "";
            lngField.value = "";
            if (labelField) labelField.value = "";
            if (typeField) typeField.value = "";
            if (precisionField) precisionField.value = "";
            confirmedCenter = null;
        }

        function renderPreview(data) {
            previewData = data;
            streetDisplay.textContent = normalizeLabel(data);
            districtDisplay.textContent = normalizeSubtitle(data);
        }

        function fallbackPreview(center) {
            return {
                label: "Ponto confirmado no mapa",
                street: "Ponto confirmado no mapa",
                district: "",
                city: "Rio Verde",
                state: "GO",
                lat: Number(center.lat),
                lng: Number(center.lng),
                type: "manual",
                precision: "manual",
            };
        }

        async function reverseFromCenter(center) {
            const resolved = await reverseGeocode(center.lat, center.lng);
            return resolved || fallbackPreview(center);
        }

        function getCenter() {
            if (!mapInstance) return { ...defaultCenter };
            if (mapInstance.__provider === "google") {
                const center = mapInstance.getCenter();
                return { lat: center.lat(), lng: center.lng() };
            }
            const center = mapInstance.getCenter();
            return { lat: center.lat, lng: center.lng };
        }

        function hasCenterChanged(nextCenter) {
            if (!confirmedCenter) return true;
            const latDiff = Math.abs(Number(nextCenter.lat) - Number(confirmedCenter.lat));
            const lngDiff = Math.abs(Number(nextCenter.lng) - Number(confirmedCenter.lng));
            return latDiff > 0.00001 || lngDiff > 0.00001;
        }

        async function syncPreview({ commit = false } = {}) {
            const center = getCenter();
            const data = await reverseFromCenter(center);
            renderPreview(data);
            if (commit) {
                writeHidden(data);
                confirmedCenter = { lat: Number(center.lat), lng: Number(center.lng) };
                setFeedback("Ponto confirmado para este cálculo.", false);
                return;
            }
            if (!hasCenterChanged(center)) {
                setFeedback("Ponto confirmado e pronto para uso.", false);
                return;
            }
            clearHidden();
            setFeedback("Mova o mapa e confirme o ponto para usar este local.", false);
        }

        async function centerOnLocation() {
            if (!navigator.geolocation) {
                setFeedback("Seu navegador não permite usar localização nesta tela.", true);
                return;
            }
            useLocationButton.disabled = true;
            setFeedback("Buscando sua localização atual...", false);
            navigator.geolocation.getCurrentPosition(
                async (position) => {
                    const nextCenter = {
                        lat: position.coords.latitude,
                        lng: position.coords.longitude,
                    };
                    isProgrammaticMove = true;
                    if (mapInstance.__provider === "google") {
                        mapInstance.setCenter(nextCenter);
                        mapInstance.setZoom(Math.max(mapInstance.getZoom() || 16, 17));
                    } else {
                        mapInstance.setView(nextCenter, Math.max(mapInstance.getZoom() || 16, 17));
                    }
                    window.setTimeout(() => {
                        isProgrammaticMove = false;
                    }, 220);
                    await syncPreview({ commit: false });
                    useLocationButton.disabled = false;
                },
                () => {
                    useLocationButton.disabled = false;
                    setFeedback("Não foi possível acessar sua localização atual.", true);
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        }

        async function initGoogleMap(center) {
            await loadGoogleMapsRuntime();
            const { Map } = await google.maps.importLibrary("maps");
            mapInstance = new Map(mapRoot, {
                center,
                zoom: 16,
                mapTypeControl: false,
                streetViewControl: false,
                fullscreenControl: false,
                gestureHandling: "greedy",
            });
            mapInstance.__provider = "google";
            mapInstance.addListener("idle", async () => {
                if (isProgrammaticMove) return;
                await syncPreview({ commit: false });
            });
        }

        async function initLeafletMap(center) {
            const L = await loadLeafletAssets();
            mapInstance = L.map(mapRoot, {
                zoomControl: true,
                attributionControl: true,
            }).setView(center, 16);
            mapInstance.__provider = "leaflet";
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: "&copy; OpenStreetMap",
            }).addTo(mapInstance);
            mapInstance.on("moveend", async () => {
                if (isProgrammaticMove) return;
                await syncPreview({ commit: false });
            });
        }

        async function initMap() {
            const lat = Number(latField.value || "");
            const lng = Number(lngField.value || "");
            const initialCenter = Number.isFinite(lat) && Number.isFinite(lng)
                ? { lat, lng }
                : { ...defaultCenter };

            if (hasGoogleMapsProvider()) {
                try {
                    await initGoogleMap(initialCenter);
                } catch (error) {
                    await initLeafletMap(initialCenter);
                }
            } else {
                await initLeafletMap(initialCenter);
            }

            if (latField.value && lngField.value) {
                await syncPreview({ commit: true });
                } else {
                await syncPreview({ commit: false });
            }
        }

        confirmButton.addEventListener("click", async () => {
            confirmButton.disabled = true;
            await syncPreview({ commit: true });
            if (shouldSaveOnConfirm) {
                setFeedback("Salvando Origem Oficial...", false);
                const form = confirmButton.closest("form");
                if (form) {
                    form.querySelectorAll("input[data-auto-action]").forEach((input) => input.remove());
                    const actionInput = document.createElement("input");
                    actionInput.type = "hidden";
                    actionInput.name = "action";
                    actionInput.value = "save_frete";
                    actionInput.setAttribute("data-auto-action", "true");
                    form.appendChild(actionInput);
                    form.requestSubmit();
                    return;
                }
            }
            confirmButton.disabled = false;
        });

        useLocationButton.addEventListener("click", centerOnLocation);
        initMap();
    }

    initPinResolver({
        mapId: "ajustes-origem-map",
        feedbackId: "ajustes-origem-feedback",
        streetId: "ajustes-origem-street",
        districtId: "ajustes-origem-district",
        confirmButtonId: "ajustes-origem-confirm",
        useLocationButtonId: "ajustes-origem-use-location",
        addressFieldId: "ajustes-origem-endereco",
        latFieldId: "ajustes-origem-lat",
        lngFieldId: "ajustes-origem-lng",
        labelFieldId: "ajustes-origem-label-input",
        typeFieldId: "ajustes-origem-tipo-input",
        precisionFieldId: "ajustes-origem-precision-input",
    });

    initPinResolver({
        mapId: "ajustes-destino-map",
        feedbackId: "ajustes-destino-feedback",
        streetId: "ajustes-destino-street",
        districtId: "ajustes-destino-district",
        confirmButtonId: "ajustes-destino-confirm",
        useLocationButtonId: "ajustes-destino-use-location",
        addressFieldId: "ajustes-destino-teste",
        latFieldId: "ajustes-destino-lat",
        lngFieldId: "ajustes-destino-lng",
        labelFieldId: "ajustes-destino-label-input",
        typeFieldId: "ajustes-destino-tipo-input",
        precisionFieldId: "ajustes-destino-precision-input",
    });

    function setGoogleTestStatus(message, tone) {
        const status = document.getElementById("google-maps-test-status");
        if (!status) return;
        status.classList.remove("is-success", "is-error");
        if (tone) status.classList.add(tone);
        status.innerHTML = `<strong>Status do teste</strong><p>${message}</p>`;
    }

    async function initGoogleMapsTester() {
        const button = document.getElementById("google-maps-test-button");
        const apiKeyInput = document.getElementById("google-maps-api-key");
        const languageInput = document.getElementById("google-maps-language");
        const regionInput = document.getElementById("google-maps-region");
        const mapRoot = document.getElementById("google-maps-test-map");
        if (!button || !apiKeyInput || !languageInput || !regionInput || !mapRoot) return;

        let map = null;

        button.addEventListener("click", async () => {
            const apiKey = apiKeyInput.value.trim();
            const language = languageInput.value.trim() || "pt-BR";
            const region = regionInput.value.trim() || "BR";
            if (!apiKey) {
                setGoogleTestStatus("Informe a API key antes de testar.", "is-error");
                return;
            }

            button.disabled = true;
            setGoogleTestStatus("Carregando Google Maps e validando a chave...", "");
            try {
                await loadGoogleMapsRuntime(apiKey, language, region, true);
                const { Map } = await google.maps.importLibrary("maps");
                const { Geocoder } = await google.maps.importLibrary("geocoding");
                const geocoder = new Geocoder();
                const center = { ...defaultCenter };
                const response = await geocoder.geocode({ location: center, language });
                const result = response?.results?.[0];
                if (!result) {
                    throw new Error("O Google respondeu, mas não retornou endereco para o ponto de teste.");
                }

                mapRoot.classList.remove("hidden");
                if (!map) {
                    map = new Map(mapRoot, {
                        center,
                        zoom: 15,
                        mapTypeControl: false,
                        streetViewControl: false,
                        fullscreenControl: false,
                    });
                } else {
                    map.setCenter(center);
                    map.setZoom(15);
                }
                setGoogleTestStatus(`Chave válida. Endereço de teste resolvido: ${result.formatted_address}`, "is-success");
            } catch (error) {
                mapRoot.classList.add("hidden");
                setGoogleTestStatus(error.message || "Não foi possível validar a chave do Google Maps.", "is-error");
            } finally {
                button.disabled = false;
            }
        });
    }

    initGoogleMapsTester();
})();
