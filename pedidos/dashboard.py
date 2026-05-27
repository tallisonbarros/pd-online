from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum

from .models import Pedido, ResumoOperacionalDia
from .order_services import normalize_phone


def _finished_orders_for_day(data):
    return Pedido.objects.filter(status=Pedido.Status.FINALIZADO, criado_em__date=data)


def _recurring_order_count(pedidos_do_dia, data):
    telefones = []
    for pedido in pedidos_do_dia:
        telefone = normalize_phone(pedido.telefone)
        if telefone and telefone not in telefones:
            telefones.append(telefone)

    if not telefones:
        return 0

    telefones_recorrentes = set()
    pedidos_anteriores = Pedido.objects.exclude(status__in=[Pedido.Status.RASCUNHO, Pedido.Status.CANCELADO]).filter(
        criado_em__date__lt=data,
    )
    for telefone in pedidos_anteriores.values_list("telefone", flat=True):
        telefone_normalizado = normalize_phone(telefone)
        if telefone_normalizado in telefones:
            telefones_recorrentes.add(telefone_normalizado)

    return sum(1 for pedido in pedidos_do_dia if normalize_phone(pedido.telefone) in telefones_recorrentes)


def get_dashboard_diaria(data):
    operacional, _created = ResumoOperacionalDia.objects.get_or_create(data=data)
    pedidos_do_dia = list(_finished_orders_for_day(data).order_by("criado_em", "id"))
    por_canal_raw = (
        _finished_orders_for_day(data)
        .values("canal")
        .annotate(total=Count("id"))
        .order_by("canal")
    )
    por_canal_map = {row["canal"]: int(row["total"] or 0) for row in por_canal_raw}
    canais = [
        {
            "key": value,
            "label": label,
            "total": por_canal_map.get(value, 0),
        }
        for value, label in Pedido.Canal.choices
    ]
    principal_canal = max(canais, key=lambda canal: canal["total"]) if canais else None
    for canal in canais:
        canal["is_primary"] = bool(principal_canal and principal_canal["total"] > 0 and canal["key"] == principal_canal["key"])

    total_pedidos = len(pedidos_do_dia)
    faturamento_total = sum((pedido.total or Decimal("0.00") for pedido in pedidos_do_dia), Decimal("0.00")).quantize(Decimal("0.01"))
    custo_entrega = sum((pedido.valor_frete or Decimal("0.00") for pedido in pedidos_do_dia), Decimal("0.00")).quantize(Decimal("0.01"))
    pedidos_recorrentes = _recurring_order_count(pedidos_do_dia, data)
    marmita_filter = Q(itens__prato__isnull=False) | Q(
        observacao_geral__startswith="[IMPORTADO DO SISTEMA ANTIGO]",
        itens__prato__isnull=True,
        itens__bebida__isnull=True,
        itens__adicional__isnull=True,
        itens__observacao__icontains="Tipo legado: dish",
    )
    marmitas = _finished_orders_for_day(data).filter(marmita_filter).aggregate(
        saida=Sum("itens__quantidade"),
        vendidas=Sum("itens__quantidade", filter=Q(itens__classificacao_saida="vendida")),
        cortesias=Sum("itens__quantidade", filter=Q(itens__classificacao_saida="cortesia")),
        promocao=Sum("itens__quantidade", filter=Q(itens__classificacao_saida="promocao")),
    )
    marmitas_saida = int(marmitas.get("saida") or 0)
    marmitas_vendidas = int(marmitas.get("vendidas") or 0)
    marmitas_cortesia = int(marmitas.get("cortesias") or 0)
    marmitas_promocao = int(marmitas.get("promocao") or 0)
    marmitas_excedentes = operacional.marmitas_produzidas - marmitas_saida - operacional.consumo_interno
    custo_total_producao = operacional.custo_insumos
    custo_total_operacional = (custo_total_producao + custo_entrega).quantize(Decimal("0.01"))
    custo_unitario_marmita = Decimal("0.00")
    if operacional.marmitas_produzidas:
        custo_unitario_marmita = (custo_total_producao / Decimal(operacional.marmitas_produzidas)).quantize(Decimal("0.01"))
    custo_unitario_marmita_label = f"R$ {custo_unitario_marmita:.2f}".replace(".", ",")
    custo_unitario_marmita_vendida = Decimal("0.00")
    if marmitas_vendidas:
        custo_unitario_marmita_vendida = (custo_total_producao / Decimal(marmitas_vendidas)).quantize(Decimal("0.01"))
    custo_unitario_marmita_vendida_label = f"R$ {custo_unitario_marmita_vendida:.2f}".replace(".", ",")
    resultado_operacional = (faturamento_total - custo_total_operacional).quantize(Decimal("0.01"))

    return {
        "data": data,
        "data_anterior": data - timedelta(days=1),
        "data_proxima": data + timedelta(days=1),
        "total_pedidos": total_pedidos,
        "faturamento_total": faturamento_total,
        "custo_entrega": custo_entrega,
        "canais": canais,
        "pedidos_recorrentes": pedidos_recorrentes,
        "marmitas_saida": marmitas_saida,
        "marmitas_vendidas": marmitas_vendidas,
        "marmitas_cortesia": marmitas_cortesia,
        "marmitas_promocao": marmitas_promocao,
        "marmitas_produzidas": operacional.marmitas_produzidas,
        "consumo_interno": operacional.consumo_interno,
        "custo_insumos": operacional.custo_insumos,
        "custo_unitario_marmita": custo_unitario_marmita,
        "custo_unitario_marmita_label": custo_unitario_marmita_label,
        "custo_unitario_marmita_vendida": custo_unitario_marmita_vendida,
        "custo_unitario_marmita_vendida_label": custo_unitario_marmita_vendida_label,
        "custo_total_producao": custo_total_producao,
        "custo_total_operacional": custo_total_operacional,
        "resultado_operacional": resultado_operacional,
        "marmitas_excedentes": marmitas_excedentes,
        "operacional": operacional,
        "balanco": {
            "label": "Balanco geral",
            "value": f"R$ {resultado_operacional:.2f}".replace(".", ","),
            "details": [
                {"label": "Receita", "value": f"+ R$ {faturamento_total:.2f}".replace(".", ",")},
                {"label": "Custos producao", "value": f"- R$ {custo_total_producao:.2f}".replace(".", ",")},
                {"label": "Custo entrega", "value": f"- R$ {custo_entrega:.2f}".replace(".", ",")},
            ],
            "footer_details": [
                {"label": "Resultado", "value": f"R$ {resultado_operacional:.2f}".replace(".", ",")},
            ],
        },
        "cards": [
            {
                "label": "Marmitas vendidas",
                "value": marmitas_vendidas,
                "details": [
                    {"label": "Saidas", "value": marmitas_saida},
                    {"label": "Cortesias", "value": marmitas_cortesia},
                    {"label": "Promocao", "value": marmitas_promocao},
                    {
                        "label": "Pedidos",
                        "value": total_pedidos,
                        "secondary_label": "Recorrentes",
                        "secondary_value": pedidos_recorrentes,
                    },
                ],
                "channels": canais,
            },
            {
                "label": "Marmitas produzidas",
                "value": operacional.marmitas_produzidas,
                "details": [
                    {"label": "Saidas", "value": marmitas_saida},
                    {"label": "Vendidas", "value": marmitas_vendidas},
                    {"label": "Consumo interno", "value": operacional.consumo_interno},
                    {"label": "Excedente", "value": marmitas_excedentes},
                ],
            },
            {
                "label": "Custos de producao",
                "value": f"R$ {custo_total_producao:.2f}".replace(".", ","),
                "variant": "discreet",
                "is_wide": True,
                "group": "costs",
                "details": [
                    {"label": "Insumos", "value": f"R$ {operacional.custo_insumos:.2f}".replace(".", ","), "muted": True},
                    {"label": "Equipe", "value": "R$ 0,00", "muted": True, "mock": True},
                    {"label": "Embalagens", "value": "R$ 0,00", "muted": True, "mock": True},
                ],
                "footer_details": [
                    {"label": "Custo por marmita produzida", "value": custo_unitario_marmita_label, "hint": "Custos / produzidas"},
                    {"label": "Custo por marmita vendida", "value": custo_unitario_marmita_vendida_label, "hint": "Custos / vendidas"},
                ],
            },
        ],
    }
