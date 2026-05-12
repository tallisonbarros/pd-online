(function () {
    const config = window.PRATO_CONFIG || {};
    const cartKey = config.cartKey || "prato_delivery_cart";
    const checkoutProfilesKey = `${cartKey}_checkout_profiles`;
    const legacyCheckoutProfileKey = `${cartKey}_checkout_profile`;
    const checkoutDraftKey = `${cartKey}_checkout_draft`;
    const checkoutPaymentKey = `${cartKey}_checkout_payment`;
    const checkoutCustomerNameKey = `${cartKey}_checkout_customer_name`;
    const placeholderImage = `${config.staticUrl || "/static/"}img/placeholder-prato.svg`;
    const checkoutLookup = (() => {
        const node = document.getElementById("checkout-pratos-lookup");
        if (!node) return {};
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return {};
        }
    })();
    const reverseGeocodeUrl = config.reverseGeocodeUrl || "/api/address/reverse-geocode/";
    const deliveryEtaUrl = config.deliveryEtaUrl || "/api/address/delivery-time/";
    const googleMapsApiKey = String(config.googleMapsApiKey || "").trim();
    const googleMapsLanguage = String(config.googleMapsLanguage || "pt-BR").trim() || "pt-BR";
    const googleMapsRegion = String(config.googleMapsRegion || "BR").trim() || "BR";
    let leafletAssetsPromise = null;
    let googleMapsAssetsPromise = null;

    function hasGoogleMapsProvider() {
        return Boolean(googleMapsApiKey);
    }

    function loadGoogleMapsAssets() {
        if (!hasGoogleMapsProvider()) {
            return Promise.reject(new Error("Google Maps não configurado."));
        }
        if (window.google?.maps?.importLibrary) {
            return Promise.resolve(window.google.maps);
        }
        if (googleMapsAssetsPromise) return googleMapsAssetsPromise;

        googleMapsAssetsPromise = new Promise((resolve, reject) => {
            window.__pratoGoogleMapsReady = () => resolve(window.google.maps);

            const existingScript = document.querySelector("script[data-google-maps-js]");
            if (existingScript) {
                existingScript.addEventListener("error", () => reject(new Error("Falha ao carregar Google Maps.")));
                return;
            }

            const script = document.createElement("script");
            const params = new URLSearchParams({
                key: googleMapsApiKey,
                loading: "async",
                callback: "__pratoGoogleMapsReady",
                language: googleMapsLanguage,
                region: googleMapsRegion,
                v: "weekly",
            });
            script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
            script.async = true;
            script.defer = true;
            script.setAttribute("data-google-maps-js", "true");
            script.onerror = () => reject(new Error("Falha ao carregar Google Maps."));
            document.body.appendChild(script);
        });

        return googleMapsAssetsPromise;
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
                existingScript.addEventListener("load", () => resolve(window.L));
                existingScript.addEventListener("error", reject);
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

    function parsePrice(value) {
        if (typeof value === "number") return Number.isFinite(value) ? value : 0;
        let normalized = String(value || "").replace(/\s/g, "").replace("R$", "");
        if (normalized.includes(",")) {
            normalized = normalized.replace(/\./g, "").replace(",", ".");
        }
        const parsed = Number(normalized);
        return Number.isFinite(parsed) ? parsed : 0;
    }

    function normalizeText(value) {
        return String(value || "")
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();
    }

    function money(value) {
        const amount = Number(value || 0);
        return amount.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    function showUiNotice(message, options = {}) {
        const modal = document.getElementById("checkout-notice-modal");
        const titleNode = document.getElementById("checkout-notice-title");
        const messageNode = document.getElementById("checkout-notice-message");
        const dismissButton = modal?.querySelector(".notice-modal-actions [data-notice-close]");
        const cancelButton = modal?.querySelector("[data-notice-cancel]");
        const confirmButton = modal?.querySelector("[data-notice-confirm]");
        if (!modal || !titleNode || !messageNode) {
            alert(String(message || ""));
            return;
        }

        if (!modal.dataset.bound) {
            const close = () => {
                modal.classList.add("hidden");
                modal.setAttribute("aria-hidden", "true");
                document.body.classList.remove("modal-open");
                modal.__noticeConfirm = null;
            };

            modal.querySelectorAll("[data-notice-close]").forEach((button) => {
                button.addEventListener("click", close);
            });
            modal.querySelector("[data-notice-cancel]")?.addEventListener("click", close);
            modal.querySelector("[data-notice-confirm]")?.addEventListener("click", () => {
                const onConfirm = modal.__noticeConfirm;
                close();
                if (typeof onConfirm === "function") onConfirm();
            });

            modal.addEventListener("click", (event) => {
                if (event.target === modal) close();
            });

            document.addEventListener("keydown", (event) => {
                if (event.key === "Escape" && !modal.classList.contains("hidden")) {
                    close();
                }
            });

            modal.dataset.bound = "true";
        }

        titleNode.textContent = String(options.title || "Atencao");
        const messageLines = Array.isArray(options.messageLines) ? options.messageLines : [message];
        messageNode.innerHTML = "";
        messageLines.filter((line) => String(line || "").trim()).forEach((line) => {
            const paragraph = document.createElement("span");
            paragraph.textContent = String(line);
            messageNode.appendChild(paragraph);
        });
        modal.__noticeConfirm = typeof options.onConfirm === "function" ? options.onConfirm : null;
        const isConfirm = Boolean(modal.__noticeConfirm);
        if (cancelButton) cancelButton.textContent = String(options.cancelLabel || "Cancelar");
        if (confirmButton) confirmButton.textContent = String(options.confirmLabel || "Continuar");
        if (dismissButton) dismissButton.textContent = String(options.dismissLabel || "Entendi");
        dismissButton?.classList.toggle("hidden", isConfirm);
        cancelButton?.classList.toggle("hidden", !isConfirm);
        confirmButton?.classList.toggle("hidden", !isConfirm);
        modal.classList.remove("hidden");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
        setTimeout(() => (isConfirm ? confirmButton : dismissButton)?.focus(), 20);
    }

    function ensureCartDockStructure(cartDock) {
        if (!cartDock) return null;
        const summary = cartDock.querySelector("[data-cart-dock-summary]");
        const count = cartDock.querySelector("[data-cart-dock-count]");
        const icon = cartDock.querySelector(".cart-dock-icon");
        const copy = cartDock.querySelector(".cart-dock-copy");

        if (summary && count && icon && copy) {
            return { summary, count };
        }

        cartDock.innerHTML = `
            <span class="cart-dock-icon" aria-hidden="true">
                <svg class="cart-icon" viewBox="0 0 24 24">
                    <path d="M3 4h2.2a1 1 0 0 1 .97.758L6.6 6.5H20a1 1 0 0 1 .97 1.242l-1.5 6A1 1 0 0 1 18.5 14H8.1a1 1 0 0 1-.97-.757L5.1 5.5H3a1 1 0 1 1 0-2Z"></path>
                    <path d="M9 19.5a1.5 1.5 0 1 0 0 .01ZM17 19.5a1.5 1.5 0 1 0 0 .01Z"></path>
                </svg>
            </span>
            <span class="cart-dock-copy">
                <strong data-cart-dock-summary>0 itens no carrinho</strong>
                <small>Toque para finalizar</small>
            </span>
            <span class="cart-dock-badge" data-cart-dock-count>0</span>
        `;

        return {
            summary: cartDock.querySelector("[data-cart-dock-summary]"),
            count: cartDock.querySelector("[data-cart-dock-count]"),
        };
    }

    function escapeHtml(value) {
        return String(value || "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function cartItemType(item) {
        return String(item?.tipo || (item?.adicional_id ? "adicional" : item?.bebida_id ? "bebida" : "prato")).trim() || "prato";
    }

    function cartItemId(item) {
        return item?.item_id || item?.adicional_id || item?.bebida_id || item?.prato_id || item?.id;
    }

    function cartItemKey(item) {
        return `${cartItemType(item)}:${cartItemId(item)}`;
    }

    function normalizeCatalogCartFields(item) {
        const tipo = cartItemType(item);
        const itemId = cartItemId(item);
        return {
            ...item,
            tipo,
            item_id: itemId,
            prato_id: tipo === "prato" ? itemId : undefined,
            adicional_id: tipo === "adicional" ? itemId : undefined,
            bebida_id: tipo === "bebida" ? itemId : undefined,
        };
    }

    function enrichCartItem(item) {
        const normalizedItem = normalizeCatalogCartFields(item);
        const lookupItem =
            checkoutLookup[cartItemKey(normalizedItem)] ||
            checkoutLookup[String(normalizedItem.prato_id)] ||
            {};
        return {
            ...normalizedItem,
            nome: String(normalizedItem.nome || lookupItem.nome || "Item"),
            preco: parsePrice(normalizedItem.preco || lookupItem.preco),
            quantidade: Math.max(1, Number(normalizedItem.quantidade || 1)),
            observacao: String(normalizedItem.observacao || "").trim(),
            imagem: String(normalizedItem.imagem || lookupItem.imagem || placeholderImage),
        };
    }

    function mergeSimpleDuplicates(cart) {
        const merged = [];
        for (const item of cart) {
            if (item.observacao) {
                merged.push(item);
                continue;
            }
            const existing = merged.find((entry) => cartItemKey(entry) === cartItemKey(item) && !entry.observacao);
            if (existing) {
                existing.quantidade = Number(existing.quantidade || 0) + Number(item.quantidade || 0);
            } else {
                merged.push({ ...item, quantidade: Number(item.quantidade || 1) });
            }
        }
        return merged;
    }

    function normalizeCart(cart) {
        if (!Array.isArray(cart)) return [];
        return mergeSimpleDuplicates(cart.map(enrichCartItem));
    }

    function getCart() {
        try {
            return normalizeCart(JSON.parse(localStorage.getItem(cartKey) || "[]"));
        } catch (error) {
            return [];
        }
    }

    function saveCart(cart) {
        localStorage.setItem(cartKey, JSON.stringify(normalizeCart(cart)));
        syncCartCount();
    }

    function getCheckoutDraft() {
        try {
            const parsed = JSON.parse(localStorage.getItem(checkoutDraftKey) || "{}");
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (error) {
            return {};
        }
    }

    function saveCheckoutDraft(draft) {
        try {
            const nome = String(draft?.nome || "").trim();
            if (nome) {
                localStorage.setItem(checkoutCustomerNameKey, nome);
            }
            localStorage.setItem(
                checkoutDraftKey,
                JSON.stringify({
                    nome,
                    observacao_geral: String(draft?.observacao_geral || "").trim(),
                    enviar_talheres: draft?.enviar_talheres === "nao" ? "nao" : "sim",
                })
            );
        } catch (error) {
            // Ignora falha de storage.
        }
    }

    function getCheckoutCustomerName() {
        try {
            return String(localStorage.getItem(checkoutCustomerNameKey) || "").trim();
        } catch (error) {
            return "";
        }
    }

    function getCheckoutPaymentPreference() {
        try {
            const parsed = JSON.parse(localStorage.getItem(checkoutPaymentKey) || "{}");
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (error) {
            return {};
        }
    }

    function saveCheckoutPaymentPreference(preference) {
        try {
            const type = String(preference?.type || "").trim();
            const method = String(preference?.method || "").trim();
            if (!type && !method) {
                localStorage.removeItem(checkoutPaymentKey);
                return;
            }
            localStorage.setItem(checkoutPaymentKey, JSON.stringify({ type, method }));
        } catch (error) {
            // Ignora falha de storage.
        }
    }

    function syncCartCount() {
        const count = getCart().reduce((total, item) => total + Number(item.quantidade || 0), 0);
        document.querySelectorAll("[data-cart-count]").forEach((element) => {
            element.textContent = count;
        });

        const cartDock = document.querySelector("[data-cart-dock]");
        if (cartDock) {
            const cartDockRefs = ensureCartDockStructure(cartDock);
            const cartDockSummary = cartDockRefs?.summary;
            const cartDockCount = cartDockRefs?.count;
            const cartDockWrap = cartDock.closest(".cart-dock-wrap");
            const previousCount = Number(cartDock.dataset.cartCount || "0");
            const hydrated = cartDock.dataset.hydrated === "true";
            cartDock.dataset.cartCount = String(count);
            cartDock.dataset.hydrated = "true";
            cartDock.classList.toggle("is-visible", count > 0);
            cartDockWrap?.classList.toggle("is-visible", count > 0);

            if (cartDockSummary) {
                cartDockSummary.textContent = count === 1 ? "1 item no carrinho" : `${count} itens no carrinho`;
            }

            if (cartDockCount) {
                cartDockCount.textContent = count;
            }

            if (hydrated && count > previousCount) {
                cartDock.classList.remove("is-bump");
                void cartDock.offsetWidth;
                cartDock.classList.add("is-bump");
                if (cartDock._bumpTimer) {
                    clearTimeout(cartDock._bumpTimer);
                }
                cartDock._bumpTimer = window.setTimeout(() => {
                    cartDock.classList.remove("is-bump");
                }, 360);
            }
        }
    }

    function buildCheckoutProfileId(profile) {
        const key = [
            profile.rua || profile.endereco_formatado,
            profile.numero,
            profile.bairro,
            profile.cidade,
            profile.estado,
        ]
            .map((part) => normalizeText(part))
            .join("|");
        const slug = key
            .replace(/\|/g, "-")
            .replace(/[^a-z0-9-]/g, "")
            .replace(/-+/g, "-")
            .replace(/^-|-$/g, "")
            .slice(0, 120);
        return slug || `endereco-${Date.now()}`;
    }

    function sanitizeCheckoutProfile(profile) {
        if (!profile || typeof profile !== "object") return null;
        const clean = {
            id: String(profile.id || "").trim(),
            rua: String(profile.rua || "").trim(),
            numero: String(profile.numero || "").trim(),
            bairro: String(profile.bairro || "").trim(),
            lote_quadra: String(profile.lote_quadra || "").trim(),
            complemento: String(profile.complemento || "").trim(),
            ponto_referencia: String(profile.ponto_referencia || "").trim(),
            cidade: String(profile.cidade || "Rio Verde").trim(),
            estado: String(profile.estado || "GO").trim(),
            latitude: String(profile.latitude || "").trim(),
            longitude: String(profile.longitude || "").trim(),
            endereco_formatado: String(profile.endereco_formatado || "").trim(),
            geocode_tipo: String(profile.geocode_tipo || "").trim(),
            geocode_precision: String(profile.geocode_precision || "").trim(),
        };
        if (!clean.id) clean.id = buildCheckoutProfileId(clean);
        const hasCoordinates = Boolean(clean.latitude && clean.longitude);
        const hasAddress = Boolean(clean.rua || clean.endereco_formatado);
        if (!clean.numero || !hasCoordinates || !hasAddress) return null;
        return clean;
    }

    function normalizeCheckoutProfiles(profiles) {
        if (!Array.isArray(profiles)) return [];
        const seen = new Set();
        const normalized = [];
        for (const rawProfile of profiles) {
            const profile = sanitizeCheckoutProfile(rawProfile);
            if (!profile || seen.has(profile.id)) continue;
            seen.add(profile.id);
            normalized.push(profile);
        }
        return normalized;
    }

    function getSavedCheckoutProfiles() {
        try {
            const rawProfiles = localStorage.getItem(checkoutProfilesKey);
            const parsedProfiles = rawProfiles ? JSON.parse(rawProfiles) : null;
            const profiles = normalizeCheckoutProfiles(parsedProfiles);
            if (profiles.length) return profiles;

            const legacyRaw = localStorage.getItem(legacyCheckoutProfileKey);
            if (!legacyRaw) return [];
            const legacyParsed = JSON.parse(legacyRaw);
            const migrated = normalizeCheckoutProfiles([legacyParsed]);
            if (migrated.length) {
                localStorage.setItem(checkoutProfilesKey, JSON.stringify(migrated));
                localStorage.removeItem(legacyCheckoutProfileKey);
            }
            return migrated;
        } catch (error) {
            return [];
        }
    }

    function saveCheckoutProfiles(profiles) {
        try {
            const normalized = normalizeCheckoutProfiles(profiles);
            if (!normalized.length) {
                localStorage.removeItem(checkoutProfilesKey);
                localStorage.removeItem(legacyCheckoutProfileKey);
                return;
            }
            localStorage.setItem(checkoutProfilesKey, JSON.stringify(normalized));
            localStorage.removeItem(legacyCheckoutProfileKey);
        } catch (error) {
            // Ignora falha de storage.
        }
    }

    function upsertCheckoutProfile(profile) {
        const sanitized = sanitizeCheckoutProfile(profile);
        if (!sanitized) return null;
        const nextProfiles = getSavedCheckoutProfiles().filter((item) => item.id !== sanitized.id);
        saveCheckoutProfiles([sanitized, ...nextProfiles]);
        return sanitized;
    }

    function deleteCheckoutProfile(profileId) {
        const normalizedId = String(profileId || "").trim();
        if (!normalizedId) return;
        saveCheckoutProfiles(getSavedCheckoutProfiles().filter((profile) => profile.id !== normalizedId));
    }

    function buildCartItemMarkup(item, index) {
        const noteMarkup = item.observacao
            ? `<div class="checkout-item-note-wrap"><p class="checkout-item-note">Obs: ${escapeHtml(item.observacao)}</p></div>`
            : "";
        return `
            <article class="checkout-item">
                <div class="checkout-item-main">
                    <div class="checkout-item-media">
                        <img src="${escapeHtml(item.imagem || placeholderImage)}" alt="${escapeHtml(item.nome)}" loading="lazy" decoding="async">
                    </div>
                    <div class="checkout-item-body">
                        <div class="checkout-item-top">
                            <div>
                                <strong class="checkout-item-title">${escapeHtml(item.nome)}</strong>
                            </div>
                            <strong class="checkout-item-price">${money(parsePrice(item.preco) * Number(item.quantidade))}</strong>
                        </div>
                        <div class="checkout-item-bottom">
                            <div class="checkout-item-qty-control" aria-label="Controle de quantidade">
                                <button type="button" class="qty-btn" data-qty-change="${index}" data-delta="-1" aria-label="Diminuir quantidade">-</button>
                                <strong class="qty-value">${item.quantidade}</strong>
                                <button type="button" class="qty-btn" data-qty-change="${index}" data-delta="1" aria-label="Aumentar quantidade">+</button>
                            </div>
                            <div class="checkout-item-actions">
                                <button type="button" class="icon-button" data-remove-item="${index}" aria-label="Remover item">
                                    <svg viewBox="0 0 24 24" aria-hidden="true">
                                        <path d="M9 3.75h6a1.25 1.25 0 0 1 1.25 1.25V6H20a1 1 0 1 1 0 2h-1l-.72 10.1A2 2 0 0 1 16.28 20H7.72a2 2 0 0 1-1.99-1.9L5 8H4a1 1 0 1 1 0-2h3.75V5A1.25 1.25 0 0 1 9 3.75Zm1.25 2.25h3.5V5.75h-3.5V6Zm-.5 4.25a1 1 0 0 1 1 1V16a1 1 0 1 1-2 0v-4.75a1 1 0 0 1 1-1Zm4.5 0a1 1 0 0 1 1 1V16a1 1 0 1 1-2 0v-4.75a1 1 0 0 1 1-1Z"></path>
                                    </svg>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
                ${noteMarkup}
            </article>
        `;
    }

    function resolutionTone(precision) {
        const normalized = normalizeText(precision);
        if (normalized === "exact" || normalized === "exato") return { label: "Confirmado", tone: "is-exact" };
        if (normalized === "approximate" || normalized === "aproximado") return { label: "Aproximado", tone: "is-approximate" };
        if (normalized === "manual") return { label: "Manual", tone: "is-manual" };
        return { label: "A confirmar", tone: "is-pending" };
    }

    function buildProfileDestinationText(profile) {
        if (String(profile.endereco_formatado || "").trim()) return String(profile.endereco_formatado).trim();
        return [profile.rua, profile.numero, profile.bairro, profile.cidade || "Rio Verde", profile.estado || "GO"]
            .filter(Boolean)
            .join(", ");
    }

    function initCardapioPage() {
        const revealItems = document.querySelectorAll("[data-page='cardapio'] .reveal-on-scroll");
        const featureCard = document.querySelector("[data-page='cardapio'] .menu-feature-card-wrap .dish-card");
        const featureMarquee = document.querySelector("[data-page='cardapio'] .menu-feature-marquee");

        function syncFeatureMarqueeWidth() {
            if (!featureCard || !featureMarquee) return;
            const cardWidth = featureCard.getBoundingClientRect().width;
            if (cardWidth > 0) {
                featureMarquee.style.setProperty("--marquee-width", `${Math.ceil(cardWidth)}px`);
            }
        }

        syncFeatureMarqueeWidth();
        window.addEventListener("resize", syncFeatureMarqueeWidth);
        if ("ResizeObserver" in window && featureCard) {
            new ResizeObserver(syncFeatureMarqueeWidth).observe(featureCard);
        }

        if (revealItems.length) {
            if (!("IntersectionObserver" in window)) {
                revealItems.forEach((item) => item.classList.add("is-visible"));
            } else {
                const revealObserver = new IntersectionObserver((entries) => {
                    entries.forEach((entry) => {
                        if (!entry.isIntersecting) return;
                        entry.target.classList.add("is-visible");
                        revealObserver.unobserve(entry.target);
                    });
                }, { rootMargin: "0px 0px -8% 0px", threshold: 0.14 });

                revealItems.forEach((item, index) => {
                    item.style.setProperty("--reveal-order", String(index % 6));
                    revealObserver.observe(item);
                });
            }
        }

        const modal = document.getElementById("pedido-modal");
        if (!modal) return;

        const image = document.getElementById("modal-prato-imagem");
        const name = document.getElementById("modal-prato-nome");
        const description = document.getElementById("modal-prato-descricao");
        const price = document.getElementById("modal-prato-preco");
        const obs = document.getElementById("modal-observacao");
        const quantityDisplay = document.getElementById("modal-quantidade");
        const addButton = document.getElementById("modal-add-cart");

        let currentDish = null;
        let quantity = 1;

        function addDishToCart(incomingItem) {
            const normalizedIncomingItem = enrichCartItem(incomingItem);
            const cart = getCart();
            if (!incomingItem.observacao) {
                const existing = cart.find((entry) => cartItemKey(entry) === cartItemKey(normalizedIncomingItem) && !entry.observacao);
                if (existing) {
                    existing.quantidade = Number(existing.quantidade || 0) + Number(normalizedIncomingItem.quantidade || 0);
                } else {
                    cart.push(normalizedIncomingItem);
                }
            } else {
                cart.push(normalizedIncomingItem);
            }
            saveCart(cart);
        }

        function buildCardCartItem(dish, quantityToAdd = 1) {
            const dishType = dish.tipo || "prato";
            return {
                tipo: dishType,
                item_id: dish.id,
                prato_id: dishType === "prato" ? dish.id : undefined,
                adicional_id: dishType === "adicional" ? dish.id : undefined,
                bebida_id: dishType === "bebida" ? dish.id : undefined,
                nome: dish.nome,
                preco: parsePrice(dish.preco),
                quantidade: Math.max(1, Number(quantityToAdd || 1)),
                observacao: "",
                imagem: dish.imagem || placeholderImage,
            };
        }

        function getCartQuantityForDish(dish) {
            const key = cartItemKey(normalizeCatalogCartFields(dish));
            return getCart()
                .filter((item) => cartItemKey(item) === key)
                .reduce((total, item) => total + Number(item.quantidade || 0), 0);
        }

        function syncCardQuantityBadges() {
            document.querySelectorAll("[data-prato-card]").forEach((card) => {
                const qtyValue = card.querySelector("[data-card-qty-value]");
                if (!qtyValue) return;
                const dish = JSON.parse(card.dataset.prato || "{}");
                qtyValue.textContent = String(getCartQuantityForDish(dish));
            });
        }

        function incrementCardCartItem(dish, delta) {
            const normalizedDish = normalizeCatalogCartFields(dish);
            const key = cartItemKey(normalizedDish);
            const cart = getCart();

            if (delta > 0) {
                addDishToCart(buildCardCartItem(dish, delta));
                syncCardQuantityBadges();
                return true;
            }

            const simpleIndex = cart.findIndex((item) => cartItemKey(item) === key && !item.observacao);
            let fallbackIndex = -1;
            for (let index = cart.length - 1; index >= 0; index -= 1) {
                if (cartItemKey(cart[index]) === key) {
                    fallbackIndex = index;
                    break;
                }
            }
            const index = simpleIndex >= 0 ? simpleIndex : fallbackIndex;
            if (index < 0) return false;

            const nextQuantity = Number(cart[index].quantidade || 0) - 1;
            if (nextQuantity > 0) {
                cart[index].quantidade = nextQuantity;
            } else {
                cart.splice(index, 1);
            }
            saveCart(cart);
            syncCardQuantityBadges();
            return true;
        }

        function animateQuantityNumber(trigger, delta, changed = true) {
            const badge = trigger?.closest(".dish-qty-badge");
            const value = badge?.querySelector("[data-card-qty-value]");
            if (!badge || !value) return;

            const directionClass = delta > 0 ? "is-qty-increasing" : "is-qty-decreasing";
            const idleClass = changed ? "" : "is-qty-unchanged";

            if (value._qtyAnimationTimer) {
                clearTimeout(value._qtyAnimationTimer);
            }

            value.classList.remove("is-qty-increasing", "is-qty-decreasing", "is-qty-unchanged");
            badge.classList.remove("is-qty-active");
            void value.offsetWidth;
            badge.classList.add("is-qty-active");
            value.classList.add(directionClass);
            if (idleClass) value.classList.add(idleClass);

            value._qtyAnimationTimer = window.setTimeout(() => {
                value.classList.remove("is-qty-increasing", "is-qty-decreasing", "is-qty-unchanged");
                badge.classList.remove("is-qty-active");
            }, 360);
        }

        function animateInlineQuantityNumber(value, delta) {
            if (!value) return;
            const directionClass = delta > 0 ? "is-qty-increasing" : "is-qty-decreasing";
            if (value._qtyAnimationTimer) {
                clearTimeout(value._qtyAnimationTimer);
            }
            value.classList.remove("is-qty-increasing", "is-qty-decreasing");
            void value.offsetWidth;
            value.classList.add(directionClass);
            value._qtyAnimationTimer = window.setTimeout(() => {
                value.classList.remove("is-qty-increasing", "is-qty-decreasing");
            }, 360);
        }

        function animateAddFeedback(button, quantityAdded) {
            if (button) {
                if (button._confirmTimer) {
                    clearTimeout(button._confirmTimer);
                }
                button.classList.remove("is-confirming");
                void button.offsetWidth;
                button.classList.add("is-confirming");
                button._confirmTimer = window.setTimeout(() => {
                    button.classList.remove("is-confirming");
                }, 950);
            }

            const cartChip = document.querySelector("[data-cart-anchor]") || document.querySelector(".cart-chip");
            if (!button || !cartChip) return;

            const sourceRect = button.getBoundingClientRect();
            const targetRect = cartChip.getBoundingClientRect();
            const startX = sourceRect.left + sourceRect.width / 2;
            const startY = sourceRect.top + sourceRect.height / 2;
            const targetX = targetRect.left + targetRect.width / 2;
            const targetY = targetRect.top + targetRect.height / 2;

            const flyChip = document.createElement("span");
            flyChip.className = "cart-fly-chip";
            flyChip.textContent = `+${Math.max(1, Number(quantityAdded || 1))}`;
            flyChip.style.left = `${startX}px`;
            flyChip.style.top = `${startY}px`;
            flyChip.style.setProperty("--fly-x", `${targetX - startX}px`);
            flyChip.style.setProperty("--fly-y", `${targetY - startY}px`);
            document.body.appendChild(flyChip);

            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    flyChip.classList.add("is-flying");
                });
            });

            window.setTimeout(() => {
                flyChip.remove();
            }, 760);
        }

        function openModal(dish) {
            currentDish = dish;
            quantity = 1;
            quantityDisplay.textContent = "1";
            obs.value = "";
            image.src = dish.imagem;
            image.alt = dish.nome;
            name.textContent = dish.nome;
            description.textContent = dish.descricao || "";
            price.textContent = dish.preco_formatado || "Preço sob consulta";
            modal.classList.remove("hidden");
            modal.setAttribute("aria-hidden", "false");
        }

        function closeModal() {
            modal.classList.add("hidden");
            modal.setAttribute("aria-hidden", "true");
        }

        modal.addEventListener("click", function (event) {
            if (event.target === modal || event.target.hasAttribute("data-close-modal")) {
                closeModal();
            }
        });

        document.querySelector("[data-qty-minus]")?.addEventListener("click", function () {
            const previousQuantity = quantity;
            quantity = Math.max(1, quantity - 1);
            quantityDisplay.textContent = String(quantity);
            animateInlineQuantityNumber(quantityDisplay, quantity < previousQuantity ? -1 : 0);
        });

        document.querySelector("[data-qty-plus]")?.addEventListener("click", function () {
            quantity += 1;
            quantityDisplay.textContent = String(quantity);
            animateInlineQuantityNumber(quantityDisplay, 1);
        });

        addButton.addEventListener("click", function () {
            if (!currentDish) return;
            const currentType = currentDish.tipo || "prato";
            const incomingItem = {
                tipo: currentType,
                item_id: currentDish.id,
                prato_id: currentType === "prato" ? currentDish.id : undefined,
                adicional_id: currentType === "adicional" ? currentDish.id : undefined,
                bebida_id: currentType === "bebida" ? currentDish.id : undefined,
                nome: currentDish.nome,
                preco: parsePrice(currentDish.preco),
                quantidade: quantity,
                observacao: obs.value.trim(),
                imagem: currentDish.imagem || placeholderImage,
            };
            addDishToCart(incomingItem);
            animateAddFeedback(addButton, incomingItem.quantidade);
            syncCardQuantityBadges();
            closeModal();
        });

        document.querySelectorAll("[data-prato-card]").forEach((card) => {
            const qtyValue = card.querySelector("[data-card-qty-value]");
            const dish = JSON.parse(card.dataset.prato || "{}");
            if (!qtyValue || !dish.id) return;

            card.addEventListener("click", (event) => {
                if (event.target.closest("button, a, input, textarea, select, [data-card-qty-change]")) return;
                openModal(dish);
            });

            card.querySelectorAll("[data-card-qty-change]").forEach((button) => {
                button.addEventListener("click", (event) => {
                    event.preventDefault();
                    const delta = Number(button.getAttribute("data-card-qty-change"));
                    const changed = incrementCardCartItem(dish, delta);
                    animateQuantityNumber(button, delta, changed);
                    if (changed && delta > 0) animateAddFeedback(button, delta);
                });
            });

        });

        syncCardQuantityBadges();

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape") closeModal();
        });
    }

    function hasCheckoutDeliveryData(form) {
        const read = (name) => String(form.querySelector(`[name='${name}']`)?.value || "").trim();
        return Boolean(
            read("numero") &&
                read("latitude") &&
                read("longitude") &&
                (read("rua") || read("endereco_formatado"))
        );
    }

    function getMissingCheckoutDeliveryField(form) {
        const read = (name) => String(form.querySelector(`[name='${name}']`)?.value || "").trim();
        if (!read("numero")) return "endereco";
        if (!read("latitude") || !read("longitude") || !(read("rua") || read("endereco_formatado"))) return "endereco";
        return "";
    }

    function persistCheckoutProfileFromForm(form) {
        const read = (name) => String(form.querySelector(`[name='${name}']`)?.value || "").trim();
        upsertCheckoutProfile({
            rua: read("rua"),
            numero: read("numero"),
            bairro: read("bairro"),
            lote_quadra: read("lote_quadra"),
            complemento: read("complemento"),
            ponto_referencia: read("ponto_referencia"),
            cidade: read("cidade"),
            estado: read("estado"),
            latitude: read("latitude"),
            longitude: read("longitude"),
            endereco_formatado: read("endereco_formatado"),
            geocode_tipo: read("geocode_tipo"),
            geocode_precision: read("geocode_precision"),
        });
    }

    function initSavedCheckoutProfiles(form, profileForm, addressController, onShippingUpdate) {
        const container = document.getElementById("profile-editor-modal");
        const listNode = document.getElementById("saved-checkout-profiles-list");
        const createButtonNode = document.getElementById("saved-profile-create");
        const openButton = document.getElementById("saved-profile-open");
        const summaryCard = document.getElementById("checkout-address-summary");
        const summaryLabel = document.getElementById("checkout-address-summary-label");
        const summaryMeta = document.getElementById("checkout-address-summary-meta");
        const editorModal = document.getElementById("profile-editor-modal");
        const selectorPanel = document.getElementById("profile-selector-panel");
        const editorPanel = document.getElementById("profile-editor-panel");
        if (!openButton || !editorModal || !selectorPanel || !editorPanel || !profileForm) return;
        const list = listNode || { innerHTML: "", addEventListener() {} };
        const createButton = createButtonNode || { addEventListener() {} };

        const editorCloseButtons = editorModal.querySelectorAll("[data-profile-editor-close]");
        const readEditor = (name) => String(profileForm.querySelector(`[name='${name}']`)?.value || "").trim();
        const setEditor = (name, value) => {
            const field = profileForm.querySelector(`[name='${name}']`);
            if (field) field.value = String(value || "");
        };
        const setCheckout = (name, value) => {
            const field = form.querySelector(`[name='${name}']`);
            if (field) field.value = String(value || "");
        };

        const checkoutFields = [
            "rua",
            "numero",
            "bairro",
            "lote_quadra",
            "complemento",
            "ponto_referencia",
            "cidade",
            "estado",
            "latitude",
            "longitude",
            "endereco_formatado",
            "geocode_tipo",
            "geocode_precision",
        ];

        let selectedProfileId = "";
        let openMenuProfileId = "";
        let editingProfileId = "";
        const deliveryCache = new Map();
        const etaPending = new Set();

        function buildEtaKey(profile) {
            return [
                profile.id,
                profile.latitude,
                profile.longitude,
                profile.rua,
                profile.numero,
                profile.bairro,
                profile.endereco_formatado,
            ].join("|");
        }

        function getCachedDelivery(profile) {
            return deliveryCache.get(buildEtaKey(profile)) || null;
        }

        function renderEtaContent(profile) {
            const key = buildEtaKey(profile);
            const cached = getCachedDelivery(profile);
            if (cached && Number.isFinite(cached.etaMinutes)) {
                return `<span class="saved-profile-eta-value">${cached.etaMinutes}<small>min</small></span>`;
            }
            if (etaPending.has(key)) {
                return `<span class="saved-profile-eta-value is-loading">...</span>`;
            }
            return `<span class="saved-profile-eta-value">--</span>`;
        }

        function buildProfileTitle(profile) {
            return [profile.rua || profile.endereco_formatado || "Endereço salvo", profile.numero].filter(Boolean).join(", ");
        }

        function buildProfileSubtitle(profile) {
            return [profile.bairro, profile.lote_quadra, profile.complemento || profile.ponto_referencia, profile.cidade || "Rio Verde"]
                .filter(Boolean)
                .slice(0, 3)
                .join("  ");
        }

        function renderSummary(profile) {
            if (!summaryCard) return;
            if (!profile) {
                summaryCard.classList.add("hidden");
                return;
            }

            const cached = getCachedDelivery(profile) || {};
            const tone = resolutionTone(cached.destinationPrecision || profile.geocode_precision);
            summaryCard.classList.remove("hidden", "is-exact", "is-approximate", "is-manual", "is-pending");
            summaryCard.classList.add(tone.tone);
            summaryLabel.textContent = cached.destinationLabel || buildProfileDestinationText(profile);
            summaryMeta.textContent = cached.error === "origin_not_configured"
                ? "Origem oficial não configurada"
                : Number.isFinite(cached.distanceKm)
                ? `Distância ${cached.distanceKm.toFixed(2)} km`
                : "Distância --";
        }

        function pushShipping(profile) {
            if (typeof onShippingUpdate !== "function") return;
            const cached = profile ? getCachedDelivery(profile) : null;
            if (!cached) {
                onShippingUpdate(null);
                return;
            }
            onShippingUpdate({
                shippingFee: cached.shippingFee,
                distanceKm: cached.distanceKm,
                etaMinutes: cached.etaMinutes,
                error: cached.error,
            });
        }

        async function fetchProfileEta(profile) {
            const key = buildEtaKey(profile);
            if (deliveryCache.has(key) || etaPending.has(key)) return;
            etaPending.add(key);

            const params = new URLSearchParams({
                lat: String(profile.latitude || ""),
                lng: String(profile.longitude || ""),
                resolved_label: String(profile.endereco_formatado || ""),
                resolved_type: String(profile.geocode_tipo || ""),
                resolved_precision: String(profile.geocode_precision || ""),
                rua: String(profile.rua || ""),
                numero: String(profile.numero || ""),
                bairro: String(profile.bairro || ""),
                cidade: String(profile.cidade || "Rio Verde"),
                estado: String(profile.estado || "GO"),
            });

            let deliveryData = {
                etaMinutes: null,
                shippingFee: null,
                distanceKm: null,
                destinationLabel: buildProfileDestinationText(profile),
                destinationType: String(profile.geocode_tipo || ""),
                destinationPrecision: String(profile.geocode_precision || ""),
                destinationLat: profile.latitude || null,
                destinationLng: profile.longitude || null,
                error: null,
            };

            try {
                const response = await fetch(`${deliveryEtaUrl}?${params.toString()}`, {
                    method: "GET",
                    headers: { Accept: "application/json" },
                });
                if (response.ok) {
                    const payload = await response.json();
                    if (payload?.ok) {
                        const etaMinutes = Number(payload.eta_minutes);
                        const shippingFee = Number(payload.shipping_fee);
                        const distanceKm = Number(payload.distance_km);
                        deliveryData = {
                            etaMinutes: Number.isFinite(etaMinutes) ? Math.max(1, Math.round(etaMinutes)) : null,
                            shippingFee: Number.isFinite(shippingFee) ? shippingFee : null,
                            distanceKm: Number.isFinite(distanceKm) ? distanceKm : null,
                            destinationLabel: String(payload.destination_label || deliveryData.destinationLabel || "").trim(),
                            destinationType: String(payload.destination_type || deliveryData.destinationType || "").trim(),
                            destinationPrecision: String(payload.destination_precision || deliveryData.destinationPrecision || "").trim(),
                            destinationLat: Number.isFinite(Number(payload.destination_lat)) ? Number(payload.destination_lat) : deliveryData.destinationLat,
                            destinationLng: Number.isFinite(Number(payload.destination_lng)) ? Number(payload.destination_lng) : deliveryData.destinationLng,
                        };
                    } else if (payload?.error) {
                        deliveryData.error = String(payload.error || "").trim();
                    }
                }
            } catch (error) {
                // Mantem fallback local.
            }

            deliveryCache.set(key, deliveryData);
            etaPending.delete(key);

            if (selectedProfileId === profile.id) {
                if (deliveryData.destinationLabel) setCheckout("endereco_formatado", deliveryData.destinationLabel);
                if (deliveryData.destinationType) setCheckout("geocode_tipo", deliveryData.destinationType);
                if (deliveryData.destinationPrecision) setCheckout("geocode_precision", deliveryData.destinationPrecision);
                if (deliveryData.destinationLat != null) setCheckout("latitude", deliveryData.destinationLat);
                if (deliveryData.destinationLng != null) setCheckout("longitude", deliveryData.destinationLng);
                renderSummary(profile);
                pushShipping(profile);
            }

            renderProfiles();
        }

        function clearSelection() {
            checkoutFields.forEach((fieldName) => {
                const fallback = fieldName === "cidade" ? "Rio Verde" : fieldName === "estado" ? "GO" : "";
                setCheckout(fieldName, fallback);
            });
            selectedProfileId = "";
            pushShipping(null);
            renderSummary(null);
        }

        function applyProfile(profile) {
            if (!profile) return;
            checkoutFields.forEach((fieldName) => {
                const fallback = fieldName === "cidade" ? "Rio Verde" : fieldName === "estado" ? "GO" : "";
                setCheckout(fieldName, profile[fieldName] || fallback);
            });
            selectedProfileId = profile.id;
            renderSummary(profile);
            pushShipping(profile);
            fetchProfileEta(profile);
        }

        function fillEditor(profile) {
            setEditor("rua", profile?.rua || "");
            setEditor("bairro", profile?.bairro || "");
            setEditor("numero", profile?.numero || "");
            setEditor("lote_quadra", profile?.lote_quadra || "");
            setEditor("complemento", profile?.complemento || "");
            setEditor("ponto_referencia", profile?.ponto_referencia || "");
            setEditor("cidade", profile?.cidade || "Rio Verde");
            setEditor("estado", profile?.estado || "GO");
            setEditor("latitude", profile?.latitude || "");
            setEditor("longitude", profile?.longitude || "");
            setEditor("endereco_formatado", profile?.endereco_formatado || "");
            setEditor("geocode_tipo", profile?.geocode_tipo || "");
            setEditor("geocode_precision", profile?.geocode_precision || "");

            if (addressController) {
                if (profile?.latitude && profile?.longitude) {
                    addressController.applyResolvedAddress({
                        label: profile.endereco_formatado,
                        street: profile.rua,
                        district: profile.bairro,
                        city: profile.cidade,
                        state: profile.estado,
                        lat: profile.latitude,
                        lng: profile.longitude,
                        type: profile.geocode_tipo,
                        precision: profile.geocode_precision,
                    }, { confirmed: false });
                } else {
                    addressController.clearResolvedAddress();
                }
            }
        }

        function openModal() {
            editorModal.classList.remove("hidden");
            editorModal.setAttribute("aria-hidden", "false");
            document.body.classList.add("modal-open");
        }

        function closeModal() {
            editorModal.classList.add("hidden");
            editorModal.setAttribute("aria-hidden", "true");
            document.body.classList.remove("modal-open");
        }

        function showSelectorPanel() {
            selectorPanel.classList.remove("hidden");
            editorPanel.classList.add("hidden");
        }

        function showEditorPanel() {
            selectorPanel.classList.add("hidden");
            editorPanel.classList.remove("hidden");
        }

        function openSelector() {
            openModal();
            renderProfiles();
            showSelectorPanel();
        }

        function openEditor(mode, profile) {
            editingProfileId = mode === "edit" ? String(profile?.id || "") : "";
            fillEditor(profile || null);
            openModal();
            showEditorPanel();
            addressController?.refreshMap?.();
            if (mode === "create") {
                addressController?.startCurrentLocation?.();
            } else {
                profileForm.querySelector("[name='numero']")?.focus();
            }
        }

        function openSelectedProfileEditor() {
            if (!selectedProfileId) return;
            const profile = getSavedCheckoutProfiles().find((item) => item.id === selectedProfileId);
            if (!profile) return;
            openMenuProfileId = "";
            openEditor("edit", profile);
        }

        function closeEditor() {
            editorPanel.classList.add("hidden");
            editingProfileId = "";
        }

        function readProfileFromEditor() {
            return {
                id: editingProfileId || "",
                rua: readEditor("rua"),
                numero: readEditor("numero"),
                bairro: readEditor("bairro"),
                lote_quadra: readEditor("lote_quadra"),
                complemento: readEditor("complemento"),
                ponto_referencia: readEditor("ponto_referencia"),
                cidade: readEditor("cidade") || "Rio Verde",
                estado: readEditor("estado") || "GO",
                latitude: readEditor("latitude"),
                longitude: readEditor("longitude"),
                endereco_formatado: readEditor("endereco_formatado"),
                geocode_tipo: readEditor("geocode_tipo"),
                geocode_precision: readEditor("geocode_precision"),
            };
        }

        function renderProfiles() {
            const profiles = getSavedCheckoutProfiles();
            if (!profiles.length) {
                clearSelection();
                openButton.textContent = "Cadastrar novo endereço";
                openButton.classList.remove("saved-profile-create--compact");
                list.innerHTML = `
                    <div class="saved-profile-empty">
                        <strong>Nenhum endereco salvo ainda.</strong>
                        <small>Cadastre um novo endereco para usar no checkout.</small>
                    </div>
                `;
                return;
            }

            openButton.textContent = "Meus endereços";
            openButton.classList.add("saved-profile-create--compact");
            if (!profiles.some((profile) => profile.id === selectedProfileId)) {
                selectedProfileId = "";
            }
            if (!selectedProfileId) {
                applyProfile(profiles[0]);
            }

            list.innerHTML = profiles
                .map((profile) => {
                    const isSelected = selectedProfileId === profile.id ? "is-selected" : "";
                    const isMenuOpen = openMenuProfileId === profile.id;
                    return `
                        <article class="saved-profile-entry ${isSelected}" data-profile-id="${escapeHtml(profile.id)}">
                            <button type="button" class="saved-profile-button" data-profile-action="apply" data-profile-id="${escapeHtml(profile.id)}">
                                <span class="saved-profile-meta">
                                    <span class="saved-profile-eta">${renderEtaContent(profile)}</span>
                                    <span class="saved-profile-text">
                                        <strong>${escapeHtml(buildProfileTitle(profile))}</strong>
                                        <small>${escapeHtml(buildProfileSubtitle(profile) || "Toque para usar este endereco")}</small>
                                    </span>
                                </span>
                            </button>
                            <div class="saved-profile-menu">
                                <button
                                    type="button"
                                    class="saved-profile-menu-toggle"
                                    data-profile-action="toggle-menu"
                                    data-profile-id="${escapeHtml(profile.id)}"
                                    aria-haspopup="menu"
                                    aria-expanded="${isMenuOpen ? "true" : "false"}"
                                    aria-label="Acoes do endereco salvo"
                                >

                                </button>
                                <div class="saved-profile-menu-list ${isMenuOpen ? "" : "hidden"}" role="menu">
                                    <button type="button" class="saved-profile-menu-item" role="menuitem" data-profile-action="edit" data-profile-id="${escapeHtml(profile.id)}">
                                        Editar
                                    </button>
                                    <button type="button" class="saved-profile-menu-item is-danger" role="menuitem" data-profile-action="delete" data-profile-id="${escapeHtml(profile.id)}">
                                        Excluir
                                    </button>
                                </div>
                            </div>
                        </article>
                    `;
                })
                .join("");

            profiles.forEach((profile) => fetchProfileEta(profile));
        }

        createButton.addEventListener("click", () => {
            openMenuProfileId = "";
            openEditor("create", null);
        });

        openButton.addEventListener("click", () => {
            openMenuProfileId = "";
            if (getSavedCheckoutProfiles().length) {
                openSelector();
                return;
            }
            openEditor("create", null);
        });

        summaryCard?.addEventListener("click", openSelectedProfileEditor);
        summaryCard?.addEventListener("keydown", (event) => {
            if (event.key !== "Enter" && event.key !== " ") return;
            event.preventDefault();
            openSelectedProfileEditor();
        });

        list.addEventListener("click", (event) => {
            const actionNode = event.target.closest("[data-profile-action]");
            if (!actionNode) return;
            const action = actionNode.getAttribute("data-profile-action");
            const profileId = actionNode.getAttribute("data-profile-id");
            const profile = getSavedCheckoutProfiles().find((item) => item.id === profileId);
            if (!action || !profileId) return;

            if (action === "toggle-menu") {
                event.preventDefault();
                event.stopPropagation();
                openMenuProfileId = openMenuProfileId === profileId ? "" : profileId;
                renderProfiles();
                return;
            }

            if (action === "apply") {
                applyProfile(profile);
                openMenuProfileId = "";
                renderProfiles();
                closeModal();
                return;
            }

            if (action === "edit") {
                openMenuProfileId = "";
                renderProfiles();
                openEditor("edit", profile);
                return;
            }

            if (action === "delete") {
                deleteCheckoutProfile(profileId);
                if (selectedProfileId === profileId) selectedProfileId = "";
                openMenuProfileId = "";
                renderProfiles();
            }
        });

        profileForm.addEventListener("submit", (event) => {
            event.preventDefault();
            const saved = upsertCheckoutProfile(readProfileFromEditor());
            if (!saved) {
                showUiNotice("Confirme um ponto no mapa e informe o número para salvar o endereço.");
                return;
            }
            applyProfile(saved);
            openMenuProfileId = "";
            renderProfiles();
            closeEditor();
            closeModal();
        });

        editorCloseButtons.forEach((button) => {
            button.addEventListener("click", () => {
                closeEditor();
                closeModal();
            });
        });

        document.addEventListener("click", (event) => {
            if (openMenuProfileId && !container.contains(event.target)) {
                openMenuProfileId = "";
                renderProfiles();
            }
        });

        editorModal.addEventListener("click", (event) => {
            if (event.target === editorModal) {
                closeEditor();
                closeModal();
            }
        });

        document.addEventListener("keydown", (event) => {
            if (event.key !== "Escape") return;
            if (openMenuProfileId) {
                openMenuProfileId = "";
                renderProfiles();
            }
            if (!editorModal.classList.contains("hidden")) {
                closeEditor();
                closeModal();
            }
        });

        renderProfiles();
    }

    function initAddressEditor(form) {
        const noopApi = {
            applyResolvedAddress() {},
            clearResolvedAddress() {},
            refreshMap() {},
        };

        const ruaInput = form.querySelector("input[name='rua']");
        const bairroInput = form.querySelector("input[name='bairro']");
        const cidadeInput = form.querySelector("input[name='cidade']");
        const estadoInput = form.querySelector("input[name='estado']");
        const latitudeInput = form.querySelector("input[name='latitude']");
        const longitudeInput = form.querySelector("input[name='longitude']");
        const enderecoFormatadoInput = form.querySelector("input[name='endereco_formatado']");
        const geocodeTipoInput = form.querySelector("input[name='geocode_tipo']");
        const geocodePrecisionInput = form.querySelector("input[name='geocode_precision']");
        const feedback = document.getElementById("address-feedback");
        const coordsWarning = document.getElementById("coords-warning");
        const resolutionCard = document.getElementById("address-resolution-card");
        const resolutionBadge = document.getElementById("address-resolution-badge");
        const resolutionLabel = document.getElementById("address-resolution-label");
        const resolutionMeta = document.getElementById("address-resolution-meta");
        const resolvedStreetDisplay = document.getElementById("resolved-street-display");
        const resolvedDistrictDisplay = document.getElementById("resolved-district-display");
        const mapStep = document.getElementById("address-step-map");
        const detailsStep = document.getElementById("address-step-details");
        const detailsStepMarker = document.getElementById("address-step-marker-details");
        const backToMapButton = document.getElementById("address-step-back-to-map");
        const previewMapRoot = document.getElementById("address-preview-map");
        const previewTitle = document.getElementById("address-preview-title");
        const previewSubtitle = document.getElementById("address-preview-subtitle");
        const mapRoot = document.getElementById("address-map");
        const mapShell = mapRoot?.closest(".address-map-shell");
        const mapFeedback = document.getElementById("address-map-feedback");
        const useLocationButton = document.getElementById("use-current-location");
        const confirmMapCenterButton = document.getElementById("confirm-map-center");

        if (
            !ruaInput ||
            !bairroInput ||
            !cidadeInput ||
            !estadoInput ||
            !latitudeInput ||
            !longitudeInput ||
            !enderecoFormatadoInput ||
            !geocodeTipoInput ||
            !geocodePrecisionInput ||
            !feedback ||
            !coordsWarning ||
            !resolvedStreetDisplay ||
            !resolvedDistrictDisplay ||
            !mapStep ||
            !detailsStep ||
            !detailsStepMarker ||
            !backToMapButton ||
            !previewMapRoot ||
            !previewTitle ||
            !previewSubtitle ||
            !mapRoot ||
            !mapFeedback ||
            !useLocationButton ||
            !confirmMapCenterButton
        ) {
            return noopApi;
        }

        let reverseController = null;
        let shouldShowCoordsWarning = false;
        let mapInstance = null;
        let previewMapInstance = null;
        let isProgrammaticMapMove = false;
        let googleGeocoder = null;
        let currentProvider = hasGoogleMapsProvider() ? "google" : "openstreetmap";
        let addressPointConfirmed = false;
        let isRequestingCurrentLocation = false;

        function showFeedback(message, warning = false) {
            feedback.textContent = message;
            feedback.classList.toggle("hidden", !message);
            feedback.classList.toggle("is-warning", warning);
        }

        function showMapFeedback(message, warning = false) {
            mapFeedback.textContent = message;
            mapFeedback.classList.toggle("is-warning", warning);
        }

        function setCurrentLocationLoadingState(isLoading) {
            isRequestingCurrentLocation = isLoading;
            useLocationButton.disabled = isLoading;
            useLocationButton.textContent = isLoading ? "Carregando..." : "Usar minha localização";
            mapShell?.classList.toggle("is-locating", isLoading);
        }

        function syncCoordsWarning() {
            const hasCoords = Boolean(latitudeInput.value && longitudeInput.value);
            coordsWarning.classList.toggle("hidden", hasCoords || !shouldShowCoordsWarning);
        }

        function updateResolvedDisplay(data) {
            resolvedStreetDisplay.textContent = data?.street || data?.label || "Confirme um ponto no mapa";
            resolvedDistrictDisplay.textContent = data?.district || "Aguardando confirmação";
            previewTitle.textContent = data?.street || data?.label || "Rua aguardando confirmação";
            previewSubtitle.textContent = [data?.district, data?.city || "Rio Verde", data?.state || "GO"].filter(Boolean).join(", ") || "Setor, cidade e estado aparecerão aqui.";
        }

        function renderResolutionState(data) {
            if (!resolutionCard || !resolutionBadge || !resolutionLabel || !resolutionMeta) {
                return;
            }
            const tone = resolutionTone(data?.precision);
            resolutionCard.classList.remove("hidden", "is-exact", "is-approximate", "is-manual", "is-pending");
            resolutionCard.classList.add(tone.tone);
            resolutionBadge.className = `address-resolution-badge ${tone.tone}`;
            resolutionBadge.textContent = tone.label;
            resolutionLabel.textContent = data?.label || "Ajuste o mapa e confirme o local da entrega.";
            if (data?.lat && data?.lng) {
                resolutionMeta.textContent = `${Number(data.lat).toFixed(6)}, ${Number(data.lng).toFixed(6)}${data?.type ? ` | ${data.type}` : ""}`;
            } else {
                resolutionMeta.textContent = "Sem coordenadas confirmadas ainda.";
            }
        }

        function setMapCenter(lat, lng, zoom = 18) {
            if (!mapInstance || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return;
            isProgrammaticMapMove = true;
            mapInstance.setCenter(Number(lat), Number(lng), zoom);
        }

        function setPreviewMapCenter(lat, lng, zoom = 17) {
            if (!previewMapInstance || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lng))) return;
            previewMapInstance.setCenter(Number(lat), Number(lng), zoom);
        }

        function refreshPreviewMap() {
            if (!previewMapInstance) return;
            if (previewMapInstance.provider === "google") {
                const center = previewMapInstance.map?.getCenter?.();
                if (window.google?.maps && previewMapInstance.map) {
                    google.maps.event.trigger(previewMapInstance.map, "resize");
                    if (center) previewMapInstance.map.setCenter(center);
                }
                return;
            }
            previewMapInstance.map?.invalidateSize?.();
        }

        function showDetailsStep(show) {
            mapStep.classList.toggle("hidden", !!show);
            detailsStep.classList.toggle("hidden", !show);
            detailsStepMarker.classList.toggle("is-ready", !!show);
            detailsStepMarker.classList.toggle("is-active", !show);
            if (show) {
                setTimeout(refreshPreviewMap, 60);
            }
        }

        function applyResolvedAddress(data, options = {}) {
            const payload = data || {};
            ruaInput.value = String(payload.street || payload.label || "").trim();
            bairroInput.value = String(payload.district || "").trim();
            cidadeInput.value = String(payload.city || cidadeInput.value || "Rio Verde").trim();
            estadoInput.value = String(payload.state || estadoInput.value || "GO").trim();
            latitudeInput.value = payload?.lat ?? "";
            longitudeInput.value = payload?.lng ?? "";
            enderecoFormatadoInput.value = payload?.label ?? "";
            geocodeTipoInput.value = payload?.type ?? "";
            geocodePrecisionInput.value = payload?.precision ?? "";
            shouldShowCoordsWarning = true;
            updateResolvedDisplay(payload);
            renderResolutionState(payload);
            syncCoordsWarning();
            if (options.confirmed === true) {
                addressPointConfirmed = Boolean(payload?.lat && payload?.lng);
            } else if (options.confirmed === false) {
                addressPointConfirmed = false;
            }
            showDetailsStep(Boolean(payload?.lat && payload?.lng) && addressPointConfirmed);
            if (payload?.lat && payload?.lng && options.updateMap !== false) {
                setMapCenter(payload.lat, payload.lng, payload.precision === "exact" ? 18 : 17);
            }
            if (payload?.lat && payload?.lng) {
                setPreviewMapCenter(payload.lat, payload.lng, payload.precision === "exact" ? 17 : 16);
            }
        }

        function clearResolvedAddress(options = {}) {
            ruaInput.value = "";
            bairroInput.value = "";
            latitudeInput.value = "";
            longitudeInput.value = "";
            enderecoFormatadoInput.value = "";
            geocodeTipoInput.value = "";
            geocodePrecisionInput.value = "";
            shouldShowCoordsWarning = true;
            addressPointConfirmed = false;
            updateResolvedDisplay(null);
            renderResolutionState(null);
            syncCoordsWarning();
            showDetailsStep(false);
            if (!options.keepFeedback) showFeedback("", false);
            if (!options.keepMapFeedback) showMapFeedback("Mova o mapa até o pin central ficar no local exato da entrega.");
        }

        function getGoogleComponent(components, type, field = "long_name") {
            const match = Array.isArray(components)
                ? components.find((component) => Array.isArray(component.types) && component.types.includes(type))
                : null;
            return String(match?.[field] || "").trim();
        }

        function resolveGooglePrecision(types) {
            const normalized = Array.isArray(types) ? types : [];
            if (normalized.includes("street_address") || normalized.includes("premise") || normalized.includes("subpremise")) {
                return "exact";
            }
            if (normalized.includes("route") || normalized.includes("intersection") || normalized.includes("plus_code")) {
                return "approximate";
            }
            return "manual";
        }

        function mapGoogleResult(result, lat, lng) {
            if (!result) return null;
            const components = result.address_components || [];
            const street = getGoogleComponent(components, "route") || result.formatted_address || "";
            const district =
                getGoogleComponent(components, "sublocality_level_1") ||
                getGoogleComponent(components, "sublocality") ||
                getGoogleComponent(components, "neighborhood") ||
                getGoogleComponent(components, "administrative_area_level_3");
            const city =
                getGoogleComponent(components, "locality") ||
                getGoogleComponent(components, "administrative_area_level_2") ||
                "Rio Verde";
            const state = getGoogleComponent(components, "administrative_area_level_1", "short_name") || "GO";
            const primaryType = Array.isArray(result.types) && result.types.length ? result.types[0] : "google";

            return {
                label: result.formatted_address || street || "Ponto confirmado no mapa",
                street,
                district,
                city,
                state,
                lat: Number(lat),
                lng: Number(lng),
                type: primaryType,
                precision: resolveGooglePrecision(result.types),
            };
        }

        async function reverseGeocodeWithGoogle(lat, lng) {
            if (!googleGeocoder) return null;
            try {
                const response = await googleGeocoder.geocode({
                    location: { lat: Number(lat), lng: Number(lng) },
                    language: googleMapsLanguage,
                });
                const result = response?.results?.[0];
                return result ? mapGoogleResult(result, lat, lng) : null;
            } catch (error) {
                return null;
            }
        }

        async function reverseGeocodeWithFallback(lat, lng) {
            if (reverseController) reverseController.abort();
            reverseController = new AbortController();
            try {
                const response = await fetch(`${reverseGeocodeUrl}?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`, {
                    method: "GET",
                    headers: { Accept: "application/json" },
                    signal: reverseController.signal,
                });
                if (!response.ok) return null;
                const payload = await response.json();
                return payload?.ok ? payload : null;
            } catch (error) {
                if (error.name === "AbortError") return null;
                return null;
            }
        }

        async function reverseGeocodeCenter(lat, lng) {
            showMapFeedback("Atualizando endereco pelo centro do mapa...");
            if (currentProvider === "google") {
                const googleResult = await reverseGeocodeWithGoogle(lat, lng);
                if (googleResult) return googleResult;
            }
            return reverseGeocodeWithFallback(lat, lng);
        }

        async function syncAddressFromMapCenter(options = {}) {
            const confirmed = options.confirmed === true;
            if (!mapInstance) return;
            const center = mapInstance.getCenter();
            const resolved = await reverseGeocodeCenter(center.lat, center.lng);
            if (!resolved) {
                applyResolvedAddress(
                    {
                        label: enderecoFormatadoInput.value || ruaInput.value || "Ponto confirmado no mapa",
                        street: ruaInput.value || "Ponto confirmado no mapa",
                        district: bairroInput.value || "",
                        city: cidadeInput.value || "Rio Verde",
                        state: estadoInput.value || "GO",
                        lat: center.lat.toFixed(7),
                        lng: center.lng.toFixed(7),
                        type: "manual",
                        precision: "manual",
                    },
                    { updateMap: false, confirmed }
                );
                showMapFeedback(
                    confirmed
                        ? "Ponto confirmado manualmente. O texto do endereco pode ficar aproximado."
                        : "",
                    confirmed
                );
                return;
            }

            applyResolvedAddress(
                {
                    ...resolved,
                    lat: center.lat,
                    lng: center.lng,
                    type: resolved.type || "manual",
                    precision: resolved.precision || "manual",
                },
                { updateMap: false, confirmed }
            );
            showMapFeedback(confirmed ? "Local confirmado pelo centro do mapa." : "");
        }

        async function initializeMap() {
            if (hasGoogleMapsProvider()) {
                try {
                    await loadGoogleMapsAssets();
                    const { Map } = await google.maps.importLibrary("maps");
                    const { Geocoder } = await google.maps.importLibrary("geocoding");

                    const googleMap = new Map(mapRoot, {
                        center: { lat: -17.7923, lng: -50.9192 },
                        zoom: 14,
                        mapTypeControl: false,
                        streetViewControl: false,
                        fullscreenControl: false,
                        clickableIcons: false,
                    });
                    googleGeocoder = new Geocoder();
                    currentProvider = "google";

                    mapInstance = {
                        provider: "google",
                        setCenter(lat, lng, zoom = 18) {
                            googleMap.setCenter({ lat: Number(lat), lng: Number(lng) });
                            googleMap.setZoom(zoom);
                        },
                        getCenter() {
                            const center = googleMap.getCenter();
                            return {
                                lat: center ? center.lat() : -17.7923,
                                lng: center ? center.lng() : -50.9192,
                            };
                        },
                        invalidateSize() {
                            const center = googleMap.getCenter();
                            google.maps.event.trigger(googleMap, "resize");
                            if (center) googleMap.setCenter(center);
                        },
                    };

                    previewMapInstance = {
                        provider: "google",
                        map: new Map(previewMapRoot, {
                            center: { lat: -17.7923, lng: -50.9192 },
                            zoom: 15,
                            disableDefaultUI: true,
                            gestureHandling: "none",
                            clickableIcons: false,
                            keyboardShortcuts: false,
                        }),
                        setCenter(lat, lng, zoom = 17) {
                            this.map.setCenter({ lat: Number(lat), lng: Number(lng) });
                            this.map.setZoom(zoom);
                        },
                    };

                    googleMap.addListener("idle", async () => {
                        if (isProgrammaticMapMove) {
                            isProgrammaticMapMove = false;
                            return;
                        }
                        await syncAddressFromMapCenter({ confirmed: false });
                    });

                    showMapFeedback("Google Maps pronto. Mova o mapa até o pin central ficar no local exato da entrega.");
                    return;
                } catch (error) {
                    currentProvider = "openstreetmap";
                    showMapFeedback("Google Maps indisponível no momento. Usando mapa alternativo.", true);
                }
            }

            try {
                const L = await loadLeafletAssets();
                if (!L || mapInstance) return;

                const leafletMap = L.map(mapRoot, {
                    center: [-17.7923, -50.9192],
                    zoom: 14,
                    zoomControl: true,
                    attributionControl: true,
                });
                L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 19,
                    attribution: "&copy; OpenStreetMap",
                }).addTo(leafletMap);

                mapInstance = {
                    provider: "openstreetmap",
                    setCenter(lat, lng, zoom = 18) {
                        leafletMap.setView([Number(lat), Number(lng)], zoom, { animate: false });
                    },
                    getCenter() {
                        const center = leafletMap.getCenter();
                        return { lat: center.lat, lng: center.lng };
                    },
                    invalidateSize() {
                        leafletMap.invalidateSize();
                    },
                };

                const leafletPreviewMap = L.map(previewMapRoot, {
                    center: [-17.7923, -50.9192],
                    zoom: 15,
                    zoomControl: false,
                    attributionControl: false,
                    dragging: false,
                    touchZoom: false,
                    doubleClickZoom: false,
                    scrollWheelZoom: false,
                    boxZoom: false,
                    keyboard: false,
                });
                L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                    maxZoom: 19,
                    attribution: "&copy; OpenStreetMap",
                }).addTo(leafletPreviewMap);
                previewMapInstance = {
                    provider: "openstreetmap",
                    map: leafletPreviewMap,
                    setCenter(lat, lng, zoom = 17) {
                        leafletPreviewMap.setView([Number(lat), Number(lng)], zoom, { animate: false });
                    },
                };

                leafletMap.on("moveend", async () => {
                    if (isProgrammaticMapMove) {
                        isProgrammaticMapMove = false;
                        return;
                    }
                    await syncAddressFromMapCenter({ confirmed: false });
                });

                setTimeout(() => mapInstance.invalidateSize(), 60);
                showMapFeedback("Mova o mapa até o pin central ficar no local exato da entrega.");
            } catch (error) {
                showMapFeedback("Não foi possível carregar o mapa neste momento.", true);
            }
        }

        function requestCurrentLocation() {
            if (isRequestingCurrentLocation) return;
            if (!navigator.geolocation) {
                showMapFeedback("Seu navegador não permite usar localização.", true);
                return;
            }
            setCurrentLocationLoadingState(true);
            showMapFeedback("Carregando sua localização...");
            navigator.geolocation.getCurrentPosition(
                async (position) => {
                    setMapCenter(position.coords.latitude, position.coords.longitude, 18);
                    await syncAddressFromMapCenter({ confirmed: false });
                    setCurrentLocationLoadingState(false);
                },
                () => {
                    setCurrentLocationLoadingState(false);
                    showMapFeedback("Não foi possível acessar sua localização atual.", true);
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        }

        useLocationButton.addEventListener("click", () => {
            requestCurrentLocation();
        });

        confirmMapCenterButton.addEventListener("click", async () => {
            await syncAddressFromMapCenter({ confirmed: true });
        });

        backToMapButton.addEventListener("click", () => {
            addressPointConfirmed = false;
            showDetailsStep(false);
            showMapFeedback("Ajuste o ponto no mapa e confirme novamente.");
            setTimeout(() => mapRoot.scrollIntoView({ behavior: "smooth", block: "center" }), 40);
        });

        form.addEventListener("submit", () => {
            shouldShowCoordsWarning = true;
            syncCoordsWarning();
        });

        const mapReadyPromise = initializeMap().then(() => {
            if (latitudeInput.value && longitudeInput.value) {
                setMapCenter(latitudeInput.value, longitudeInput.value, 18);
                setPreviewMapCenter(latitudeInput.value, longitudeInput.value, 17);
                showMapFeedback("Local carregado a partir das coordenadas salvas.");
                addressPointConfirmed = false;
                showDetailsStep(false);
            }
        });

        updateResolvedDisplay(null);
        renderResolutionState(null);
        syncCoordsWarning();
        showDetailsStep(false);
        return {
            applyResolvedAddress,
            clearResolvedAddress,
            refreshMap() {
                if (!mapInstance) return;
                setTimeout(() => mapInstance.invalidateSize(), 60);
            },
            async startCurrentLocation() {
                await mapReadyPromise;
                requestCurrentLocation();
            },
        };
    }

    function initCheckoutPage() {
        const itemsContainer = document.getElementById("checkout-items");
        const itemsSubtotalElement = document.getElementById("checkout-items-subtotal");
        const totalReviewElement = document.getElementById("checkout-total-review");
        const shippingReviewElement = document.getElementById("checkout-shipping-review");
        const totalReviewPaymentElement = document.getElementById("checkout-total-review-payment");
        const shippingReviewPaymentElement = document.getElementById("checkout-shipping-review-payment");
        const heroTitleElement = document.getElementById("checkout-hero-title");
        const heroSubtitleElement = document.getElementById("checkout-hero-subtitle");
        const heroEtaElement = document.getElementById("checkout-hero-eta");
        const shippingValueInput = document.getElementById("checkout-shipping-value");
        const distanceInput = document.getElementById("checkout-distance-km");
        const paymentMethodInput = document.getElementById("checkout-payment-method");
        const checkoutNamePayloadInput = document.getElementById("checkout-nome-payload");
        const orderNoteInput = document.getElementById("checkout-order-note");
        const orderNotePayloadInput = document.getElementById("checkout-order-note-payload");
        const talheresToggleInput = document.getElementById("checkout-talheres-toggle");
        const talheresPayloadInput = document.getElementById("checkout-talheres-payload");
        const payloadInput = document.getElementById("carrinho-payload");
        const form = document.getElementById("checkout-form");
        const profileForm = document.getElementById("profile-form");
        const stageDelivery = document.getElementById("checkout-stage-delivery");
        const deliveryFields = document.getElementById("checkout-delivery-fields");
        const stagePayment = document.getElementById("checkout-stage-payment");
        const paymentDeliveryOptions = document.getElementById("payment-delivery-options");
        const paymentPixPanel = document.getElementById("payment-pix-panel");
        const checkoutNameInput = document.getElementById("checkout-nome");
        const checkoutAddressSummary = document.getElementById("checkout-address-summary");
        const savedProfileOpenButton = document.getElementById("saved-profile-open");
        const cardapioLink =
            document.querySelector(".checkout-footer-back")?.getAttribute("href") ||
            document.querySelector(".context-header .brand-header-logo")?.getAttribute("href") ||
            "/";
        const backToItemsButton = document.getElementById("checkout-back-to-items");
        const stageTriggers = Array.from(document.querySelectorAll("[data-checkout-stage-trigger]"));
        if (!payloadInput || !form) return;

        let selectedShippingFee = Number.parseFloat(shippingValueInput?.value || "0") || 0;
        let activeStage = "delivery";
        let whatsappSubmitInProgress = false;
        const myOrdersUrl = window.PRATO_CONFIG?.myOrdersUrl || "/meus-pedidos/";

        function submitOrderInNewTab(orderForm) {
            orderForm.target = "_blank";
            orderForm.submit();
            window.setTimeout(() => {
                window.location.href = myOrdersUrl;
            }, 160);
        }

        function redirectToCardapio() {
            window.location.href = cardapioLink;
        }

        function syncOrderNotePayload() {
            if (orderNoteInput && orderNotePayloadInput) {
                orderNotePayloadInput.value = String(orderNoteInput?.value || "").trim();
            }
        }

        function syncCheckoutNamePayload() {
            if (checkoutNameInput && checkoutNamePayloadInput) {
                checkoutNamePayloadInput.value = String(checkoutNameInput?.value || "").trim();
            }
        }

        function syncTalheresPayload() {
            if (talheresToggleInput && talheresPayloadInput) {
                talheresPayloadInput.value = talheresToggleInput?.checked ? "sim" : "nao";
            }
        }

        function clearCheckoutFieldHighlights() {
            checkoutAddressSummary?.classList.remove("field-needs-attention");
            savedProfileOpenButton?.classList.remove("field-needs-attention");
            stagePayment?.classList.remove("field-needs-attention");
        }

        function highlightMissingDeliveryField() {
            clearCheckoutFieldHighlights();
            const missingField = getMissingCheckoutDeliveryField(form);
            if (!missingField) return true;
            const target = checkoutAddressSummary && !checkoutAddressSummary.classList.contains("hidden")
                ? checkoutAddressSummary
                : savedProfileOpenButton;
            target?.classList.add("field-needs-attention");
            target?.focus?.();
            target?.scrollIntoView({ behavior: "smooth", block: "center" });
            return false;
        }

        function highlightMissingPaymentField() {
            stagePayment?.classList.add("field-needs-attention");
            stagePayment?.scrollIntoView({ behavior: "smooth", block: "center" });
            const target = stagePayment?.querySelector("[data-payment-type]");
            window.setTimeout(() => target?.focus?.(), 160);
        }

        function setActiveStage(stage) {
            const cart = getCart();
            activeStage = stage;

            stageDelivery?.classList.toggle("hidden", activeStage !== "delivery");
            deliveryFields?.classList.toggle("hidden", activeStage !== "delivery");
            stagePayment?.classList.toggle("hidden", activeStage !== "delivery");

            stageTriggers.forEach((button) => {
                const isActive = button.getAttribute("data-checkout-stage-trigger") === activeStage;
                button.classList.toggle("is-active", isActive);
                if (isActive) {
                    button.setAttribute("aria-current", "step");
                } else {
                    button.removeAttribute("aria-current");
                }
            });

            if (heroTitleElement) {
                heroTitleElement.textContent = "Entrega";
            }
            if (heroSubtitleElement) {
                heroSubtitleElement.textContent = "Confirme os dados de entrega, escolha o pagamento e envie o pedido.";
            }
        }

        function syncStageAvailability(cartLength) {
            const hasItems = cartLength > 0;

            stageTriggers.forEach((button) => {
                const targetStage = button.getAttribute("data-checkout-stage-trigger");
                if (targetStage === "delivery") {
                    button.disabled = !hasItems;
                }
            });

            if (!hasItems) {
                window.location.href = document.querySelector(".checkout-footer-back")?.getAttribute("href") || "/";
            }
        }

        function updateShippingDisplay(data) {
            const shippingFee = Number(data?.shippingFee);
            const distanceKm = Number(data?.distanceKm);
            if (!Number.isFinite(shippingFee) || shippingFee < 0) {
                selectedShippingFee = 0;
                if (shippingReviewElement) shippingReviewElement.textContent = data?.error === "origin_not_configured" ? "Origem não configurada" : "--";
                if (shippingReviewPaymentElement) shippingReviewPaymentElement.textContent = data?.error === "origin_not_configured" ? "Origem não configurada" : "--";
                if (heroEtaElement) heroEtaElement.textContent = Number.isFinite(Number(data?.etaMinutes)) ? `${Math.max(1, Math.round(Number(data.etaMinutes)))} min` : "--";
                if (shippingValueInput) shippingValueInput.value = "0.00";
                if (distanceInput) distanceInput.value = Number.isFinite(distanceKm) ? distanceKm.toFixed(2) : "0.00";
                render();
                return;
            }

            selectedShippingFee = shippingFee;
            if (shippingReviewElement) shippingReviewElement.textContent = money(shippingFee);
            if (shippingReviewPaymentElement) shippingReviewPaymentElement.textContent = money(shippingFee);
            if (heroEtaElement) heroEtaElement.textContent = Number.isFinite(Number(data?.etaMinutes)) ? `${Math.max(1, Math.round(Number(data.etaMinutes)))} min` : "--";
            if (shippingValueInput) shippingValueInput.value = shippingFee.toFixed(2);
            if (distanceInput) distanceInput.value = Number.isFinite(distanceKm) ? distanceKm.toFixed(2) : "0.00";
            render();
        }

        function render() {
            const cart = getCart();
            payloadInput.value = JSON.stringify(cart);
            syncOrderNotePayload();
            syncCheckoutNamePayload();
            syncTalheresPayload();
            if (!cart.length) {
                redirectToCardapio();
                return;
            }

            const itemsTotal = cart.reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0);
            const orderTotal = itemsTotal + selectedShippingFee;
            if (itemsContainer) itemsContainer.innerHTML = cart.map(buildCartItemMarkup).join("");
            if (itemsSubtotalElement) itemsSubtotalElement.textContent = money(itemsTotal);
            if (totalReviewElement) totalReviewElement.textContent = money(orderTotal);
            if (totalReviewPaymentElement) totalReviewPaymentElement.textContent = money(orderTotal);
            if (shippingReviewElement && !shippingReviewElement.textContent.trim()) {
                shippingReviewElement.textContent = Number.isFinite(selectedShippingFee) && selectedShippingFee > 0 ? money(selectedShippingFee) : "--";
            }
            if (shippingReviewPaymentElement && !shippingReviewPaymentElement.textContent.trim()) {
                shippingReviewPaymentElement.textContent = Number.isFinite(selectedShippingFee) && selectedShippingFee > 0 ? money(selectedShippingFee) : "--";
            }
            syncStageAvailability(cart.length);

            itemsContainer?.querySelectorAll("[data-qty-change]").forEach((button) => {
                button.addEventListener("click", function () {
                    const index = Number(this.getAttribute("data-qty-change"));
                    const delta = Number(this.getAttribute("data-delta"));
                    const updatedCart = getCart();
                    if (!updatedCart[index]) return;
                    updatedCart[index].quantidade = Math.max(1, Number(updatedCart[index].quantidade || 1) + delta);
                    saveCart(updatedCart);
                    render();
                });
            });

            itemsContainer?.querySelectorAll("[data-remove-item]").forEach((button) => {
                button.addEventListener("click", function () {
                    const index = Number(this.getAttribute("data-remove-item"));
                    saveCart(getCart().filter((_, itemIndex) => itemIndex !== index));
                    render();
                });
            });
        }

        const addressController = profileForm ? initAddressEditor(profileForm) : null;
        initSavedCheckoutProfiles(form, profileForm, addressController, updateShippingDisplay);
        const draft = getCheckoutDraft();
        if (checkoutNamePayloadInput) checkoutNamePayloadInput.value = draft.nome || getCheckoutCustomerName();
        if (orderNotePayloadInput) orderNotePayloadInput.value = draft.observacao_geral || "";
        if (talheresPayloadInput) talheresPayloadInput.value = draft.enviar_talheres === "nao" ? "nao" : "sim";
        checkoutNameInput?.addEventListener("input", clearCheckoutFieldHighlights);
        savedProfileOpenButton?.addEventListener("click", clearCheckoutFieldHighlights);
        checkoutAddressSummary?.addEventListener("click", clearCheckoutFieldHighlights);
        talheresToggleInput?.addEventListener("change", syncTalheresPayload);
        syncTalheresPayload();

        function setPaymentSelection(paymentType, paymentMethod, options = {}) {
            const type = String(paymentType || "").trim();
            let method = String(paymentMethod || "").trim();
            const pixConfigured = stagePayment?.dataset.pixConfigured === "true";

            if (type === "pix" && !pixConfigured) {
                method = "";
            } else if (type === "pix") {
                method = "pix";
            }

            document.querySelectorAll("[data-payment-type]").forEach((item) => {
                item.classList.toggle("is-selected", item.getAttribute("data-payment-type") === type);
            });
            document.querySelectorAll("[data-payment-method]").forEach((item) => {
                item.classList.toggle("is-selected", item.getAttribute("data-payment-method") === method);
            });

            paymentDeliveryOptions?.classList.toggle("hidden", type !== "entrega");
            paymentPixPanel?.classList.toggle("hidden", type !== "pix");
            if (paymentMethodInput) paymentMethodInput.value = method;
            if (method) {
                stagePayment?.classList.remove("field-needs-attention");
            }

            if (options.persist !== false) {
                saveCheckoutPaymentPreference({ type, method });
            }

            if (type === "pix" && !pixConfigured && options.notice !== false) {
                showUiNotice("Pix online ainda não est? configurado.");
            }
        }

        document.querySelectorAll("[data-payment-type]").forEach((button) => {
            button.addEventListener("click", () => {
                const paymentType = button.getAttribute("data-payment-type");
                setPaymentSelection(paymentType, paymentType === "pix" ? "pix" : "");
            });
        });

        document.querySelectorAll("[data-payment-method]").forEach((button) => {
            button.addEventListener("click", () => {
                setPaymentSelection("entrega", button.getAttribute("data-payment-method") || "");
            });
        });

        const paymentPreference = getCheckoutPaymentPreference();
        if (paymentPreference.method === "pix" && stagePayment?.dataset.pixConfigured === "true") {
            setPaymentSelection("pix", "pix", { persist: false, notice: false });
        } else if (["dinheiro", "cartao_entrega"].includes(paymentPreference.method)) {
            setPaymentSelection("entrega", paymentPreference.method, { persist: false, notice: false });
        } else if (paymentPreference.type === "entrega") {
            setPaymentSelection("entrega", "", { persist: false, notice: false });
        }

        document.querySelector("[data-copy-pix]")?.addEventListener("click", async (event) => {
            const button = event.currentTarget;
            const pixKey = String(button.getAttribute("data-copy-pix") || "").trim();
            const feedback = document.getElementById("pix-copy-feedback");
            if (!pixKey) return;
            try {
                if (navigator.clipboard?.writeText) {
                    await navigator.clipboard.writeText(pixKey);
                } else {
                    const input = document.createElement("input");
                    input.value = pixKey;
                    input.setAttribute("readonly", "readonly");
                    input.style.position = "fixed";
                    input.style.opacity = "0";
                    document.body.appendChild(input);
                    input.select();
                    document.execCommand("copy");
                    input.remove();
                }
                feedback?.classList.remove("hidden");
                window.setTimeout(() => feedback?.classList.add("hidden"), 1600);
            } catch (error) {
                showUiNotice("Não foi possível copiar a chave Pix automaticamente.");
            }
        });

        stageTriggers.forEach((button) => {
            button.addEventListener("click", () => {
                const targetStage = button.getAttribute("data-checkout-stage-trigger");
                if (!targetStage) return;
                if (targetStage === "delivery" && !getCart().length) return;
                setActiveStage(targetStage);
            });
        });

        form.addEventListener("submit", function (event) {
            const cart = getCart();
            if (!cart.length) {
                event.preventDefault();
                showUiNotice("Adicione pelo menos um item ao carrinho.");
                return;
            }
            if (!hasCheckoutDeliveryData(form)) {
                event.preventDefault();
                highlightMissingDeliveryField();
                return;
            }
            if (!String(paymentMethodInput?.value || "").trim()) {
                event.preventDefault();
                setActiveStage("delivery");
                highlightMissingPaymentField();
                showUiNotice("Selecione uma forma de pagamento para continuar.");
                return;
            }
            payloadInput.value = JSON.stringify(cart);
            syncOrderNotePayload();
            syncCheckoutNamePayload();
            syncTalheresPayload();
            persistCheckoutProfileFromForm(form);
            if (!whatsappSubmitInProgress) {
                event.preventDefault();
                showUiNotice("", {
                    title: "Finalizar no WhatsApp",
                    messageLines: [
                        "Seu pedido será gerado e o WhatsApp abrirá com o resumo pronto.",
                        "Depois é só enviar a mensagem para nossa equipe confirmar.",
                    ],
                    cancelLabel: "Cancelar",
                    confirmLabel: "Continuar",
                    onConfirm() {
                        whatsappSubmitInProgress = true;
                        form.querySelectorAll("button, input[type='submit']").forEach((button) => {
                            button.disabled = true;
                        });
                        submitOrderInNewTab(form);
                    },
                });
                return;
            }
        });

        render();
        setActiveStage(activeStage);
    }

    function initCarrinhoPage() {
        const root = document.querySelector("[data-page='carrinho']");
        if (!root) return;
        const itemsContainer = document.getElementById("checkout-items");
        const itemsSubtotalElement = document.getElementById("checkout-items-subtotal");
        const nameInput = document.getElementById("checkout-nome");
        const orderNoteInput = document.getElementById("checkout-order-note");
        const talheresToggleInput = document.getElementById("checkout-talheres-toggle");
        const goDeliveryLink = document.getElementById("checkout-go-delivery");
        const goPickupButton = document.getElementById("checkout-go-pickup");
        const pickupForm = document.getElementById("pickup-form");
        const pickupPayloadInput = document.getElementById("pickup-carrinho-payload");
        const pickupNameInput = document.getElementById("pickup-nome-payload");
        const pickupNoteInput = document.getElementById("pickup-order-note-payload");
        const pickupTalheresInput = document.getElementById("pickup-talheres-payload");
        const myOrdersUrl = window.PRATO_CONFIG?.myOrdersUrl || "/meus-pedidos/";
        if (!itemsContainer || !itemsSubtotalElement || !goDeliveryLink) return;

        function readDraftFromPage() {
            return {
                nome: nameInput?.value || "",
                observacao_geral: orderNoteInput?.value || "",
                enviar_talheres: talheresToggleInput?.checked ? "sim" : "nao",
            };
        }

        function persistDraftFromPage() {
            saveCheckoutDraft(readDraftFromPage());
        }

        function persistCustomerNameFromPage() {
            saveCheckoutDraft({
                ...getCheckoutDraft(),
                nome: nameInput?.value || "",
            });
        }

        function syncPickupFormPayload() {
            const cart = getCart();
            const draftPayload = readDraftFromPage();
            if (pickupPayloadInput) pickupPayloadInput.value = JSON.stringify(cart);
            if (pickupNameInput) pickupNameInput.value = String(draftPayload.nome || "").trim();
            if (pickupNoteInput) pickupNoteInput.value = String(draftPayload.observacao_geral || "").trim();
            if (pickupTalheresInput) pickupTalheresInput.value = draftPayload.enviar_talheres === "nao" ? "nao" : "sim";
        }

        const draft = getCheckoutDraft();
        if (nameInput) nameInput.value = draft.nome || getCheckoutCustomerName();
        if (orderNoteInput) orderNoteInput.value = draft.observacao_geral || "";
        if (talheresToggleInput) talheresToggleInput.checked = draft.enviar_talheres !== "nao";

        function render() {
            const cart = getCart();
            if (!cart.length) {
                window.location.href = document.querySelector(".checkout-footer-back")?.getAttribute("href") || "/";
                return;
            }
            itemsContainer.innerHTML = cart.map(buildCartItemMarkup).join("");
            const itemsTotal = cart.reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0);
            itemsSubtotalElement.textContent = money(itemsTotal);
            goDeliveryLink.classList.toggle("is-disabled", !cart.length);
            goDeliveryLink.setAttribute("aria-disabled", cart.length ? "false" : "true");
            if (goPickupButton) goPickupButton.disabled = !cart.length;
        }

        itemsContainer.addEventListener("click", (event) => {
            const qtyButton = event.target.closest("[data-qty-change]");
            if (qtyButton) {
                const index = Number(qtyButton.getAttribute("data-qty-change"));
                const delta = Number(qtyButton.getAttribute("data-delta"));
                const updatedCart = getCart();
                if (!updatedCart[index]) return;
                updatedCart[index].quantidade = Math.max(1, Number(updatedCart[index].quantidade || 1) + delta);
                saveCart(updatedCart);
                render();
                return;
            }

            const removeButton = event.target.closest("[data-remove-item]");
            if (removeButton) {
                const index = Number(removeButton.getAttribute("data-remove-item"));
                saveCart(getCart().filter((_, itemIndex) => itemIndex !== index));
                render();
            }
        });

        nameInput?.addEventListener("input", persistCustomerNameFromPage);
        nameInput?.addEventListener("change", persistCustomerNameFromPage);
        nameInput?.addEventListener("blur", persistCustomerNameFromPage);
        orderNoteInput?.addEventListener("input", persistDraftFromPage);
        orderNoteInput?.addEventListener("change", persistDraftFromPage);
        orderNoteInput?.addEventListener("blur", persistDraftFromPage);
        talheresToggleInput?.addEventListener("change", persistDraftFromPage);
        window.addEventListener("pagehide", persistDraftFromPage);
        window.addEventListener("beforeunload", persistDraftFromPage);
        goDeliveryLink.addEventListener("click", (event) => {
            const cart = getCart();
            if (!cart.length) {
                event.preventDefault();
                return;
            }
            persistDraftFromPage();
        });
        let pickupSubmitInProgress = false;
        goPickupButton?.addEventListener("click", () => {
            const cart = getCart();
            if (!cart.length || !pickupForm || pickupSubmitInProgress) return;
            persistDraftFromPage();
            syncPickupFormPayload();
            showUiNotice("", {
                title: "Fazer retirada",
                messageLines: [
                    "Vamos gerar seu pedido e abrir o WhatsApp com a mensagem pronta.",
                    "Envie a mensagem para confirmar com nossa equipe.",
                ],
                cancelLabel: "Voltar",
                confirmLabel: "Abrir WhatsApp",
                onConfirm() {
                    pickupSubmitInProgress = true;
                    goPickupButton.disabled = true;
                    pickupForm.target = "_blank";
                    pickupForm.submit();
                    window.setTimeout(() => {
                        window.location.href = myOrdersUrl;
                    }, 160);
                },
            });
        });

        render();
    }

    function kitchenCardMarkup(pedido, statusChoices) {
        const statusButtons = statusChoices
            .map(([value, label]) => {
                const active = pedido.status === value ? "is-active" : "";
                return `<button type="button" class="status-button ${active}" data-status-update data-pedido-id="${pedido.id}" data-status="${value}">${label}</button>`;
            })
            .join("");

        const itens = pedido.itens
            .map((item) => `<li>${item.quantidade}x ${escapeHtml(item.nome)}${item.observacao ? `<small>Obs: ${escapeHtml(item.observacao)}</small>` : ""}</li>`)
            .join("");

        return `
            <article class="kitchen-card status-${pedido.status}">
                <div class="kitchen-head">
                    <div>
                        <p class="order-number">#${pedido.numero}</p>
                        <h2>${escapeHtml(pedido.cliente)}</h2>
                    </div>
                    <span class="status-badge">${escapeHtml(pedido.status_label)}</span>
                </div>
                <div class="kitchen-meta">
                    <p><strong>Telefone:</strong> ${escapeHtml(pedido.telefone)}</p>
                    <p><strong>Endereço:</strong> ${escapeHtml(pedido.endereco)}</p>
                    ${pedido.lote_quadra ? `<p><strong>Lote/Quadra:</strong> ${escapeHtml(pedido.lote_quadra)}</p>` : ""}
                    ${pedido.complemento ? `<p><strong>Complemento:</strong> ${escapeHtml(pedido.complemento)}</p>` : ""}
                    ${pedido.ponto_referencia ? `<p><strong>Ponto de referência:</strong> ${escapeHtml(pedido.ponto_referencia)}</p>` : ""}
                    <p><strong>Talheres:</strong> ${pedido.enviar_talheres ? "Sim" : "Nao"}</p>
                    <p><strong>Horário:</strong> ${escapeHtml(pedido.horario)}</p>
                </div>
                <ul class="kitchen-items">${itens}</ul>
                ${pedido.observacao_geral ? `<p class="kitchen-note"><strong>Observação geral:</strong> ${escapeHtml(pedido.observacao_geral)}</p>` : ""}
                <div class="header-actions">
                    <a class="secondary-pill compact" href="${escapeHtml(pedido.google_maps_route_url || "#")}" target="_blank" rel="noopener noreferrer">
                        Abrir rota no Google Maps
                    </a>
                </div>
                ${pedido.has_coordinates ? "" : `<p class="kitchen-note">Rota baseada no endereço digitado pelo cliente.</p>`}
                <div class="status-actions">${statusButtons}</div>
            </article>
        `;
    }

    function getCsrfToken() {
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : "";
    }

    function initCozinhaPage() {
        const container = document.getElementById("cozinha-lista");
        const root = document.querySelector("[data-page='cozinha']");
        if (!container || !root) return;
        const apiUrl = root.dataset.apiUrl;

        async function refresh() {
            const response = await fetch(apiUrl, { headers: { Accept: "application/json" } });
            if (!response.ok) return;
            const data = await response.json();
            if (!data.pedidos.length) {
                container.innerHTML = `
                    <div class="empty-state">
                        <h2>Nenhum pedido ainda.</h2>
                        <p>Assim que os clientes enviarem pedidos, eles aparecerao aqui.</p>
                    </div>
                `;
                return;
            }
            container.innerHTML = data.pedidos.map((pedido) => kitchenCardMarkup(pedido, data.status_choices)).join("");
            bindStatusButtons();
        }

        async function updateStatus(pedidoId, status) {
            const response = await fetch(`/controle/pedido/${pedidoId}/status/`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-CSRFToken": getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: new URLSearchParams({ status }).toString(),
            });
            if (response.ok) refresh();
        }

        function bindStatusButtons() {
            container.querySelectorAll("[data-status-update]").forEach((button) => {
                button.addEventListener("click", function () {
                    updateStatus(this.dataset.pedidoId, this.dataset.status);
                });
            });
        }

        bindStatusButtons();
        setInterval(refresh, 5000);
    }

        syncCartCount();
        initCardapioPage();
        initCarrinhoPage();
        initCheckoutPage();
        initCozinhaPage();
})();
