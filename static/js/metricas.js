(function () {
    const root = document.querySelector("[data-metrics-root]");
    if (!root) return;

    const apiUrl = root.dataset.apiUrl;
    const refreshMs = 3000;
    let currentPeriod = root.dataset.currentPeriod || "today";
    let refreshTimer = null;
    let inFlight = null;

    function setText(selector, value) {
        document.querySelectorAll(selector).forEach((node) => {
            node.textContent = String(value ?? "");
        });
    }

    function formatCount(count, prefix = "") {
        const value = Number(count || 0);
        const label = value > 99 ? "99+" : String(value);
        return `${prefix}${label}`;
    }

    function updateSidebarOrderBadges(data) {
        const currentCount = data.pedidos_badge ?? 0;
        document.querySelectorAll("[data-current-orders-badge]").forEach((badge) => {
            badge.textContent = formatCount(currentCount);
        });
        if (!Object.prototype.hasOwnProperty.call(data, "aprovacao_count")) return;
        const approvalCount = Number(data.aprovacao_count || 0);
        document.querySelectorAll("[data-sidebar-approval-badge]").forEach((badge) => {
            badge.textContent = formatCount(approvalCount, "+");
            badge.classList.toggle("is-hidden", approvalCount <= 0);
        });
    }

    function setStatus(message, isError = false) {
        const node = document.querySelector("[data-metrics-status]");
        if (!node) return;
        node.textContent = message;
        node.classList.toggle("is-error", isError);
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    function updatePeriods(period) {
        document.querySelectorAll("[data-metrics-periods] [data-period]").forEach((link) => {
            link.classList.toggle("is-active", link.dataset.period === period);
        });
        root.dataset.currentPeriod = period;
        const url = new URL(window.location.href);
        url.searchParams.set("period", period);
        window.history.replaceState({}, "", url.toString());
    }

    function renderFunnel(steps) {
        const node = document.querySelector("[data-metrics-funnel]");
        if (!node) return;
        node.innerHTML = (steps || [])
            .map((step) => `
                <article class="metrics-funnel-step">
                    <div>
                        <span>${escapeHtml(step.label)}</span>
                        <strong>${escapeHtml(step.count)}</strong>
                    </div>
                    <div class="metrics-funnel-track" aria-hidden="true">
                        <span style="width: ${Number(step.width || 0)}%;"></span>
                    </div>
                    <b>${escapeHtml(step.rate)}</b>
                </article>
            `)
            .join("");
    }

    function renderBars(bars) {
        const node = document.querySelector("[data-metrics-bars]");
        if (!node) return;
        node.innerHTML = (bars || [])
            .map((bar) => `
                <div class="metrics-bar">
                    <span style="height: ${Number(bar.height || 4)}%;"></span>
                    <small>${escapeHtml(bar.label)}</small>
                    <b>${escapeHtml(bar.value)}</b>
                </div>
            `)
            .join("");
    }

    function renderRanking(items) {
        const node = document.querySelector("[data-metrics-ranking]");
        if (!node) return;
        if (!items || !items.length) {
            node.innerHTML = '<li class="is-empty">Ainda nao ha eventos de carrinho no periodo.</li>';
            return;
        }
        node.innerHTML = items
            .map((item, index) => `
                <li>
                    <span>#${index + 1}</span>
                    <strong>${escapeHtml(item.nome)}</strong>
                    <b>${escapeHtml(item.total)}</b>
                </li>
            `)
            .join("");
    }

    function applyMetrics(data) {
        const kpis = data.kpis || {};
        Object.entries(kpis).forEach(([key, value]) => {
            setText(`[data-metric-value="${key}"]`, value);
        });
        renderFunnel(data.funnel_steps || []);
        renderBars(data.access_bars || []);
        renderRanking(data.top_items || []);
        setText("[data-metrics-peak]", data.peak?.label || "00h concentrou 0 eventos.");
        setText("[data-metric-period-label]", String(data.periodo_label || "").toLowerCase());
        setText("[data-metrics-period-strong]", data.periodo_label || "");
        updateSidebarOrderBadges(data);
        updatePeriods(data.periodo_key || currentPeriod);
        setStatus(`Atualizado ${data.updated_at || ""}`.trim());
    }

    async function fetchMetrics(period = currentPeriod) {
        if (!apiUrl) return;
        if (inFlight) inFlight.abort();
        inFlight = new AbortController();
        const url = new URL(apiUrl, window.location.origin);
        url.searchParams.set("period", period);
        try {
            const response = await fetch(url.toString(), {
                headers: { Accept: "application/json" },
                signal: inFlight.signal,
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const data = await response.json();
            currentPeriod = data.periodo_key || period;
            applyMetrics(data);
        } catch (error) {
            if (error.name !== "AbortError") {
                setStatus("Falha ao atualizar", true);
            }
        } finally {
            inFlight = null;
        }
    }

    function scheduleRefresh() {
        if (refreshTimer) clearInterval(refreshTimer);
        refreshTimer = setInterval(() => {
            if (document.hidden) return;
            fetchMetrics(currentPeriod);
        }, refreshMs);
    }

    document.querySelector("[data-metrics-periods]")?.addEventListener("click", (event) => {
        const link = event.target.closest("[data-period]");
        if (!link) return;
        event.preventDefault();
        currentPeriod = link.dataset.period || "today";
        updatePeriods(currentPeriod);
        setStatus("Atualizando agora");
        fetchMetrics(currentPeriod);
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) fetchMetrics(currentPeriod);
    });

    fetchMetrics(currentPeriod);
    scheduleRefresh();
})();
