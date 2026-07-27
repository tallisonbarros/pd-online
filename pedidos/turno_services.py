from datetime import datetime, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from .models import (
    ConfiguracaoEntrega,
    DataFechada,
    DisponibilidadeTurnoDia,
    DisponibilidadeTurnoItem,
    Pedido,
    Prato,
    TurnoAtendimento,
    TurnoPratoPadrao,
)


WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sab", "dom"]
DEFAULT_PRATO_PRONTO_DAYS = "seg,ter,qua,qui,sex,sab"


def ensure_turnos_padrao():
    principal, _created = TurnoAtendimento.objects.get_or_create(
        codigo=TurnoAtendimento.Codigo.PRINCIPAL,
        defaults={
            "nome": "Atendimento principal",
            "ativo": True,
            "dias_semana": "seg,ter,qua,qui,sex,sab,dom",
            "permite_entrega": True,
            "permite_retirada": True,
            "permite_promocao": True,
            "permite_cupom": True,
            "ordem": 10,
        },
    )
    prato_pronto, _created = TurnoAtendimento.objects.get_or_create(
        codigo=TurnoAtendimento.Codigo.PRATO_PRONTO,
        defaults={
            "nome": "Prato Pronto",
            "ativo": False,
            "dias_semana": DEFAULT_PRATO_PRONTO_DAYS,
            "horario_inicio": datetime.strptime("17:00", "%H:%M").time(),
            "horario_fim": datetime.strptime("19:00", "%H:%M").time(),
            "horario_limite_entrega": datetime.strptime("19:00", "%H:%M").time(),
            "permite_entrega": True,
            "permite_retirada": True,
            "modo_cardapio": TurnoAtendimento.ModoCardapio.FIXO,
            "preco_padrao": Decimal("22.00"),
            "permite_promocao": False,
            "permite_cupom": False,
            "mensagem": "Facilidade para sua janta.",
            "orientacao_cliente": (
                "Marmitas seladas e refrigeradas · Feitas no dia · Aqueça em casa."
            ),
            "ordem": 20,
        },
    )
    return principal, prato_pronto


def turno_agendado_no_dia(turno, target_date):
    if not turno or not turno.ativo or not turno.horario_inicio or not turno.horario_fim:
        return False
    dias = turno.dias_semana_set
    return not dias or WEEKDAYS[target_date.weekday()] in dias


def _site_price(prato):
    return prato.preco_site if prato.preco_site is not None else prato.preco


def preco_turno_prato(turno, prato, preco_especifico=None):
    if preco_especifico is not None:
        return Decimal(preco_especifico).quantize(Decimal("0.01"))
    if turno.preco_padrao is not None:
        return Decimal(turno.preco_padrao).quantize(Decimal("0.01"))
    preco_base = Decimal(_site_price(prato) or Decimal("0.00"))
    desconto = Decimal(turno.desconto_padrao or Decimal("0.00"))
    return max(preco_base - desconto, Decimal("0.00")).quantize(Decimal("0.01"))


def _pratos_padrao_turno(turno, target_date):
    if turno.modo_cardapio == TurnoAtendimento.ModoCardapio.FIXO:
        rows = list(
            TurnoPratoPadrao.objects.select_related("prato")
            .filter(turno=turno, ativo=True, prato__ativo=True)
            .order_by("ordem", "prato__nome")
        )
        result = []
        for row in rows:
            dias = row.dias_semana_set
            if dias and WEEKDAYS[target_date.weekday()] not in dias:
                continue
            preco = preco_turno_prato(turno, row.prato, row.preco)
            if preco > 0:
                result.append({"prato": row.prato, "preco": preco, "ordem": row.ordem})
        return result

    weekday_key = WEEKDAYS[target_date.weekday()]
    pratos = []
    for prato in Prato.objects.filter(ativo=True, exclusivo_prato_pronto=False).order_by("nome"):
        dias = {dia.strip().lower() for dia in (prato.dias_disponiveis or "").split(",") if dia.strip()}
        if not dias or weekday_key in dias:
            preco = preco_turno_prato(turno, prato)
            if preco > 0:
                pratos.append(
                    {
                        "prato": prato,
                        "preco": preco,
                        "ordem": len(pratos) * 10,
                    }
                )
    return pratos


@transaction.atomic
def sincronizar_disponibilidade_automatica(disponibilidade):
    disponibilidade = (
        DisponibilidadeTurnoDia.objects.select_for_update()
        .select_related("turno")
        .get(pk=disponibilidade.pk)
    )
    if disponibilidade.personalizado:
        return disponibilidade

    defaults = _pratos_padrao_turno(disponibilidade.turno, disponibilidade.data)
    default_ids = set()
    for row in defaults:
        default_ids.add(row["prato"].id)
        item, created = DisponibilidadeTurnoItem.objects.get_or_create(
            disponibilidade=disponibilidade,
            prato=row["prato"],
            defaults={
                "preco": row["preco"],
                "ordem": row["ordem"],
                "ativo": True,
            },
        )
        if not created:
            update_fields = []
            if item.preco != row["preco"]:
                item.preco = row["preco"]
                update_fields.append("preco")
            if item.ordem != row["ordem"]:
                item.ordem = row["ordem"]
                update_fields.append("ordem")
            if not item.ativo:
                item.ativo = True
                update_fields.append("ativo")
            if update_fields:
                item.save(update_fields=[*update_fields, "atualizado_em"])

    for item in disponibilidade.itens.exclude(prato_id__in=default_ids):
        if item.quantidade_reservada:
            if item.ativo:
                item.ativo = False
                item.save(update_fields=["ativo", "atualizado_em"])
        else:
            item.delete()
    return disponibilidade


def ensure_disponibilidade_turno(turno, target_date):
    if not turno_agendado_no_dia(turno, target_date):
        return None
    disponibilidade, _created = DisponibilidadeTurnoDia.objects.get_or_create(
        turno=turno,
        data=target_date,
    )
    return sincronizar_disponibilidade_automatica(disponibilidade)


def _aware_on_date(target_date, value, tzinfo):
    if value is None:
        return None
    return timezone.make_aware(datetime.combine(target_date, value), tzinfo)


def resolve_turno_publico(now=None, create_availability=True):
    current = now or timezone.localtime()
    if timezone.is_naive(current):
        current = timezone.make_aware(current, timezone.get_current_timezone())
    principal, prato_pronto = ensure_turnos_padrao()
    config = ConfiguracaoEntrega.get_solo()
    current_date = current.date()
    closed_globally = DataFechada.objects.filter(data=current_date, ativo=True).exists()

    principal.horario_inicio = config.horario_abertura
    principal.horario_fim = config.horario_fechamento
    disponibilidade = None
    if turno_agendado_no_dia(prato_pronto, current_date):
        disponibilidade = (
            ensure_disponibilidade_turno(prato_pronto, current_date)
            if create_availability
            else DisponibilidadeTurnoDia.objects.filter(
                turno=prato_pronto,
                data=current_date,
            ).first()
        )

    inicio = disponibilidade.inicio_efetivo if disponibilidade else prato_pronto.horario_inicio
    fim = disponibilidade.fim_efetivo if disponibilidade else prato_pronto.horario_fim
    limite_entrega = disponibilidade.limite_entrega_efetivo if disponibilidade else (
        prato_pronto.horario_limite_entrega or fim
    )
    itens = []
    if disponibilidade:
        itens = list(
            disponibilidade.itens.select_related("prato")
            .filter(ativo=True, prato__ativo=True)
            .order_by("ordem", "prato__nome")
        )
    itens_disponiveis = [item for item in itens if not item.esgotado]

    scheduled = bool(
        disponibilidade
        and not disponibilidade.pausado
        and not closed_globally
        and inicio
        and fim
    )
    is_open = bool(scheduled and inicio <= current.time() < fim and itens_disponiveis)
    owns_menu_context = bool(
        scheduled
        and current.time() < fim
        and (
            is_open
            or (
                principal.horario_fim
                and current.time() >= principal.horario_fim
            )
        )
    )
    accepting_orders = bool(owns_menu_context and itens_disponiveis)
    delivery_allowed = bool(
        accepting_orders
        and disponibilidade.permite_entrega_efetivo
        and (not limite_entrega or current.time() < limite_entrega)
    )
    pickup_allowed = bool(accepting_orders and disponibilidade.permite_retirada_efetivo)

    state = "inactive"
    if scheduled:
        if current.time() < inicio:
            state = "scheduled"
        elif current.time() >= fim:
            state = "closed"
        elif not itens_disponiveis:
            state = "sold_out"
        else:
            state = "open"
    elif disponibilidade and disponibilidade.pausado:
        state = "paused"

    inicio_dt = _aware_on_date(current_date, inicio, current.tzinfo) if inicio else None
    fim_dt = _aware_on_date(current_date, fim, current.tzinfo) if fim else None
    return {
        "principal": principal,
        "prato_pronto": prato_pronto,
        "disponibilidade": disponibilidade,
        "itens": itens,
        "itens_disponiveis": itens_disponiveis,
        "state": state,
        "scheduled": scheduled,
        "is_open": is_open,
        "owns_menu_context": owns_menu_context,
        "accepting_orders": accepting_orders,
        "delivery_allowed": delivery_allowed,
        "pickup_allowed": pickup_allowed,
        "inicio": inicio,
        "fim": fim,
        "limite_entrega": limite_entrega,
        "inicio_em": inicio_dt,
        "fim_em": fim_dt,
        "closed_globally": closed_globally,
    }


def cart_window_for_turno(config=None, now=None):
    current = now or timezone.localtime()
    context = resolve_turno_publico(current)
    if context["accepting_orders"]:
        disponibilidade = context["disponibilidade"]
        disponibilidade_revision = disponibilidade.atualizado_em.strftime("%Y%m%d%H%M%S%f")
        turno_revision = context["prato_pronto"].atualizado_em.strftime("%Y%m%d%H%M%S%f")
        revision = f"{turno_revision}:{disponibilidade_revision}"
        return {
            "cycle_key": f"{current.date().isoformat()}:prato-pronto:{disponibilidade.id}:{revision}",
            "expires_at": context["fim_em"].isoformat() if context["fim_em"] else "",
            "server_now": current.isoformat(),
            "turno_codigo": TurnoAtendimento.Codigo.PRATO_PRONTO,
            "promocao_habilitada": context["prato_pronto"].permite_promocao,
            "cupom_habilitado": context["prato_pronto"].permite_cupom,
            "entrega_habilitada": context["delivery_allowed"],
            "retirada_habilitada": context["pickup_allowed"],
        }

    config = config or ConfiguracaoEntrega.get_solo()
    fechamento = config.horario_fechamento
    cycle_date = current.date()
    expires_at = None
    if fechamento:
        if current.time() >= fechamento:
            cycle_date += timedelta(days=1)
        while DataFechada.objects.filter(data=cycle_date, ativo=True).exists():
            cycle_date += timedelta(days=1)
        expires_at = _aware_on_date(cycle_date, fechamento, current.tzinfo)
    return {
        "cycle_key": cycle_date.isoformat(),
        "expires_at": expires_at.isoformat() if expires_at else "",
        "server_now": current.isoformat(),
        "turno_codigo": TurnoAtendimento.Codigo.PRINCIPAL,
        "promocao_habilitada": True,
        "cupom_habilitado": True,
        "entrega_habilitada": True,
        "retirada_habilitada": True,
    }


def validar_turno_para_pedido(tipo_coleta, now=None):
    context = resolve_turno_publico(now)
    if not context["accepting_orders"]:
        return context["principal"], None
    if tipo_coleta == Pedido.TipoColeta.ENTREGA and not context["delivery_allowed"]:
        raise ValueError("O horario de entregas do Prato Pronto encerrou. Escolha retirada no local.")
    if tipo_coleta == Pedido.TipoColeta.RETIRADA and not context["pickup_allowed"]:
        raise ValueError("A retirada nao esta disponivel neste turno.")
    return context["prato_pronto"], context["disponibilidade"]


@transaction.atomic
def reservar_estoque_pedido(pedido):
    pedido_banco = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if not pedido_banco.estoque_turno_liberado:
        return
    reservas_por_item = list(
        pedido_banco.itens.exclude(disponibilidade_turno_item__isnull=True)
        .values("disponibilidade_turno_item_id")
        .annotate(quantidade=Sum("quantidade"))
        .order_by("disponibilidade_turno_item_id")
    )
    for reserva in reservas_por_item:
        quantidade = int(reserva["quantidade"] or 0)
        disponibilidade_item = DisponibilidadeTurnoItem.objects.select_for_update().get(
            pk=reserva["disponibilidade_turno_item_id"]
        )
        reserva_filter = {
            "pk": disponibilidade_item.pk,
            "ativo": True,
        }
        queryset = DisponibilidadeTurnoItem.objects.filter(**reserva_filter)
        if disponibilidade_item.quantidade_disponivel is not None:
            limite_reservado = disponibilidade_item.quantidade_disponivel - quantidade
            queryset = queryset.filter(quantidade_reservada__lte=limite_reservado)
        reservado = queryset.update(
            quantidade_reservada=F("quantidade_reservada") + quantidade,
            atualizado_em=timezone.now(),
        )
        if not reservado:
            raise ValueError(
                f"Nao ha estoque suficiente de {disponibilidade_item.prato.nome} "
                "para reabrir este pedido."
            )
    Pedido.objects.filter(pk=pedido_banco.pk).update(estoque_turno_liberado=False)
    pedido.estoque_turno_liberado = False


@transaction.atomic
def liberar_estoque_pedido(pedido):
    pedido = Pedido.objects.select_for_update().get(pk=pedido.pk)
    if pedido.estoque_turno_liberado:
        return
    reservas_por_item = list(
        pedido.itens.exclude(disponibilidade_turno_item__isnull=True)
        .values("disponibilidade_turno_item_id")
        .annotate(quantidade=Sum("quantidade"))
    )
    for reserva in reservas_por_item:
        quantidade = int(reserva["quantidade"] or 0)
        DisponibilidadeTurnoItem.objects.filter(
            pk=reserva["disponibilidade_turno_item_id"]
        ).update(
            quantidade_reservada=Greatest(
                F("quantidade_reservada") - quantidade,
                Value(0),
            ),
            atualizado_em=timezone.now(),
        )
    Pedido.objects.filter(pk=pedido.pk).update(estoque_turno_liberado=True)
    pedido.estoque_turno_liberado = True


def turno_label_pedido(pedido):
    if pedido.turno_id and pedido.turno:
        return pedido.turno.nome
    return "Atendimento principal"
