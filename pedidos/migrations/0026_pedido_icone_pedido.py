from django.db import migrations, models


PEDIDO_ICON_FOLDER = "Icones_pedidos"
PEDIDO_ICON_COUNT = 30


def icon_path_for_number(numero):
    base_number = int(numero or 1)
    icon_index = ((base_number - 1) % PEDIDO_ICON_COUNT) + 1
    return f"{PEDIDO_ICON_FOLDER}/{icon_index}.svg"


def preencher_icones(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    for pedido in Pedido.objects.filter(icone_pedido="").only("id", "numero"):
        pedido.icone_pedido = icon_path_for_number(pedido.numero or pedido.id)
        pedido.save(update_fields=["icone_pedido"])


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0025_pedido_tipo_coleta"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="icone_pedido",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.RunPython(preencher_icones, migrations.RunPython.noop),
    ]
