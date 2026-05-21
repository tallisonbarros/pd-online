from datetime import timedelta

from django.db.models import Count, Sum

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

    total_pedidos = len(pedidos_do_dia)
    pedidos_recorrentes = _recurring_order_count(pedidos_do_dia, data)
    marmitas_vendidas = int(
        _finished_orders_for_day(data)
        .filter(itens__prato__isnull=False)
        .aggregate(total=Sum("itens__quantidade"))
        .get("total")
        or 0
    )
    marmitas_excedentes = operacional.marmitas_produzidas - marmitas_vendidas - operacional.consumo_interno

    return {
        "data": data,
        "data_anterior": data - timedelta(days=1),
        "data_proxima": data + timedelta(days=1),
        "total_pedidos": total_pedidos,
        "canais": canais,
        "pedidos_recorrentes": pedidos_recorrentes,
        "marmitas_vendidas": marmitas_vendidas,
        "marmitas_produzidas": operacional.marmitas_produzidas,
        "consumo_interno": operacional.consumo_interno,
        "marmitas_excedentes": marmitas_excedentes,
        "operacional": operacional,
        "cards": [
            {
                "label": "Pedidos finalizados",
                "value": total_pedidos,
                "details": [{"label": "Marmitas", "value": marmitas_vendidas}],
            },
            {
                "label": "Pedidos recorrentes",
                "value": pedidos_recorrentes,
                "details": [],
            },
            {
                "label": "Marmitas produzidas",
                "value": operacional.marmitas_produzidas,
                "details": [
                    {"label": "Consumo interno", "value": operacional.consumo_interno},
                    {"label": "Excedente", "value": marmitas_excedentes},
                ],
            },
        ],
    }
