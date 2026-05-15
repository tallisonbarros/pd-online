(function () {
    const main = document.querySelector('[data-page="cozinha"]');
    if (!main) return;

    const listNode = document.getElementById("cozinha-lista");
    const apiUrl = main.dataset.apiUrl;
    const statusUrlTemplate = main.dataset.statusUrlTemplate || "";
    const csrfToken = (window.PRATO_CONFIG && window.PRATO_CONFIG.csrfToken) || "";
    let pollHandle = null;
    let isSyncing = false;

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function formatMetaLabel(label, value) {
        return `
            <div class="ops-order-meta-card">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
            </div>
        `;
    }

    function buildStatusButtons(pedidoId, currentStatus, statusChoices) {
        return (statusChoices || []).map(([value, label]) => `
            <button
                type="button"
                class="status-button ${value === currentStatus ? "is-active" : ""}"
                data-status-update
                data-pedido-id="${pedidoId}"
                data-status="${escapeHtml(value)}"
            >
                ${escapeHtml(label)}
            </button>
        `).join("");
    }

    function buildItems(items) {
        return (items || []).map((item) => `
            <li class="ops-order-item">
                <div>
                    <strong>${escapeHtml(item.quantidade)}x ${escapeHtml(item.nome)}</strong>
                    ${item.observacao ? `<small>Obs.: ${escapeHtml(item.observacao)}</small>` : ""}
                </div>
                <span>${escapeHtml(item.subtotal)}</span>
            </li>
        `).join("");
    }

    function buildKitchenTypeCounts(pedido) {
        const counts = pedido.item_type_counts || {};
        const pratos = Number(counts.pratos || 0);
        const adicionais = Number(counts.adicionais || 0);
        const bebidas = Number(counts.bebidas || 0);
        return `
            <div class="kitchen-type-counts" aria-label="Resumo de itens do pedido">
                <span title="Pratos">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 2a7 7 0 1 1 0 14 7 7 0 0 1 0-14zm0 2.5a4.5 4.5 0 1 0 0 9 4.5 4.5 0 0 0 0-9z"/></svg>
                    ${pratos}
                </span>
                <span title="Adicionais"><i aria-hidden="true">+</i>${adicionais}</span>
                <span title="Bebidas">
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 2h10l-1 7v10a3 3 0 0 1-3 3h-2a3 3 0 0 1-3-3V9L7 2zm2.3 2 .5 4h4.4l.5-4H9.3zM10 10v9a1 1 0 0 0 1 1h2a1 1 0 0 0 1-1v-9h-4z"/></svg>
                    ${bebidas}
                </span>
            </div>
        `;
    }

    function buildOrderCard(pedido, statusChoices) {
        const endereco = [pedido.endereco, pedido.complemento].filter(Boolean).join(", ");
        const routeHint = pedido.has_coordinates ? "" : '<span class="ops-order-hint">Rota aproximada pelo endereço digitado.</span>';

        return `
            <article class="ops-order-card" data-order-id="${pedido.id}">
                <div class="ops-order-topline">
                    <p class="ops-order-code">Pedido #${escapeHtml(pedido.numero)}</p>
                    <div class="ops-order-topline-right">
                        ${buildKitchenTypeCounts(pedido)}
                        <span class="status-badge">${escapeHtml(pedido.status_label)}</span>
                    </div>
                </div>

                <div class="ops-order-header">
                    <div>
                        <h3>${escapeHtml(pedido.cliente)}</h3>
                        <p>${escapeHtml(pedido.horario)}</p>
                    </div>
                    <div class="ops-order-total">
                        <span>Total</span>
                        <strong>${escapeHtml(pedido.total)}</strong>
                    </div>
                </div>

                <div class="ops-order-meta-grid">
                    ${formatMetaLabel("Telefone", pedido.telefone || "-")}
                    ${formatMetaLabel("Talheres", pedido.enviar_talheres ? "Enviar" : "Não enviar")}
                    <div class="ops-order-meta-card ops-order-meta-card--wide">
                        <span>Endereço</span>
                        <strong>${escapeHtml(endereco || pedido.endereco_formatado || "-")}</strong>
                    </div>
                </div>

                <div class="ops-order-block">
                    <div class="ops-order-block-head">
                        <p class="ops-kicker">Itens</p>
                    </div>
                    <ul class="ops-order-items">
                        ${buildItems(pedido.itens)}
                    </ul>
                </div>

                ${pedido.observacao_geral ? `
                    <div class="ops-order-note">
                        <p class="ops-kicker">Observação geral</p>
                        <p>${escapeHtml(pedido.observacao_geral)}</p>
                    </div>
                ` : ""}

                <div class="ops-order-footer">
                    <div class="status-actions">
                        ${buildStatusButtons(pedido.id, pedido.status, statusChoices)}
                    </div>

                    <div class="ops-order-links">
                        <a class="secondary-pill compact" href="${escapeHtml(pedido.google_maps_route_url)}" target="_blank" rel="noopener noreferrer">Abrir rota</a>
                        ${routeHint}
                    </div>
                </div>
            </article>
        `;
    }

    function renderOrders(payload) {
        if (!listNode) return;
        const pedidos = Array.isArray(payload.pedidos) ? payload.pedidos : [];
        const statusChoices = Array.isArray(payload.status_choices) ? payload.status_choices : [];

        if (!pedidos.length) {
            listNode.innerHTML = `
                <div class="empty-state ops-order-empty">
                    <h2>Nenhum pedido ainda.</h2>
                    <p>Assim que os clientes enviarem pedidos, eles aparecem aqui automaticamente.</p>
                </div>
            `;
            return;
        }

        listNode.innerHTML = pedidos.map((pedido) => buildOrderCard(pedido, statusChoices)).join("");
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
            const payload = await response.json();
            renderOrders(payload);
        } catch (error) {
            console.error(error);
        } finally {
            isSyncing = false;
        }
    }

    function buildStatusUrl(pedidoId) {
        return statusUrlTemplate.replace("/0/", `/${pedidoId}/`);
    }

    async function updateStatus(button) {
        const pedidoId = button.dataset.pedidoId;
        const status = button.dataset.status;
        if (!pedidoId || !status) return;

        const parent = button.closest(".status-actions");
        if (parent) {
            parent.querySelectorAll("[data-status-update]").forEach((node) => {
                node.disabled = true;
            });
        }

        try {
            const response = await fetch(buildStatusUrl(pedidoId), {
                method: "POST",
                headers: {
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                },
                body: new URLSearchParams({ status }).toString(),
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao atualizar status (${response.status})`);
            await syncOrders();
        } catch (error) {
            console.error(error);
        } finally {
            if (parent) {
                parent.querySelectorAll("[data-status-update]").forEach((node) => {
                    node.disabled = false;
                });
            }
        }
    }

    document.addEventListener("click", (event) => {
        const button = event.target.closest("[data-status-update]");
        if (!button) return;
        updateStatus(button);
    });

    syncOrders();
    pollHandle = window.setInterval(syncOrders, 5000);

    window.addEventListener("beforeunload", () => {
        if (pollHandle) window.clearInterval(pollHandle);
    });
})();
