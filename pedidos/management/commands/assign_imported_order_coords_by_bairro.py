import hashlib
import math
from decimal import Decimal

from django.core.management.base import BaseCommand

from pedidos.models import Pedido
from pedidos.views import _resolve_address_coordinates


def to_decimal_7(value):
    return Decimal(str(value)).quantize(Decimal("0.0000001"))


def stable_jitter(order_number, radius_deg=0.0032):
    digest = hashlib.sha256(str(order_number).encode("utf-8")).digest()
    angle_seed = int.from_bytes(digest[:8], "big") / 2**64
    radius_seed = int.from_bytes(digest[8:16], "big") / 2**64
    angle = angle_seed * math.tau
    radius = math.sqrt(radius_seed) * radius_deg
    lat_offset = math.sin(angle) * radius
    lng_offset = math.cos(angle) * radius
    return lat_offset, lng_offset


class Command(BaseCommand):
    help = "Atribui coordenadas aproximadas por bairro para pedidos importados, suficiente para heatmap historico."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        queryset = Pedido.objects.filter(
            observacao_geral__startswith="[IMPORTADO DO SISTEMA ANTIGO]",
            latitude__isnull=True,
            longitude__isnull=True,
        ).order_by("numero")

        bairros = sorted({(pedido.bairro or "").strip() for pedido in queryset if (pedido.bairro or "").strip()})
        centroides = {}
        unresolved_bairros = []

        for bairro in bairros:
            lat, lng = _resolve_address_coordinates(f"{bairro}, Rio Verde, GO")
            if lat is None or lng is None:
                unresolved_bairros.append(bairro)
                continue
            centroides[bairro] = (lat, lng)

        updated = 0
        unresolved_orders = 0

        for pedido in queryset:
            bairro = (pedido.bairro or "").strip()
            centroid = centroides.get(bairro)
            if not centroid:
                unresolved_orders += 1
                continue

            lat_offset, lng_offset = stable_jitter(pedido.numero or pedido.pk)
            lat = centroid[0] + lat_offset
            lng = centroid[1] + lng_offset

            if not options["dry_run"]:
                Pedido.objects.filter(pk=pedido.pk).update(
                    latitude=to_decimal_7(lat),
                    longitude=to_decimal_7(lng),
                )
            updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Coordenadas aproximadas atribuidas. Atualizados: {updated} | Pedidos sem bairro resolvido: {unresolved_orders}"
            )
        )
        if unresolved_bairros:
            self.stdout.write(f"Bairros nao resolvidos: {', '.join(unresolved_bairros)}")
