(function () {
    const config = window.PRATO_CONFIG || {};
    const eventUrl = String(config.metricEventUrl || "").trim();
    const page = document.querySelector("[data-page]")?.dataset.page || "";
    const eventMap = {
        cardapio: "menu_view",
        carrinho: "cart_view",
        checkout: "checkout_view",
    };
    const eventType = eventMap[page];
    if (!eventUrl || !eventType || window.__pratoPageViewTracked) return;

    window.__pratoPageViewTracked = true;

    function csrfToken() {
        const match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function pageOpenId() {
        return window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

    const body = JSON.stringify({
        event_type: eventType,
        path: window.location.pathname,
        metadata: {
            origem: "page_open",
            page_open_id: pageOpenId(),
        },
    });

    fetch(eventUrl, {
        method: "POST",
        credentials: "same-origin",
        keepalive: true,
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": config.csrfToken || csrfToken(),
            "X-Requested-With": "XMLHttpRequest",
        },
        body,
    }).catch(() => {});
})();
