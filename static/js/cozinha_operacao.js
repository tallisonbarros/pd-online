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
    const autoScrollTimers = [];

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

    function stopAutoScrollLists() {
        while (autoScrollTimers.length) {
            window.clearInterval(autoScrollTimers.pop());
        }
    }

    function startAutoScrollLists() {
        stopAutoScrollLists();
        document.querySelectorAll("[data-auto-scroll-list]").forEach((list) => {
            if (list.scrollHeight <= list.clientHeight + 2) return;
            let pauseTicks = 0;
            const timer = window.setInterval(() => {
                if (pauseTicks > 0) {
                    pauseTicks -= 1;
                    return;
                }
                if (list.scrollTop + list.clientHeight >= list.scrollHeight - 1) {
                    list.scrollTop = 0;
                    pauseTicks = 8;
                    return;
                }
                list.scrollTop += 1;
            }, 90);
            autoScrollTimers.push(timer);
        });
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
                                    <h2>${escapeHtml(pedido.cliente)} <span>#${escapeHtml(pedido.pedido_numero)}</span></h2>
                                    <p class="ped-time">${escapeHtml(pedido.criado_em || "")}</p>
                                </div>
                            </div>

                        </div>
                        <div class="coz-prod-priority-head">
                            <span>Prioridade</span>
                        </div>
                        <div class="coz-prod-priority-track">
                            ${buildPrioritySegments(pedido.elapsed_min ?? 0)}
                        </div>
                        <div class="coz-prod-priority-scale">
                            <span>10m</span><span>20m</span><span>30m</span><span>40m</span><span>50m</span><span>60m</span>
                        </div>
                        <p class="coz-prod-stage">Estágio atual: ${escapeHtml(pedido.elapsed_min ?? 0)}m</p>
                        <ul class="ped-item-list coz-prod-item-list coz-prod-item-list--stage" data-auto-scroll-list>
                            ${buildItemLines(pedido.item_lines)}
                        </ul>
                    </article>
                `
            )
            .join("");
        listaNode.innerHTML = `<div class="coz-live-orders-grid">${html}</div>`;
        startAutoScrollLists();
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
            renderList(payload.pedidos_cards || []);
        } catch (error) {
            console.error(error);
        }
    }

    tickClock();
    window.setInterval(tickClock, 1000);
    startAutoScrollLists();
    fullscreenButton?.addEventListener("click", toggleFullscreen);
    document.addEventListener("fullscreenchange", syncFullscreenState);
    syncOperação();
    window.setInterval(syncOperação, 5000);
})();
