from decimal import Decimal, InvalidOperation
import unicodedata

from django.db.models import Sum
from django.utils import timezone

from .models import Adicional, Bebida, Cliente, ClienteTokenConflito, ConfiguracaoEntrega, Cupom, EnderecoCliente, ItemPedido, Pedido, Prato


DUPLA_VARIACOES_DESCONTO = Decimal("5.10")
DUPLA_VARIACOES_PRATOS = ("estrogonofe", "picadinho")
DUPLA_VARIACOES_OPCOES = ("frango", "fraldinha")
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
WEEKDAY_LABELS = {
    "seg": "SEGUNDA",
    "ter": "TERCA",
    "qua": "QUARTA",
    "qui": "QUINTA",
    "sex": "SEXTA",
    "sab": "SABADO",
    "dom": "DOMINGO",
}


def safe_text(value):
    return str(value or "").strip()


def normalize_text_key(value):
    normalized = unicodedata.normalize("NFD", safe_text(value))
    without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
    return without_accents.casefold().strip()


def money_decimal(value):
    try:
        return Decimal(str(value or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def normalize_classificacao_saida(value):
    value = safe_text(value)
    valid = {choice[0] for choice in ItemPedido.ClassificacaoSaida.choices}
    return value if value in valid else ItemPedido.ClassificacaoSaida.VENDIDA


def clear_order_items_prefetch(pedido):
    if hasattr(pedido, "_prefetched_objects_cache"):
        pedido._prefetched_objects_cache.pop("itens", None)


def normalize_coupon_code(value):
    return safe_text(value).upper()


def prato_dias_disponiveis(prato):
    if not safe_text(getattr(prato, "dias_disponiveis", "")):
        return set(WEEKDAYS)
    return {dia.strip().lower() for dia in prato.dias_disponiveis.split(",") if dia.strip()}


def prato_disponivel_no_dia(prato, weekday_key):
    return weekday_key in prato_dias_disponiveis(prato)


def resolve_pratos_disponiveis_context(config=None, now=None):
    config = config or ConfiguracaoEntrega.get_solo()
    current = now or timezone.localtime()
    fechamento = getattr(config, "horario_fechamento", None)
    start_offset = 1 if fechamento and current.time() >= fechamento else 0
    active_pratos = list(Prato.objects.filter(ativo=True))

    for offset in range(start_offset, start_offset + 7):
        weekday_key = WEEKDAYS[(current.weekday() + offset) % 7]
        pratos = [prato for prato in active_pratos if prato_disponivel_no_dia(prato, weekday_key)]
        if pratos:
            return {
                "pratos": pratos,
                "weekday_key": weekday_key,
                "label": "Pratos do dia" if offset == 0 else f"Pratos de {WEEKDAY_LABELS[weekday_key]}",
                "day_offset": offset,
            }

    weekday_key = WEEKDAYS[(current.weekday() + start_offset) % 7]
    return {
        "pratos": [],
        "weekday_key": weekday_key,
        "label": "Pratos do dia" if start_offset == 0 else f"Pratos de {WEEKDAY_LABELS[weekday_key]}",
        "day_offset": start_offset,
    }


def catalog_price(item, canal=None, use_ifood=False):
    if use_ifood:
        canal = Pedido.Canal.IFOOD
    channel_field = {
        Pedido.Canal.BALCAO: "preco_balcao",
        Pedido.Canal.SITE: "preco_site",
        Pedido.Canal.IFOOD: "preco_ifood",
    }.get(canal)
    if channel_field and getattr(item, channel_field, None) is not None:
        return getattr(item, channel_field)
    return getattr(item, "preco", None) or Decimal("0.00")


def normalize_phone(value, default_ddd="64"):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    ddd = "".join(char for char in str(default_ddd or "") if char.isdigit())

    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("55") and len(digits[2:]) in {8, 9, 10, 11}:
        digits = digits[2:]

    if len(digits) == 8:
        digits = f"{ddd}9{digits}"
    elif len(digits) == 9:
        digits = f"{ddd}{digits}"
    elif len(digits) == 10:
        digits = f"{digits[:2]}9{digits[2:]}"

    return digits if len(digits) == 11 else ""


def _order_name_is_placeholder(value):
    normalized = safe_text(value).casefold()
    return normalized in {"", "cliente"}


def _address_defaults_from_order(pedido):
    return {
        "endereco_formatado": safe_text(pedido.endereco_formatado),
        "rua": safe_text(pedido.rua),
        "numero_endereco": safe_text(pedido.numero_endereco),
        "bairro": safe_text(pedido.bairro),
        "cidade": safe_text(pedido.cidade) or "Rio Verde",
        "estado": safe_text(pedido.estado) or "GO",
        "latitude": pedido.latitude,
        "longitude": pedido.longitude,
        "primeiro_uso_em": pedido.criado_em,
        "ultimo_uso_em": pedido.criado_em,
        "ultimo_pedido": pedido,
    }


def sync_customer_from_order(pedido):
    telefone_normalizado = normalize_phone(pedido.telefone)
    if not telefone_normalizado or pedido.status == Pedido.Status.RASCUNHO:
        if not telefone_normalizado and pedido.cliente_id:
            pedido.cliente = None
            pedido.save(update_fields=["cliente"])
        return None

    nome_cliente = safe_text(pedido.nome_cliente) or "Cliente"
    should_inherit_customer_name = _order_name_is_placeholder(pedido.nome_cliente)
    cliente, created = Cliente.objects.get_or_create(
        telefone_normalizado=telefone_normalizado,
        defaults={
            "telefone": telefone_normalizado,
            "nome": nome_cliente,
            "primeiro_pedido_em": pedido.criado_em,
            "ultimo_pedido_em": pedido.criado_em,
        },
    )

    update_fields = []
    if cliente.telefone != telefone_normalizado:
        cliente.telefone = telefone_normalizado
        update_fields.append("telefone")
    if not should_inherit_customer_name and not cliente.nome_editado_manualmente and nome_cliente and cliente.nome != nome_cliente:
        cliente.nome = nome_cliente
        update_fields.append("nome")
    if pedido.criado_em and (not cliente.primeiro_pedido_em or pedido.criado_em < cliente.primeiro_pedido_em):
        cliente.primeiro_pedido_em = pedido.criado_em
        update_fields.append("primeiro_pedido_em")
    if pedido.criado_em and (not cliente.ultimo_pedido_em or pedido.criado_em > cliente.ultimo_pedido_em):
        cliente.ultimo_pedido_em = pedido.criado_em
        update_fields.append("ultimo_pedido_em")
    if update_fields:
        cliente.save(update_fields=list(set(update_fields)))

    order_update_fields = []
    if should_inherit_customer_name and safe_text(cliente.nome):
        pedido.nome_cliente = safe_text(cliente.nome)
        order_update_fields.append("nome_cliente")
    if pedido.cliente_id != cliente.id:
        pedido.cliente = cliente
        order_update_fields.append("cliente")
    if order_update_fields:
        pedido.save(update_fields=list(set(order_update_fields)))

    endereco = safe_text(pedido.endereco)
    if endereco:
        endereco_cliente, created = EnderecoCliente.objects.get_or_create(
            cliente=cliente,
            endereco=endereco,
            complemento=safe_text(pedido.complemento),
            lote_quadra=safe_text(pedido.lote_quadra),
            ponto_referencia=safe_text(pedido.ponto_referencia),
            defaults=_address_defaults_from_order(pedido),
        )
        endereco_updates = []
        for field, value in _address_defaults_from_order(pedido).items():
            current = getattr(endereco_cliente, field)
            if current != value:
                setattr(endereco_cliente, field, value)
                endereco_updates.append(field)
        if endereco_updates:
            endereco_cliente.save(update_fields=list(set(endereco_updates)))

    return cliente


def normalize_known_order_tokens(tokens):
    normalized = []
    for raw_token in tokens or []:
        token = safe_text(raw_token)
        if not token or len(token) > 120 or token in normalized:
            continue
        normalized.append(token)
        if len(normalized) >= 30:
            break
    return normalized


def inherit_customer_from_known_tokens(pedido, tokens):
    if normalize_phone(pedido.telefone) or pedido.cliente_id or pedido.status == Pedido.Status.RASCUNHO:
        return sync_customer_from_order(pedido)

    known_tokens = normalize_known_order_tokens(tokens)
    if not known_tokens:
        return None

    matched_orders = (
        Pedido.objects.select_related("cliente")
        .exclude(pk=pedido.pk)
        .filter(public_token__in=known_tokens)
    )
    customers = []
    for matched_order in matched_orders:
        customer = matched_order.cliente
        if not customer and normalize_phone(matched_order.telefone):
            customer = sync_customer_from_order(matched_order)
        if customer and normalize_phone(customer.telefone) and customer.id not in [item.id for item in customers]:
            customers.append(customer)

    if len(customers) == 1:
        customer = customers[0]
        pedido.telefone = customer.telefone
        pedido.cliente = customer
        pedido.save(update_fields=["telefone", "cliente"])
        return sync_customer_from_order(pedido)

    if len(customers) > 1:
        conflito = ClienteTokenConflito.objects.create(pedido=pedido, tokens=known_tokens)
        conflito.clientes.set(customers)
    return None


def create_order_items_from_payload(pedido, itens_payload, clear_existing=False):
    if clear_existing:
        pedido.itens.all().delete()

    total = Decimal("0.00")
    prato_ids = []
    adicional_ids = []
    bebida_ids = []
    for item in itens_payload:
        tipo = safe_text(item.get("tipo") or ("prato" if item.get("prato_id") else ""))
        try:
            item_id = int(item.get("item_id") or item.get("adicional_id") or item.get("bebida_id") or item.get("prato_id"))
        except (TypeError, ValueError):
            raise ValueError("Um dos itens do carrinho e invalido.")
        if tipo == "adicional":
            adicional_ids.append(item_id)
        elif tipo == "bebida":
            bebida_ids.append(item_id)
        else:
            prato_ids.append(item_id)

    pratos = {prato.id: prato for prato in Prato.objects.filter(id__in=prato_ids, ativo=True)}
    adicionais = {adicional.id: adicional for adicional in Adicional.objects.filter(id__in=adicional_ids, ativo=True)}
    bebidas = {bebida.id: bebida for bebida in Bebida.objects.filter(id__in=bebida_ids, ativo=True)}

    for item in itens_payload:
        tipo = safe_text(item.get("tipo") or ("prato" if item.get("prato_id") else ""))
        try:
            item_id = int(item.get("item_id") or item.get("adicional_id") or item.get("bebida_id") or item.get("prato_id"))
            quantidade = max(int(item.get("quantidade", 1)), 1)
        except (TypeError, ValueError):
            raise ValueError("Um dos itens do carrinho e invalido.")

        observacao = safe_text(item.get("observacao"))
        variacao_nome = safe_text(item.get("variacao") or item.get("variacao_nome"))
        prato = adicional = bebida = None

        if tipo == "adicional":
            adicional = adicionais.get(item_id)
            catalog_item = adicional
        elif tipo == "bebida":
            bebida = bebidas.get(item_id)
            catalog_item = bebida
        else:
            prato = pratos.get(item_id)
            catalog_item = prato
            tipo = "prato"

        if not catalog_item:
            raise ValueError("Um dos itens nao esta mais disponivel.")

        if tipo == "prato":
            variacoes_validas = {
                safe_text(line).casefold(): safe_text(line)
                for line in (getattr(catalog_item, "variacoes", "") or "").splitlines()
                if safe_text(line)
            }
            if variacoes_validas:
                variacao_key = variacao_nome.casefold()
                if variacao_key not in variacoes_validas:
                    raise ValueError(f"Selecione uma variacao para {catalog_item.nome}.")
                variacao_nome = variacoes_validas[variacao_key]
            else:
                variacao_nome = ""
        else:
            variacao_nome = ""

        preco = catalog_price(catalog_item, pedido.canal, pedido.ifood)
        classificacao_saida = (
            normalize_classificacao_saida(item.get("classificacao_saida"))
            if tipo == "prato"
            else ItemPedido.ClassificacaoSaida.VENDIDA
        )
        item_pedido = ItemPedido.objects.create(
            pedido=pedido,
            prato=prato,
            adicional=adicional,
            bebida=bebida,
            nome_prato_snapshot=catalog_item.nome,
            variacao_nome_snapshot=variacao_nome,
            preco_snapshot=preco,
            quantidade=quantidade,
            observacao=observacao,
            classificacao_saida=classificacao_saida,
        )
        total += item_pedido.subtotal
    return total


def reprice_order_items_from_catalog(pedido):
    for item in pedido.itens.select_related("prato", "bebida", "adicional"):
        catalog_item = item.prato or item.bebida or item.adicional
        if not catalog_item:
            continue
        item.preco_snapshot = catalog_price(catalog_item, pedido.canal, pedido.ifood)
        if not item.prato_id:
            item.classificacao_saida = ItemPedido.ClassificacaoSaida.VENDIDA
        item.save(update_fields=["preco_snapshot", "classificacao_saida", "subtotal"])


def calcular_promocao_marmitas(pedido):
    itens_prato = [item for item in pedido.itens.all() if item.prato_id]
    quantidade_pratos = sum(max(item.quantidade, 0) for item in itens_prato)
    marmitas_gratis = quantidade_pratos // 5
    if marmitas_gratis <= 0:
        return {"descricao": "", "discount": Decimal("0.00")}
    precos = [item.preco_snapshot for item in itens_prato if item.preco_snapshot and item.preco_snapshot > 0]
    if not precos:
        return {"descricao": "", "discount": Decimal("0.00")}
    desconto = (min(precos) * marmitas_gratis).quantize(Decimal("0.01"))
    descricao = "5ª marmita grátis" if marmitas_gratis == 1 else f"{marmitas_gratis} marmitas grátis"
    return {"descricao": descricao, "discount": desconto}


def normalizar_promocao_marmitas(pedido):
    itens_prato = [
        item
        for item in pedido.itens.select_related("prato").all()
        if item.prato_id and item.classificacao_saida != ItemPedido.ClassificacaoSaida.CORTESIA
    ]
    quantidade_pratos = sum(max(item.quantidade, 0) for item in itens_prato)
    marmitas_gratis = quantidade_pratos // 5
    if not itens_prato:
        return {"descricao": "", "valor": Decimal("0.00"), "quantidade": 0}

    grupos = [
        {
            "prato": item.prato,
            "nome_prato_snapshot": item.nome_prato_snapshot,
            "variacao_nome_snapshot": item.variacao_nome_snapshot,
            "preco_snapshot": item.preco_snapshot,
            "quantidade": max(item.quantidade, 0),
            "observacao": item.observacao,
            "promocao": 0,
        }
        for item in itens_prato
    ]
    pedido.itens.filter(prato_id__isnull=False).exclude(
        classificacao_saida=ItemPedido.ClassificacaoSaida.CORTESIA
    ).delete()

    if marmitas_gratis > 0:
        restantes = marmitas_gratis
        for grupo in sorted(grupos, key=lambda item: (item["preco_snapshot"] or Decimal("0.00"), item["nome_prato_snapshot"])):
            if restantes <= 0:
                break
            quantidade_promocao = min(grupo["quantidade"], restantes)
            grupo["promocao"] = quantidade_promocao
            restantes -= quantidade_promocao

    valor_promocional = Decimal("0.00")
    for grupo in grupos:
        quantidade_vendida = grupo["quantidade"] - grupo["promocao"]
        if quantidade_vendida > 0:
            ItemPedido.objects.create(
                pedido=pedido,
                prato=grupo["prato"],
                nome_prato_snapshot=grupo["nome_prato_snapshot"],
                variacao_nome_snapshot=grupo["variacao_nome_snapshot"],
                preco_snapshot=grupo["preco_snapshot"],
                quantidade=quantidade_vendida,
                observacao=grupo["observacao"],
                classificacao_saida=ItemPedido.ClassificacaoSaida.VENDIDA,
            )
        if grupo["promocao"] > 0:
            valor_promocional += (grupo["preco_snapshot"] or Decimal("0.00")) * grupo["promocao"]
            ItemPedido.objects.create(
                pedido=pedido,
                prato=grupo["prato"],
                nome_prato_snapshot=grupo["nome_prato_snapshot"],
                variacao_nome_snapshot=grupo["variacao_nome_snapshot"],
                preco_snapshot=grupo["preco_snapshot"],
                quantidade=grupo["promocao"],
                observacao=grupo["observacao"],
                classificacao_saida=ItemPedido.ClassificacaoSaida.PROMOCAO,
            )

    descricao = ""
    if marmitas_gratis == 1:
        descricao = "5ª marmita grátis"
    elif marmitas_gratis > 1:
        descricao = f"{marmitas_gratis} marmitas grátis"
    return {"descricao": descricao, "valor": valor_promocional.quantize(Decimal("0.01")), "quantidade": marmitas_gratis}


def calcular_promocao_dupla_variacoes(pedido):
    pares_por_prato = {}
    for item in pedido.itens.all():
        if not item.prato_id:
            continue
        if item.classificacao_saida != ItemPedido.ClassificacaoSaida.VENDIDA:
            continue
        nome_key = normalize_text_key(item.nome_prato_snapshot)
        if not any(prato_key in nome_key for prato_key in DUPLA_VARIACOES_PRATOS):
            continue
        variacao_key = normalize_text_key(item.variacao_nome_snapshot)
        if variacao_key not in DUPLA_VARIACOES_OPCOES:
            continue
        prato_promocao = next(prato_key for prato_key in DUPLA_VARIACOES_PRATOS if prato_key in nome_key)
        pares_por_prato.setdefault(prato_promocao, {opcao: 0 for opcao in DUPLA_VARIACOES_OPCOES})
        pares_por_prato[prato_promocao][variacao_key] += max(item.quantidade, 0)

    pares = sum(min(quantidades.values()) for quantidades in pares_por_prato.values())
    if pares <= 0:
        return {"descricao": "", "discount": Decimal("0.00")}

    desconto = (DUPLA_VARIACOES_DESCONTO * pares).quantize(Decimal("0.01"))
    descricao = "Dupla frango + fraldinha" if pares == 1 else f"{pares} duplas frango + fraldinha"
    return {"descricao": descricao, "discount": desconto}


def calcular_promocoes_pedido(pedido):
    promocoes = [
        calcular_promocao_dupla_variacoes(pedido),
    ]
    promocoes = [promo for promo in promocoes if promo["discount"] > 0]
    if not promocoes:
        return {"descricao": "", "discount": Decimal("0.00")}
    return {
        "descricao": " + ".join(promo["descricao"] for promo in promocoes if promo["descricao"]),
        "discount": sum((promo["discount"] for promo in promocoes), Decimal("0.00")).quantize(Decimal("0.01")),
    }


def validar_cupom(codigo, subtotal, frete=Decimal("0.00"), pedido=None):
    codigo = normalize_coupon_code(codigo)
    subtotal = money_decimal(subtotal)
    frete = money_decimal(frete)
    if not codigo:
        return {"ok": False, "message": "Informe um cupom.", "discount": Decimal("0.00"), "coupon": None}
    cupom = Cupom.objects.filter(codigo__iexact=codigo).first()
    if not cupom:
        return {"ok": False, "message": "Cupom nao encontrado.", "discount": Decimal("0.00"), "coupon": None}
    now = timezone.now()
    if not cupom.ativo:
        return {"ok": False, "message": "Cupom inativo.", "discount": Decimal("0.00"), "coupon": cupom}
    if cupom.data_inicio and cupom.data_inicio > now:
        return {"ok": False, "message": "Cupom ainda nao esta valido.", "discount": Decimal("0.00"), "coupon": cupom}
    if cupom.data_fim and cupom.data_fim < now:
        return {"ok": False, "message": "Cupom expirado.", "discount": Decimal("0.00"), "coupon": cupom}
    if cupom.valor_minimo_pedido and subtotal < cupom.valor_minimo_pedido:
        return {"ok": False, "message": f"Pedido minimo de R$ {cupom.valor_minimo_pedido:.2f}.".replace(".", ","), "discount": Decimal("0.00"), "coupon": cupom}
    usos = cupom.pedidos.exclude(pk=pedido.pk).count() if pedido else cupom.pedidos.count()
    if cupom.uso_maximo_total is not None and usos >= cupom.uso_maximo_total:
        return {"ok": False, "message": "Limite de uso do cupom atingido.", "discount": Decimal("0.00"), "coupon": cupom}
    if cupom.tipo_desconto == Cupom.TipoDesconto.PERCENTUAL:
        discount = (subtotal * cupom.valor / Decimal("100")).quantize(Decimal("0.01"))
    else:
        discount = cupom.valor.quantize(Decimal("0.01"))
    discount = min(max(discount, Decimal("0.00")), subtotal)
    total = subtotal + frete - discount
    return {"ok": True, "message": "Cupom aplicado.", "discount": discount, "coupon": cupom, "total": total}


def recalculate_order_totals(pedido, cupom_codigo=None):
    clear_order_items_prefetch(pedido)
    promocao_marmitas = normalizar_promocao_marmitas(pedido)
    clear_order_items_prefetch(pedido)
    subtotal = pedido.itens.aggregate(total_sum=Sum("subtotal")).get("total_sum") or Decimal("0.00")
    subtotal_bruto = sum(
        (Decimal(item.preco_snapshot or 0) * item.quantidade for item in pedido.itens.all()),
        Decimal("0.00"),
    ).quantize(Decimal("0.01"))
    promocao_result = calcular_promocoes_pedido(pedido)
    descricoes_promocao = [
        descricao
        for descricao in [promocao_marmitas["descricao"], promocao_result["descricao"]]
        if descricao
    ]
    promocao_desconto = min(promocao_result["discount"], subtotal)
    subtotal_com_promocao = max(subtotal - promocao_desconto, Decimal("0.00"))
    codigo = normalize_coupon_code(cupom_codigo if cupom_codigo is not None else pedido.cupom_codigo)
    cupom_result = validar_cupom(codigo, subtotal_com_promocao, pedido.valor_frete, pedido=pedido) if codigo else None
    if codigo and not cupom_result["ok"]:
        raise ValueError(cupom_result["message"])
    cupom_desconto = min(cupom_result["discount"], subtotal_com_promocao) if cupom_result else Decimal("0.00")

    pedido.total_sem_desconto = subtotal_bruto + pedido.valor_frete
    pedido.promocao_descricao = " + ".join(descricoes_promocao)
    pedido.promocao_desconto = promocao_desconto
    pedido.cupom = cupom_result["coupon"] if cupom_result else None
    pedido.cupom_codigo = cupom_result["coupon"].codigo if cupom_result else ""
    pedido.cupom_desconto = cupom_desconto
    pedido.total = subtotal + pedido.valor_frete - promocao_desconto - cupom_desconto
    pedido.save(update_fields=[
        "total_sem_desconto",
        "promocao_descricao",
        "promocao_desconto",
        "cupom",
        "cupom_codigo",
        "cupom_desconto",
        "total",
    ])
    return pedido.total


def replace_order_items(pedido, itens_payload):
    create_order_items_from_payload(pedido, itens_payload, clear_existing=True)
    return recalculate_order_totals(pedido)


def serialize_editor_catalog():
    def item_payload(tipo, item):
        return {
            "tipo": tipo,
            "id": item.id,
            "nome": item.nome,
            "preco": f"{(item.preco or Decimal('0.00')):.2f}",
            "preco_balcao": f"{catalog_price(item, Pedido.Canal.BALCAO):.2f}",
            "preco_site": f"{catalog_price(item, Pedido.Canal.SITE):.2f}",
            "preco_ifood": f"{(item.preco_ifood or item.preco or Decimal('0.00')):.2f}",
            "variacoes": [
                safe_text(line)
                for line in (getattr(item, "variacoes", "") or "").splitlines()
                if safe_text(line)
            ],
        }

    pratos_context = resolve_pratos_disponiveis_context()
    pratos = [item_payload("prato", prato) for prato in pratos_context["pratos"]]
    bebidas = [item_payload("bebida", bebida) for bebida in Bebida.objects.filter(ativo=True)]
    adicionais = [item_payload("adicional", adicional) for adicional in Adicional.objects.filter(ativo=True)]
    return {
        "items": pratos + bebidas + adicionais,
        "pratos_context": {
            "weekday_key": pratos_context["weekday_key"],
            "label": pratos_context["label"],
            "day_offset": pratos_context["day_offset"],
        },
    }
