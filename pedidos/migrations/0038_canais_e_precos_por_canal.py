from django.db import migrations, models


def preencher_canal_pedidos(apps, schema_editor):
    Pedido = apps.get_model("pedidos", "Pedido")
    Pedido.objects.filter(ifood=True).update(canal="ifood")
    Pedido.objects.filter(ifood=False).update(canal="balcao")


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0037_pedido_atualizado_em"),
    ]

    operations = [
        migrations.AddField(
            model_name="adicional",
            name="preco_balcao",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="adicional",
            name="preco_site",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="bebida",
            name="preco_balcao",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="bebida",
            name="preco_site",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="pedido",
            name="canal",
            field=models.CharField(
                choices=[("balcao", "Balcao"), ("site", "Site"), ("ifood", "iFood")],
                default="balcao",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="prato",
            name="preco_balcao",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="prato",
            name="preco_site",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.RunPython(preencher_canal_pedidos, migrations.RunPython.noop),
    ]
