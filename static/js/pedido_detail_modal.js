(function () {
    const modal = document.querySelector("[data-pedido-detail-modal]");
    if (!modal) return;
    const itemsModal = document.querySelector("[data-items-editor-modal]");
    const itemsEditorHost = itemsModal?.querySelector("[data-items-editor-host]");
    const deliveryModal = document.querySelector("[data-delivery-editor-modal]");
    const deliveryEditorHost = deliveryModal?.querySelector("[data-delivery-editor-host]");

    const content = modal.querySelector("[data-pedido-detail-content]");
    const loading = modal.querySelector("[data-pedido-detail-loading]");
    const csrfToken = (window.PRATO_CONFIG && window.PRATO_CONFIG.csrfToken) || "";
    let lastFocus = null;
    let currentDetailUrl = "";

    function setOpen(isOpen) {
        modal.classList.toggle("hidden", !isOpen);
        modal.setAttribute("aria-hidden", isOpen ? "false" : "true");
        document.body.classList.toggle("modal-open", isOpen);
        if (isOpen) {
            modal.querySelector("[data-close-pedido-detail-modal]")?.focus();
        } else if (lastFocus) {
            lastFocus.focus();
        }
    }

    function setItemsEditorOpen(isOpen) {
        if (!itemsModal) return;
        itemsModal.classList.toggle("hidden", !isOpen);
        itemsModal.setAttribute("aria-hidden", isOpen ? "false" : "true");
        document.body.classList.toggle("modal-open", isOpen || !modal.classList.contains("hidden"));
        if (isOpen) {
            itemsModal.querySelector("[data-close-items-editor]")?.focus();
        }
    }

    function setDeliveryEditorOpen(isOpen) {
        if (!deliveryModal) return;
        deliveryModal.classList.toggle("hidden", !isOpen);
        deliveryModal.setAttribute("aria-hidden", isOpen ? "false" : "true");
        document.body.classList.toggle("modal-open", isOpen || !modal.classList.contains("hidden"));
        if (isOpen) {
            deliveryModal.querySelector("[data-close-delivery-editor]")?.focus();
        }
    }

    function shouldIgnoreCardClick(target) {
        return Boolean(target.closest("a, button, input, select, textarea, form"));
    }

    async function openDetail(card) {
        const url = card.dataset.orderDetailUrl;
        if (!url) return;
        currentDetailUrl = url;
        lastFocus = document.activeElement;
        if (content) content.innerHTML = "";
        if (loading) loading.classList.remove("hidden");
        setOpen(true);

        try {
            const response = await fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao carregar pedido (${response.status})`);
            if (content) content.innerHTML = await response.text();
        } catch (error) {
            if (content) {
                content.innerHTML = '<div class="ped-modal-error">Não foi possível carregar os detalhes do pedido.</div>';
            }
            console.error(error);
        } finally {
            if (loading) loading.classList.add("hidden");
        }
    }

    async function openCreateOrder(button) {
        const url = button.dataset.newOrderUrl;
        if (!url) return;
        currentDetailUrl = "";
        lastFocus = document.activeElement;
        if (content) content.innerHTML = "";
        if (loading) loading.classList.remove("hidden");
        setOpen(true);

        try {
            const response = await fetch(url, {
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                },
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao carregar novo pedido (${response.status})`);
            if (content) {
                content.innerHTML = await response.text();
                currentDetailUrl = content.querySelector("[data-current-detail-url]")?.dataset.currentDetailUrl || "";
            }
        } catch (error) {
            if (content) {
                content.innerHTML = '<div class="ped-modal-error">Não foi possível carregar o novo pedido.</div>';
            }
            console.error(error);
        } finally {
            if (loading) loading.classList.add("hidden");
        }
    }

    function closeDetail() {
        setOpen(false);
    }

    function notifyOrdersChanged() {
        document.dispatchEvent(new CustomEvent("prato:orders-changed"));
    }

    function confirmModal(message) {
        return new Promise((resolve) => {
            const confirmBackdrop = document.createElement("div");
            confirmBackdrop.className = "modal-backdrop ped-confirm-modal";
            confirmBackdrop.innerHTML = `
                <div class="modal-card ped-confirm-card" role="alertdialog" aria-modal="true" aria-labelledby="ped-confirm-title">
                    <div class="modal-content ped-confirm-content">
                        <strong id="ped-confirm-title">Confirmar</strong>
                        <p>${escapeHtml(message || "Deseja continuar?")}</p>
                        <div class="ped-confirm-actions">
                            <button type="button" class="ped-btn ped-btn-soft" data-confirm-cancel>Voltar</button>
                            <button type="button" class="ped-btn ped-btn-danger" data-confirm-ok>Continuar</button>
                        </div>
                    </div>
                </div>
            `;

            const onKeydown = (event) => {
                if (event.key !== "Escape") return;
                close(false);
            };

            function close(value) {
                document.removeEventListener("keydown", onKeydown);
                confirmBackdrop.remove();
                resolve(value);
            }

            confirmBackdrop.addEventListener("click", (event) => {
                if (event.target === confirmBackdrop || event.target.closest("[data-confirm-cancel]")) {
                    close(false);
                    return;
                }
                if (event.target.closest("[data-confirm-ok]")) {
                    close(true);
                }
            });

            document.addEventListener("keydown", onKeydown);
            document.body.appendChild(confirmBackdrop);
            confirmBackdrop.querySelector("[data-confirm-cancel]")?.focus();
        });
    }

    async function submitPaymentForm(form) {
        const button = form.querySelector("button");
        if (button) button.disabled = true;
        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                body: form.__body || new URLSearchParams(new FormData(form)).toString(),
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao atualizar pagamento (${response.status})`);
            if (currentDetailUrl) {
                await openDetail({ dataset: { orderDetailUrl: currentDetailUrl } });
            }
        } catch (error) {
            if (content) {
                content.insertAdjacentHTML("afterbegin", '<div class="ped-modal-error">Não foi possível salvar o pagamento.</div>');
            }
            console.error(error);
        } finally {
            if (button) button.disabled = false;
        }
    }

    async function submitPrintQueueForm(form) {
        const button = form.querySelector("button");
        const feedback = form.querySelector("[data-print-queue-feedback]");
        if (button) button.disabled = true;
        if (feedback) feedback.textContent = "";
        try {
            const response = await fetch(form.action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                body: new URLSearchParams(new FormData(form)).toString(),
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(`Falha ao registrar rotulo (${response.status})`);
            if (feedback) feedback.textContent = "Adicionado a lista.";
        } catch (error) {
            if (feedback) feedback.textContent = "Nao foi possivel adicionar.";
            console.error(error);
        } finally {
            if (button) button.disabled = false;
        }
    }

    function openInlineEditor(node) {
        if (node.dataset.editing === "true") return;
        node.dataset.editing = "true";
        const field = node.dataset.field;
        const type = node.dataset.type || "text";
        const value = node.dataset.value || "";
        const action = node.dataset.action;
        const form = document.createElement("form");
        form.className = "ped-inline-edit-form";
        form.action = action;
        form.method = "post";
        form.dataset.inlineEditForm = "true";
        form.dataset.action = action;
        form.dataset.field = field;
        form.dataset.param = node.dataset.param || "value";

        let control;
        if (type === "select") {
            control = document.createElement("select");
            (node.dataset.options || "").split("|").forEach((entry) => {
                const [optionValue, label] = entry.split(":");
                const option = document.createElement("option");
                option.value = optionValue;
                option.textContent = label || optionValue;
                option.selected = optionValue === value;
                control.appendChild(option);
            });
        } else if (type === "textarea") {
            control = document.createElement("textarea");
            control.rows = 2;
            control.value = value;
        } else {
            control = document.createElement("input");
            control.type = "text";
            control.value = value;
        }
        control.name = "value";
        control.setAttribute("aria-label", "Editar campo");

        const save = document.createElement("button");
        save.type = "submit";
        save.className = "ped-btn ped-btn-primary";
        save.textContent = "Salvar";

        form.appendChild(control);
        form.appendChild(save);
        node.replaceWith(form);
        control.focus();
        if (control.select) control.select();
    }

    function openItemsEditor() {
        const template = content.querySelector("[data-items-editor-template]");
        if (!template || !itemsEditorHost) return;
        itemsEditorHost.innerHTML = "";
        itemsEditorHost.appendChild(template.content.cloneNode(true));
        setItemsEditorOpen(true);
        loadCatalog(itemsEditorHost);
    }

    function closeItemsEditor() {
        setItemsEditorOpen(false);
        if (itemsEditorHost) itemsEditorHost.innerHTML = "";
    }

    function openDeliveryEditor(clearFields) {
        const template = content.querySelector("[data-delivery-editor-template]");
        if (!template || !deliveryEditorHost) return;
        deliveryEditorHost.innerHTML = "";
        deliveryEditorHost.appendChild(template.content.cloneNode(true));
        const form = deliveryEditorHost.querySelector("[data-delivery-editor]");
        deliveryEditorHost.querySelector("#address-step-map")?.classList.add("is-operator-search-mode");
        const controller = window.PRATO_ADDRESS_EDITOR?.initAddressEditor?.(form, {
            isOperatorCheckout: true,
            root: deliveryEditorHost,
        });
        if (form && controller) {
            form.__addressController = controller;
            const currentAddress = {
                street: form.querySelector("input[name='rua']")?.value || "",
                district: form.querySelector("input[name='bairro']")?.value || "",
                city: form.querySelector("input[name='cidade']")?.value || "Rio Verde",
                state: form.querySelector("input[name='estado']")?.value || "GO",
                lat: form.querySelector("input[name='latitude']")?.value || "",
                lng: form.querySelector("input[name='longitude']")?.value || "",
                label: form.querySelector("input[name='endereco_formatado']")?.value || "",
            };
            if (currentAddress.street || currentAddress.label) {
                controller.applyResolvedAddress(currentAddress, {
                    confirmed: Boolean(currentAddress.lat && currentAddress.lng),
                    updateMap: false,
                });
            }
        }
        setDeliveryEditorOpen(true);
        if (clearFields) {
            showDeliveryEditorForm(deliveryEditorHost, true);
        }
    }

    function closeDeliveryEditor() {
        setDeliveryEditorOpen(false);
        if (deliveryEditorHost) deliveryEditorHost.innerHTML = "";
    }

    function showDeliveryEditorForm(scope, clearFields) {
        const selector = scope.querySelector("[data-delivery-selector-panel]");
        const panel = scope.querySelector("[data-delivery-editor-panel]");
        const form = scope.querySelector("[data-delivery-editor]");
        selector?.classList.add("hidden");
        panel?.classList.remove("hidden");
        if (clearFields && form) {
            form.querySelectorAll("input").forEach((input) => {
                if (input.name === "csrfmiddlewaretoken") {
                    return;
                }
                if (input.name === "tipo_coleta") {
                    input.value = "entrega";
                    return;
                }
                if (input.name === "cidade") {
                    input.value = "Rio Verde";
                } else if (input.name === "estado") {
                    input.value = "GO";
                } else {
                    input.value = "";
                }
            });
        }
        form?.querySelector("#operator-address-query, input[name='rua']")?.focus();
        if (form?.__addressController) {
            form.__addressController.ensureMapReady?.();
            if (clearFields) form.__addressController.clearResolvedAddress?.();
        }
    }

    function showDeliverySelector(scope) {
        scope.querySelector("[data-delivery-selector-panel]")?.classList.remove("hidden");
        scope.querySelector("[data-delivery-editor-panel]")?.classList.add("hidden");
    }

    async function loadCatalog(scope) {
        const form = (scope || content).querySelector("[data-items-editor]");
        const select = form?.querySelector("[data-editor-catalog]");
        if (!form || !select || select.dataset.loaded === "true") return;
        const response = await fetch(form.dataset.catalogUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
        });
        if (!response.ok) return;
        const payload = await response.json();
        select.innerHTML = (payload.items || []).map((item) => {
            const variations = encodeURIComponent(JSON.stringify(item.variacoes || []));
            return `<option value="${item.tipo}:${item.id}" data-name="${escapeHtml(item.nome)}" data-price="${escapeHtml(item.preco)}" data-variations="${variations}">${escapeHtml(item.nome)} - R$ ${escapeHtml(item.preco).replace(".", ",")}</option>`;
        }).join("");
        select.dataset.loaded = "true";
        updateVariationSelect(form);
    }

    function escapeHtml(value) {
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function selectedCatalogOption(form) {
        return form.querySelector("[data-editor-catalog]")?.selectedOptions?.[0] || null;
    }

    function updateVariationSelect(form) {
        const option = selectedCatalogOption(form);
        const variationSelect = form.querySelector("[data-editor-variation]");
        if (!option || !variationSelect) return;
        const variations = JSON.parse(decodeURIComponent(option.dataset.variations || "%5B%5D"));
        variationSelect.innerHTML = variations.map((variation) => `<option value="${escapeHtml(variation)}">${escapeHtml(variation)}</option>`).join("");
        variationSelect.classList.toggle("hidden", !variations.length);
    }

    function addEditorItem(form) {
        const option = selectedCatalogOption(form);
        if (!option) return;
        const [tipo, itemId] = option.value.split(":");
        const variationSelect = form.querySelector("[data-editor-variation]");
        const qty = Math.max(parseInt(form.querySelector("[data-editor-qty]")?.value || "1", 10), 1);
        const note = form.querySelector("[data-editor-note]")?.value || "";
        const variation = variationSelect && !variationSelect.classList.contains("hidden") ? variationSelect.value : "";
        const row = document.createElement("div");
        row.className = "ped-item-editor-row";
        row.dataset.editorRow = "true";
        row.dataset.tipo = tipo;
        row.dataset.itemId = itemId;
        row.dataset.variacao = variation;
        row.dataset.quantidade = String(qty);
        row.dataset.observacao = note;
        row.dataset.preco = option.dataset.price || "0";
        row.innerHTML = `<span>${qty}x ${escapeHtml(option.dataset.name)}${variation ? ` - ${escapeHtml(variation)}` : ""}</span><button type="button" data-editor-remove-item>Remover</button>`;
        form.querySelector("[data-editor-items]")?.appendChild(row);
        updateCreateOrderTotal(form);
    }

    function buildItemsPayload(form) {
        return Array.from(form.querySelectorAll("[data-editor-row]")).map((row) => ({
            tipo: row.dataset.tipo,
            item_id: row.dataset.itemId,
            variacao: row.dataset.variacao || "",
            quantidade: row.dataset.quantidade || "1",
            observacao: row.dataset.observacao || "",
        }));
    }

    async function submitAjaxForm(form, beforeSubmit) {
        const button = form.querySelector('button[type="submit"]');
        if (typeof beforeSubmit === "function") beforeSubmit();
        if (button) button.disabled = true;
        try {
            const action = form.action || form.dataset.action;
            if (!action) throw new Error("Formulario sem destino de envio.");
            const response = await fetch(action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": csrfToken,
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                },
                body: form.__body || new URLSearchParams(new FormData(form)).toString(),
                credentials: "same-origin",
            });
            if (!response.ok) throw new Error(await response.text());
            if (form.matches("[data-new-order-finalize-form]")) {
                await response.json();
                closeDetail();
                notifyOrdersChanged();
                return;
            }
            if (currentDetailUrl) {
                if (form.matches("[data-items-editor]")) closeItemsEditor();
                if (form.matches("[data-delivery-editor]")) closeDeliveryEditor();
                if (form.matches("[data-modal-status-form]")) {
                    closeDetail();
                    notifyOrdersChanged();
                    return;
                }
                await openDetail({ dataset: { orderDetailUrl: currentDetailUrl } });
                notifyOrdersChanged();
            }
        } catch (error) {
            if (content) {
                content.insertAdjacentHTML("afterbegin", '<div class="ped-modal-error">Não foi possível salvar as alterações.</div>');
            }
            console.error(error);
        } finally {
            if (button) button.disabled = false;
        }
    }

    document.addEventListener("click", (event) => {
        const createButton = event.target.closest("[data-new-order-url]");
        if (createButton) {
            event.preventDefault();
            openCreateOrder(createButton);
            return;
        }

        const closeButton = event.target.closest("[data-close-pedido-detail-modal]");
        if (closeButton || event.target === modal) {
            closeDetail();
            return;
        }
        if (event.target.closest("[data-close-items-editor]") || event.target === itemsModal) {
            closeItemsEditor();
            return;
        }
        if (event.target.closest("[data-close-delivery-editor]") || event.target === deliveryModal) {
            closeDeliveryEditor();
            return;
        }

        const card = event.target.closest("[data-order-detail-url]");
        if (!card || shouldIgnoreCardClick(event.target)) return;
        openDetail(card);
    });

    document.addEventListener("change", (event) => {
        const form = event.target.closest("[data-items-editor]");
        if (form && event.target.matches("[data-editor-catalog]")) {
            updateVariationSelect(form);
            return;
        }
    });

    document.addEventListener("click", (event) => {
        if (event.target.closest("[data-open-items-editor]")) {
            openItemsEditor();
            return;
        }
        if (event.target.closest("[data-open-delivery-editor]")) {
            openDeliveryEditor(false);
            return;
        }
        if (event.target.closest("[data-delivery-use-current]")) {
            showDeliveryEditorForm(deliveryEditorHost || document, false);
            return;
        }
        if (event.target.closest("[data-delivery-create]")) {
            showDeliveryEditorForm(deliveryEditorHost || document, true);
            return;
        }
        if (event.target.closest("[data-delivery-back]")) {
            showDeliverySelector(deliveryEditorHost || document);
            return;
        }
        const inlineEdit = event.target.closest("[data-inline-edit]");
        if (inlineEdit) {
            openInlineEditor(inlineEdit);
            return;
        }
        const addButton = event.target.closest("[data-editor-add-item]");
        if (addButton) {
            addEditorItem(addButton.closest("[data-items-editor]"));
            return;
        }
        const removeButton = event.target.closest("[data-editor-remove-item]");
        if (removeButton) {
            const form = removeButton.closest("[data-items-editor]");
            removeButton.closest("[data-editor-row]")?.remove();
        }
    });

    document.addEventListener("submit", async (event) => {
        const form = event.target.closest("[data-payment-form]");
        if (form) {
            event.preventDefault();
            submitPaymentForm(form);
            return;
        }
        const itemsForm = event.target.closest("[data-items-editor]");
        if (itemsForm) {
            event.preventDefault();
            submitAjaxForm(itemsForm, () => {
                itemsForm.querySelector("[data-editor-payload]").value = JSON.stringify(buildItemsPayload(itemsForm));
            });
            return;
        }
        const statusForm = event.target.closest("[data-modal-status-form]");
        if (statusForm) {
            event.preventDefault();
            const message = statusForm.dataset.confirm;
            if (message && !(await confirmModal(message))) return;
            submitAjaxForm(statusForm);
            return;
        }
        const inlineForm = event.target.closest("[data-inline-edit-form]");
        if (inlineForm) {
            event.preventDefault();
            const inlineValue = inlineForm.querySelector("[name='value']")?.value || "";
            if (inlineForm.dataset.field === "tipo_coleta" && inlineValue === "entrega") {
                openDeliveryEditor(true);
                return;
            }
            if (
                inlineForm.dataset.field === "tipo_coleta"
                && inlineValue === "retirada"
                && !(await confirmModal("Alterar este pedido para retirada? O frete sera zerado e o endereco virara Retirada no local."))
            ) {
                return;
            }
            const formData = new URLSearchParams();
            const param = inlineForm.dataset.param || "value";
            if (param === "value") {
                formData.set("field", inlineForm.dataset.field);
            }
            formData.set(param, inlineValue);
            submitAjaxForm(inlineForm, () => {
                inlineForm.__body = formData.toString();
            });
            return;
        }
        const couponForm = event.target.closest("[data-coupon-form]");
        if (couponForm) {
            event.preventDefault();
            submitAjaxForm(couponForm);
            return;
        }
        const printQueueForm = event.target.closest("[data-print-queue-form]");
        if (printQueueForm) {
            event.preventDefault();
            submitPrintQueueForm(printQueueForm);
            return;
        }
        const newOrderFinalizeForm = event.target.closest("[data-new-order-finalize-form]");
        if (newOrderFinalizeForm) {
            event.preventDefault();
            submitAjaxForm(newOrderFinalizeForm);
            return;
        }
        const simpleForm = event.target.closest("[data-delivery-editor]");
        if (!simpleForm) return;
        event.preventDefault();
        submitAjaxForm(simpleForm);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && deliveryModal && !deliveryModal.classList.contains("hidden")) {
            closeDeliveryEditor();
            return;
        }
        if (event.key === "Escape" && itemsModal && !itemsModal.classList.contains("hidden")) {
            closeItemsEditor();
            return;
        }
        if (event.key === "Escape" && !modal.classList.contains("hidden")) {
            closeDetail();
            return;
        }

        if ((event.key === "Enter" || event.key === " ") && event.target.matches("[data-order-detail-url]")) {
            event.preventDefault();
            openDetail(event.target);
        }
    });
})();
