from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.utils import timezone

from .models import Adicional, Bebida, Cliente, ClienteTokenConflito, Cupom, EnderecoCliente, ItemPedido, Pedido, Prato


def safe_text(value):
    return str(value or "").strip()


def money_decimal(value):
    try:
        return Decimal(str(value or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def normalize_coupon_code(value):
    return safe_text(value).upper()


def normalize_phone(value):
    digits = "".join(char for char in str(value or "") if char.isdigit())
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    return digits


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
            "telefone": safe_text(pedido.telefone),
            "nome": nome_cliente,
            "primeiro_pedido_em": pedido.criado_em,
            "ultimo_pedido_em": pedido.criado_em,
        },
    )

    update_fields = []
    if safe_text(pedido.telefone) and cliente.telefone != safe_text(pedido.telefone):
        cliente.telefone = safe_text(pedido.telefone)
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

        preco = catalog_item.preco or Decimal("0.00")
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
        )
        total += item_pedido.subtotal
    return total


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
    subtotal = pedido.itens.aggregate(total_sum=Sum("subtotal")).get("total_sum") or Decimal("0.00")
    promocao_result = calcular_promocao_marmitas(pedido)
    promocao_desconto = min(promocao_result["discount"], subtotal)
    subtotal_com_promocao = max(subtotal - promocao_desconto, Decimal("0.00"))
    codigo = normalize_coupon_code(cupom_codigo if cupom_codigo is not None else pedido.cupom_codigo)
    cupom_result = validar_cupom(codigo, subtotal_com_promocao, pedido.valor_frete, pedido=pedido) if codigo else None
    if codigo and not cupom_result["ok"]:
        raise ValueError(cupom_result["message"])
    cupom_desconto = min(cupom_result["discount"], subtotal_com_promocao) if cupom_result else Decimal("0.00")

    pedido.total_sem_desconto = subtotal + pedido.valor_frete
    pedido.promocao_descricao = promocao_result["descricao"]
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
            "variacoes": [
                safe_text(line)
                for line in (getattr(item, "variacoes", "") or "").splitlines()
                if safe_text(line)
            ],
        }

    pratos = [item_payload("prato", prato) for prato in Prato.objects.filter(ativo=True)]
    bebidas = [item_payload("bebida", bebida) for bebida in Bebida.objects.filter(ativo=True)]
    adicionais = [item_payload("adicional", adicional) for adicional in Adicional.objects.filter(ativo=True)]
    return {"items": pratos + bebidas + adicionais}
