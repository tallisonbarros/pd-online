(function () {
    const root = document.querySelector('[data-page="pedidos-admin"], [data-page="pedidos-approval-admin"], [data-page="pedidos-closed-admin"]');
    if (!root) return;

    const page = root.dataset.page || "pedidos-admin";
    const listNode = root.querySelector("[data-orders-list]") || document.getElementById("pedidos-lista");
    const apiUrl = root.dataset.apiUrl;
    const statusUrlTemplate = root.dataset.statusUrlTemplate || "";
    const config = window.PRATO_CONFIG || {};
    const csrfToken = config.csrfToken || "";
    const deliveryEtaUrl = config.deliveryEtaUrl || "/api/address/delivery-time/";
    const googleMapsLanguage = config.googleMapsLanguage || "pt-BR";
    const googleMapsRegion = config.googleMapsRegion || "BR";
    let googleMapsPromise = null;
    let googleGeocoder = null;
    let pollHandle = null;
    let isSyncing = false;

    const defaultStages = [
        ["novo", "1", "Pedido recebido"],
        ["em_preparo", "2", "Em produção"],
        ["aguardando_entregador", "3", "Aguardando coleta"],
        ["saiu_entrega", "4", "Saiu para entrega"],
        ["finalizado", "5", "Entregue"],
    ];

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function loadGoogleMaps() {
        if (!config.googleMapsApiKey) return Promise.reject(new Error("Google Maps nao configurado."));
        if (window.google?.maps?.importLibrary) return Promise.resolve(window.google.maps);
        if (googleMapsPromise) return googleMapsPromise;

        googleMapsPromise = new Promise((resolve, reject) => {
            const existingScript = document.querySelector("script[data-google-maps-js]");
            if (existingScript) {
                existingScript.addEventListener("load", () => resolve(window.google.maps), { once: true });
                existingScript.addEventListener("error", () => reject(new Error("Falha ao carregar Google Maps.")), { once: true });
                return;
            }

            const params = new URLSearchParams({
                key: config.googleMapsApiKey,
                v: "weekly",
                libraries: "places",
                language: googleMapsLanguage,
                region: googleMapsRegion,
            });
            const script = document.createElement("script");
            script.src = `https://maps.googleapis.com/maps/api/js?${params.toString()}`;
            script.async = true;
            script.defer = true;
            script.setAttribute("data-google-maps-js", "true");
            script.onload = () => resolve(window.google.maps);
            script.onerror = () => reject(new Error("Falha ao carregar Google Maps."));
            document.head.appendChild(script);
        });

        return googleMapsPromise;
    }

    async function geocodeDeliverySector(setor) {
        await loadGoogleMaps();
        if (!googleGeocoder) {
            const { Geocoder } = await google.maps.importLibrary("geocoding");
            googleGeocoder = new Geocoder();
        }
        const address = [setor, "Rio Verde", "GO", "Brasil"].filter(Boolean).join(", ");
        const response = await googleGeocoder.geocode({
            address,
            componentRestrictions: {
                country: "BR",
                administrativeArea: "GO",
                locality: "Rio Verde",
            },
            language: googleMapsLanguage,
        });
        const result = response?.results?.[0];
        const location = result?.geometry?.location;
        if (!result || !location) throw new Error("Setor nao encontrado no Google Maps.");
        return {
            lat: location.lat(),
            lng: location.lng(),
            label: result.formatted_address || address,
        };
    }

    function buildStatusUrl(pedidoId) {
        return statusUrlTemplate.replace("/0/", `/${pedidoId}/`);
    }

    function buildEntregadorUrl(pedidoId) {
        return buildStatusUrl(pedidoId).replace("/status/", "/entregador/");
    }

    function buildCopyUrl(pedido) {
        return pedido.copy_url || buildStatusUrl(pedido.id).replace("/controle/pedido/", "/controle/api/pedido/").replace("/status/", "/copias/");
    }

    function isPickupOrder(pedido) {
        return pedido.tipo_coleta === "retirada";
    }

    function previousStatus(pedido) {
        const status = pedido.status;
        if (isPickupOrder(pedido) && status === "finalizado") return "aguardando_entregador";
        if (status === "finalizado") return "saiu_entrega";
        if (status === "saiu_entrega") return "aguardando_entregador";
        if (status === "aguardando_entregador") return "em_preparo";
        if (status === "em_preparo") return "novo";
        return "novo";
    }

    function nextStatus(pedido) {
        const status = pedido.status;
        if (status === "novo") return "em_preparo";
        if (status === "em_preparo") return "aguardando_entregador";
        if (isPickupOrder(pedido) && status === "aguardando_entregador") return "finalizado";
        if (status === "aguardando_entregador") return "saiu_entrega";
        if (status === "saiu_entrega") return "finalizado";
        return "finalizado";
    }

    function buildStages(pedido) {
        const stageItems = Array.isArray(pedido.stage_labels) && pedido.stage_labels.length
            ? pedido.stage_labels.map((stage) => [stage.status, stage.number, stage.label])
            : defaultStages;
        const currentStatus = pedido.status;
        return stageItems.map(([status, number, label]) => {
            const active = status === currentStatus ? " is-active" : "";
            return `<div class="ped-stage${active}"><i>${number}</i><span>${escapeHtml(label)}</span></div>`;
        }).join("");
    }

    function buildStatusForm(pedidoId, status, buttonClass, label) {
        return `
            <form method="post" action="${escapeHtml(buildStatusUrl(pedidoId))}" data-status-form>
                <input type="hidden" name="status" value="${escapeHtml(status)}">
                <button class="${escapeHtml(buttonClass)}" type="submit">${label}</button>
            </form>
        `;
    }

    function buildEntregadorForm(pedido) {
        const active = pedido.entregador_solicitado ? " is-active" : "";
        return `
            <form method="post" action="${escapeHtml(buildEntregadorUrl(pedido.id))}" data-entregador-form>
                <button class="ped-btn ped-btn-toggle${active}" type="submit">Entregador solicitado</button>
            </form>
        `;
    }

    function buildCopyButton(pedido, kind, label) {
        return `
            <button
                class="ped-btn ped-btn-soft ped-btn-copy"
                type="button"
                data-copy-kind="${escapeHtml(kind)}"
                data-copy-url="${escapeHtml(buildCopyUrl(pedido))}"
            >${escapeHtml(label)}</button>
        `;
    }

    function buildItemList(pedido) {
        const lines = Array.isArray(pedido.item_lines) && pedido.item_lines.length ? pedido.item_lines : [pedido.item_line || "Sem itens"];
        return `
            <ul class="ped-item-list ped-item-list--top">
                ${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}
            </ul>
        `;
    }

    function buildPedidoIcon(pedido, fallbackPath) {
        if (pedido.icone_url) {
            return `<img src="${escapeHtml(pedido.icone_url)}" alt="">`;
        }
        return `<svg viewBox="0 0 24 24"><path d="${fallbackPath || "M4 2h2v9h2V2h2v9a2 2 0 0 1-2 2v9H6v-9a2 2 0 0 1-2-2V2zm10 0h6v2h-1v18h-2V4h-1v18h-2V2z"}"/></svg>`;
    }

    function buildOrderCard(pedido) {
        const pedidoId = escapeHtml(pedido.id);
        const pedidoNumero = escapeHtml(pedido.numero);
        const detailUrl = escapeHtml(pedido.detail_url);
        return `
            <article
                class="ped-card ped-card--clickable"
                data-context-menu
                data-context-edit-mode="order-modal"
                data-context-edit-url="${detailUrl}"
                data-context-duplicate-url="${escapeHtml(buildStatusUrl(pedido.id).replace("/status/", "/duplicar/"))}"
                data-context-cancel-url="${escapeHtml(buildStatusUrl(pedido.id))}"
                data-context-cancel-body="status=cancelado"
                data-context-cancel-message="Cancelar pedido #${pedidoNumero}?"
                data-context-delete-url="${escapeHtml(buildStatusUrl(pedido.id).replace("/status/", "/excluir/"))}"
                data-context-delete-message="Excluir pedido #${pedidoNumero} definitivamente?"
                data-order-id="${pedidoId}"
                data-order-detail-url="${detailUrl}"
                role="button"
                tabindex="0"
                aria-label="Abrir detalhes do pedido #${pedidoNumero}"
            >
                <div class="ped-card-top">
                    <div class="ped-client">
                        <div class="ped-icon" aria-hidden="true">
                            ${buildPedidoIcon(pedido)}
                        </div>
                        <div>
                            <h2>${escapeHtml(pedido.cliente)} <span>#${pedidoNumero}</span></h2>
                            <p class="ped-time">${escapeHtml(pedido.criado_em)}</p>
                        </div>
                    </div>

                    ${buildItemList(pedido)}

                    <div class="ped-card-tools">
                        <div class="ped-stats">
                            <div class="ped-chip-box">
                                <span>Tempo em produção</span>
                                <strong>${escapeHtml(pedido.tempo_producao)}</strong>
                            </div>
                            <div class="ped-chip-box">
                                <span>Valor total</span>
                                <strong>${escapeHtml(pedido.total)}</strong>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="ped-flow">
                    <div class="ped-stages">
                        ${buildStages(pedido)}
                    </div>
                </div>

                <div class="ped-actions">
                    <div class="ped-actions-left">
                        ${buildCopyButton(pedido, "cliente", "Copiar pedido")}
                        ${buildCopyButton(pedido, "entregador", "Copiar endereço")}
                        ${buildEntregadorForm(pedido)}
                    </div>
                    <div class="ped-actions-right">
                        ${buildStatusForm(pedido.id, previousStatus(pedido), "ped-btn ped-btn-soft", '<span aria-hidden="true">&larr;</span> Voltar etapa')}
                        ${buildStatusForm(pedido.id, nextStatus(pedido), "ped-btn ped-btn-primary", 'Avançar etapa <span aria-hidden="true">&rarr;</span>')}
                    </div>
                </div>
            </article>
        `;
    }

    function buildApprovalCard(pedido) {
        const pedidoId = escapeHtml(pedido.id);
        const pedidoNumero = escapeHtml(pedido.numero);
        const detailUrl = escapeHtml(pedido.detail_url);
        return `
            <article
                class="ped-card ped-card--clickable"
                data-context-menu
                data-context-edit-mode="order-modal"
                data-context-edit-url="${detailUrl}"
                data-context-duplicate-url="${escapeHtml(buildStatusUrl(pedido.id).replace("/status/", "/duplicar/"))}"
                data-context-cancel-url="${escapeHtml(buildStatusUrl(pedido.id))}"
                data-context-cancel-body="status=cancelado"
                data-context-cancel-message="Cancelar pedido #${pedidoNumero}?"
                data-context-delete-url="${escapeHtml(buildStatusUrl(pedido.id).replace("/status/", "/excluir/"))}"
                data-context-delete-message="Excluir pedido #${pedidoNumero} definitivamente?"
                data-order-id="${pedidoId}"
                data-order-detail-url="${detailUrl}"
                role="button"
                tabindex="0"
                aria-label="Abrir detalhes do pedido #${pedidoNumero}"
            >
                <div class="ped-card-top">
                    <div class="ped-client">
                        <div class="ped-icon" aria-hidden="true">
                            ${buildPedidoIcon(pedido)}
                        </div>
                        <div>
                            <h2>${escapeHtml(pedido.cliente)} <span>#${pedidoNumero}</span></h2>
                            <p class="ped-time">${escapeHtml(pedido.criado_em)}</p>
                        </div>
                    </div>
                    ${buildItemList(pedido)}
                    <div class="ped-card-tools ped-card-tools--approval">
                        <div class="ped-stats">
                            <div class="ped-chip-box">
                                <span>Status</span>
                                <strong>Aguardando aprovação</strong>
                            </div>
                            <div class="ped-chip-box">
                                <span>Valor total</span>
                                <strong>${escapeHtml(pedido.total)}</strong>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="ped-card-note">Aguardando confirmação no WhatsApp</div>
                <div class="ped-actions">
                    ${buildStatusForm(pedido.id, "cancelado", "ped-btn ped-btn-danger", "Cancelar pedido")}
                    <div class="ped-actions-right">
                        ${buildStatusForm(pedido.id, "em_preparo", "ped-btn ped-btn-primary", "Aprovar pedido")}
                    </div>
                </div>
            </article>
        `;
    }

    function buildClosedCard(pedido, iconPath) {
        const pedidoNumero = escapeHtml(pedido.numero);
        const pedidoId = escapeHtml(pedido.id);
        const detailUrl = escapeHtml(pedido.detail_url);
        const actionMarkup = pedido.status === "finalizado"
            ? `
                <div class="ped-actions">
                    <div class="ped-actions-right">
                        ${buildStatusForm(pedido.id, previousStatus(pedido), "ped-btn ped-btn-soft", '<span aria-hidden="true">&larr;</span> Voltar etapa')}
                    </div>
                </div>
            `
            : "";
        return `
            <article
                class="ped-card ped-card--clickable"
                data-context-menu
                data-context-edit-mode="order-modal"
                data-context-edit-url="${detailUrl}"
                data-context-duplicate-url="${escapeHtml(buildStatusUrl(pedido.id).replace("/status/", "/duplicar/"))}"
                data-context-cancel-url="${escapeHtml(buildStatusUrl(pedido.id))}"
                data-context-cancel-body="status=cancelado"
                data-context-cancel-message="Cancelar pedido #${pedidoNumero}?"
                data-context-delete-url="${escapeHtml(buildStatusUrl(pedido.id).replace("/status/", "/excluir/"))}"
                data-context-delete-message="Excluir pedido #${pedidoNumero} definitivamente?"
                data-order-id="${pedidoId}"
                data-order-detail-url="${detailUrl}"
                role="button"
                tabindex="0"
                aria-label="Abrir detalhes do pedido #${pedidoNumero}"
            >
                <div class="ped-card-top">
                    <div class="ped-client">
                        <div class="ped-icon" aria-hidden="true">
                            ${buildPedidoIcon(pedido, iconPath)}
                        </div>
                        <div>
                            <h2>${escapeHtml(pedido.cliente)} <span>#${pedidoNumero}</span></h2>
                            <p class="ped-time">${escapeHtml(pedido.criado_em)}</p>
                            <p class="ped-item-line">${escapeHtml(pedido.status_label)}</p>
                        </div>
                    </div>
                    <div class="ped-card-tools">
                        <div class="ped-stats">
                            <div class="ped-chip-box">
                                <span>Valor total</span>
                                <strong>${escapeHtml(pedido.total)}</strong>
                            </div>
                        </div>
                    </div>
                </div>
                ${actionMarkup}
            </article>
        `;
    }

    function formatCount(count, prefix = "") {
        const value = Number(count || 0);
        const label = value > 99 ? "99+" : String(value);
        return `${prefix}${label}`;
    }

    function updateSidebarBadge(count) {
        document.querySelectorAll("[data-current-orders-badge]").forEach((badge) => {
            badge.textContent = formatCount(count);
        });
    }

    function updateApprovalBadges(count) {
        const value = Number(count || 0);
        document.querySelectorAll("[data-approval-badge], [data-sidebar-approval-badge]").forEach((badge) => {
            const isSidebarBadge = badge.hasAttribute("data-sidebar-approval-badge");
            badge.textContent = formatCount(value, isSidebarBadge ? "+" : "");
            badge.classList.toggle("is-hidden", value <= 0);
        });
    }

    function renderCurrentOrders(payload) {
        if (!listNode) return;
        const pedidos = Array.isArray(payload.pedidos) ? payload.pedidos : [];

        if (!pedidos.length) {
            listNode.innerHTML = `
                <div class="empty-state">
                    <h2>Nenhum pedido ativo</h2>
                    <p>Os pedidos em andamento aparecerão aqui.</p>
                </div>
            `;
            return;
        }

        listNode.innerHTML = pedidos.map(buildOrderCard).join("");
    }

    function renderApprovalOrders(payload) {
        if (!listNode) return;
        const pedidos = Array.isArray(payload.pedidos) ? payload.pedidos : [];

        if (!pedidos.length) {
            listNode.innerHTML = `
                <div class="empty-state">
                    <h2>Nenhum pedido para aprovação</h2>
                    <p>Pedidos aguardando confirmação aparecerão aqui.</p>
                </div>
            `;
            return;
        }

        listNode.innerHTML = pedidos.map(buildApprovalCard).join("");
    }

    function renderClosedOrders(payload) {
        if (!listNode) return;
        const concluidos = Array.isArray(payload.pedidos_concluidos) ? payload.pedidos_concluidos : [];
        const cancelados = Array.isArray(payload.pedidos_cancelados) ? payload.pedidos_cancelados : [];
        const doneIcon = "M7 11l3 3 7-7 1.4 1.4L10 16.8 5.6 12.4 7 11z";
        const cancelIcon = "M7.4 6L12 10.6 16.6 6 18 7.4 13.4 12 18 16.6 16.6 18 12 13.4 7.4 18 6 16.6 10.6 12 6 7.4 7.4 6z";
        const concludedMarkup = concluidos.length
            ? concluidos.map((pedido) => buildClosedCard(pedido, doneIcon)).join("")
            : `
                <div class="empty-state">
                    <h2>Nenhum pedido concluído</h2>
                    <p>Pedidos entregues aparecerão aqui.</p>
                </div>
            `;
        const canceledMarkup = cancelados.map((pedido) => buildClosedCard(pedido, cancelIcon)).join("");

        listNode.innerHTML = `
            <details class="ped-collapse" open>
                <summary>
                    <div>
                        <h3>Concluídos</h3>
                        <p>${escapeHtml(payload.concluidos_count || 0)} pedido(s) entregue(s)</p>
                    </div>
                    <span class="ped-badge done">${escapeHtml(payload.concluidos_count || 0)}</span>
                </summary>
            </details>
            ${concludedMarkup}
            <details class="ped-collapse" open>
                <summary>
                    <div>
                        <h3>Cancelados</h3>
                        <p>${Number(payload.cancelados_count || 0) ? `${escapeHtml(payload.cancelados_count)} pedido(s) cancelado(s).` : "Nenhum pedido cancelado no momento."}</p>
                    </div>
                    <span class="ped-badge cancel">${escapeHtml(payload.cancelados_count || 0)}</span>
                </summary>
            </details>
            ${canceledMarkup}
        `;
    }

    function renderOrders(payload) {
        updateSidebarBadge(payload.pedidos_badge);
        updateApprovalBadges(payload.aprovacao_count);
        if (page === "pedidos-approval-admin") {
            renderApprovalOrders(payload);
            return;
        }
        if (page === "pedidos-closed-admin") {
            renderClosedOrders(payload);
            return;
        }
        renderCurrentOrders(payload);
    }

    async function syncOrders() {
        if (isSyncing || !apiUrl) return;
        isSyncing = true;
        try {
            const response = await fetch(apiUrl, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao carregar pedidos (${response.status})`);
            renderOrders(await response.json());
        } catch (error) {
            console.error(error);
        } finally {
            isSyncing = false;
        }
    }

    async function updateStatus(form) {
        const action = form.getAttribute("action");
        const formData = new FormData(form);
        const controls = form.closest(".ped-actions")?.querySelectorAll("button") || [];
        controls.forEach((button) => {
            button.disabled = true;
        });

        try {
            const response = await fetch(action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                body: new URLSearchParams(formData).toString(),
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao atualizar status (${response.status})`);
            await syncOrders();
        } catch (error) {
            console.error(error);
        } finally {
            controls.forEach((button) => {
                button.disabled = false;
            });
        }
    }

    function fallbackCopy(text) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "");
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand("copy");
        textarea.remove();
    }

    async function copyOrderText(button) {
        const url = button.dataset.copyUrl;
        const kind = button.dataset.copyKind;
        if (!url || !kind) return;
        const originalText = button.textContent;
        button.disabled = true;
        try {
            const response = await fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao carregar texto (${response.status})`);
            const payload = await response.json();
            const text = payload[kind] || "";
            if (!text) throw new Error("Texto de copia vazio.");
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(text);
            } else {
                fallbackCopy(text);
            }
            button.textContent = "Copiado";
            window.setTimeout(() => {
                button.textContent = originalText;
            }, 1300);
        } catch (error) {
            console.error(error);
            button.textContent = "Erro ao copiar";
            window.setTimeout(() => {
                button.textContent = originalText;
            }, 1600);
        } finally {
            button.disabled = false;
        }
    }

    const deliveryLookupModal = document.querySelector("[data-delivery-lookup-modal]");
    const deliveryLookupForm = deliveryLookupModal?.querySelector("[data-delivery-lookup-form]");
    const deliveryLookupResult = deliveryLookupModal?.querySelector("[data-delivery-lookup-result]");
    const deliveryLookupInput = deliveryLookupForm?.querySelector("input[name='setor']");

    function setDeliveryLookupResult(markup, isError = false) {
        if (!deliveryLookupResult) return;
        deliveryLookupResult.classList.remove("hidden", "is-error");
        deliveryLookupResult.classList.toggle("is-error", Boolean(isError));
        deliveryLookupResult.innerHTML = markup;
    }

    function openDeliveryLookup(button) {
        if (!deliveryLookupModal) return;
        deliveryLookupModal.classList.remove("hidden");
        deliveryLookupModal.setAttribute("aria-hidden", "false");
        deliveryLookupResult?.classList.add("hidden");
        window.setTimeout(() => deliveryLookupInput?.focus(), 20);
    }

    function closeDeliveryLookup() {
        if (!deliveryLookupModal) return;
        deliveryLookupModal.classList.add("hidden");
        deliveryLookupModal.setAttribute("aria-hidden", "true");
    }

    async function submitDeliveryLookup(event) {
        event.preventDefault();
        if (!deliveryLookupForm) return;
        const setor = String(deliveryLookupInput?.value || "").trim();
        if (!setor) {
            setDeliveryLookupResult("<p>Informe o nome do setor.</p>", true);
            return;
        }
        const submitButton = deliveryLookupForm.querySelector("button[type='submit']");
        submitButton.disabled = true;
        setDeliveryLookupResult("<p>Localizando setor...</p>");
        try {
            const destination = await geocodeDeliverySector(setor);
            const params = new URLSearchParams({
                lat: String(destination.lat),
                lng: String(destination.lng),
                resolved_label: destination.label,
                resolved_type: "district",
                resolved_precision: "approximate",
                bairro: setor,
                cidade: "Rio Verde",
                estado: "GO",
            });
            setDeliveryLookupResult("<p>Calculando frete...</p>");
            const response = await fetch(`${deliveryEtaUrl}?${params.toString()}`, {
                method: "GET",
                headers: { Accept: "application/json" },
                credentials: "same-origin",
            });
            const payload = await response.json();
            if (!response.ok || !payload.ok) {
                const error = payload.error === "origin_not_configured"
                    ? "Configure a origem de entrega em Ajustes > Frete."
                    : "Nao foi possivel consultar o frete.";
                throw new Error(error);
            }
            setDeliveryLookupResult(`
                <span>${escapeHtml(setor)}</span>
                <strong>${escapeHtml(payload.shipping_fee_formatted)}</strong>
                <small>${escapeHtml(payload.distance_km)} km - ${escapeHtml(payload.shipping_rule?.tipo || "faixa")} ${escapeHtml(payload.shipping_rule?.km_limite || "")} km</small>
            `);
        } catch (error) {
            setDeliveryLookupResult(`<p>${escapeHtml(error.message || "Erro ao consultar entrega.")}</p>`, true);
        } finally {
            submitButton.disabled = false;
        }
    }

    root.addEventListener("submit", (event) => {
        const form = event.target.closest("[data-status-form], [data-entregador-form]");
        if (!form) return;
        event.preventDefault();
        updateStatus(form);
    });

    root.addEventListener("click", (event) => {
        const button = event.target.closest("[data-copy-kind][data-copy-url]");
        if (!button) return;
        event.preventDefault();
        copyOrderText(button);
    });

    root.addEventListener("click", (event) => {
        const button = event.target.closest("[data-open-delivery-lookup]");
        if (!button) return;
        event.preventDefault();
        openDeliveryLookup(button);
    });

    deliveryLookupForm?.addEventListener("submit", submitDeliveryLookup);
    deliveryLookupModal?.addEventListener("click", (event) => {
        if (event.target === deliveryLookupModal || event.target.closest("[data-close-delivery-lookup]")) {
            closeDeliveryLookup();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && deliveryLookupModal && !deliveryLookupModal.classList.contains("hidden")) {
            closeDeliveryLookup();
        }
    });

    document.addEventListener("prato:orders-changed", syncOrders);

    syncOrders();
    pollHandle = window.setInterval(syncOrders, 5000);

    window.addEventListener("beforeunload", () => {
        if (pollHandle) window.clearInterval(pollHandle);
    });
})();
