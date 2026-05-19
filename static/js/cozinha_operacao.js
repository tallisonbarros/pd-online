(function () {
    const root = document.querySelector('[data-page="cozinha-operacao"]');
    if (!root) return;

    const apiUrl = root.dataset.apiUrl || "";
    const entreguesNode = document.getElementById("coz-entregues");
    const producaoNode = document.getElementById("coz-producao");
    const diaNode = document.getElementById("coz-dia");
    const horaNode = document.getElementById("coz-hora");
    const listaNode = document.getElementById("coz-lista");
    const shellNode = root.closest(".ops-shell--cozinha");
    const fullscreenButton = document.querySelector("[data-cozinha-fullscreen-toggle]");
    let knownProductionOrderIds = new Set();
    let productionOrdersInitialized = false;

    function pad(value) {
        return String(value).padStart(2, "0");
    }

    function tickClock() {
        const now = new Date();
        horaNode.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function buildPrioritySegments(minutes) {
        const safeMinutes = Math.max(0, Number(minutes) || 0);
        const activeCount = Math.min(6, Math.max(1, Math.ceil(safeMinutes / 10)));
        let html = "";
        for (let i = 0; i < 6; i += 1) {
            html += `<i class="${i < activeCount ? "is-active" : ""}"></i>`;
        }
        return html;
    }

    function buildItemLines(lines) {
        const safeLines = Array.isArray(lines) && lines.length ? lines : ["Sem itens"];
        return safeLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("");
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

    async function toggleFullscreen() {
        if (!shellNode) return;
        const isActive = shellNode.classList.toggle("is-kitchen-fullscreen");
        fullscreenButton?.setAttribute("aria-pressed", isActive ? "true" : "false");
        fullscreenButton?.setAttribute("aria-label", isActive ? "Sair da tela cheia da cozinha" : "Expandir cozinha para tela cheia");
        try {
            if (isActive && document.fullscreenEnabled && !document.fullscreenElement) {
                await shellNode.requestFullscreen();
            } else if (!isActive && document.fullscreenElement) {
                await document.exitFullscreen();
            }
        } catch (error) {
            // A classe visual cobre navegadores que bloqueiam fullscreen.
        }
    }

    function syncFullscreenState() {
        if (!shellNode || !fullscreenButton) return;
        const isActive = Boolean(document.fullscreenElement);
        shellNode.classList.toggle("is-kitchen-fullscreen", isActive);
        fullscreenButton.setAttribute("aria-pressed", isActive ? "true" : "false");
        fullscreenButton.setAttribute("aria-label", isActive ? "Sair da tela cheia da cozinha" : "Expandir cozinha para tela cheia");
    }

    function renderList(pedidosCards) {
        if (!Array.isArray(pedidosCards) || !pedidosCards.length) {
            listaNode.innerHTML = `
                <div class="coz-live-empty">
                    <div class="coz-live-empty-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24"><path d="M4 8a6 6 0 0 1 12 0h2a1 1 0 1 1 0 2h-1a5 5 0 0 1-10 0H6a1 1 0 1 1 0-2h2zm3 0a3 3 0 1 0 6 0H7zm9 6H8a4 4 0 0 0 8 0z"/></svg>
                    </div>
                    <h3>Nenhum item em produção</h3>
                    <p>Quando novos pedidos ativos entrarem, eles serao agrupados aqui para a cozinha.</p>
                </div>
            `;
            return;
        }

        const html = pedidosCards
            .map(
                (pedido) => `
                    <article class="coz-prod-card">
                        <div class="ped-card-top coz-prod-card-head">
                            <div class="ped-client">
                                <div class="ped-icon" aria-hidden="true">
                                    <img src="${escapeHtml(pedido.icone_url || "")}" alt="">
                                </div>
                                <div>
                                    <h2>${escapeHtml(pedido.cliente)}</h2>
                                    <p class="ped-time">${escapeHtml(pedido.criado_em || "")}</p>
                                </div>
                            </div>
                            ${buildKitchenTypeCounts(pedido)}

                        </div>
                        <div class="coz-prod-priority-track">
                            ${buildPrioritySegments(pedido.elapsed_min ?? 0)}
                        </div>
                        <div class="coz-prod-priority-scale">
                            <span>10m</span><span>20m</span><span>30m</span><span>40m</span><span>50m</span><span>60m</span>
                        </div>
                        <ul class="ped-item-list coz-prod-item-list coz-prod-item-list--stage">
                            ${buildItemLines(pedido.item_lines)}
                        </ul>
                        <div class="coz-prod-card-footer">
                            <span class="coz-prod-stage">${escapeHtml(pedido.elapsed_min ?? 0)}m</span>
                            <span class="coz-prod-order-number">#${escapeHtml(pedido.pedido_numero)}</span>
                        </div>
                    </article>
                `
            )
            .join("");
        listaNode.innerHTML = `<div class="coz-live-orders-grid">${html}</div>`;
    }

    function orderId(pedido) {
        return String(pedido?.id || pedido?.pedido_numero || "");
    }

    function notifyNewProductionOrders(pedidosCards) {
        const ids = new Set((Array.isArray(pedidosCards) ? pedidosCards : []).map(orderId).filter(Boolean));
        if (!productionOrdersInitialized) {
            knownProductionOrderIds = ids;
            productionOrdersInitialized = true;
            return;
        }
        const hasNewOrder = Array.from(ids).some((id) => !knownProductionOrderIds.has(id));
        knownProductionOrderIds = ids;
        if (hasNewOrder) {
            window.PRATO_ALERT_SOUNDS?.bell?.();
        }
    }

    async function syncOperação() {
        if (!apiUrl) return;
        try {
            const response = await fetch(apiUrl, {
                headers: { "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin",
            });
            if (!response.ok) return;
            const payload = await response.json();
            entreguesNode.textContent = payload.entregues_hoje ?? 0;
            producaoNode.textContent = payload.total_para_producao ?? 0;
            if (payload.weekday_label && payload.date_label) {
                diaNode.textContent = `${payload.weekday_label}, ${payload.date_label}`;
            }
            const pedidosCards = payload.pedidos_cards || [];
            notifyNewProductionOrders(pedidosCards);
            renderList(pedidosCards);
        } catch (error) {
            console.error(error);
        }
    }

    tickClock();
    window.setInterval(tickClock, 1000);
    fullscreenButton?.addEventListener("click", toggleFullscreen);
    document.addEventListener("fullscreenchange", syncFullscreenState);
    syncOperação();
    window.setInterval(syncOperação, 5000);
})();
