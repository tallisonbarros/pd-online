from decimal import Decimal

from django.db import migrations


def preencher_precos_ausentes(apps, schema_editor):
    TurnoPratoPadrao = apps.get_model("pedidos", "TurnoPratoPadrao")
    DisponibilidadeTurnoItem = apps.get_model("pedidos", "DisponibilidadeTurnoItem")

    rows = TurnoPratoPadrao.objects.filter(
        turno__codigo="prato_pronto",
        preco__isnull=True,
    ).select_related("prato")
    for row in rows:
        latest_price = (
            DisponibilidadeTurnoItem.objects.filter(
                disponibilidade__turno_id=row.turno_id,
                prato_id=row.prato_id,
                preco__isnull=False,
            )
            .order_by("-disponibilidade__data", "-id")
            .values_list("preco", flat=True)
            .first()
        )
        row.preco = (
            latest_price
            or row.prato.preco_site
            or row.prato.preco
            or Decimal("22.00")
        )
        row.save(update_fields=["preco"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0057_prato_pronto_simplificado"),
    ]

    operations = [
        migrations.RunPython(preencher_precos_ausentes, migrations.RunPython.noop),
    ]
