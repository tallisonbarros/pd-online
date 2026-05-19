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
    let latestDetailPayload = null;
    const suggestedCustomerPhones = new Set();

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
            latestDetailPayload = null;
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
                latestDetailPayload = null;
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

    function normalizePhone(value) {
        let digits = String(value || "").replace(/\D/g, "");
        if (digits.length > 11 && digits.startsWith("55")) digits = digits.slice(2);
        return digits;
    }

    function detailMeta() {
        return content?.querySelector("[data-current-detail-url]") || null;
    }

    function isDraftOrder() {
        const meta = detailMeta();
        return meta?.dataset.isNewOrder === "true" || meta?.dataset.orderStatus === "rascunho";
    }

    function currentAddressAllowsSuggestion() {
        const meta = detailMeta();
        if (meta?.dataset.isNewOrder === "true") return true;
        const address = content?.querySelector("[data-modal-address] > span")?.textContent?.trim() || "";
        return !address || address === "Retirada no local";
    }

    function updateLinkedCustomerName(name) {
        const phoneFact = content?.querySelector("[data-modal-fact='telefone']");
        if (!phoneFact || !name) return;
        let linked = phoneFact.querySelector(".ped-linked-client-name");
        if (!linked) {
            linked = document.createElement("small");
            linked.className = "ped-linked-client-name";
            phoneFact.prepend(linked);
        }
        linked.textContent = name;
    }

    function buildAddressMeta(endereco) {
        return [endereco.complemento, endereco.lote_quadra, endereco.ponto_referencia].filter(Boolean).join(" - ");
    }

    function chooseCustomerAddressModal(cliente, enderecos) {
        return new Promise((resolve) => {
            const backdrop = document.createElement("div");
            backdrop.className = "modal-backdrop ped-confirm-modal";
            backdrop.innerHTML = `
                <div class="modal-card ped-confirm-card" role="dialog" aria-modal="true" aria-labelledby="customer-address-title">
                    <div class="modal-content ped-confirm-content">
                        <strong id="customer-address-title">Endereco encontrado</strong>
                        <p>Esse telefone ja tem enderecos salvos${cliente?.nome ? ` para ${escapeHtml(cliente.nome)}` : ""}. Quer usar um deles neste pedido?</p>
                        <div class="saved-profile-list">
                            ${enderecos.map((endereco, index) => `
                                <article class="saved-profile-entry">
                                    <button type="button" class="saved-profile-button" data-customer-address-index="${index}">
                                        <span class="saved-profile-meta">
                                            <span class="saved-profile-text">
                                                <strong>${escapeHtml(endereco.endereco_formatado || endereco.endereco)}</strong>
                                                ${buildAddressMeta(endereco) ? `<small>${escapeHtml(buildAddressMeta(endereco))}</small>` : ""}
                                            </span>
                                        </span>
                                    </button>
                                </article>
                            `).join("")}
                        </div>
                        <div class="ped-confirm-actions">
                            <button type="button" class="ped-btn ped-btn-soft" data-customer-address-new>Cadastrar outro endereco</button>
                            <button type="button" class="ped-btn ped-btn-soft" data-customer-address-ignore>Ignorar</button>
                        </div>
                    </div>
                </div>
            `;

            const onKeydown = (event) => {
                if (event.key === "Escape") close(null);
            };

            function close(value) {
                document.removeEventListener("keydown", onKeydown);
                backdrop.remove();
                resolve(value);
            }

            backdrop.addEventListener("click", (event) => {
                if (event.target === backdrop || event.target.closest("[data-customer-address-ignore]")) {
                    close(null);
                    return;
                }
                if (event.target.closest("[data-customer-address-new]")) {
                    close("new");
                    return;
                }
                const button = event.target.closest("[data-customer-address-index]");
                if (!button) return;
                close(enderecos[Number(button.dataset.customerAddressIndex)]);
            });

            document.addEventListener("keydown", onKeydown);
            document.body.appendChild(backdrop);
            backdrop.querySelector("[data-customer-address-ignore]")?.focus();
        });
    }

    function addressToFormBody(endereco) {
        const body = new URLSearchParams();
        body.set("tipo_coleta", "entrega");
        body.set("rua", endereco.rua || "");
        body.set("numero", endereco.numero_endereco || "");
        body.set("bairro", endereco.bairro || "");
        body.set("cidade", endereco.cidade || "Rio Verde");
        body.set("estado", endereco.estado || "GO");
        body.set("endereco_formatado", endereco.endereco_formatado || endereco.endereco || "");
        body.set("latitude", endereco.latitude || "");
        body.set("longitude", endereco.longitude || "");
        body.set("complemento", endereco.complemento || "");
        body.set("lote_quadra", endereco.lote_quadra || "");
        body.set("ponto_referencia", endereco.ponto_referencia || "");
        return body;
    }

    function addressHasCoordinates(endereco) {
        return Boolean(endereco?.latitude && endereco?.longitude);
    }

    function fillDeliveryFormFromAddress(form, endereco) {
        if (!form || !endereco) return;
        const values = {
            rua: endereco.rua || "",
            numero: endereco.numero_endereco || "",
            bairro: endereco.bairro || "",
            cidade: endereco.cidade || "Rio Verde",
            estado: endereco.estado || "GO",
            endereco_formatado: endereco.endereco_formatado || endereco.endereco || "",
            latitude: endereco.latitude || "",
            longitude: endereco.longitude || "",
            complemento: endereco.complemento || "",
            lote_quadra: endereco.lote_quadra || "",
            ponto_referencia: endereco.ponto_referencia || "",
        };
        Object.entries(values).forEach(([name, value]) => {
            const input = form.querySelector(`[name='${name}']`);
            if (input) input.value = value;
        });
        const searchInput = form.querySelector("#operator-address-query");
        if (searchInput) searchInput.value = values.endereco_formatado || values.rua;
        const districtInput = form.querySelector("#operator-district-query");
        if (districtInput) districtInput.value = values.bairro;
    }

    function openDeliveryEditorWithAddress(endereco) {
        openDeliveryEditor(false, endereco);
        const form = deliveryEditorHost?.querySelector("[data-delivery-editor]");
        const feedback = form?.querySelector("#address-map-feedback");
        if (feedback) {
            feedback.textContent = "Endereco preenchido. Confirme o ponto no mapa para calcular a entrega.";
        }
    }

    async function applySuggestedAddress(endereco) {
        const action = detailMeta()?.dataset.deliveryActionUrl;
        if (!action || !endereco) return;
        const response = await fetch(action, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": csrfToken,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            body: addressToFormBody(endereco).toString(),
            credentials: "same-origin",
        });
        if (!response.ok) throw new Error(await response.text());
        applyModalPayload(await response.json(), { syncEditor: false });
    }

    async function suggestCustomerFromPhone(phone) {
        if (!isDraftOrder() || !currentAddressAllowsSuggestion()) return;
        const normalized = normalizePhone(phone);
        if (!normalized || suggestedCustomerPhones.has(normalized)) return;
        suggestedCustomerPhones.add(normalized);

        const url = detailMeta()?.dataset.customerAddressUrl;
        if (!url) return;
        const response = await fetch(`${url}?telefone=${encodeURIComponent(phone)}`, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
        });
        if (!response.ok) return;
        const payload = await response.json();
        if (payload?.cliente?.nome) updateLinkedCustomerName(payload.cliente.nome);
        const enderecos = Array.isArray(payload?.enderecos) ? payload.enderecos : [];
        if (!enderecos.length) return;
        const selected = await chooseCustomerAddressModal(payload.cliente, enderecos);
        if (selected === "new") {
            openDeliveryEditor(true);
            return;
        }
        if (!selected) return;
        if (!addressHasCoordinates(selected)) {
            openDeliveryEditorWithAddress(selected);
            return;
        }
        await applySuggestedAddress(selected);
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
            applyModalPayload(await response.json(), { syncEditor: false });
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
        form.dataset.type = type;
        form.dataset.inlineClass = node.className || "ped-inline-edit";
        if (node.dataset.options) form.dataset.options = node.dataset.options;

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

        const status = document.createElement("span");
        status.className = "ped-autosave-status";
        status.dataset.inlineAutosaveStatus = "true";
        status.setAttribute("aria-live", "polite");

        form.appendChild(control);
        form.appendChild(status);
        node.replaceWith(form);
        control.focus();
        if (control.select) control.select();
        if (type === "select") {
            control.addEventListener("change", () => submitInlineForm(form));
        } else {
            control.addEventListener("blur", () => submitInlineForm(form));
            control.addEventListener("keydown", (event) => {
                if (event.key === "Enter" && type !== "textarea") {
                    event.preventDefault();
                    submitInlineForm(form);
                }
                if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                    event.preventDefault();
                    submitInlineForm(form);
                }
            });
        }
    }

    function openItemsEditor() {
        const template = content.querySelector("[data-items-editor-template]");
        if (!template || !itemsEditorHost) return;
        itemsEditorHost.innerHTML = "";
        itemsEditorHost.appendChild(template.content.cloneNode(true));
        if (latestDetailPayload?.itens?.length) {
            const editorItems = itemsEditorHost.querySelector("[data-editor-items]");
            if (editorItems) editorItems.innerHTML = buildEditorRows(latestDetailPayload);
        }
        setItemsEditorOpen(true);
        loadCatalog(itemsEditorHost);
    }

    function closeItemsEditor() {
        setItemsEditorOpen(false);
        if (itemsEditorHost) itemsEditorHost.innerHTML = "";
    }

    function openDeliveryEditor(clearFields, prefillAddress) {
        const template = content.querySelector("[data-delivery-editor-template]");
        if (!template || !deliveryEditorHost) return;
        deliveryEditorHost.innerHTML = "";
        deliveryEditorHost.appendChild(template.content.cloneNode(true));
        const form = deliveryEditorHost.querySelector("[data-delivery-editor]");
        if (prefillAddress) fillDeliveryFormFromAddress(form, prefillAddress);
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
        const useIfood = content?.querySelector("[data-inline-edit][data-field='ifood']")?.dataset.value === "sim";
        select.innerHTML = (payload.items || []).map((item) => {
            const variations = encodeURIComponent(JSON.stringify(item.variacoes || []));
            const price = useIfood ? item.preco_ifood : item.preco;
            return `<option value="${item.tipo}:${item.id}" data-name="${escapeHtml(item.nome)}" data-price="${escapeHtml(price)}" data-price-ifood="${escapeHtml(item.preco_ifood)}" data-variations="${variations}">${escapeHtml(item.nome)} - R$ ${escapeHtml(price).replace(".", ",")}</option>`;
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

    function modalPedido(payload) {
        return payload?.pedido || {};
    }

    function fieldValueFromPayload(field, pedido) {
        if (field === "nome_cliente") return pedido.nome_cliente || "";
        if (field === "telefone") return pedido.telefone || "";
        if (field === "forma_pagamento") return pedido.forma_pagamento || "";
        if (field === "enviar_talheres") return pedido.enviar_talheres || "nao";
        if (field === "ifood") return pedido.ifood || "nao";
        if (field === "tipo_coleta") return pedido.tipo_coleta || "";
        if (field === "observacao_geral") return pedido.observacao_geral || "";
        return "";
    }

    function fieldLabelFromPayload(field, pedido) {
        if (field === "nome_cliente") return pedido.nome_cliente || "Cliente";
        if (field === "telefone") return pedido.telefone || "Adicionar telefone";
        if (field === "forma_pagamento") return pedido.forma_pagamento_label || "";
        if (field === "enviar_talheres") return pedido.enviar_talheres_label || "";
        if (field === "ifood") return pedido.ifood_label || "";
        if (field === "tipo_coleta") return pedido.tipo_coleta_label || "";
        if (field === "observacao_geral") return pedido.observacao_geral || "Adicionar observacao";
        return "";
    }

    function createInlineDisplay(form, payload) {
        const pedido = modalPedido(payload);
        const span = document.createElement("span");
        span.className = form.dataset.inlineClass || "ped-inline-edit";
        span.dataset.inlineEdit = "true";
        span.dataset.field = form.dataset.field || "";
        span.dataset.type = form.dataset.type || "text";
        span.dataset.value = fieldValueFromPayload(span.dataset.field, pedido);
        span.dataset.action = form.dataset.action || form.action || "";
        span.dataset.param = form.dataset.param || "value";
        if (form.dataset.options) span.dataset.options = form.dataset.options;
        span.textContent = fieldLabelFromPayload(span.dataset.field, pedido);
        return span;
    }

    function buildModalItems(payload) {
        const itens = Array.isArray(payload?.itens) ? payload.itens : [];
        const pedido = modalPedido(payload);
        const rows = itens.length
            ? itens.map((item) => `
                <li>
                    <div>
                        <strong>${escapeHtml(item.quantidade)}x ${escapeHtml(item.nome)}</strong>
                        ${item.variacao ? `<small>${escapeHtml(item.variacao)}</small>` : ""}
                        ${item.observacao ? `<small>Obs.: ${escapeHtml(item.observacao)}</small>` : ""}
                    </div>
                    <span>${escapeHtml(item.subtotal)}</span>
                </li>
            `).join("")
            : '<li class="is-empty">Nenhum item encontrado.</li>';
        const promo = pedido.promocao_descricao && pedido.promocao_desconto && pedido.promocao_desconto !== "R$ 0,00"
            ? `
                <li class="is-discount">
                    <div>
                        <strong>${escapeHtml(pedido.promocao_descricao || "Promocao especial")}</strong>
                        <small>Promocao aplicada</small>
                    </div>
                    <span>- ${escapeHtml(pedido.promocao_desconto)}</span>
                </li>
            `
            : "";
        const coupon = pedido.cupom_codigo && pedido.cupom_desconto && pedido.cupom_desconto !== "R$ 0,00"
            ? `
                <li class="is-discount">
                    <div>
                        <strong>Cupom ${escapeHtml(pedido.cupom_codigo)}</strong>
                        <small>Desconto aplicado</small>
                    </div>
                    <span>- ${escapeHtml(pedido.cupom_desconto)}</span>
                </li>
            `
            : "";
        return rows + promo + coupon;
    }

    function buildEditorRows(payload) {
        return (Array.isArray(payload?.itens) ? payload.itens : []).filter((item) => item.tipo && item.item_id).map((item) => `
            <div
                class="ped-item-editor-row"
                data-editor-row
                data-tipo="${escapeHtml(item.tipo)}"
                data-item-id="${escapeHtml(item.item_id)}"
                data-variacao="${escapeHtml(item.variacao)}"
                data-quantidade="${escapeHtml(item.quantidade)}"
                data-observacao="${escapeHtml(item.observacao)}"
            >
                <span>${escapeHtml(item.quantidade)}x ${escapeHtml(item.nome)}${item.variacao ? ` - ${escapeHtml(item.variacao)}` : ""}</span>
                <button type="button" data-editor-remove-item aria-label="Remover item">Remover</button>
            </div>
        `).join("");
    }

    function applyModalPayload(payload, options = {}) {
        if (!payload?.ok) return;
        latestDetailPayload = payload;
        const pedido = modalPedido(payload);
        const totalNode = content?.querySelector("[data-modal-total]");
        if (totalNode) totalNode.textContent = pedido.total || "";
        const itemsList = content?.querySelector("[data-modal-items-list]");
        if (itemsList) itemsList.innerHTML = buildModalItems(payload);
        const editorItems = itemsEditorHost?.querySelector("[data-editor-items]");
        if (editorItems && options.syncEditor !== false) editorItems.innerHTML = buildEditorRows(payload);

        content?.querySelectorAll("[data-inline-edit]").forEach((node) => {
            const field = node.dataset.field;
            node.dataset.value = fieldValueFromPayload(field, pedido);
            node.textContent = fieldLabelFromPayload(field, pedido);
        });
        if (pedido.cliente_nome) updateLinkedCustomerName(pedido.cliente_nome);

        const facts = content?.querySelector(".ped-modal-facts");
        facts?.classList.toggle("is-pickup", pedido.tipo_coleta === "retirada");

        const address = content?.querySelector("[data-modal-address] > span");
        if (address) address.textContent = pedido.endereco || "";
        const route = content?.querySelector("[data-modal-route]");
        if (route) {
            route.href = pedido.google_maps_route_url || "#";
            route.classList.toggle("hidden", pedido.tipo_coleta === "retirada");
        }

        const subtotal = content?.querySelector("[data-modal-audit='subtotal']");
        if (subtotal) subtotal.textContent = pedido.itens_subtotal || "";
        const frete = content?.querySelector("[data-modal-frete]");
        if (frete) frete.textContent = pedido.valor_frete || "";
        const distancia = content?.querySelector("[data-modal-distancia]");
        if (distancia) distancia.textContent = `${pedido.distancia_km || "0,00"} km`;
        const auditTotal = content?.querySelector("[data-modal-audit='total']");
        if (auditTotal) auditTotal.textContent = pedido.total || "";

        const couponInput = content?.querySelector("[data-autosave-coupon]");
        if (couponInput && document.activeElement !== couponInput) couponInput.value = pedido.cupom_codigo || "";
        const couponSummary = content?.querySelector(".ped-coupon-box strong");
        if (couponSummary) {
            couponSummary.textContent = pedido.cupom_codigo
                ? `${pedido.cupom_codigo} - ${pedido.cupom_desconto}`
                : "Nenhum cupom aplicado";
        }
        notifyOrdersChanged();
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

    async function submitAjaxForm(form, beforeSubmit, options = {}) {
        const button = form.querySelector('button[type="submit"]');
        const statusNode = form.querySelector("[data-inline-autosave-status], [data-editor-autosave-status], [data-coupon-autosave-status], [data-delivery-autosave-status]");
        if (typeof beforeSubmit === "function") beforeSubmit();
        if (button) button.disabled = true;
        if (statusNode) statusNode.textContent = "Salvando...";
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
            const payload = await response.json();
            applyModalPayload(payload, options);
            if (statusNode) statusNode.textContent = "Salvo";
            if (form.matches("[data-delivery-editor]")) {
                closeDeliveryEditor();
            }
            if (currentDetailUrl && form.matches("[data-modal-status-form]")) {
                closeDetail();
                notifyOrdersChanged();
                return payload;
            }
            return payload;
        } catch (error) {
            if (content) {
                content.insertAdjacentHTML("afterbegin", '<div class="ped-modal-error">Nao foi possivel salvar as alteracoes.</div>');
            }
            if (statusNode) statusNode.textContent = "Erro ao salvar";
            console.error(error);
            throw error;
        } finally {
            if (button) button.disabled = false;
            if (statusNode) {
                window.setTimeout(() => {
                    if (statusNode.textContent === "Salvo") statusNode.textContent = "";
                }, 1400);
            }
        }
    }

    async function submitInlineForm(inlineForm) {
        if (!inlineForm || inlineForm.dataset.saving === "true") return;
        const inlineValue = inlineForm.querySelector("[name='value']")?.value || "";
        if (inlineForm.dataset.field === "tipo_coleta" && inlineValue === "entrega") {
            openDeliveryEditor(true);
            inlineForm.replaceWith(createInlineDisplay(inlineForm, { ok: true, pedido: { tipo_coleta: "retirada", tipo_coleta_label: "Retirada" } }));
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
        inlineForm.__body = formData.toString();
        inlineForm.dataset.saving = "true";
        try {
            const payload = await submitAjaxForm(inlineForm, null, { syncEditor: false });
            inlineForm.replaceWith(createInlineDisplay(inlineForm, payload));
            if (inlineForm.dataset.field === "telefone") {
                await suggestCustomerFromPhone(inlineValue);
            }
        } finally {
            inlineForm.dataset.saving = "false";
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

    document.addEventListener("prato:open-order-detail", (event) => {
        const url = event.detail?.url;
        if (!url) return;
        openDetail({ dataset: { orderDetailUrl: url } });
    });

    document.addEventListener("change", (event) => {
        const form = event.target.closest("[data-items-editor]");
        if (form && event.target.matches("[data-editor-catalog]")) {
            updateVariationSelect(form);
            return;
        }
        const inlineForm = event.target.closest("[data-inline-edit-form]");
        if (inlineForm && event.target.matches("select")) {
            submitInlineForm(inlineForm);
            return;
        }
    });

    document.addEventListener("blur", (event) => {
        const inlineForm = event.target.closest("[data-inline-edit-form]");
        if (inlineForm && event.target.matches("input, textarea")) {
            submitInlineForm(inlineForm);
            return;
        }
        const couponForm = event.target.closest("[data-coupon-form]");
        if (couponForm && event.target.matches("[data-autosave-coupon]")) {
            submitAjaxForm(couponForm);
        }
    }, true);

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
            const form = addButton.closest("[data-items-editor]");
            addEditorItem(form);
            submitAjaxForm(form, () => {
                form.querySelector("[data-editor-payload]").value = JSON.stringify(buildItemsPayload(form));
            }, { syncEditor: false }).catch(() => {});
            return;
        }
        const removeButton = event.target.closest("[data-editor-remove-item]");
        if (removeButton) {
            const form = removeButton.closest("[data-items-editor]");
            if (form.querySelectorAll("[data-editor-row]").length <= 1) {
                const status = form.querySelector("[data-editor-autosave-status]");
                if (status) status.textContent = "O pedido precisa ter pelo menos um item.";
                return;
            }
            removeButton.closest("[data-editor-row]")?.remove();
            submitAjaxForm(form, () => {
                form.querySelector("[data-editor-payload]").value = JSON.stringify(buildItemsPayload(form));
            }, { syncEditor: false }).catch(() => {});
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
            submitInlineForm(inlineForm);
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
