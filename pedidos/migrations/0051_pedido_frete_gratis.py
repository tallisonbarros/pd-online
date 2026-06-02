from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0050_configuracaoentrega_bancos_conta"),
    ]

    operations = [
        migrations.AddField(
            model_name="pedido",
            name="frete_gratis",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterModelOptions(
            name="faixafrete",
            options={
                "ordering": ["ordem", "km_limite", "id"],
                "verbose_name": "Faixa de entrega",
                "verbose_name_plural": "Faixas de entrega",
            },
        ),
    ]
