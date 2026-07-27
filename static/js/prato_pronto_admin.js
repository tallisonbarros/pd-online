(function () {
    document.querySelectorAll("[data-confirm-message]").forEach(function (button) {
        button.addEventListener("click", function (event) {
            if (!window.confirm(button.dataset.confirmMessage || "Confirmar esta ação?")) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll("[data-confirm-delete]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (!window.confirm("Excluir este prato do Prato Pronto? O histórico de pedidos será preservado.")) {
                event.preventDefault();
            }
        });
    });

    const sourceSelect = document.querySelector("#pronto-copy-source");
    const catalogNode = document.querySelector("#pronto-copy-catalog");
    const preview = document.querySelector("#pronto-copy-preview");
    const previewImage = document.querySelector("#pronto-copy-preview-image");
    const previewText = document.querySelector("#pronto-copy-preview-text");
    if (!sourceSelect || !catalogNode) return;

    let catalog = [];
    try {
        catalog = JSON.parse(catalogNode.textContent || "[]");
    } catch (_error) {
        return;
    }

    sourceSelect.addEventListener("change", function () {
        const source = catalog.find(function (item) {
            return String(item.id) === sourceSelect.value;
        });
        if (!source) {
            if (preview) preview.hidden = true;
            if (previewImage) previewImage.removeAttribute("src");
            return;
        }

        const fields = {
            id_nome: source.nome,
            id_descricao: source.descricao,
            id_variacoes: source.variacoes,
            id_preco_prato_pronto: source.preco_site || source.preco,
        };
        Object.entries(fields).forEach(function ([id, value]) {
            const input = document.getElementById(id);
            if (input) input.value = value == null ? "" : value;
        });
        if (preview && previewImage) {
            const hasImage = Boolean(source.imagem_url);
            preview.hidden = false;
            preview.classList.toggle("is-missing", !hasImage);
            previewImage.hidden = !hasImage;
            if (source.imagem_url) {
                previewImage.src = source.imagem_url;
                previewImage.alt = source.nome || "";
            } else {
                previewImage.removeAttribute("src");
            }
            if (previewText) {
                previewText.textContent = hasImage
                    ? "Esta imagem também será copiada."
                    : "A imagem original não está disponível. Escolha uma nova imagem abaixo.";
            }
        }
    });
})();
