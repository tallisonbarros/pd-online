(function () {
    function setModalOpen(modal, isOpen) {
        if (!modal) return;
        modal.classList.toggle("hidden", !isOpen);
        modal.setAttribute("aria-hidden", isOpen ? "false" : "true");
        document.body.classList.toggle("modal-open", isOpen);

        if (isOpen) {
            const focusTarget = modal.querySelector("input:not([type='hidden']), textarea, select, button");
            window.setTimeout(function () {
                focusTarget?.focus();
            }, 0);
        }
    }

    document.querySelectorAll("[data-open-management-modal]").forEach(function (button) {
        button.addEventListener("click", function () {
            setModalOpen(document.querySelector(button.dataset.openManagementModal), true);
        });
    });

    document.querySelectorAll("[data-management-modal]").forEach(function (modal) {
        modal.querySelectorAll("[data-close-management-modal]").forEach(function (button) {
            button.addEventListener("click", function () {
                setModalOpen(modal, false);
            });
        });

        modal.addEventListener("click", function (event) {
            if (event.target === modal) {
                setModalOpen(modal, false);
            }
        });

        if (modal.dataset.autoOpen === "true") {
            setModalOpen(modal, true);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Escape") return;
        const openModal = document.querySelector("[data-management-modal]:not(.hidden)");
        if (openModal) {
            setModalOpen(openModal, false);
        }
    });

    document.querySelectorAll("[data-image-upload]").forEach(function (upload) {
        const input = upload.querySelector("[data-image-upload-input]");
        const deleteButton = upload.querySelector("[data-image-upload-delete]");
        const preview = upload.querySelector("[data-image-upload-preview]");
        const title = upload.querySelector("[data-image-upload-title]");
        const filename = upload.querySelector("[data-image-upload-filename]");

        function csrfToken() {
            return upload.closest("form")?.querySelector("[name='csrfmiddlewaretoken']")?.value || "";
        }

        input?.addEventListener("change", function () {
            const file = input.files && input.files[0];
            if (!file) return;

            if (filename) filename.textContent = file.name;
            if (title) title.textContent = "Nova imagem";

            if (preview && file.type.startsWith("image/")) {
                const reader = new FileReader();
                reader.addEventListener("load", function () {
                    preview.innerHTML = "";
                    const image = document.createElement("img");
                    image.src = reader.result;
                    image.alt = "";
                    preview.appendChild(image);
                });
                reader.readAsDataURL(file);
            }
        });

        deleteButton?.addEventListener("click", async function () {
            const deleteUrl = deleteButton.dataset.deleteUrl;
            if (!deleteUrl || deleteButton.disabled) return;

            const originalText = deleteButton.textContent;
            deleteButton.disabled = true;
            deleteButton.textContent = "Excluindo...";

            try {
                const response = await fetch(deleteUrl, {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": csrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });

                if (!response.ok) {
                    throw new Error("Falha ao excluir imagem.");
                }

                const payload = await response.json();
                if (!payload.ok) {
                    throw new Error(payload.message || "Falha ao excluir imagem.");
                }

                if (input) input.value = "";
                if (title) title.textContent = "Adicionar imagem";
                if (filename) filename.textContent = "PNG, JPG ou WEBP";
                if (preview) preview.innerHTML = "<span>Sem imagem</span>";
                deleteButton.remove();
            } catch (error) {
                deleteButton.disabled = false;
                deleteButton.textContent = originalText;
                if (filename) filename.textContent = error.message || "Nao foi possivel excluir a imagem";
            }
        });
    });
})();
