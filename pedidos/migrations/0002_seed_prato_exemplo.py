from decimal import Decimal

from django.db import migrations


def criar_prato_exemplo(apps, schema_editor):
    Prato = apps.get_model("pedidos", "Prato")
    if not Prato.objects.filter(nome="Frango Guisado").exists():
        Prato.objects.create(
            nome="Frango Guisado",
            descricao="Frango macio com molho caseiro, arroz soltinho e acompanhamento do dia.",
            preco=Decimal("24.90"),
            ativo=True,
            dias_disponiveis="",
        )


def remover_prato_exemplo(apps, schema_editor):
    Prato = apps.get_model("pedidos", "Prato")
    Prato.objects.filter(nome="Frango Guisado").delete()


class Migration(migrations.Migration):
    dependencies = [("pedidos", "0001_initial")]

    operations = [migrations.RunPython(criar_prato_exemplo, remover_prato_exemplo)]
