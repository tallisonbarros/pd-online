from django.db import migrations, models


def inferir_retiradas(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    Pedido.objects.filter(endereco__iexact="Retirada no local").update(tipo_coleta="retirada")


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0024_pedido_entregador_solicitado"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="tipo_coleta",
            field=models.CharField(
                choices=[("entrega", "Entrega"), ("retirada", "Retirada")],
                default="entrega",
                max_length=8,
            ),
        ),
        migrations.RunPython(inferir_retiradas, migrations.RunPython.noop),
    ]
