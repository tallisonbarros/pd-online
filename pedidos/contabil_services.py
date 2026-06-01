from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .models import (
    BancoConta,
    CategoriaMovimentacaoCaixa,
    CategoriaMovimentacaoConta,
    ConfiguracaoEntrega,
    MovimentacaoCaixa,
    MovimentacaoConta,
    Pedido,
    TerminalCaixa,
)
from .order_services import money_decimal


def money_label(value):
    return f"R$ {Decimal(value or 0).quantize(Decimal('0.01')):.2f}".replace(".", ",")


def signed_money_label(value, positive_prefix=False):
    value = Decimal(value or 0).quantize(Decimal("0.01"))
    if value < 0:
        return f"- {money_label(abs(value))}"
    if positive_prefix:
        return f"+ {money_label(value)}"
    return money_label(value)


def terminal_padrao():
    terminal = TerminalCaixa.objects.filter(ativo=True).order_by("ordem", "id").first()
    if terminal:
        return terminal
    return TerminalCaixa.objects.create(nome="Terminal 01", codigo="terminal-01", ordem=10, ativo=True)


def banco_padrao():
    banco = BancoConta.objects.filter(ativo=True).order_by("ordem", "id").first()
    if banco:
        return banco
    return BancoConta.objects.create(nome="Banco 01", codigo="banco-01", ordem=10, ativo=True)


def normalize_categoria_nome(nome):
    return " ".join(str(nome or "").strip().split())


def get_or_create_categoria(nome, tipo):
    nome = normalize_categoria_nome(nome)
    if not nome:
        raise ValueError("Informe uma categoria.")

    categoria = CategoriaMovimentacaoCaixa.objects.filter(nome__iexact=nome).first()
    if categoria:
        if not categoria.ativo:
            categoria.ativo = True
            categoria.save(update_fields=["ativo"])
        return categoria

    tipo_padrao = tipo if tipo in dict(MovimentacaoCaixa.Tipo.choices) else CategoriaMovimentacaoCaixa.TipoPadrao.AMBOS
    return CategoriaMovimentacaoCaixa.objects.create(nome=nome, tipo_padrao=tipo_padrao)


def get_or_create_categoria_conta(nome, tipo):
    nome = normalize_categoria_nome(nome)
    if not nome:
        raise ValueError("Informe uma categoria.")

    categoria = CategoriaMovimentacaoConta.objects.filter(nome__iexact=nome).first()
    if categoria:
        if not categoria.ativo:
            categoria.ativo = True
            categoria.save(update_fields=["ativo"])
        return categoria

    tipo_padrao = tipo if tipo in dict(MovimentacaoConta.Tipo.choices) else CategoriaMovimentacaoConta.TipoPadrao.AMBOS
    return CategoriaMovimentacaoConta.objects.create(nome=nome, tipo_padrao=tipo_padrao)


def categoria_pedidos_dinheiro():
    categoria = CategoriaMovimentacaoCaixa.objects.filter(nome__iexact="Pedidos em dinheiro").first()
    if categoria:
        return categoria
    return CategoriaMovimentacaoCaixa.objects.create(
        nome="Pedidos em dinheiro",
        tipo_padrao=CategoriaMovimentacaoCaixa.TipoPadrao.ENTRADA,
    )


def categoria_pedidos_cartao_entrega():
    categoria = CategoriaMovimentacaoConta.objects.filter(nome__iexact="Pedidos no cartao").first()
    if categoria:
        return categoria
    return CategoriaMovimentacaoConta.objects.create(
        nome="Pedidos no cartao",
        tipo_padrao=CategoriaMovimentacaoConta.TipoPadrao.ENTRADA,
    )


def categoria_pedidos_pix_online():
    categoria = CategoriaMovimentacaoConta.objects.filter(nome__iexact="Pedidos no pix online").first()
    if categoria:
        return categoria
    return CategoriaMovimentacaoConta.objects.create(
        nome="Pedidos no pix online",
        tipo_padrao=CategoriaMovimentacaoConta.TipoPadrao.ENTRADA,
    )


def banco_pagamento_conta(pedido):
    config = ConfiguracaoEntrega.get_solo()
    if pedido.forma_pagamento == Pedido.FormaPagamento.PIX and config.banco_pix_id:
        return config.banco_pix
    if pedido.forma_pagamento == Pedido.FormaPagamento.CARTAO and config.banco_cartao_id:
        return config.banco_cartao
    return banco_padrao()


def categoria_pagamento_conta(pedido):
    if pedido.forma_pagamento == Pedido.FormaPagamento.PIX:
        return categoria_pedidos_pix_online()
    return categoria_pedidos_cartao_entrega()


def terminal_from_payload(post):
    terminal = None
    terminal_id = post.get("terminal")
    if terminal_id:
        terminal = TerminalCaixa.objects.filter(id=terminal_id, ativo=True).first()
    return terminal or terminal_padrao()


def banco_from_payload(post):
    banco = None
    banco_id = post.get("banco")
    if banco_id:
        banco = BancoConta.objects.filter(id=banco_id, ativo=True).first()
    return banco or banco_padrao()


def parse_movimentacao_payload(post):
    tipo = str(post.get("tipo") or "").strip().lower()
    if tipo not in dict(MovimentacaoCaixa.Tipo.choices):
        raise ValueError("Informe se a movimentacao e entrada ou saida.")

    nome = " ".join(str(post.get("nome") or "").strip().split())
    if not nome:
        raise ValueError("Informe o nome da movimentacao.")

    valor = money_decimal(post.get("valor"))
    if valor <= Decimal("0.00"):
        raise ValueError("Informe um valor maior que zero.")

    return {
        "terminal": terminal_from_payload(post),
        "tipo": tipo,
        "nome": nome,
        "descricao": str(post.get("descricao") or "").strip(),
        "valor": valor,
        "categoria": get_or_create_categoria(post.get("categoria"), tipo),
    }


def parse_movimentacao_conta_payload(post):
    tipo = str(post.get("tipo") or "").strip().lower()
    if tipo not in dict(MovimentacaoConta.Tipo.choices):
        raise ValueError("Informe se a movimentacao e entrada ou saida.")

    nome = " ".join(str(post.get("nome") or "").strip().split())
    if not nome:
        raise ValueError("Informe o nome da movimentacao.")

    valor = money_decimal(post.get("valor"))
    if valor <= Decimal("0.00"):
        raise ValueError("Informe um valor maior que zero.")

    return {
        "banco": banco_from_payload(post),
        "tipo": tipo,
        "nome": nome,
        "descricao": str(post.get("descricao") or "").strip(),
        "valor": valor,
        "categoria": get_or_create_categoria_conta(post.get("categoria"), tipo),
    }


def movimentacoes_ativas():
    return MovimentacaoCaixa.objects.filter(excluido_em__isnull=True)


def movimentacoes_conta_ativas():
    return MovimentacaoConta.objects.filter(excluido_em__isnull=True)


def criar_movimentacao_caixa(*, data_movimento, post, user):
    payload = parse_movimentacao_payload(post)
    return MovimentacaoCaixa.objects.create(
        data_movimento=data_movimento,
        criado_por=user,
        atualizado_por=user,
        **payload,
    )


def criar_movimentacao_conta(*, data_movimento, post, user):
    payload = parse_movimentacao_conta_payload(post)
    return MovimentacaoConta.objects.create(
        data_movimento=data_movimento,
        criado_por=user,
        atualizado_por=user,
        **payload,
    )


def atualizar_movimentacao_caixa(movimentacao, post, user):
    payload = parse_movimentacao_payload(post)
    for field, value in payload.items():
        setattr(movimentacao, field, value)
    movimentacao.atualizado_por = user
    movimentacao.save(
        update_fields=["terminal", "tipo", "nome", "descricao", "valor", "categoria", "atualizado_por", "atualizado_em"]
    )
    return movimentacao


def atualizar_movimentacao_conta(movimentacao, post, user):
    payload = parse_movimentacao_conta_payload(post)
    for field, value in payload.items():
        setattr(movimentacao, field, value)
    movimentacao.atualizado_por = user
    movimentacao.save(
        update_fields=["banco", "tipo", "nome", "descricao", "valor", "categoria", "atualizado_por", "atualizado_em"]
    )
    return movimentacao


def duplicar_movimentacao_caixa(movimentacao, user):
    return MovimentacaoCaixa.objects.create(
        terminal=movimentacao.terminal,
        categoria=movimentacao.categoria,
        data_movimento=movimentacao.data_movimento,
        tipo=movimentacao.tipo,
        nome=f"{movimentacao.nome} (copia)",
        descricao=movimentacao.descricao,
        valor=movimentacao.valor,
        origem=MovimentacaoCaixa.Origem.MANUAL,
        criado_por=user,
        atualizado_por=user,
    )


def duplicar_movimentacao_conta(movimentacao, user):
    return MovimentacaoConta.objects.create(
        banco=movimentacao.banco,
        categoria=movimentacao.categoria,
        data_movimento=movimentacao.data_movimento,
        tipo=movimentacao.tipo,
        nome=f"{movimentacao.nome} (copia)",
        descricao=movimentacao.descricao,
        valor=movimentacao.valor,
        origem=MovimentacaoConta.Origem.MANUAL,
        criado_por=user,
        atualizado_por=user,
    )


def excluir_movimentacao_caixa(movimentacao, user):
    movimentacao.excluido_em = timezone.now()
    movimentacao.excluido_por = user
    movimentacao.save(update_fields=["excluido_em", "excluido_por", "atualizado_em"])


def excluir_movimentacao_conta(movimentacao, user):
    movimentacao.excluido_em = timezone.now()
    movimentacao.excluido_por = user
    movimentacao.save(update_fields=["excluido_em", "excluido_por", "atualizado_em"])


def pedido_deve_gerar_movimentacao_caixa(pedido):
    return (
        pedido.forma_pagamento == Pedido.FormaPagamento.DINHEIRO
        and pedido.status not in {Pedido.Status.RASCUNHO, Pedido.Status.CANCELADO}
    )


def pedido_deve_gerar_movimentacao_conta(pedido):
    return (
        pedido.forma_pagamento in {Pedido.FormaPagamento.CARTAO, Pedido.FormaPagamento.PIX}
        and pedido.status not in {Pedido.Status.RASCUNHO, Pedido.Status.CANCELADO}
    )


def sync_movimentacao_conta_pedido(pedido, user=None):
    movimento = getattr(pedido, "movimentacao_conta", None)
    if not pedido_deve_gerar_movimentacao_conta(pedido):
        if movimento and movimento.excluido_em is None:
            movimento.excluido_em = timezone.now()
            movimento.excluido_por = user
            movimento.save(update_fields=["excluido_em", "excluido_por", "atualizado_em"])
        return None

    banco = banco_pagamento_conta(pedido)
    categoria = categoria_pagamento_conta(pedido)
    data_movimento = timezone.localtime(pedido.criado_em).date() if pedido.criado_em else timezone.localdate()
    nome = f"Pedido #{pedido.numero or pedido.id}"
    descricao = f"{pedido.nome_cliente} - {pedido.get_canal_display()}"

    if movimento:
        movimento.banco = banco
        movimento.categoria = categoria
        movimento.data_movimento = data_movimento
        movimento.tipo = MovimentacaoConta.Tipo.ENTRADA
        movimento.nome = nome
        movimento.descricao = descricao
        movimento.valor = pedido.total
        movimento.origem = MovimentacaoConta.Origem.SISTEMA
        movimento.atualizado_por = user
        movimento.excluido_em = None
        movimento.excluido_por = None
        movimento.save(
            update_fields=[
                "banco",
                "categoria",
                "data_movimento",
                "tipo",
                "nome",
                "descricao",
                "valor",
                "origem",
                "atualizado_por",
                "excluido_em",
                "excluido_por",
                "atualizado_em",
            ]
        )
        return movimento

    return MovimentacaoConta.objects.create(
        banco=banco,
        pedido=pedido,
        categoria=categoria,
        data_movimento=data_movimento,
        tipo=MovimentacaoConta.Tipo.ENTRADA,
        nome=nome,
        descricao=descricao,
        valor=pedido.total,
        origem=MovimentacaoConta.Origem.SISTEMA,
        criado_por=user,
        atualizado_por=user,
    )


def sync_movimentacao_caixa_pedido(pedido, user=None):
    sync_movimentacao_conta_pedido(pedido, user)
    movimento = getattr(pedido, "movimentacao_caixa", None)
    if not pedido_deve_gerar_movimentacao_caixa(pedido):
        if movimento and movimento.excluido_em is None:
            movimento.excluido_em = timezone.now()
            movimento.excluido_por = user
            movimento.save(update_fields=["excluido_em", "excluido_por", "atualizado_em"])
        return None

    terminal = pedido.terminal or terminal_padrao()
    categoria = categoria_pedidos_dinheiro()
    data_movimento = timezone.localtime(pedido.criado_em).date() if pedido.criado_em else timezone.localdate()
    nome = f"Pedido #{pedido.numero or pedido.id}"
    descricao = f"{pedido.nome_cliente} - {pedido.get_canal_display()}"

    if movimento:
        movimento.terminal = terminal
        movimento.categoria = categoria
        movimento.data_movimento = data_movimento
        movimento.tipo = MovimentacaoCaixa.Tipo.ENTRADA
        movimento.nome = nome
        movimento.descricao = descricao
        movimento.valor = pedido.total
        movimento.origem = MovimentacaoCaixa.Origem.SISTEMA
        movimento.atualizado_por = user
        movimento.excluido_em = None
        movimento.excluido_por = None
        movimento.save(
            update_fields=[
                "terminal",
                "categoria",
                "data_movimento",
                "tipo",
                "nome",
                "descricao",
                "valor",
                "origem",
                "atualizado_por",
                "excluido_em",
                "excluido_por",
                "atualizado_em",
            ]
        )
        return movimento

    return MovimentacaoCaixa.objects.create(
        terminal=terminal,
        pedido=pedido,
        categoria=categoria,
        data_movimento=data_movimento,
        tipo=MovimentacaoCaixa.Tipo.ENTRADA,
        nome=nome,
        descricao=descricao,
        valor=pedido.total,
        origem=MovimentacaoCaixa.Origem.SISTEMA,
        criado_por=user,
        atualizado_por=user,
    )


def excluir_movimentacao_caixa_pedido(pedido, user=None):
    movimento = getattr(pedido, "movimentacao_caixa", None)
    if movimento and movimento.excluido_em is None:
        movimento.excluido_em = timezone.now()
        movimento.excluido_por = user
        movimento.save(update_fields=["excluido_em", "excluido_por", "atualizado_em"])
    movimento_conta = getattr(pedido, "movimentacao_conta", None)
    if movimento_conta and movimento_conta.excluido_em is None:
        movimento_conta.excluido_em = timezone.now()
        movimento_conta.excluido_por = user
        movimento_conta.save(update_fields=["excluido_em", "excluido_por", "atualizado_em"])


def caixa_diario_context(data):
    movimentos = (
        movimentacoes_ativas()
        .filter(data_movimento=data)
        .select_related("terminal", "categoria", "criado_por", "atualizado_por")
        .order_by("terminal__ordem", "criado_em", "id")
    )
    agregados_dia = movimentos.aggregate(
        entradas=Sum("valor", filter=Q(tipo=MovimentacaoCaixa.Tipo.ENTRADA)),
        saidas=Sum("valor", filter=Q(tipo=MovimentacaoCaixa.Tipo.SAIDA)),
    )
    agregados_anteriores = movimentacoes_ativas().filter(data_movimento__lt=data).aggregate(
        entradas=Sum("valor", filter=Q(tipo=MovimentacaoCaixa.Tipo.ENTRADA)),
        saidas=Sum("valor", filter=Q(tipo=MovimentacaoCaixa.Tipo.SAIDA)),
    )
    entradas_dia = agregados_dia["entradas"] or Decimal("0.00")
    saidas_dia = agregados_dia["saidas"] or Decimal("0.00")
    saldo_anterior = (agregados_anteriores["entradas"] or Decimal("0.00")) - (
        agregados_anteriores["saidas"] or Decimal("0.00")
    )
    saldo_atual = saldo_anterior + entradas_dia - saidas_dia

    return {
        "movimentacoes": list(movimentos),
        "saldo_anterior": saldo_anterior.quantize(Decimal("0.01")),
        "entradas_dia": entradas_dia.quantize(Decimal("0.01")),
        "saidas_dia": saidas_dia.quantize(Decimal("0.01")),
        "saldo_atual": saldo_atual.quantize(Decimal("0.01")),
        "saldo_anterior_label": money_label(saldo_anterior),
        "entradas_dia_label": signed_money_label(entradas_dia, positive_prefix=True),
        "saidas_dia_label": f"- {money_label(saidas_dia)}",
        "saldo_atual_label": money_label(saldo_atual),
    }


def conta_diario_context(data):
    movimentos = (
        movimentacoes_conta_ativas()
        .filter(data_movimento=data)
        .select_related("banco", "categoria", "criado_por", "atualizado_por")
        .order_by("banco__ordem", "criado_em", "id")
    )
    agregados_dia = movimentos.aggregate(
        entradas=Sum("valor", filter=Q(tipo=MovimentacaoConta.Tipo.ENTRADA)),
        saidas=Sum("valor", filter=Q(tipo=MovimentacaoConta.Tipo.SAIDA)),
    )
    agregados_anteriores = movimentacoes_conta_ativas().filter(data_movimento__lt=data).aggregate(
        entradas=Sum("valor", filter=Q(tipo=MovimentacaoConta.Tipo.ENTRADA)),
        saidas=Sum("valor", filter=Q(tipo=MovimentacaoConta.Tipo.SAIDA)),
    )
    entradas_dia = agregados_dia["entradas"] or Decimal("0.00")
    saidas_dia = agregados_dia["saidas"] or Decimal("0.00")
    saldo_anterior = (agregados_anteriores["entradas"] or Decimal("0.00")) - (
        agregados_anteriores["saidas"] or Decimal("0.00")
    )
    saldo_atual = saldo_anterior + entradas_dia - saidas_dia

    return {
        "movimentacoes": list(movimentos),
        "saldo_anterior": saldo_anterior.quantize(Decimal("0.01")),
        "entradas_dia": entradas_dia.quantize(Decimal("0.01")),
        "saidas_dia": saidas_dia.quantize(Decimal("0.01")),
        "saldo_atual": saldo_atual.quantize(Decimal("0.01")),
        "saldo_anterior_label": money_label(saldo_anterior),
        "entradas_dia_label": signed_money_label(entradas_dia, positive_prefix=True),
        "saidas_dia_label": f"- {money_label(saidas_dia)}",
        "saldo_atual_label": money_label(saldo_atual),
    }
