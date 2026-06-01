(function () {
    const terminalStorageKey = "prato_contabil_terminal_id";
    const bancoStorageKey = "prato_contabil_banco_id";

    function preferredTerminal(defaultValue) {
        return window.localStorage.getItem(terminalStorageKey) || defaultValue || "";
    }

    function preferredBanco(defaultValue) {
        return window.localStorage.getItem(bancoStorageKey) || defaultValue || "";
    }

    function applyPreferredTerminal(scope) {
        scope.querySelectorAll("[data-terminal-select]").forEach(function (select) {
            const preferred = preferredTerminal(select.dataset.defaultTerminal || select.value);
            if (preferred && Array.from(select.options).some(function (option) { return option.value === preferred; })) {
                select.value = preferred;
            }
        });
    }

    function applyPreferredBanco(scope) {
        scope.querySelectorAll("[data-banco-select]").forEach(function (select) {
            const preferred = preferredBanco(select.dataset.defaultBanco || select.value);
            if (preferred && Array.from(select.options).some(function (option) { return option.value === preferred; })) {
                select.value = preferred;
            }
        });
    }

    applyPreferredTerminal(document);
    applyPreferredBanco(document);

    document.querySelectorAll("[data-terminal-select]").forEach(function (select) {
        select.addEventListener("change", function () {
            if (select.value) {
                window.localStorage.setItem(terminalStorageKey, select.value);
            }
        });
        select.form?.addEventListener("submit", function () {
            if (select.value) {
                window.localStorage.setItem(terminalStorageKey, select.value);
            }
        });
    });

    document.querySelectorAll("[data-banco-select]").forEach(function (select) {
        select.addEventListener("change", function () {
            if (select.value) {
                window.localStorage.setItem(bancoStorageKey, select.value);
            }
        });
        select.form?.addEventListener("submit", function () {
            if (select.value) {
                window.localStorage.setItem(bancoStorageKey, select.value);
            }
        });
    });

    document.querySelectorAll("[data-movement-type]").forEach(function (button) {
        button.addEventListener("click", function () {
            const modal = document.querySelector(button.dataset.openManagementModal);
            const field = modal?.querySelector("[data-movement-type-field]");
            if (modal) {
                applyPreferredTerminal(modal);
                applyPreferredBanco(modal);
            }
            if (field) {
                field.value = button.dataset.movementType || "entrada";
            }
        });
    });
})();
