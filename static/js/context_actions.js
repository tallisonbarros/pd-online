(function () {
    const csrfToken = (window.PRATO_CONFIG && window.PRATO_CONFIG.csrfToken) || "";
    let menu = null;

    function closeMenu() {
        menu?.remove();
        menu = null;
    }

    function clamp(value, min, max) {
        return Math.max(min, Math.min(value, max));
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    async function postAction(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrfToken,
                "X-Requested-With": "XMLHttpRequest",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            body: body || "",
            credentials: "same-origin",
        });
        if (!response.ok) throw new Error(await response.text());
        const type = response.headers.get("content-type") || "";
        return type.includes("application/json") ? response.json() : {};
    }

    function refreshAfterAction(payload) {
        if (payload?.detail_url) {
            document.dispatchEvent(new CustomEvent("prato:open-order-detail", { detail: { url: payload.detail_url } }));
            document.dispatchEvent(new CustomEvent("prato:orders-changed"));
            return;
        }
        if (payload?.redirect_url) {
            window.location.href = payload.redirect_url;
            return;
        }
        document.dispatchEvent(new CustomEvent("prato:orders-changed"));
    }

    async function runAction(card, action) {
        closeMenu();
        if (action === "edit") {
            const url = card.dataset.contextEditUrl || card.dataset.orderDetailUrl;
            if (!url) return;
            if (card.dataset.contextEditMode === "order-modal") {
                document.dispatchEvent(new CustomEvent("prato:open-order-detail", { detail: { url } }));
                return;
            }
            window.location.href = url;
            return;
        }

        if (action === "duplicate") {
            const url = card.dataset.contextDuplicateUrl;
            if (!url) return;
            const payload = await postAction(url);
            refreshAfterAction(payload);
            return;
        }

        if (action === "delete") {
            const url = card.dataset.contextDeleteUrl;
            if (!url) return;
            const message = card.dataset.contextDeleteMessage || "Excluir este item?";
            if (!window.confirm(message)) return;
            const payload = await postAction(url, card.dataset.contextDeleteBody || "");
            refreshAfterAction(payload);
            return;
        }

        if (action === "cancel") {
            const url = card.dataset.contextCancelUrl;
            if (!url) return;
            const message = card.dataset.contextCancelMessage || "Cancelar este pedido?";
            if (!window.confirm(message)) return;
            const payload = await postAction(url, card.dataset.contextCancelBody || "status=cancelado");
            refreshAfterAction(payload);
        }
    }

    function openMenu(card, x, y) {
        closeMenu();
        const isOrder = card.dataset.contextEditMode === "order-modal";
        const editLabel = card.dataset.contextEditLabel || (isOrder ? "Editar pedido" : "Editar");
        const duplicateLabel = card.dataset.contextDuplicateLabel || (isOrder ? "Duplicar pedido" : "Duplicar");
        const deleteLabel = card.dataset.contextDeleteLabel || (isOrder ? "Excluir pedido" : "Excluir");
        const cancelButton = isOrder && card.dataset.contextCancelUrl
            ? `<button type="button" class="is-warning" data-context-action="cancel" role="menuitem">Cancelar pedido</button>`
            : "";
        menu = document.createElement("div");
        menu.className = "context-actions-menu";
        menu.setAttribute("role", "menu");
        menu.innerHTML = `
            <button type="button" data-context-action="edit" role="menuitem">${escapeHtml(editLabel)}</button>
            <button type="button" data-context-action="duplicate" role="menuitem">${escapeHtml(duplicateLabel)}</button>
            ${cancelButton}
            <button type="button" class="is-danger" data-context-action="delete" role="menuitem">${escapeHtml(deleteLabel)}</button>
        `;
        document.body.appendChild(menu);
        const rect = menu.getBoundingClientRect();
        menu.style.left = `${clamp(x, 10, window.innerWidth - rect.width - 10)}px`;
        menu.style.top = `${clamp(y, 10, window.innerHeight - rect.height - 10)}px`;
        menu.querySelector("button")?.focus();

        menu.addEventListener("click", async (event) => {
            const button = event.target.closest("[data-context-action]");
            if (!button) return;
            try {
                await runAction(card, button.dataset.contextAction);
            } catch (error) {
                closeMenu();
                window.alert("Nao foi possivel executar a acao.");
                console.error(error);
            }
        });
    }

    document.addEventListener("contextmenu", (event) => {
        const card = event.target.closest("[data-context-menu]");
        if (!card) return;
        event.preventDefault();
        openMenu(card, event.clientX, event.clientY);
    });

    document.addEventListener("click", (event) => {
        if (!menu || menu.contains(event.target)) return;
        closeMenu();
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeMenu();
    });

    window.addEventListener("resize", closeMenu);
    window.addEventListener("scroll", closeMenu, true);
})();
