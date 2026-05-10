(function () {
    const root = document.querySelector('[data-page="cozinha-operacao"]');
    if (!root) return;

    const apiUrl = root.dataset.apiUrl || "";
    const entreguesNode = document.getElementById("coz-entregues");
    const producaoNode = document.getElementById("coz-producao");
    const diaNode = document.getElementById("coz-dia");
    const horaNode = document.getElementById("coz-hora");
    const listaNode = document.getElementById("coz-lista");

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

    function renderList(pedidosCards) {
        if (!Array.isArray(pedidosCards) || !pedidosCards.length) {
            listaNode.innerHTML = `
                <div class="coz-live-empty">
                    <div class="coz-live-empty-icon" aria-hidden="true">
                        <svg viewBox="0 0 24 24"><path d="M4 8a6 6 0 0 1 12 0h2a1 1 0 1 1 0 2h-1a5 5 0 0 1-10 0H6a1 1 0 1 1 0-2h2zm3 0a3 3 0 1 0 6 0H7zm9 6H8a4 4 0 0 0 8 0z"/></svg>
                    </div>
                    <h3>Nenhum item em produção</h3>
                    <p>Quando novos pedidos ativos entrarem, eles serão agrupados aqui para a cozinha.</p>
                </div>
            `;
            return;
        }

        const html = pedidosCards
            .map(
                (pedido) => `
                    <article class="coz-prod-card">
                        <div class="coz-prod-top">
                            <div class="coz-prod-title-wrap">
                                <div class="coz-prod-icon" aria-hidden="true">
                                    <svg viewBox="0 0 24 24"><path d="M4 2h2v9h2V2h2v9a2 2 0 0 1-2 2v9H6v-9a2 2 0 0 1-2-2V2zm10 0h6v2h-1v18h-2V4h-1v18h-2V2z"/></svg>
                                </div>
                                <h3>${escapeHtml(pedido.cliente)}</h3>
                            </div>
                            <div class="coz-prod-pratos">
                                <span>Pratos</span>
                                <strong>${escapeHtml(pedido.pratos_total ?? 0)}</strong>
                            </div>
                        </div>
                        <div class="coz-prod-priority-head">
                            <span>Prioridade</span>
                            <strong>${escapeHtml(pedido.elapsed_min ?? 0)} min</strong>
                        </div>
                        <div class="coz-prod-priority-track">
                            ${buildPrioritySegments(pedido.elapsed_min ?? 0)}
                        </div>
                        <div class="coz-prod-priority-scale">
                            <span>10m</span><span>20m</span><span>30m</span><span>40m</span><span>50m</span><span>60m</span>
                        </div>
                        <p class="coz-prod-stage">Estágio atual: ${escapeHtml(pedido.elapsed_min ?? 0)}m</p>
                        <p class="coz-prod-number">#${escapeHtml(pedido.pedido_numero)}</p>
                    </article>
                `
            )
            .join("");
        listaNode.innerHTML = `<div class="coz-live-orders-grid">${html}</div>`;
    }

    async function syncOperacao() {
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
            renderList(payload.pedidos_cards || []);
        } catch (error) {
            console.error(error);
        }
    }

    tickClock();
    window.setInterval(tickClock, 1000);
    syncOperacao();
    window.setInterval(syncOperacao, 5000);
})();
