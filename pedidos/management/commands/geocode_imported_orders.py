import time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from pedidos.models import Pedido
from pedidos.views import _resolve_address_coordinates


def to_decimal_7(value):
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal("0.0000001"))


def build_query(order):
    parts = [
        order.rua.strip(),
        order.numero_endereco.strip(),
        order.bairro.strip(),
        (order.cidade or "Rio Verde").strip(),
        (order.estado or "GO").strip(),
    ]
    query = ", ".join([part for part in parts if part])
    if query:
        return query
    return (order.endereco_formatado or order.endereco or "").strip()


class Command(BaseCommand):
    help = "Geocodifica pedidos importados do sistema antigo para entrarem no heatmap."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0)
        parser.add_argument("--sleep-ms", type=int, default=250)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = Pedido.objects.filter(
            observacao_geral__startswith="[IMPORTADO DO SISTEMA ANTIGO]",
            latitude__isnull=True,
            longitude__isnull=True,
        ).order_by("numero")

        limit = options["limit"] or 0
        if limit > 0:
            queryset = queryset[:limit]

        cache = {}
        updated = 0
        unresolved = 0
        skipped = 0

        for order in queryset:
            query = build_query(order)
            if len(query) < 8:
                skipped += 1
                continue

            if query in cache:
                lat, lng = cache[query]
            else:
                lat, lng = _resolve_address_coordinates(query)
                cache[query] = (lat, lng)
                if options["sleep_ms"] > 0:
                    time.sleep(options["sleep_ms"] / 1000)

            if lat is None or lng is None:
                unresolved += 1
                continue

            if options["dry_run"]:
                updated += 1
                continue

            with transaction.atomic():
                Pedido.objects.filter(pk=order.pk).update(
                    latitude=to_decimal_7(lat),
                    longitude=to_decimal_7(lng),
                )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Geocodificacao concluida. Atualizados: {updated} | Nao resolvidos: {unresolved} | Pulados: {skipped}"
            )
        )
