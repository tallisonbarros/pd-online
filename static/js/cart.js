(function () {
    const config = window.PRATO_CONFIG || {};
    const cartKey = config.cartKey || "prato_delivery_cart";
    const checkoutProfilesKey = `${cartKey}_checkout_profiles`;
    const legacyCheckoutProfileKey = `${cartKey}_checkout_profile`;
    const checkoutDraftKey = `${cartKey}_checkout_draft`;
    const checkoutPaymentKey = `${cartKey}_checkout_payment`;
    const checkoutCustomerNameKey = `${cartKey}_checkout_customer_name`;
    const checkoutCouponKey = `${cartKey}_checkout_coupon`;
    const checkoutPendingKey = `${cartKey}_checkout_pending_key`;
    const checkoutAutoAddressKey = `${cartKey}_checkout_auto_address`;
    const cartMetaKey = `${cartKey}_meta`;
    const placeholderImage = `${config.staticUrl || "/static/"}img/placeholder-prato.svg`;
    const currentCartCycleKey = String(config.cartCycleKey || "").trim();
    const cartExpiresAt = String(config.cartExpiresAt || "").trim();
    const serverNow = String(config.serverNow || "").trim();
    const serverClockOffsetMs = (() => {
        const serverTime = Date.parse(serverNow);
        return Number.isFinite(serverTime) ? serverTime - Date.now() : 0;
    })();
    const checkoutLookup = (() => {
        const node = document.getElementById("checkout-pratos-lookup");
        if (!node) return {};
        try {
            return JSON.parse(node.textContent || "{}");
        } catch (error) {
            return {};
        }
    })();
    const deliveryEtaUrl = config.deliveryEtaUrl || "/api/address/delivery-time/";
    const googleMapsApiKey = String(config.googleMapsApiKey || "").trim();
    const googleMapsLanguage = String(config.googleMapsLanguage || "pt-BR").trim() || "pt-BR";
    const googleMapsRegion = String(config.googleMapsRegion || "BR").trim() || "BR";
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
                existingScript.addEventListener("load", () => resolve(window.google.maps), { once: true });
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
                libraries: "places",
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

    function calculateMealPromo(cart) {
        const mealItems = (Array.isArray(cart) ? cart : []).filter((item) => cartItemType(item) === "prato");
        const mealCount = mealItems.reduce((total, item) => total + Number(item.quantidade || 0), 0);
        const freeMeals = Math.floor(mealCount / 5);
        const cycleCount = mealCount % 5;
        const progressCount = freeMeals > 0 && cycleCount === 0 ? 4 : Math.min(cycleCount, 4);
        const remaining = Math.max(4 - progressCount, 0);
        if (freeMeals <= 0) {
            return {
                freeMeals: 0,
                discount: 0,
                mealCount,
                progressCount,
                remaining,
                readyForFreeMeal: progressCount >= 4,
                label: "",
            };
        }
        const mealPrices = mealItems.map((item) => parsePrice(item.preco)).filter((price) => price > 0);
        const unitPrice = mealPrices.length ? Math.min(...mealPrices) : 0;
        return {
            freeMeals,
            discount: unitPrice * freeMeals,
            mealCount,
            progressCount,
            remaining,
            readyForFreeMeal: progressCount >= 4 && cycleCount !== 0,
            label: freeMeals === 1 ? "5ª marmita grátis" : `${freeMeals} marmitas grátis`,
        };
    }

    function mealPromoMessage(promo, options = {}) {
        const remaining = Number(promo?.remaining || 0);
        const freeMeals = Number(promo?.freeMeals || 0);
        if (promo?.readyForFreeMeal) {
            return freeMeals > 0 ? "Adicione sua próxima marmita grátis agora" : "Adicione sua marmita grátis agora";
        }
        if (freeMeals <= 0) {
            return remaining === 1 ? "Falta 1 marmita para liberar 1 grátis" : `Faltam ${remaining} marmitas para liberar 1 grátis`;
        }
        if (Number(promo?.progressCount || 0) >= 4) {
            return freeMeals === 1 ? "Promoção aplicada: 1 marmita grátis" : `Promoção aplicada: ${freeMeals} marmitas grátis`;
        }
        if (options.nextCycle) {
            return remaining === 1 ? "Mais 1 para liberar outra grátis" : `Mais ${remaining} para liberar outra grátis`;
        }
        return freeMeals === 1 ? "Promoção aplicada: 1 marmita grátis" : `Promoção aplicada: ${freeMeals} marmitas grátis`;
    }

    function syncMealPromoProgress(container, promo, options = {}) {
        if (!container) return;
        const progressCount = Math.max(0, Math.min(Number(promo?.progressCount || 0), 4));
        const percent = (progressCount / 4) * 100;
        const countNode = container.querySelector("[data-meal-promo-count], [data-cart-meal-promo-count]");
        const messageNode = container.querySelector("[data-meal-promo-message], [data-cart-meal-promo-message]");
        const fillNode = container.querySelector("[data-meal-promo-fill], [data-cart-meal-promo-fill]");
        const nextNode = container.querySelector("[data-cart-meal-promo-next]");
        if (countNode) countNode.textContent = `${progressCount}/4 marmitas`;
        if (messageNode) messageNode.textContent = mealPromoMessage(promo, options);
        if (fillNode) fillNode.style.width = `${percent}%`;
        if (nextNode) {
            const freeMeals = Number(promo?.freeMeals || 0);
            nextNode.textContent = freeMeals > 0 && progressCount >= 4 && !promo?.readyForFreeMeal ? "Próxima: mais 4 marmitas liberam outra." : "";
        }
        container.classList.toggle("is-applied", Number(promo?.freeMeals || 0) > 0);
        container.classList.toggle("is-complete", progressCount >= 4);
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

    function normalizeVariationName(value) {
        return String(value || "").trim().replace(/\s+/g, " ");
    }

    function parseDishVariations(dish) {
        const raw = Array.isArray(dish?.variacoes)
            ? dish.variacoes
            : String(dish?.variacoes || "").split(/\r?\n|;/);
        const seen = new Set();
        return raw
            .map(normalizeVariationName)
            .filter((variation) => {
                const key = normalizeText(variation);
                if (!variation || seen.has(key)) return false;
                seen.add(key);
                return true;
            });
    }

    function cartItemKey(item) {
        const variationKey = cartItemType(item) === "prato" ? normalizeText(item?.variacao || item?.variacao_nome) : "";
        return `${cartItemType(item)}:${cartItemId(item)}:${variationKey}`;
    }

    function cartItemBaseKey(item) {
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
            variacao: normalizeVariationName(normalizedItem.variacao || normalizedItem.variacao_nome),
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

    function operationalNowMs() {
        return Date.now() + serverClockOffsetMs;
    }

    function readCartMeta() {
        try {
            const parsed = JSON.parse(localStorage.getItem(cartMetaKey) || "{}");
            return parsed && typeof parsed === "object" ? parsed : {};
        } catch (error) {
            return {};
        }
    }

    function writeCartMeta() {
        if (!currentCartCycleKey) {
            localStorage.removeItem(cartMetaKey);
            return;
        }
        localStorage.setItem(
            cartMetaKey,
            JSON.stringify({
                cycle_key: currentCartCycleKey,
                expires_at: cartExpiresAt,
                saved_at: new Date(operationalNowMs()).toISOString(),
            })
        );
    }

    function clearCartStorage(options = {}) {
        const shouldNotify = options.notify === true;
        const hadCart = Boolean(localStorage.getItem(cartKey));
        localStorage.removeItem(cartKey);
        localStorage.removeItem(cartMetaKey);
        localStorage.removeItem(checkoutDraftKey);
        localStorage.removeItem(checkoutPaymentKey);
        localStorage.removeItem(checkoutCouponKey);
        if (shouldNotify && hadCart) {
            showNotice(
                "Carrinho reiniciado",
                "O horario de pedidos virou. Monte seu carrinho novamente com os itens disponiveis agora."
            );
        }
        syncCartCount();
        document.dispatchEvent(new CustomEvent("prato:cart-cleared"));
    }

    function cartExpired(meta = readCartMeta()) {
        if (!localStorage.getItem(cartKey)) return false;
        if (currentCartCycleKey && meta.cycle_key !== currentCartCycleKey) return true;
        const expiresAtMs = Date.parse(meta.expires_at || cartExpiresAt || "");
        return Number.isFinite(expiresAtMs) && operationalNowMs() >= expiresAtMs;
    }

    function ensureCartIsCurrent(options = {}) {
        if (!localStorage.getItem(cartKey)) return false;
        if (cartExpired()) {
            clearCartStorage(options);
            return true;
        }
        return false;
    }

    function getCart() {
        if (ensureCartIsCurrent({ notify: true })) return [];
        try {
            return normalizeCart(JSON.parse(localStorage.getItem(cartKey) || "[]"));
        } catch (error) {
            return [];
        }
    }

    function saveCart(cart) {
        const normalizedCart = normalizeCart(cart);
        if (normalizedCart.length) {
            writeCartMeta();
            localStorage.setItem(cartKey, JSON.stringify(normalizedCart));
        } else {
            clearCartStorage();
        }
        syncCartCount();
    }

    function scheduleCartExpiration() {
        ensureCartIsCurrent({ notify: true });
        const expiresAtMs = Date.parse(cartExpiresAt || "");
        if (!Number.isFinite(expiresAtMs)) return;
        const delay = expiresAtMs - operationalNowMs();
        if (delay <= 0) {
            ensureCartIsCurrent({ notify: true });
            return;
        }
        window.setTimeout(() => {
            ensureCartIsCurrent({ notify: true });
        }, Math.min(delay + 500, 2147483647));
    }

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) ensureCartIsCurrent({ notify: true });
    });
    window.addEventListener("pageshow", () => ensureCartIsCurrent({ notify: true }));

    function cartStats(cartOverride) {
        const cart = Array.isArray(cartOverride) ? normalizeCart(cartOverride) : getCart();
        return {
            count: cart.reduce((total, item) => total + Number(item.quantidade || 0), 0),
            total: cart.reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0),
        };
    }

    function trackMetricEvent(eventType, payload = {}) {
        const eventUrl = String(config.metricEventUrl || "").trim();
        if (!eventUrl || !eventType) return;
        window.__pratoMetricLastSent = window.__pratoMetricLastSent || new Map();
        const dedupeKey = JSON.stringify({
            eventType,
            path: window.location.pathname,
            itemType: payload.item_type || "",
            itemId: payload.item_id || "",
            metadata: payload.metadata || {},
        });
        const now = Date.now();
        const lastSent = window.__pratoMetricLastSent.get(dedupeKey) || 0;
        if (now - lastSent < 900) return;
        window.__pratoMetricLastSent.set(dedupeKey, now);
        const stats = cartStats();
        const body = {
            event_type: eventType,
            path: window.location.pathname,
            cart_items_count: payload.cart_items_count ?? stats.count,
            cart_total: payload.cart_total ?? stats.total.toFixed(2),
            item_type: payload.item_type || "",
            item_id: payload.item_id || "",
            metadata: payload.metadata || {},
        };
        fetch(eventUrl, {
            method: "POST",
            credentials: "same-origin",
            keepalive: true,
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": config.csrfToken || getCsrfToken(),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(body),
        }).catch(() => {});
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

    function getCheckoutCouponCode() {
        try {
            return String(localStorage.getItem(checkoutCouponKey) || "").trim().toUpperCase();
        } catch (error) {
            return "";
        }
    }

    function saveCheckoutCouponCode(code) {
        try {
            const normalized = String(code || "").trim().toUpperCase();
            if (normalized) {
                localStorage.setItem(checkoutCouponKey, normalized);
            } else {
                localStorage.removeItem(checkoutCouponKey);
            }
        } catch (error) {
            // Ignora falha de storage.
        }
    }

    function getKnownOrderTokens() {
        try {
            const key = (window.PRATO_CONFIG && window.PRATO_CONFIG.orderHistoryKey) || "prato_delivery_orders";
            const parsed = JSON.parse(localStorage.getItem(key) || "[]");
            if (!Array.isArray(parsed)) return [];
            return parsed
                .map((item) => String(item?.token || "").trim())
                .filter(Boolean)
                .filter((token, index, list) => list.indexOf(token) === index)
                .slice(0, 30);
        } catch (error) {
            return [];
        }
    }

    function getOrCreateCheckoutKey(scope) {
        const storageKey = `${checkoutPendingKey}_${scope || "pedido"}`;
        try {
            const current = String(localStorage.getItem(storageKey) || "").trim();
            if (current) return current;
            const randomPart = window.crypto?.randomUUID
                ? window.crypto.randomUUID()
                : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
            const checkoutKey = String(randomPart).replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 64);
            localStorage.setItem(storageKey, checkoutKey);
            return checkoutKey;
        } catch (error) {
            return `${Date.now()}-${Math.random().toString(36).slice(2)}`.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 64);
        }
    }

    function clearCheckoutKey(scope) {
        try {
            localStorage.removeItem(`${checkoutPendingKey}_${scope || "pedido"}`);
        } catch (error) {
            // Ignora falha de storage.
        }
    }

    function rememberOrder(order) {
        if (!order || !order.token) return;
        const key = (window.PRATO_CONFIG && window.PRATO_CONFIG.orderHistoryKey) || "prato_delivery_orders";
        try {
            let currentOrders = JSON.parse(localStorage.getItem(key) || "[]");
            if (!Array.isArray(currentOrders)) currentOrders = [];
            currentOrders = currentOrders.filter((item) => item && item.token && item.token !== order.token);
            currentOrders.unshift(order);
            localStorage.setItem(key, JSON.stringify(currentOrders.slice(0, 30)));
        } catch (error) {
            // Ignora falha de storage.
        }
    }

    function clearCheckoutAfterOrder() {
        clearCartStorage();
        try {
            localStorage.removeItem(checkoutDraftKey);
            localStorage.removeItem(checkoutPaymentKey);
            localStorage.removeItem(checkoutCouponKey);
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
            const whatsappFloat = document.querySelector("[data-whatsapp-float]");
            const myOrdersFloat = document.querySelector("[data-my-orders-float]");
            const previousCount = Number(cartDock.dataset.cartCount || "0");
            const hydrated = cartDock.dataset.hydrated === "true";
            cartDock.dataset.cartCount = String(count);
            cartDock.dataset.hydrated = "true";
            cartDock.classList.toggle("is-visible", count > 0);
            cartDockWrap?.classList.toggle("is-visible", count > 0);
            whatsappFloat?.classList.toggle("is-cart-visible", count > 0);
            myOrdersFloat?.classList.toggle("is-cart-visible", count > 0);

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
        syncWhatsappCartMessage();
    }

    function buildWhatsappCartMessage(cart) {
        const itemsTotal = cart.reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0);
        const mealPromo = calculateMealPromo(cart);
        const mealPromoDiscount = Math.min(mealPromo.discount, itemsTotal);
        const lines = [
            "Ola! Quero finalizar estes itens do carrinho:",
            "",
            "*Itens:*",
        ];

        cart.forEach((item) => {
            const quantity = Math.max(1, Number(item.quantidade || 1));
            const itemTotal = parsePrice(item.preco) * quantity;
            const variation = normalizeVariationName(item.variacao || item.variacao_nome);
            const itemName = variation ? `${item.nome} - ${variation}` : item.nome;
            lines.push(`- ${quantity}x ${itemName} | ${money(itemTotal)}`);
            if (item.observacao) {
                lines.push(`  Obs: ${item.observacao}`);
            }
        });

        lines.push("", `*Subtotal dos itens:* ${money(itemsTotal)}`);
        if (mealPromoDiscount > 0) {
            lines.push(`*${mealPromo.label || "Promocao especial"}:* - ${money(mealPromoDiscount)}`);
            lines.push(`*Total parcial:* ${money(Math.max(itemsTotal - mealPromoDiscount, 0))}`);
        }
        lines.push("", "Ainda preciso confirmar entrega/retirada e pagamento.");
        return lines.join("\n");
    }

    function syncWhatsappCartMessage() {
        const whatsappFloat = document.querySelector("[data-whatsapp-float]");
        if (!whatsappFloat) return;

        if (!whatsappFloat.dataset.defaultHref) {
            whatsappFloat.dataset.defaultHref = whatsappFloat.getAttribute("href") || "";
        }

        const defaultHref = whatsappFloat.dataset.defaultHref;
        const baseHref = defaultHref.split("?")[0];
        const cart = getCart();
        const copy = whatsappFloat.querySelector(".whatsapp-float-copy");

        if (!cart.length || !baseHref) {
            whatsappFloat.setAttribute("href", defaultHref);
            whatsappFloat.setAttribute("aria-label", "Falar com atendente pelo WhatsApp");
            if (copy) copy.textContent = "Falar com atendente";
            return;
        }

        whatsappFloat.setAttribute("href", `${baseHref}?text=${encodeURIComponent(buildWhatsappCartMessage(cart))}`);
        whatsappFloat.setAttribute("aria-label", "Enviar itens do carrinho pelo WhatsApp");
        if (copy) copy.textContent = "Enviar itens";
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
        const variationMarkup = item.variacao
            ? `<small class="checkout-item-variation">${escapeHtml(item.variacao)}</small>`
            : "";
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
                                ${variationMarkup}
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
        const menuPromoProgress = document.querySelector("[data-meal-promo-progress]");

        function syncMenuPromo() {
            const promo = calculateMealPromo(getCart());
            syncMealPromoProgress(menuPromoProgress, promo);
        }

        syncMenuPromo();
        window.addEventListener("storage", syncMenuPromo);

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
        const variationField = document.getElementById("modal-variacao-field");
        const variationOptions = document.getElementById("modal-variacao-options");
        const obs = document.getElementById("modal-observacao");
        const quantityDisplay = document.getElementById("modal-quantidade");
        const modalQuantityBadge = modal.querySelector(".modal-qty-control");

        let currentDish = null;
        let selectedVariation = "";

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
            syncMenuPromo();
            trackMetricEvent("add_to_cart", {
                item_type: cartItemType(normalizedIncomingItem),
                item_id: normalizedIncomingItem.item_id || normalizedIncomingItem.prato_id || normalizedIncomingItem.adicional_id || normalizedIncomingItem.bebida_id || "",
                cart_items_count: Number(normalizedIncomingItem.quantidade || 1),
                metadata: {
                    origem: "cardapio",
                    variacao: normalizedIncomingItem.variacao || "",
                },
            });
        }

        function buildCardCartItem(dish, quantityToAdd = 1, variationOverride = "") {
            const dishType = dish.tipo || "prato";
            const variations = parseDishVariations(dish);
            const variation = normalizeVariationName(variationOverride || (variations.length === 1 ? variations[0] : ""));
            return {
                tipo: dishType,
                item_id: dish.id,
                prato_id: dishType === "prato" ? dish.id : undefined,
                adicional_id: dishType === "adicional" ? dish.id : undefined,
                bebida_id: dishType === "bebida" ? dish.id : undefined,
                nome: dish.nome,
                preco: parsePrice(dish.preco),
                quantidade: Math.max(1, Number(quantityToAdd || 1)),
                variacao: variation,
                observacao: "",
                imagem: dish.imagem || placeholderImage,
            };
        }

        function getCartQuantityForDish(dish) {
            const key = cartItemBaseKey(normalizeCatalogCartFields(dish));
            return getCart()
                .filter((item) => cartItemBaseKey(item) === key)
                .reduce((total, item) => total + Number(item.quantidade || 0), 0);
        }

        function getCartQuantityForDishVariation(dish, variation) {
            const target = cartItemKey({ ...normalizeCatalogCartFields(dish), variacao: variation });
            return getCart()
                .filter((item) => cartItemKey(item) === target)
                .reduce((total, item) => total + Number(item.quantidade || 0), 0);
        }

        function ensureVariationQuickControls(card, dish) {
            const variations = parseDishVariations(dish);
            const genericBadge = card.querySelector(".dish-qty-badge--footer:not(.dish-variation-qty)");
            let controls = card.querySelector("[data-variation-quick-controls]");
            if (!variations.length) {
                genericBadge?.classList.remove("hidden");
                controls?.remove();
                return;
            }
            genericBadge?.classList.add("hidden");
            if (!controls) {
                controls = document.createElement("div");
                controls.className = "dish-variation-quick-controls";
                controls.setAttribute("data-variation-quick-controls", "");
                genericBadge?.insertAdjacentElement("afterend", controls);
            }
            controls.innerHTML = variations
                .map((variation) => `
                    <div class="dish-variation-quick-row" data-card-variation-row="${escapeHtml(variation)}">
                        <strong class="dish-variation-quick-title">${escapeHtml(variation)}</strong>
                        <div class="dish-qty-badge dish-qty-badge--footer dish-variation-qty is-empty">
                            <button type="button" data-card-variation-qty-change="-1" data-card-variation="${escapeHtml(variation)}" aria-label="Diminuir ${escapeHtml(variation)}">-</button>
                            <strong class="dish-variation-empty-label">${escapeHtml(variation)}</strong>
                            <strong data-card-variation-qty-value>0</strong>
                            <button type="button" data-card-variation-qty-change="1" data-card-variation="${escapeHtml(variation)}" aria-label="Adicionar ${escapeHtml(variation)}">+</button>
                        </div>
                    </div>
                `)
                .join("");
        }

        function syncCardQuantityBadges() {
            document.querySelectorAll("[data-prato-card]").forEach((card) => {
                const qtyValue = card.querySelector("[data-card-qty-value]");
                if (!qtyValue) return;
                const dish = JSON.parse(card.dataset.prato || "{}");
                const badge = qtyValue.closest(".dish-qty-badge");
                ensureVariationQuickControls(card, dish);
                const quantity = getCartQuantityForDish(dish);
                const wasEmpty = badge?.classList.contains("is-empty");
                const decrementButton = badge?.querySelector("[data-card-qty-change='-1']");
                qtyValue.textContent = String(quantity);
                badge?.classList.toggle("is-empty", quantity <= 0);
                decrementButton?.setAttribute("tabindex", quantity <= 0 ? "-1" : "0");
                decrementButton?.setAttribute("aria-hidden", quantity <= 0 ? "true" : "false");
                if (badge?.dataset.qtyReady === "true" && wasEmpty && quantity > 0) {
                    if (badge._morphTimer) clearTimeout(badge._morphTimer);
                    badge.classList.remove("is-morphing");
                    void badge.offsetWidth;
                    badge.classList.add("is-morphing");
                    badge._morphTimer = window.setTimeout(() => {
                        badge.classList.remove("is-morphing");
                    }, 520);
                }
                if (badge) badge.dataset.qtyReady = "true";
                card.querySelectorAll("[data-card-variation-row]").forEach((row) => {
                    const variation = normalizeVariationName(row.getAttribute("data-card-variation-row"));
                    const variationBadge = row.querySelector(".dish-variation-qty");
                    const variationQtyValue = row.querySelector("[data-card-variation-qty-value]");
                    const variationDecrementButton = row.querySelector("[data-card-variation-qty-change='-1']");
                    const variationQuantity = getCartQuantityForDishVariation(dish, variation);
                    const wasVariationEmpty = variationBadge?.classList.contains("is-empty");
                    if (variationQtyValue) variationQtyValue.textContent = String(variationQuantity);
                    row.classList.toggle("has-quantity", variationQuantity > 0);
                    variationBadge?.classList.toggle("is-empty", variationQuantity <= 0);
                    variationDecrementButton?.setAttribute("tabindex", variationQuantity <= 0 ? "-1" : "0");
                    variationDecrementButton?.setAttribute("aria-hidden", variationQuantity <= 0 ? "true" : "false");
                    if (variationBadge?.dataset.qtyReady === "true" && wasVariationEmpty && variationQuantity > 0) {
                        if (variationBadge._morphTimer) clearTimeout(variationBadge._morphTimer);
                        variationBadge.classList.remove("is-morphing");
                        void variationBadge.offsetWidth;
                        variationBadge.classList.add("is-morphing");
                        variationBadge._morphTimer = window.setTimeout(() => {
                            variationBadge.classList.remove("is-morphing");
                        }, 520);
                    }
                    if (variationBadge) variationBadge.dataset.qtyReady = "true";
                });
            });
        }

        function incrementCardVariationCartItem(dish, variation, delta) {
            const targetKey = cartItemKey({ ...normalizeCatalogCartFields(dish), variacao: variation });
            const cart = getCart();
            if (delta > 0) {
                addDishToCart(buildCardCartItem(dish, delta, variation));
                syncCardQuantityBadges();
                return true;
            }

            const simpleIndex = cart.findIndex((item) => cartItemKey(item) === targetKey && !item.observacao);
            let fallbackIndex = -1;
            for (let index = cart.length - 1; index >= 0; index -= 1) {
                if (cartItemKey(cart[index]) === targetKey) {
                    fallbackIndex = index;
                    break;
                }
            }
            const index = simpleIndex >= 0 ? simpleIndex : fallbackIndex;
            if (index < 0) return false;

            const removedItem = cart[index];
            const nextQuantity = Number(cart[index].quantidade || 0) - 1;
            if (nextQuantity > 0) {
                cart[index].quantidade = nextQuantity;
            } else {
                cart.splice(index, 1);
            }
            saveCart(cart);
            syncCardQuantityBadges();
            syncMenuPromo();
            trackMetricEvent("remove_from_cart", {
                item_type: cartItemType(removedItem),
                item_id: removedItem.item_id || removedItem.prato_id || removedItem.adicional_id || removedItem.bebida_id || "",
                cart_items_count: 1,
                metadata: { origem: "cardapio", variacao: removedItem.variacao || "" },
            });
            return true;
        }

        function incrementCardCartItem(dish, delta) {
            const normalizedDish = normalizeCatalogCartFields(dish);
            const key = cartItemBaseKey(normalizedDish);
            const cart = getCart();

            if (delta > 0) {
                if (parseDishVariations(dish).length > 1) {
                    openModal(dish);
                    return false;
                }
                addDishToCart(buildCardCartItem(dish, delta));
                syncCardQuantityBadges();
                return true;
            }

            const simpleIndex = cart.findIndex((item) => cartItemBaseKey(item) === key && !item.observacao);
            let fallbackIndex = -1;
            for (let index = cart.length - 1; index >= 0; index -= 1) {
                if (cartItemBaseKey(cart[index]) === key) {
                    fallbackIndex = index;
                    break;
                }
            }
            const index = simpleIndex >= 0 ? simpleIndex : fallbackIndex;
            if (index < 0) return false;

            const removedItem = cart[index];
            const nextQuantity = Number(cart[index].quantidade || 0) - 1;
            if (nextQuantity > 0) {
                cart[index].quantidade = nextQuantity;
            } else {
                cart.splice(index, 1);
            }
            saveCart(cart);
            syncCardQuantityBadges();
            syncMenuPromo();
            trackMetricEvent("remove_from_cart", {
                item_type: cartItemType(removedItem),
                item_id: removedItem.item_id || removedItem.prato_id || removedItem.adicional_id || removedItem.bebida_id || "",
                cart_items_count: 1,
                metadata: { origem: "cardapio", variacao: removedItem.variacao || "" },
            });
            return true;
        }

        function getModalCartQuantity() {
            if (!currentDish) return 0;
            return selectedVariation
                ? getCartQuantityForDishVariation(currentDish, selectedVariation)
                : getCartQuantityForDish(currentDish);
        }

        function syncModalQuantity() {
            if (!quantityDisplay || !modalQuantityBadge) return;
            const modalQuantity = getModalCartQuantity();
            quantityDisplay.textContent = String(modalQuantity);
            modalQuantityBadge.classList.toggle("is-empty", modalQuantity <= 0);
        }

        function buildModalCartItem(quantityToAdd = 1) {
            if (!currentDish) return null;
            const currentType = currentDish.tipo || "prato";
            return {
                tipo: currentType,
                item_id: currentDish.id,
                prato_id: currentType === "prato" ? currentDish.id : undefined,
                adicional_id: currentType === "adicional" ? currentDish.id : undefined,
                bebida_id: currentType === "bebida" ? currentDish.id : undefined,
                nome: currentDish.nome,
                preco: parsePrice(currentDish.preco),
                quantidade: Math.max(1, Number(quantityToAdd || 1)),
                variacao: selectedVariation,
                observacao: obs.value.trim(),
                imagem: currentDish.imagem || placeholderImage,
            };
        }

        function animateQuantityNumber(trigger, delta, changed = true) {
            const badge = trigger?.closest(".dish-qty-badge");
            const value = badge?.querySelector("[data-card-qty-value], [data-card-variation-qty-value]");
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

        function animateAddFeedback(button, quantityAdded, sourceRectOverride = null) {
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

            const sourceRect = sourceRectOverride || button.getBoundingClientRect();
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
            const variations = parseDishVariations(dish);
            selectedVariation = variations.length === 1 ? variations[0] : "";
            obs.value = "";
            image.src = dish.imagem;
            image.alt = dish.nome;
            name.textContent = dish.nome;
            description.textContent = dish.descricao || "";
            price.textContent = dish.preco_formatado || "Preço sob consulta";
            if (variationField && variationOptions) {
                variationField.classList.toggle("hidden", !variations.length);
                variationOptions.innerHTML = variations
                    .map((variation, index) => {
                        const checked = variation === selectedVariation || (!selectedVariation && index === 0);
                        if (checked) selectedVariation = variation;
                        return `
                            <label class="dish-variation-chip">
                                <input type="radio" name="modal-variacao" value="${escapeHtml(variation)}" ${checked ? "checked" : ""}>
                                <span>${escapeHtml(variation)}</span>
                            </label>
                        `;
                    })
                    .join("");
            }
            syncModalQuantity();
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
        variationOptions?.addEventListener("change", (event) => {
            const input = event.target.closest("input[name='modal-variacao']");
            if (input) {
                selectedVariation = normalizeVariationName(input.value);
                syncModalQuantity();
            }
        });

        document.querySelector("[data-qty-minus]")?.addEventListener("click", function (event) {
            if (!currentDish) return;
            const changed = selectedVariation
                ? incrementCardVariationCartItem(currentDish, selectedVariation, -1)
                : incrementCardCartItem(currentDish, -1);
            syncModalQuantity();
            animateQuantityNumber(event.currentTarget, -1, changed);
        });

        document.querySelector("[data-qty-plus]")?.addEventListener("click", function (event) {
            if (!currentDish) return;
            const incomingItem = buildModalCartItem(1);
            if (!incomingItem) return;
            addDishToCart(incomingItem);
            syncCardQuantityBadges();
            syncModalQuantity();
            animateQuantityNumber(event.currentTarget, 1, true);
            animateAddFeedback(event.currentTarget, 1);
        });

        document.querySelectorAll("[data-prato-card]").forEach((card) => {
            const qtyValue = card.querySelector("[data-card-qty-value]");
            const dish = JSON.parse(card.dataset.prato || "{}");
            if (!qtyValue || !dish.id) return;

            card.addEventListener("click", (event) => {
                if (event.target.closest("button, a, input, textarea, select, [data-card-qty-change], [data-variation-quick-controls]")) return;
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

            card.addEventListener("click", (event) => {
                const variationBadge = event.target.closest(".dish-variation-qty");
                const button = event.target.closest("[data-card-variation-qty-change]");
                if (!button && !variationBadge?.classList.contains("is-empty")) return;
                event.preventDefault();
                const delta = button ? Number(button.getAttribute("data-card-variation-qty-change")) : 1;
                const variation = normalizeVariationName(
                    button?.getAttribute("data-card-variation") ||
                    variationBadge?.querySelector("[data-card-variation-qty-change='1']")?.getAttribute("data-card-variation")
                );
                const feedbackAnchor = button || variationBadge?.querySelector("[data-card-variation-qty-change='1']");
                const feedbackAnchorRect = feedbackAnchor?.getBoundingClientRect?.() || null;
                const changed = incrementCardVariationCartItem(dish, variation, delta);
                animateQuantityNumber(button || variationBadge, delta, changed);
                if (changed && delta > 0) animateAddFeedback(feedbackAnchor || variationBadge, delta, feedbackAnchorRect);
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
        const numeroField = profileForm.querySelector("[name='numero']");
        const numeroFeedback = document.getElementById("profile-numero-feedback");

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
            clearNumeroAttention();
            openModal();
            showEditorPanel();
            addressController?.ensureMapReady?.().then(() => {
                addressController?.refreshMap?.();
                if (mode === "create") {
                    addressController?.startCurrentLocation?.();
                } else {
                    profileForm.querySelector("[name='numero']")?.focus();
                }
            });
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

        function clearNumeroAttention() {
            numeroField?.classList.remove("field-needs-attention");
            numeroFeedback?.classList.add("hidden");
            numeroField?.removeAttribute("aria-invalid");
        }

        function showNumeroAttention() {
            numeroField?.classList.add("field-needs-attention");
            numeroField?.setAttribute("aria-invalid", "true");
            numeroFeedback?.classList.remove("hidden");
            numeroField?.focus();
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

            const selectedProfile = profiles.find((profile) => profile.id === selectedProfileId);
            if (selectedProfile) fetchProfileEta(selectedProfile);
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
            const profile = readProfileFromEditor();
            if (!profile.numero) {
                showNumeroAttention();
                return;
            }
            clearNumeroAttention();
            const saved = upsertCheckoutProfile(profile);
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

        numeroField?.addEventListener("input", clearNumeroAttention);

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
        try {
            if (sessionStorage.getItem(checkoutAutoAddressKey) === "1" && !getSavedCheckoutProfiles().length) {
                sessionStorage.removeItem(checkoutAutoAddressKey);
                window.setTimeout(() => openEditor("create", null), 80);
            }
        } catch (error) {
            // Sem sessionStorage, o fluxo manual continua disponivel.
        }
    }

    function initAddressEditor(form, options = {}) {
        const noopApi = {
            applyResolvedAddress() {},
            clearResolvedAddress() {},
            refreshMap() {},
        };
        const root = options.root || form?.closest("[data-address-editor-root]") || document;
        const byId = (id) => root?.querySelector?.(`#${id}`) || document.getElementById(id);

        const ruaInput = form.querySelector("input[name='rua']");
        const numeroInput = form.querySelector("input[name='numero']");
        const bairroInput = form.querySelector("input[name='bairro']");
        const cidadeInput = form.querySelector("input[name='cidade']");
        const estadoInput = form.querySelector("input[name='estado']");
        const latitudeInput = form.querySelector("input[name='latitude']");
        const longitudeInput = form.querySelector("input[name='longitude']");
        const enderecoFormatadoInput = form.querySelector("input[name='endereco_formatado']");
        const geocodeTipoInput = form.querySelector("input[name='geocode_tipo']");
        const geocodePrecisionInput = form.querySelector("input[name='geocode_precision']");
        const feedback = byId("address-feedback");
        const coordsWarning = byId("coords-warning");
        const resolutionCard = byId("address-resolution-card");
        const resolutionBadge = byId("address-resolution-badge");
        const resolutionLabel = byId("address-resolution-label");
        const resolutionMeta = byId("address-resolution-meta");
        const resolvedStreetDisplay = byId("resolved-street-display");
        const resolvedDistrictDisplay = byId("resolved-district-display");
        const mapStep = byId("address-step-map");
        const detailsStep = byId("address-step-details");
        const detailsStepMarker = byId("address-step-marker-details");
        const backToMapButton = byId("address-step-back-to-map");
        const previewMapRoot = byId("address-preview-map");
        const previewTitle = byId("address-preview-title");
        const previewSubtitle = byId("address-preview-subtitle");
        const mapRoot = byId("address-map");
        const mapShell = mapRoot?.closest(".address-map-shell");
        const mapFeedback = byId("address-map-feedback");
        const useLocationButton = byId("use-current-location");
        const confirmMapCenterButton = byId("confirm-map-center");
        const checkoutRoot = document.querySelector("[data-page='checkout']");
        const isOperatorCheckout = options.isOperatorCheckout ?? checkoutRoot?.dataset.operatorCheckout === "true";
        const operatorSearch = root?.querySelector?.("[data-operator-address-search]") || document.querySelector("[data-operator-address-search]");
        const operatorAddressInput = byId("operator-address-query");
        const operatorDistrictInput = byId("operator-district-query");
        const operatorAddressOptionsButton = byId("operator-address-options");
        const operatorAddressLoading = byId("operator-address-loading");
        const operatorAddressSuggestions = byId("operator-address-suggestions");
        const operatorAdjustMapButton = byId("operator-adjust-map");
        const operatorUseTypedAddressButton = byId("operator-use-typed-address");
        const backToTextSearchButton = byId("address-back-to-text-search");

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

        let shouldShowCoordsWarning = false;
        let mapInstance = null;
        let previewMapInstance = null;
        let isProgrammaticMapMove = false;
        let googleGeocoder = null;
        let googlePlacesAutocomplete = null;
        let googlePlacesDetails = null;
        let googlePlacesDetailsNode = null;
        let currentProvider = hasGoogleMapsProvider() ? "google" : "";
        let addressPointConfirmed = false;
        let isRequestingCurrentLocation = false;
        let operatorSearchRequestId = 0;
        let operatorSearchTimer = null;
        let operatorSelectedAddress = null;

        if (isOperatorCheckout && operatorSearch) {
            mapStep.classList.add("is-operator-search-mode");
        }

        function showFeedback(message, warning = false) {
            feedback.textContent = message;
            feedback.classList.toggle("hidden", !message);
            feedback.classList.toggle("is-warning", warning);
        }

        function showMapFeedback(message, warning = false) {
            mapFeedback.textContent = message;
            mapFeedback.classList.toggle("is-warning", warning);
        }

        function setOperatorSearchLoading(isLoading) {
            if (!operatorAddressLoading) return;
            operatorAddressLoading.classList.toggle("hidden", !isLoading);
        }

        function hideOperatorSuggestions() {
            operatorAddressSuggestions?.classList.add("hidden");
            if (operatorAddressSuggestions) operatorAddressSuggestions.innerHTML = "";
        }

        function renderOperatorSuggestions(items) {
            if (!operatorAddressSuggestions) return;
            if (!Array.isArray(items) || !items.length) {
                operatorAddressSuggestions.innerHTML = '<div class="address-suggestion-empty">Nenhuma opcao encontrada.</div>';
                operatorAddressSuggestions.classList.remove("hidden");
                return;
            }
            operatorAddressSuggestions.innerHTML = items.map((item, index) => {
                const title = item.street || item.label || "Endereco encontrado";
                const cityState = [item.city, item.state].filter(Boolean).join(" - ");
                const district = hasKnownDistrict(item) ? item.district : "Setor pendente";
                return `
                    <button type="button" class="address-suggestion-item" data-operator-address-index="${index}">
                        <strong>${escapeHtml(title)}</strong>
                        <small>${escapeHtml([district, cityState].filter(Boolean).join(" | ") || item.label || "")}</small>
                    </button>
                `;
            }).join("");
            operatorAddressSuggestions.classList.remove("hidden");
        }

        async function ensureGoogleGeocoder() {
            if (!hasGoogleMapsProvider()) {
                throw new Error("Google Maps nao configurado.");
            }
            await loadGoogleMapsAssets();
            const { Geocoder } = await google.maps.importLibrary("geocoding");
            if (!googleGeocoder) googleGeocoder = new Geocoder();
            currentProvider = "google";
            return googleGeocoder;
        }

        async function ensureGooglePlaces() {
            if (!hasGoogleMapsProvider()) {
                throw new Error("Google Maps nao configurado.");
            }
            await loadGoogleMapsAssets();
            await google.maps.importLibrary("places");
            if (!googlePlacesAutocomplete) {
                googlePlacesAutocomplete = new google.maps.places.AutocompleteService();
            }
            if (!googlePlacesDetails) {
                googlePlacesDetailsNode = googlePlacesDetailsNode || document.createElement("div");
                googlePlacesDetails = new google.maps.places.PlacesService(googlePlacesDetailsNode);
            }
            currentProvider = "google";
            return { autocomplete: googlePlacesAutocomplete, details: googlePlacesDetails };
        }

        function getPlacePredictions(service, request) {
            return new Promise((resolve, reject) => {
                service.getPlacePredictions(request, (predictions, status) => {
                    if (status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS) {
                        resolve([]);
                        return;
                    }
                    if (status !== google.maps.places.PlacesServiceStatus.OK) {
                        reject(new Error(status));
                        return;
                    }
                    resolve(predictions || []);
                });
            });
        }

        function hasKnownDistrict(item) {
            const district = normalizeText(item?.district || "");
            return Boolean(district && district !== "setor nao identificado" && district !== "setor pendente");
        }

        function googleSearchErrorMessage(error) {
            const message = String(error?.message || error || "").trim();
            if (message.includes("REQUEST_DENIED") || message.includes("ApiNotActivated") || message.includes("RefererNotAllowed")) {
                return "Busca textual indisponivel: habilite a Places API na mesma chave do Google Maps.";
            }
            if (message.includes("OVER_QUERY_LIMIT")) {
                return "Busca textual indisponivel: limite de uso da Places API atingido.";
            }
            return `Busca textual do Google Maps indisponivel${message ? ` (${message})` : ""}.`;
        }

        function getPlaceDetails(service, placeId) {
            return new Promise((resolve) => {
                service.getDetails(
                    {
                        placeId,
                        fields: ["address_components", "formatted_address", "geometry", "name", "types"],
                        language: googleMapsLanguage,
                    },
                    (place, status) => {
                        if (status !== google.maps.places.PlacesServiceStatus.OK || !place) {
                            resolve(null);
                            return;
                        }
                        resolve(place);
                    }
                );
            });
        }

        function operatorSuggestionScore(item, query) {
            const normalizedQuery = normalizeText(query);
            const normalizedTitle = normalizeText(item?.street || item?.label || "");
            const normalizedLabel = normalizeText(item?.label || "");
            const tokens = normalizedQuery.split(/\s+/).filter((token) => token.length >= 3);
            let score = 0;

            if (normalizedTitle === normalizedQuery) score += 120;
            if (normalizedTitle.includes(normalizedQuery)) score += 90;
            if (normalizedLabel.includes(normalizedQuery)) score += 45;
            if (tokens.length && tokens.every((token) => normalizedTitle.includes(token))) score += 70;
            tokens.forEach((token) => {
                if (normalizedTitle.includes(token)) score += 18;
                else if (normalizedLabel.includes(token)) score += 8;
            });
            if (hasKnownDistrict(item)) score += 18;
            if (operatorDistrictInput?.value && normalizeText(item?.district).includes(normalizeText(operatorDistrictInput.value))) score += 55;
            if (normalizeText(item?.city).includes("rio verde")) score += 12;
            if (normalizeText(item?.state) === "go") score += 6;
            if (item?.source_method === "geocode") score += 18;
            if (item?.precision === "exact") score += 12;
            if (item?.precision === "approximate") score += 4;
            return score;
        }

        async function enrichSuggestionDistricts(items) {
            const limited = items.slice(0, 8);
            return Promise.all(
                limited.map(async (item) => {
                    if (!item?.lat || !item?.lng || hasKnownDistrict(item)) return item;
                    const resolved = await reverseGeocodeWithGoogle(item.lat, item.lng);
                    if (!resolved?.district) return item;
                    return {
                        ...item,
                        district: resolved.district,
                        city: item.city || resolved.city,
                        state: item.state || resolved.state,
                    };
                })
            );
        }

        function uniqueOperatorSuggestions(items) {
            const seen = new Set();
            return items.filter((item) => {
                if (!item) return false;
                const signature = [
                    normalizeText(item.street || item.label),
                    normalizeText(item.district),
                    Number(item.lat || 0).toFixed(5),
                    Number(item.lng || 0).toFixed(5),
                ].join("|");
                if (seen.has(signature)) return false;
                seen.add(signature);
                return true;
            });
        }

        function buildOperatorGeocodeQueries(query, district, city, state) {
            const normalizedQuery = String(query || "").trim();
            const normalizedDistrict = String(district || "").trim();
            const baseStreet = normalizeText(normalizedQuery).startsWith("rua ")
                ? normalizedQuery
                : `Rua ${normalizedQuery}`;
            const variants = [normalizedQuery, baseStreet];
            const tokens = normalizeText(normalizedQuery).split(/\s+/).filter(Boolean);
            if (tokens.length === 2 && tokens[0] === "jose" && !tokens.includes("souza")) {
                variants.unshift(`Rua ${normalizedQuery} de Souza`);
            }
            const suffixes = [
                [normalizedDistrict, city, state, "Brasil"].filter(Boolean).join(", "),
                [city, state, "Brasil"].filter(Boolean).join(", "),
            ].filter(Boolean);
            const queries = [];
            variants.forEach((variant) => {
                suffixes.forEach((suffix) => {
                    queries.push([variant, suffix].filter(Boolean).join(", "));
                });
            });
            return [...new Set(queries)];
        }

        async function fetchGeocodeSuggestions(geocoder, queries, state, city) {
            const responses = await Promise.all(
                queries.map(async (address) => {
                    try {
                        return await geocoder.geocode({
                            address,
                            componentRestrictions: {
                                country: "BR",
                                administrativeArea: state,
                                locality: city,
                            },
                            language: googleMapsLanguage,
                        });
                    } catch (error) {
                        return null;
                    }
                })
            );
            return responses
                .flatMap((response) => response?.results || [])
                .map((result) => {
                    const location = result.geometry?.location;
                    if (!location) return null;
                    const mapped = mapGoogleResult(result, location.lat(), location.lng());
                    return mapped ? { ...mapped, source_method: "geocode" } : null;
                })
                .filter(Boolean);
        }

        async function fetchOperatorAddressSuggestions(query, extraParams = {}) {
            const normalizedQuery = String(query || "").trim();
            if (normalizedQuery.length < 3) return [];
            const city = extraParams.cidade || cidadeInput.value || "Rio Verde";
            const state = extraParams.estado || estadoInput.value || "GO";
            const selectedDistrict = extraParams.bairro || operatorDistrictInput?.value || "";
            let placesError = null;
            let candidates = [];

            const geocoder = await ensureGoogleGeocoder();
            const geocodeQueries = buildOperatorGeocodeQueries(normalizedQuery, selectedDistrict, city, state);
            candidates = candidates.concat(await fetchGeocodeSuggestions(geocoder, geocodeQueries, state, city));

            try {
                const { autocomplete, details } = await ensureGooglePlaces();
                const predictions = await getPlacePredictions(autocomplete, {
                    input: [normalizedQuery, selectedDistrict, city, state].filter(Boolean).join(", "),
                    componentRestrictions: { country: "br" },
                    locationBias: {
                        center: { lat: -17.7923, lng: -50.9192 },
                        radius: 18000,
                    },
                    types: ["address"],
                    language: googleMapsLanguage,
                });
                const detailed = await Promise.all(
                    predictions.slice(0, 6).map(async (prediction) => {
                        const place = await getPlaceDetails(details, prediction.place_id);
                        const location = place?.geometry?.location;
                        if (!place || !location) return null;
                        return mapGoogleResult(place, location.lat(), location.lng());
                    })
                );
                const filtered = detailed.filter((item) => {
                    if (!item) return false;
                    const itemCity = normalizeText(item.city);
                    const itemState = normalizeText(item.state);
                    return itemCity.includes(normalizeText(city)) && (itemState === normalizeText(state) || itemState.includes("goias"));
                });

                candidates = candidates.concat(filtered.map((item) => ({ ...item, source_method: "places" })));
            } catch (error) {
                placesError = error;
            }

            const enriched = await enrichSuggestionDistricts(uniqueOperatorSuggestions(candidates));
            const results = enriched
                .sort((a, b) => operatorSuggestionScore(b, normalizedQuery) - operatorSuggestionScore(a, normalizedQuery))
                .slice(0, 6);
            if (!results.length && placesError) throw placesError;
            return results;
        }

        async function runOperatorAddressSearch(query) {
            const requestId = ++operatorSearchRequestId;
            setOperatorSearchLoading(true);
            try {
                const items = await fetchOperatorAddressSuggestions(query);
                if (requestId !== operatorSearchRequestId) return;
                renderOperatorSuggestions(items);
                operatorAddressSuggestions?.querySelectorAll("[data-operator-address-index]").forEach((button) => {
                    button.addEventListener("click", async () => {
                        const item = items[Number(button.dataset.operatorAddressIndex)];
                        await selectOperatorAddress(item);
                    });
                });
            } catch (error) {
                showFeedback(googleSearchErrorMessage(error), true);
            } finally {
                if (requestId === operatorSearchRequestId) setOperatorSearchLoading(false);
            }
        }

        async function showOperatorStreetOptions() {
            const district = String(operatorDistrictInput?.value || "").trim();
            const query = String(operatorAddressInput?.value || "").trim();
            if (!district) {
                showFeedback("Escolha um setor para listar ruas relacionadas.", true);
                operatorDistrictInput?.focus();
                return;
            }
            showFeedback("", false);
            await runOperatorAddressSearch(query || "Rua");
            operatorAddressInput?.focus();
        }

        async function useTypedOperatorAddress() {
            const typedStreet = String(operatorAddressInput?.value || "").trim();
            const typedDistrict = String(operatorDistrictInput?.value || "").trim();
            if (typedStreet.length < 2) {
                showFeedback("Digite o nome da rua ou referencia antes de continuar.", true);
                operatorAddressInput?.focus();
                return;
            }
            await ensureMapReady();
            hideOperatorSuggestions();
            let centerItem = null;
            const geocodeAddress = async (address) => {
                const geocoder = await ensureGoogleGeocoder();
                const response = await geocoder.geocode({
                    address,
                    componentRestrictions: {
                        country: "BR",
                        administrativeArea: estadoInput.value || "GO",
                        locality: cidadeInput.value || "Rio Verde",
                    },
                    language: googleMapsLanguage,
                });
                const result = response?.results?.[0];
                const location = result?.geometry?.location;
                return location ? mapGoogleResult(result, location.lat(), location.lng()) : null;
            };
            try {
                const locationQuery = typedDistrict
                    ? [typedDistrict, cidadeInput.value || "Rio Verde", estadoInput.value || "GO", "Brasil"].filter(Boolean).join(", ")
                    : [typedStreet, cidadeInput.value || "Rio Verde", estadoInput.value || "GO", "Brasil"].filter(Boolean).join(", ");
                centerItem = await geocodeAddress(locationQuery);
            } catch (error) {
                centerItem = null;
            }
            const payload = {
                ...(centerItem || {}),
                label: typedStreet,
                street: typedStreet,
                district: typedDistrict || centerItem?.district || "",
                city: cidadeInput.value || centerItem?.city || "Rio Verde",
                state: estadoInput.value || centerItem?.state || "GO",
                lat: centerItem?.lat || -17.7923,
                lng: centerItem?.lng || -50.9192,
                type: centerItem?.type || "manual",
                precision: centerItem?.precision || "manual",
            };
            operatorSelectedAddress = payload;
            if (typedDistrict) {
                applyResolvedAddress(payload, { confirmed: true, updateMap: true });
                showFeedback("Texto do atendente mantido com a localizacao do setor. Informe o numero para salvar.", false);
                return;
            }
            applyResolvedAddress(payload, { confirmed: false, updateMap: true });
            mapStep.classList.add("is-map-visible");
            showMapFeedback("Texto mantido. Posicione o pin no local correto e confirme.");
            setTimeout(() => mapInstance?.invalidateSize?.(), 80);
            showFeedback("Texto do atendente mantido. Confirme o pin no mapa para continuar.", true);
        }

        async function enrichOperatorAddressFromCoordinates(item) {
            if (!item?.lat || !item?.lng || hasKnownDistrict(item)) return item;
            const resolved = await reverseGeocodeWithGoogle(item.lat, item.lng);
            if (!resolved?.district) return item;
            return {
                ...item,
                district: resolved.district,
                city: item.city || resolved.city,
                state: item.state || resolved.state,
                type: item.type || resolved.type,
                precision: item.precision || resolved.precision,
                precision_label: item.precision_label || resolved.precision_label,
            };
        }

        async function selectOperatorAddress(item) {
            if (!item) return;
            operatorSelectedAddress = item;
            operatorAddressInput.value = item.label || item.street || operatorAddressInput.value;
            hideOperatorSuggestions();
            const enriched = await enrichOperatorAddressFromCoordinates(item);
            operatorSelectedAddress = enriched;
            if (hasKnownDistrict(enriched)) {
                applyResolvedAddress(enriched, { confirmed: true, updateMap: true });
                showFeedback("Endereco selecionado. Informe o numero para salvar.", false);
                return;
            }
            await ensureMapReady();
            applyResolvedAddress(enriched, { confirmed: false, updateMap: true });
            mapStep.classList.add("is-map-visible");
            showMapFeedback("Rua encontrada. Confirme o pin no mapa para preencher o setor.");
            setTimeout(async () => {
                mapInstance?.invalidateSize?.();
                await syncAddressFromMapCenter({ confirmed: false });
            }, 120);
            showFeedback("Confirme o ponto no mapa para completar o setor antes de salvar.", true);
        }

        async function refineOperatorAddressWithNumber() {
            if (!isOperatorCheckout || !operatorSelectedAddress || !numeroInput) return;
            const number = String(numeroInput.value || "").trim();
            const street = String(ruaInput.value || operatorSelectedAddress.street || "").trim();
            if (!number || !street) return;
            const bairro = String(bairroInput.value || operatorSelectedAddress.district || "").trim();
            const query = [street, number, bairro, cidadeInput.value || "Rio Verde", estadoInput.value || "GO"].filter(Boolean).join(", ");
            try {
                const items = await fetchOperatorAddressSuggestions(query, { bairro });
                const best = items.find((item) => String(item.number || "").trim() === number) || items[0];
                if (!best) return;
                operatorSelectedAddress = {
                    ...best,
                    street: best.street || street,
                    district: best.district || bairro,
                    city: best.city || cidadeInput.value || "Rio Verde",
                    state: best.state || estadoInput.value || "GO",
                };
                applyResolvedAddress(operatorSelectedAddress, { confirmed: true, updateMap: true });
            } catch (error) {
                showFeedback("Endereco mantido pela rua selecionada. Use Ajustar no mapa se precisar.", true);
            }
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

        function returnToOperatorTextSearch() {
            if (!isOperatorCheckout) return;
            addressPointConfirmed = false;
            showDetailsStep(false);
            mapStep.classList.remove("is-map-visible");
            hideOperatorSuggestions();
            window.clearTimeout(operatorSearchTimer);
            showFeedback("", false);
            showMapFeedback("");
            window.setTimeout(() => operatorAddressInput?.focus?.(), 60);
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
            const precision = resolveGooglePrecision(result.types);

            return {
                label: result.formatted_address || street || "Ponto confirmado no mapa",
                street,
                district,
                city,
                state,
                lat: Number(lat),
                lng: Number(lng),
                type: primaryType,
                precision,
                precision_label: resolutionTone(precision).label,
            };
        }

        async function reverseGeocodeWithGoogle(lat, lng) {
            try {
                await ensureGoogleGeocoder();
                const response = await googleGeocoder.geocode({
                    location: { lat: Number(lat), lng: Number(lng) },
                    language: googleMapsLanguage,
                });
                const mappedResults = (response?.results || [])
                    .map((result) => mapGoogleResult(result, lat, lng))
                    .filter(Boolean);
                const result =
                    mappedResults.find((item) => hasKnownDistrict(item) && item.precision === "exact") ||
                    mappedResults.find((item) => hasKnownDistrict(item)) ||
                    mappedResults[0];
                return result || null;
            } catch (error) {
                return null;
            }
        }

        async function reverseGeocodeCenter(lat, lng) {
            showMapFeedback("Atualizando endereco pelo centro do mapa...");
            return reverseGeocodeWithGoogle(lat, lng);
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
            if (!hasGoogleMapsProvider()) {
                showMapFeedback("Google Maps nao configurado. Cadastre a chave em Ajustes > Google Maps.", true);
                return;
            }

            try {
                await loadGoogleMapsAssets();
                const { Map } = await google.maps.importLibrary("maps");
                await ensureGoogleGeocoder();

                const googleMap = new Map(mapRoot, {
                    center: { lat: -17.7923, lng: -50.9192 },
                    zoom: 14,
                    mapTypeControl: false,
                    streetViewControl: false,
                    fullscreenControl: false,
                    clickableIcons: false,
                });
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

                showMapFeedback("Google Maps pronto. Mova o mapa ate o pin central ficar no local exato da entrega.");
            } catch (error) {
                showMapFeedback("Nao foi possivel carregar o Google Maps. Verifique a chave em Ajustes.", true);
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

        useLocationButton.addEventListener("click", async () => {
            await ensureMapReady();
            requestCurrentLocation();
        });

        confirmMapCenterButton.addEventListener("click", async () => {
            await ensureMapReady();
            await syncAddressFromMapCenter({ confirmed: true });
        });

        operatorAddressInput?.addEventListener("input", () => {
            const query = operatorAddressInput.value.trim();
            operatorSelectedAddress = null;
            window.clearTimeout(operatorSearchTimer);
            if (query.length < 3) {
                hideOperatorSuggestions();
                return;
            }
            operatorSearchTimer = window.setTimeout(() => runOperatorAddressSearch(query), 260);
        });

        operatorAddressInput?.addEventListener("focus", () => {
            const query = operatorAddressInput.value.trim();
            if (query.length >= 3 && operatorAddressSuggestions?.classList.contains("hidden")) {
                runOperatorAddressSearch(query);
            }
        });

        operatorDistrictInput?.addEventListener("input", () => {
            window.clearTimeout(operatorSearchTimer);
            hideOperatorSuggestions();
        });

        operatorDistrictInput?.addEventListener("focus", () => {
            window.clearTimeout(operatorSearchTimer);
            hideOperatorSuggestions();
        });

        operatorAddressOptionsButton?.addEventListener("click", async () => {
            await showOperatorStreetOptions();
        });

        operatorUseTypedAddressButton?.addEventListener("click", async () => {
            await useTypedOperatorAddress();
        });

        operatorAddressInput?.addEventListener("keydown", async (event) => {
            if (event.key !== "Enter") return;
            if (!isOperatorCheckout) return;
            event.preventDefault();
            await useTypedOperatorAddress();
        });

        document.addEventListener("click", (event) => {
            if (!operatorSearch?.contains(event.target)) {
                hideOperatorSuggestions();
            }
        });

        numeroInput?.addEventListener("change", refineOperatorAddressWithNumber);
        numeroInput?.addEventListener("blur", refineOperatorAddressWithNumber);

        operatorAdjustMapButton?.addEventListener("click", async () => {
            await ensureMapReady();
            mapStep.classList.add("is-map-visible");
            showMapFeedback("Ajuste o ponto no mapa e confirme.");
            setTimeout(() => mapInstance?.invalidateSize?.(), 80);
        });

        backToMapButton.addEventListener("click", async () => {
            await ensureMapReady();
            addressPointConfirmed = false;
            showDetailsStep(false);
            mapStep.classList.add("is-map-visible");
            showMapFeedback("Ajuste o ponto no mapa e confirme novamente.");
            setTimeout(() => mapRoot.scrollIntoView({ behavior: "smooth", block: "center" }), 40);
        });

        backToTextSearchButton?.addEventListener("click", returnToOperatorTextSearch);

        form.addEventListener("submit", () => {
            shouldShowCoordsWarning = true;
            syncCoordsWarning();
        });

        let mapReadyPromise = null;

        function ensureMapReady() {
            if (!mapReadyPromise) {
                mapReadyPromise = initializeMap().then(() => {
                    if (latitudeInput.value && longitudeInput.value) {
                        setMapCenter(latitudeInput.value, longitudeInput.value, 18);
                        setPreviewMapCenter(latitudeInput.value, longitudeInput.value, 17);
                        showMapFeedback("Local carregado a partir das coordenadas salvas.");
                        addressPointConfirmed = false;
                        showDetailsStep(false);
                    }
                });
            }
            return mapReadyPromise;
        }

        updateResolvedDisplay(null);
        renderResolutionState(null);
        syncCoordsWarning();
        showDetailsStep(false);
        return {
            applyResolvedAddress,
            clearResolvedAddress,
            ensureMapReady,
            refreshMap() {
                if (!mapInstance) return;
                setTimeout(() => mapInstance.invalidateSize(), 60);
            },
            async startCurrentLocation() {
                await ensureMapReady();
                requestCurrentLocation();
            },
        };
    }

    window.PRATO_ADDRESS_EDITOR = {
        initAddressEditor,
    };

    function initCheckoutPage() {
        const itemsContainer = document.getElementById("checkout-items");
        const itemsSubtotalElement = document.getElementById("checkout-items-subtotal");
        const itemsSubtotalReviewElement = document.getElementById("checkout-items-subtotal-review");
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
        const couponPayloadInput = document.getElementById("checkout-coupon-code-payload");
        const knownOrderTokensInput = document.getElementById("checkout-known-order-tokens");
        const checkoutKeyInput = document.getElementById("checkout-key");
        const mealPromoReview = document.getElementById("checkout-meal-promo-review");
        const mealPromoReviewValue = document.getElementById("checkout-meal-promo-review-value");
        const couponReview = document.getElementById("checkout-coupon-review");
        const couponReviewValue = document.getElementById("checkout-coupon-review-value");
        const form = document.getElementById("checkout-form");
        const profileForm = document.getElementById("profile-form");
        const stageDelivery = document.getElementById("checkout-stage-delivery");
        const deliveryFields = document.getElementById("checkout-delivery-fields");
        const stagePayment = document.getElementById("checkout-stage-payment");
        const paymentDeliveryOptions = document.getElementById("payment-delivery-options");
        const paymentPixPanel = document.getElementById("payment-pix-panel");
        const paymentFeedback = document.getElementById("checkout-payment-feedback");
        const submitButton = document.getElementById("checkout-submit-button");
        const pixFooterNotice = document.getElementById("pix-copy-footer-notice");
        const checkoutNameInput = document.getElementById("checkout-nome");
        const checkoutAddressSummary = document.getElementById("checkout-address-summary");
        const savedProfileOpenButton = document.getElementById("saved-profile-open");
        const cardapioLink =
            document.querySelector("[data-checkout-cardapio-link]")?.getAttribute("href") ||
            document.querySelector(".context-header .brand-header-logo")?.getAttribute("href") ||
            "/";
        const backToItemsButton = document.getElementById("checkout-back-to-items");
        const stageTriggers = Array.from(document.querySelectorAll("[data-checkout-stage-trigger]"));
        if (!payloadInput || !form) return;

        let selectedShippingFee = Number.parseFloat(shippingValueInput?.value || "0") || 0;
        let appliedCoupon = null;
        let activeStage = "delivery";
        let whatsappSubmitInProgress = false;
        const myOrdersUrl = window.PRATO_CONFIG?.myOrdersUrl || "/meus-pedidos/";

        async function submitOrder(orderForm) {
            if (checkoutKeyInput) checkoutKeyInput.value = getOrCreateCheckoutKey("entrega");
            const response = await fetch(orderForm.action, {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: new FormData(orderForm),
            });
            if (!response.ok) {
                const message = await response.text();
                throw new Error(message || "Nao foi possivel finalizar o pedido.");
            }
            const payload = await response.json();
            if (!payload?.ok || !payload?.pedido?.token) {
                throw new Error("Nao foi possivel confirmar o pedido criado.");
            }
            rememberOrder(payload.pedido);
            clearCheckoutAfterOrder();
            clearCheckoutKey("entrega");
            window.location.href = payload.success_url || myOrdersUrl;
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

        function syncKnownOrderTokensPayload() {
            if (knownOrderTokensInput) {
                knownOrderTokensInput.value = JSON.stringify(getKnownOrderTokens());
            }
        }

        function clearCheckoutFieldHighlights() {
            checkoutAddressSummary?.classList.remove("field-needs-attention");
            savedProfileOpenButton?.classList.remove("field-needs-attention");
            stagePayment?.classList.remove("field-needs-attention");
            stagePayment?.classList.remove("is-payment-missing", "is-payment-method-missing");
            paymentFeedback?.classList.add("hidden");
        }

        function currentItemsTotal() {
            return getCart().reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0);
        }

        function currentMealPromoDiscount() {
            return Math.min(calculateMealPromo(getCart()).discount, currentItemsTotal());
        }

        function clearCoupon(message = "") {
            appliedCoupon = null;
            saveCheckoutCouponCode("");
            if (couponPayloadInput) couponPayloadInput.value = "";
            if (couponReview) couponReview.classList.add("hidden");
            if (couponReviewValue) couponReviewValue.textContent = "- R$ 0,00";
            render();
        }

        async function applyCoupon(codeOverride = "") {
            const code = String(codeOverride || getCheckoutCouponCode() || "").trim();
            if (!code) {
                clearCoupon("Informe um cupom.");
                return;
            }
            const body = new URLSearchParams({
                codigo: code,
                subtotal: Math.max(currentItemsTotal() - currentMealPromoDiscount(), 0).toFixed(2),
                frete: selectedShippingFee.toFixed(2),
            });
            try {
                const response = await fetch(window.PRATO_CONFIG?.couponValidateUrl || "/api/cupom/validar/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-CSRFToken": window.PRATO_CONFIG?.csrfToken || "",
                    },
                    body,
                });
                const data = await response.json();
                if (!data.ok) {
                    clearCoupon(data.message || "Cupom invalido.");
                    return;
                }
                appliedCoupon = {
                    codigo: data.codigo,
                    desconto: Number.parseFloat(data.desconto || "0") || 0,
                };
                saveCheckoutCouponCode(appliedCoupon.codigo);
                if (couponPayloadInput) couponPayloadInput.value = appliedCoupon.codigo;
                render();
            } catch (error) {
                clearCoupon("Nao foi possivel validar o cupom.");
            }
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
            stagePayment?.classList.remove("field-needs-attention");
            stagePayment?.classList.add("is-payment-missing");
            const selectedType = stagePayment?.querySelector("[data-payment-type].is-selected")?.getAttribute("data-payment-type") || "";
            const needsDeliveryMethod = selectedType === "entrega";
            stagePayment?.classList.toggle("is-payment-method-missing", needsDeliveryMethod);
            if (paymentFeedback) {
                paymentFeedback.textContent = needsDeliveryMethod
                    ? "Escolha Dinheiro ou Cartao para pagamento na entrega."
                    : "Escolha uma forma de pagamento para finalizar.";
                paymentFeedback.classList.remove("hidden");
            }
            stagePayment?.scrollIntoView({ behavior: "smooth", block: "center" });
            const target = needsDeliveryMethod
                ? stagePayment?.querySelector("[data-payment-method]")
                : stagePayment?.querySelector("[data-payment-type]");
            window.setTimeout(() => target?.focus?.(), 160);
        }

        function syncCheckoutSubmitReadiness() {
            const label = submitButton?.querySelector("span");
            const helper = submitButton?.querySelector("small");
            const hasItems = getCart().length > 0;
            const hasDelivery = hasCheckoutDeliveryData(form);
            const hasPayment = String(paymentMethodInput?.value || "").trim();
            const ready = Boolean(
                hasItems &&
                hasDelivery &&
                hasPayment
            );
            submitButton?.classList.toggle("is-ready", ready);
            submitButton?.classList.toggle("is-missing-step", hasItems && !ready);

            if (!label || !helper) return;
            if (!hasDelivery) {
                label.textContent = "Cadastre o endereco para continuar";
                helper.textContent = "Toque aqui para escolher ou cadastrar o ponto de entrega";
                return;
            }
            if (!hasPayment) {
                label.textContent = "Escolha a forma de pagamento";
                helper.textContent = "Selecione Pix, dinheiro ou cartao para continuar";
                return;
            }
            label.textContent = "Gerar pedido e abrir WhatsApp";
            helper.textContent = "Toque aqui para enviar seu pedido para nossa equipe";
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
                window.location.href = cardapioLink;
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
            syncKnownOrderTokensPayload();
            if (!cart.length) {
                redirectToCardapio();
                return;
            }

            const itemsTotal = currentItemsTotal();
            const mealPromo = calculateMealPromo(cart);
            const mealPromoDiscount = Math.min(mealPromo.discount, itemsTotal);
            const couponDiscount = Math.min(Number(appliedCoupon?.desconto || 0), Math.max(itemsTotal - mealPromoDiscount, 0));
            const orderTotal = itemsTotal + selectedShippingFee - mealPromoDiscount - couponDiscount;
            if (itemsContainer) itemsContainer.innerHTML = cart.map(buildCartItemMarkup).join("");
            if (itemsSubtotalElement) itemsSubtotalElement.textContent = money(itemsTotal);
            if (itemsSubtotalReviewElement) itemsSubtotalReviewElement.textContent = money(itemsTotal);
            if (totalReviewElement) totalReviewElement.textContent = money(orderTotal);
            if (totalReviewPaymentElement) totalReviewPaymentElement.textContent = money(orderTotal);
            if (mealPromoReview && mealPromoReviewValue) {
                mealPromoReview.classList.toggle("hidden", mealPromoDiscount <= 0);
                mealPromoReviewValue.textContent = `- ${money(mealPromoDiscount)}`;
            }
            if (couponReview && couponReviewValue) {
                couponReview.classList.toggle("hidden", couponDiscount <= 0);
                couponReviewValue.textContent = `- ${money(couponDiscount)}`;
            }
            if (shippingReviewElement && !shippingReviewElement.textContent.trim()) {
                shippingReviewElement.textContent = Number.isFinite(selectedShippingFee) && selectedShippingFee > 0 ? money(selectedShippingFee) : "--";
            }
            if (shippingReviewPaymentElement && !shippingReviewPaymentElement.textContent.trim()) {
                shippingReviewPaymentElement.textContent = Number.isFinite(selectedShippingFee) && selectedShippingFee > 0 ? money(selectedShippingFee) : "--";
            }
            syncStageAvailability(cart.length);
            syncCheckoutSubmitReadiness();

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
        syncKnownOrderTokensPayload();
        const savedCoupon = getCheckoutCouponCode();

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
            stagePayment?.classList.remove("field-needs-attention", "is-payment-missing", "is-payment-method-missing");
            paymentFeedback?.classList.add("hidden");
            if (method) {
                syncCheckoutSubmitReadiness();
            } else if (type === "entrega") {
                stagePayment?.classList.add("is-payment-missing", "is-payment-method-missing");
                if (paymentFeedback) {
                    paymentFeedback.textContent = "Escolha Dinheiro ou Cartao para pagamento na entrega.";
                    paymentFeedback.classList.remove("hidden");
                }
            }
            syncCheckoutSubmitReadiness();

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
                if (pixFooterNotice) {
                    pixFooterNotice.textContent = "Chave Pix copiada. Agora toque em Gerar pedido e abrir WhatsApp para concluir seu pedido.";
                    pixFooterNotice.classList.remove("hidden");
                    pixFooterNotice.style.display = "block";
                    if (pixFooterNotice._hideTimer) clearTimeout(pixFooterNotice._hideTimer);
                    pixFooterNotice._hideTimer = window.setTimeout(() => {
                        pixFooterNotice.classList.add("hidden");
                        pixFooterNotice.style.display = "";
                    }, 7000);
                }
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
                return;
            }
            payloadInput.value = JSON.stringify(cart);
            syncOrderNotePayload();
            syncCheckoutNamePayload();
            syncTalheresPayload();
            syncKnownOrderTokensPayload();
            persistCheckoutProfileFromForm(form);
            if (!whatsappSubmitInProgress) {
                event.preventDefault();
                showUiNotice("", {
                    title: "Gerar pedido e abrir WhatsApp",
                    messageLines: [
                        "Seu pedido será gerado e o WhatsApp abrirá com o resumo pronto.",
                        "Depois é só enviar a mensagem para nossa equipe confirmar.",
                    ],
                    cancelLabel: "Cancelar",
                    confirmLabel: "Continuar",
                    onConfirm() {
                        trackMetricEvent("checkout_submit", {
                            metadata: {
                                tipo_coleta: "entrega",
                                forma_pagamento: paymentMethodInput?.value || "",
                            },
                        });
                        whatsappSubmitInProgress = true;
                        form.querySelectorAll("button, input[type='submit']").forEach((button) => {
                            button.disabled = true;
                        });
                        if (submitButton) submitButton.disabled = true;
                        submitOrder(form).catch((error) => {
                            whatsappSubmitInProgress = false;
                            form.querySelectorAll("button, input[type='submit']").forEach((button) => {
                                button.disabled = false;
                            });
                            if (submitButton) submitButton.disabled = false;
                            showUiNotice(error.message || "Nao foi possivel confirmar o pedido. Confira sua conexao e toque em finalizar novamente.");
                        });
                    },
                });
                return;
            }
        });

        render();
        if (savedCoupon) {
            applyCoupon(savedCoupon);
        }
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
        const cardapioLink = document.querySelector(".context-header .brand-header-logo")?.getAttribute("href") || "/";
        const pickupForm = document.getElementById("pickup-form");
        const pickupPayloadInput = document.getElementById("pickup-carrinho-payload");
        const pickupNameInput = document.getElementById("pickup-nome-payload");
        const pickupNoteInput = document.getElementById("pickup-order-note-payload");
        const pickupTalheresInput = document.getElementById("pickup-talheres-payload");
        const pickupCouponInput = document.getElementById("pickup-coupon-code-payload");
        const pickupKnownOrderTokensInput = document.getElementById("pickup-known-order-tokens");
        const pickupCheckoutKeyInput = document.getElementById("pickup-checkout-key");
        const cartCouponInput = document.getElementById("cart-coupon-code");
        const cartCouponApplyButton = document.getElementById("cart-coupon-apply");
        const cartCouponRemoveButton = document.getElementById("cart-coupon-remove");
        const cartCouponFeedback = document.getElementById("cart-coupon-feedback");
        const cartCouponDiscountRow = document.getElementById("cart-coupon-discount-row");
        const cartCouponDiscountValue = document.getElementById("cart-coupon-discount-value");
        const cartMealPromoRow = document.getElementById("cart-meal-promo-row");
        const cartMealPromoLabel = document.getElementById("cart-meal-promo-label");
        const cartMealPromoValue = document.getElementById("cart-meal-promo-value");
        const cartMealPromoProgress = document.querySelector("[data-cart-meal-promo-progress]");
        const myOrdersUrl = window.PRATO_CONFIG?.myOrdersUrl || "/meus-pedidos/";
        if (!itemsContainer || !itemsSubtotalElement || !goDeliveryLink) return;
        let cartAppliedCoupon = null;

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
            if (pickupCouponInput) pickupCouponInput.value = getCheckoutCouponCode();
            if (pickupKnownOrderTokensInput) pickupKnownOrderTokensInput.value = JSON.stringify(getKnownOrderTokens());
            if (pickupCheckoutKeyInput) pickupCheckoutKeyInput.value = getOrCreateCheckoutKey("retirada");
        }

        async function submitPickupOrder() {
            syncPickupFormPayload();
            const response = await fetch(pickupForm.action, {
                method: "POST",
                headers: {
                    Accept: "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: new FormData(pickupForm),
            });
            if (!response.ok) {
                const message = await response.text();
                throw new Error(message || "Nao foi possivel finalizar a retirada.");
            }
            const payload = await response.json();
            if (!payload?.ok || !payload?.pedido?.token) {
                throw new Error("Nao foi possivel confirmar o pedido criado.");
            }
            rememberOrder(payload.pedido);
            clearCheckoutAfterOrder();
            clearCheckoutKey("retirada");
            window.location.href = payload.success_url || myOrdersUrl;
        }

        function cartItemsTotal() {
            return getCart().reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0);
        }

        function cartMealPromoDiscount() {
            return Math.min(calculateMealPromo(getCart()).discount, cartItemsTotal());
        }

        function getCartCouponDiscount() {
            const rawDiscount = cartAppliedCoupon ? Math.max(Number(cartAppliedCoupon.desconto || 0), 0) : 0;
            return Math.min(rawDiscount, Math.max(cartItemsTotal() - cartMealPromoDiscount(), 0));
        }

        function syncCartCouponUi(message = "") {
            const code = getCheckoutCouponCode();
            if (cartCouponInput) cartCouponInput.value = code;
            cartCouponRemoveButton?.classList.toggle("hidden", !code);
            cartCouponDiscountRow?.classList.toggle("hidden", !code || !getCartCouponDiscount());
            if (cartCouponDiscountValue) cartCouponDiscountValue.textContent = `- ${money(getCartCouponDiscount())}`;
            if (cartCouponFeedback) cartCouponFeedback.textContent = message;
        }

        async function applyCartCoupon(codeOverride = "", options = {}) {
            const code = String(codeOverride || cartCouponInput?.value || "").trim();
            if (!code) {
                cartAppliedCoupon = null;
                saveCheckoutCouponCode("");
                syncCartCouponUi("");
                render();
                return;
            }
            try {
                const response = await fetch(window.PRATO_CONFIG?.couponValidateUrl || "/api/cupom/validar/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "X-CSRFToken": window.PRATO_CONFIG?.csrfToken || "",
                    },
                    body: new URLSearchParams({
                        codigo: code,
                        subtotal: Math.max(cartItemsTotal() - cartMealPromoDiscount(), 0).toFixed(2),
                        frete: "0.00",
                    }),
                });
                const data = await response.json();
                if (!data.ok) {
                    cartAppliedCoupon = null;
                    saveCheckoutCouponCode("");
                    syncCartCouponUi(data.message || "Cupom invalido.");
                    render();
                    return;
                }
                cartAppliedCoupon = {
                    codigo: data.codigo,
                    desconto: Number.parseFloat(data.desconto || "0") || 0,
                };
                saveCheckoutCouponCode(data.codigo);
                syncCartCouponUi(options.silent ? "" : "Cupom aplicado.");
                render();
            } catch (error) {
                cartAppliedCoupon = null;
                syncCartCouponUi("Nao foi possivel validar agora.");
                render();
            }
        }

        const draft = getCheckoutDraft();
        if (nameInput) nameInput.value = draft.nome || getCheckoutCustomerName();
        if (orderNoteInput) orderNoteInput.value = draft.observacao_geral || "";
        if (talheresToggleInput) talheresToggleInput.checked = draft.enviar_talheres !== "nao";
        syncCartCouponUi();

        function render() {
            const cart = getCart();
            if (!cart.length) {
                window.location.href = cardapioLink;
                return;
            }
            itemsContainer.innerHTML = cart.map(buildCartItemMarkup).join("");
            const itemsTotal = cart.reduce((sum, item) => sum + parsePrice(item.preco) * Number(item.quantidade || 0), 0);
            const mealPromo = calculateMealPromo(cart);
            const mealPromoDiscount = Math.min(mealPromo.discount, itemsTotal);
            const couponDiscount = Math.min(getCartCouponDiscount(), Math.max(itemsTotal - mealPromoDiscount, 0));
            syncMealPromoProgress(cartMealPromoProgress, mealPromo, { nextCycle: true });
            if (cartMealPromoRow && cartMealPromoValue) {
                cartMealPromoRow.classList.toggle("hidden", mealPromoDiscount <= 0);
                if (cartMealPromoLabel) cartMealPromoLabel.textContent = mealPromo.label || "Promoção especial";
                cartMealPromoValue.textContent = `- ${money(mealPromoDiscount)}`;
            }
            itemsSubtotalElement.textContent = money(Math.max(itemsTotal - mealPromoDiscount - couponDiscount, 0));
            syncCartCouponUi(cartCouponFeedback?.textContent || "");
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
                const changedItem = updatedCart[index];
                updatedCart[index].quantidade = Math.max(1, Number(updatedCart[index].quantidade || 1) + delta);
                saveCart(updatedCart);
                render();
                if (getCheckoutCouponCode()) applyCartCoupon(getCheckoutCouponCode(), { silent: true });
                if (delta < 0) {
                    trackMetricEvent("remove_from_cart", {
                        item_type: cartItemType(changedItem),
                        item_id: changedItem.item_id || changedItem.prato_id || changedItem.adicional_id || changedItem.bebida_id || "",
                        cart_items_count: 1,
                        metadata: { origem: "carrinho" },
                    });
                }
                return;
            }

            const removeButton = event.target.closest("[data-remove-item]");
            if (removeButton) {
                const index = Number(removeButton.getAttribute("data-remove-item"));
                const cart = getCart();
                const removedItem = cart[index];
                saveCart(cart.filter((_, itemIndex) => itemIndex !== index));
                render();
                if (getCheckoutCouponCode()) applyCartCoupon(getCheckoutCouponCode(), { silent: true });
                if (removedItem) {
                    trackMetricEvent("remove_from_cart", {
                        item_type: cartItemType(removedItem),
                        item_id: removedItem.item_id || removedItem.prato_id || removedItem.adicional_id || removedItem.bebida_id || "",
                        cart_items_count: Number(removedItem.quantidade || 1),
                        metadata: { origem: "carrinho" },
                    });
                }
            }
        });

        nameInput?.addEventListener("input", persistCustomerNameFromPage);
        nameInput?.addEventListener("change", persistCustomerNameFromPage);
        nameInput?.addEventListener("blur", persistCustomerNameFromPage);
        orderNoteInput?.addEventListener("input", persistDraftFromPage);
        orderNoteInput?.addEventListener("change", persistDraftFromPage);
        orderNoteInput?.addEventListener("blur", persistDraftFromPage);
        talheresToggleInput?.addEventListener("change", persistDraftFromPage);
        cartCouponApplyButton?.addEventListener("click", () => applyCartCoupon());
        cartCouponInput?.addEventListener("keydown", (event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            applyCartCoupon();
        });
        cartCouponRemoveButton?.addEventListener("click", () => {
            cartAppliedCoupon = null;
            saveCheckoutCouponCode("");
            syncCartCouponUi("Cupom removido.");
            render();
        });
        window.addEventListener("pagehide", persistDraftFromPage);
        window.addEventListener("beforeunload", persistDraftFromPage);
        goDeliveryLink.addEventListener("click", (event) => {
            const cart = getCart();
            if (!cart.length) {
                event.preventDefault();
                return;
            }
            persistDraftFromPage();
            try {
                if (getSavedCheckoutProfiles().length) {
                    sessionStorage.removeItem(checkoutAutoAddressKey);
                } else {
                    sessionStorage.setItem(checkoutAutoAddressKey, "1");
                }
            } catch (error) {
                // Sem sessionStorage, o checkout segue com o botao manual de endereco.
            }
            trackMetricEvent("go_to_checkout", { metadata: { origem: "carrinho" } });
        });
        let pickupSubmitInProgress = false;
        goPickupButton?.addEventListener("click", () => {
            const cart = getCart();
            if (!cart.length || !pickupForm || pickupSubmitInProgress) return;
            persistDraftFromPage();
            showUiNotice("", {
                title: "Fazer retirada",
                messageLines: [
                    "Vamos gerar seu pedido e abrir o WhatsApp com a mensagem pronta.",
                    "Envie a mensagem para confirmar com nossa equipe.",
                ],
                cancelLabel: "Voltar",
                confirmLabel: "Abrir WhatsApp",
                onConfirm() {
                    trackMetricEvent("pickup_submit", { metadata: { origem: "carrinho" } });
                    pickupSubmitInProgress = true;
                    goPickupButton.disabled = true;
                    submitPickupOrder().catch((error) => {
                        pickupSubmitInProgress = false;
                        goPickupButton.disabled = false;
                        showUiNotice(error.message || "Nao foi possivel confirmar a retirada. Confira sua conexao e tente novamente.");
                    });
                },
            });
        });

        render();
        if (getCheckoutCouponCode()) applyCartCoupon(getCheckoutCouponCode(), { silent: true });
    }

    function kitchenCardMarkup(pedido, statusChoices) {
        const statusButtons = statusChoices
            .map(([value, label]) => {
                const active = pedido.status === value ? "is-active" : "";
                return `<button type="button" class="status-button ${active}" data-status-update data-pedido-id="${pedido.id}" data-status="${value}">${label}</button>`;
            })
            .join("");

        const itens = pedido.itens
            .map((item) => `<li>${item.quantidade}x ${escapeHtml(item.nome)}${item.variacao ? `<small>Variação: ${escapeHtml(item.variacao)}</small>` : ""}${item.observacao ? `<small>Obs: ${escapeHtml(item.observacao)}</small>` : ""}</li>`)
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

